# NOTE: no `from __future__ import annotations` here on purpose: FastAPI must be able to read the
# Pipecat request types (SmallWebRTCRequest / SmallWebRTCPatchRequest) from the real annotations.
"""WebRTC signalling for live mode (imported only when APP_MODE=live).

Mirrors Pipecat's own development runner: the browser POSTs an SDP offer to /api/offer, we
return the SDP answer and start one Pipecat pipeline for that connection in the background.
"""
import asyncio
import logging
import uuid

from fastapi import BackgroundTasks, FastAPI
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from app.context import AppContext
from app.voice.pipeline import run_live_bot

log = logging.getLogger("voice.live")


class LiveManager:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self.handler = SmallWebRTCRequestHandler()
        self._tasks: dict[str, object] = {}

    async def run(self, connection, call_id: str) -> None:
        calls = self.ctx.calls
        try:
            await run_live_bot(connection, self.ctx, call_id, register_task=lambda t: self._tasks.__setitem__(call_id, t))
        except Exception as exc:  # noqa: BLE001
            log.exception("Live pipeline crashed")
            self.ctx.bus.publish("error", {"source": "pipeline", "message": f"The voice pipeline stopped: {exc}"}, call_id=call_id)
        finally:
            self._tasks.pop(call_id, None)
            try:
                calls.end(call_id, "pipeline_closed")
            except Exception:  # noqa: BLE001
                pass

    def request_hangup(self, call_id: str) -> None:
        task = self._tasks.get(call_id)
        if task is not None:
            asyncio.get_running_loop().create_task(task.cancel())

    async def close(self) -> None:
        await self.handler.close()


def register_live_routes(app: FastAPI, ctx: AppContext) -> None:
    manager = LiveManager(ctx)
    ctx.live = manager

    @app.post("/api/offer", tags=["webrtc"])
    async def offer(request: SmallWebRTCRequest, background_tasks: BackgroundTasks):
        call_id = uuid.uuid4().hex[:12]

        async def webrtc_connection_callback(connection):
            ctx.calls.live_started(call_id)
            background_tasks.add_task(manager.run, connection, call_id)

        return await manager.handler.handle_web_request(
            request=request, webrtc_connection_callback=webrtc_connection_callback
        )

    @app.patch("/api/offer", tags=["webrtc"])
    async def ice_candidate(request: SmallWebRTCPatchRequest):
        await manager.handler.handle_patch_request(request)
        return {"status": "success"}
