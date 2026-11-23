"""Live voice pipeline (Pipecat).

    browser mic -> SmallWebRTC -> [Silero VAD] -> ElevenLabs STT -> Gemini (tools) -> ElevenLabs TTS -> browser

Written against the Pipecat 1.x documentation (see requirements-live.txt for the pinned version).
Pipecat imports happen inside ``run_live_bot`` so demo mode never needs the package.  A few
imports go through ``_first`` because Pipecat has renamed some classes between 1.x releases.
"""
from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

from app.context import AppContext
from app.voice.prompts import greeting, system_prompt
from app.voice.tools import TOOL_SPECS

log = logging.getLogger("voice.pipeline")


def _first(*paths: str) -> Any:
    """Import the first available ``module:Name`` (tolerates renames between Pipecat releases)."""
    errors = []
    for path in paths:
        module, name = path.split(":")
        try:
            return getattr(importlib.import_module(module), name)
        except (ImportError, AttributeError) as exc:
            errors.append(f"{path}: {exc}")
    raise ImportError("Could not import any of: " + "; ".join(errors))


async def run_live_bot(
    webrtc_connection: Any,
    ctx: AppContext,
    call_id: str,
    register_task: Callable[[Any], None] | None = None,
) -> None:
    s = ctx.settings
    bus, calls = ctx.bus, ctx.calls

    # --- Pipecat imports ---------------------------------------------------------------
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.frames.frames import (
        BotStartedSpeakingFrame, BotStoppedSpeakingFrame, ErrorFrame, InterimTranscriptionFrame,
        LLMRunFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    )
    from pipecat.observers.base_observer import BaseObserver, FramePushed
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.task import PipelineParams
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair, LLMUserAggregatorParams,
    )
    from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
    from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
    from pipecat.services.google.llm import GoogleLLMService
    from pipecat.transcriptions.language import Language
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

    PipelineTask = _first("pipecat.pipeline.task:PipelineTask", "pipecat.pipeline.worker:PipelineWorker")
    PipelineRunner = _first("pipecat.pipeline.runner:PipelineRunner", "pipecat.runner.worker:WorkerRunner")
    FunctionSchema = _first("pipecat.adapters.schemas.function_schema:FunctionSchema",
                            "pipecat.adapters.llm.schemas.function_schema:FunctionSchema")
    ToolsSchema = _first("pipecat.adapters.schemas.tools_schema:ToolsSchema",
                         "pipecat.adapters.llm.schemas.tools_schema:ToolsSchema")

    # --- services ------------------------------------------------------------------------
    try:
        language = Language(s.stt_language)
    except ValueError:
        language = Language.EN
    stt = ElevenLabsRealtimeSTTService(
        api_key=s.elevenlabs_api_key,
        settings=ElevenLabsRealtimeSTTService.Settings(model=s.elevenlabs_stt_model, language=language),
    )
    tts = ElevenLabsTTSService(
        api_key=s.elevenlabs_api_key,
        settings=ElevenLabsTTSService.Settings(voice=s.elevenlabs_voice_id, model=s.elevenlabs_tts_model),
    )
    now = ctx.clinic.now()
    llm = GoogleLLMService(
        api_key=s.google_api_key,
        settings=GoogleLLMService.Settings(
            model=s.llm_model,
            system_instruction=system_prompt(s.clinic_name, now.date().isoformat(), now.strftime("%A")),
            temperature=s.llm_temperature,
        ),
    )

    # --- tools: schemas for Gemini + handlers that hit the real database ----------------------
    tools = ToolsSchema(standard_tools=[
        FunctionSchema(name=t["name"], description=t["description"], properties=t["properties"], required=t["required"])
        for t in TOOL_SPECS
    ])

    def make_handler(tool_name: str):
        async def handler(params):  # params: pipecat FunctionCallParams
            result = await ctx.executor.execute(tool_name, dict(params.arguments or {}), call_id)
            await params.result_callback(result)
        return handler

    for spec in TOOL_SPECS:
        llm.register_function(spec["name"], make_handler(spec["name"]))

    context = LLMContext(messages=[], tools=tools)
    user_agg, assistant_agg = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),  # Silero VAD
    )

    # --- transport ---------------------------------------------------------------------------
    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )

    # --- dashboard events ----------------------------------------------------------------------
    class ActivityObserver(BaseObserver):
        """Turns pipeline frames into dashboard events (interim text, speaking state, errors)."""

        def __init__(self) -> None:
            super().__init__()
            self._seen: set[int] = set()

        async def on_push_frame(self, data: FramePushed) -> None:
            frame = data.frame
            kinds = (InterimTranscriptionFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
                     BotStartedSpeakingFrame, BotStoppedSpeakingFrame, ErrorFrame)
            if not isinstance(frame, kinds) or frame.id in self._seen:
                return
            self._seen.add(frame.id)
            if len(self._seen) > 2000:
                self._seen.clear()
            if isinstance(frame, InterimTranscriptionFrame):
                calls.transcript(call_id, "user", frame.text, final=False)
            elif isinstance(frame, (UserStartedSpeakingFrame, UserStoppedSpeakingFrame)):
                bus.publish("speaking", {"who": "user", "active": isinstance(frame, UserStartedSpeakingFrame)}, call_id=call_id)
            elif isinstance(frame, (BotStartedSpeakingFrame, BotStoppedSpeakingFrame)):
                bus.publish("speaking", {"who": "assistant", "active": isinstance(frame, BotStartedSpeakingFrame)}, call_id=call_id)
            elif isinstance(frame, ErrorFrame):
                bus.publish("error", {"source": "provider", "message": str(frame.error)[:300],
                                      "fatal": bool(getattr(frame, "fatal", False))}, call_id=call_id)

    pipeline = Pipeline([
        transport.input(),
        stt,
        user_agg,
        llm,
        tts,
        transport.output(),
        assistant_agg,
    ])
    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[ActivityObserver()],
    )
    if register_task:
        register_task(task)

    @user_agg.event_handler("on_user_turn_stopped")
    async def _user_turn(aggregator, strategy, message):
        if message.content:
            calls.transcript(call_id, "user", message.content, final=True)

    @assistant_agg.event_handler("on_assistant_turn_stopped")
    async def _assistant_turn(aggregator, message):
        if message.content:
            calls.transcript(call_id, "assistant", message.content + (" …" if message.interrupted else ""), final=True)

    @transport.event_handler("on_client_connected")
    async def _connected(transport, client):
        log.info("Caller connected (call %s)", call_id)
        calls.live_connected(call_id)
        context.add_message({
            "role": "user",
            "content": f"(A caller has just connected. Greet them now. Say: \"{greeting(s.clinic_name)}\")",
        })
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def _disconnected(transport, client):
        log.info("Caller disconnected (call %s)", call_id)
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
