"""Call sessions: lifecycle bookkeeping + transcript events for demo and live calls."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.services.errors import ApiError
from app.services.events import EventBus

MAX_TEXT = 500


@dataclass
class CallSession:
    id: str
    mode: str                     # "mock" | "live"
    started_at: str
    status: str = "connected"     # connected | ended
    ended_at: str | None = None
    agent: Any = None             # MockAgent for demo calls
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def public(self) -> dict[str, Any]:
        return {"call_id": self.id, "mode": self.mode, "status": self.status,
                "started_at": self.started_at, "ended_at": self.ended_at}


class CallManager:
    def __init__(self, bus: EventBus, agent_factory: Callable[[str], Any] | None = None) -> None:
        self.bus = bus
        self._agent_factory = agent_factory
        self._sessions: dict[str, CallSession] = {}

    # -------------------------------------------------------------- common
    def _new(self, mode: str, call_id: str | None = None, agent: Any = None) -> CallSession:
        session = CallSession(id=call_id or uuid.uuid4().hex[:12], mode=mode,
                              started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), agent=agent)
        # keep memory bounded
        if len(self._sessions) > 50:
            for old in [k for k, v in self._sessions.items() if v.status == "ended"][:25]:
                self._sessions.pop(old, None)
        self._sessions[session.id] = session
        return session

    def get(self, call_id: str) -> CallSession:
        session = self._sessions.get(call_id)
        if session is None:
            raise ApiError(404, "call_not_found", "That call does not exist.")
        return session

    def active(self) -> list[CallSession]:
        return [s for s in self._sessions.values() if s.status == "connected"]

    def transcript(self, call_id: str, role: str, text: str, final: bool = True) -> None:
        self.bus.publish("transcript", {"role": role, "text": text[:MAX_TEXT], "final": final}, call_id=call_id)

    def end(self, call_id: str, reason: str = "ended_by_user") -> CallSession:
        session = self.get(call_id)
        if session.status != "ended":
            session.status = "ended"
            session.ended_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self.bus.publish("call.ended", {"reason": reason, "mode": session.mode}, call_id=call_id)
        return session

    # ----------------------------------------------------------------- demo
    async def start_mock(self) -> tuple[CallSession, str]:
        if self._agent_factory is None:
            raise ApiError(409, "demo_unavailable", "The demo agent is not available in this mode.")
        if self.active():
            for s in self.active():
                self.end(s.id, "replaced_by_new_call")
        session = self._new("mock")
        session.agent = self._agent_factory(session.id)
        self.bus.publish("call.started", {"mode": "mock", "agent": session.agent.label}, call_id=session.id)
        greeting = session.agent.greet()
        self.transcript(session.id, "assistant", greeting)
        return session, greeting

    async def say(self, call_id: str, text: str) -> dict[str, Any]:
        session = self.get(call_id)
        if session.mode != "mock" or session.agent is None:
            raise ApiError(409, "not_a_demo_call", "Typed input only works in demo calls.")
        if session.status == "ended":
            raise ApiError(409, "call_ended", "This call has ended.")
        text = (text or "").strip()
        if not text:
            raise ApiError(422, "empty_message", "Say or type something first.")
        async with session.lock:
            self.transcript(call_id, "user", text)
            reply = await session.agent.respond(text)
            self.transcript(call_id, "assistant", reply)
            hangup = bool(session.agent.wants_hangup)
        if hangup:
            self.end(call_id, "agent_hangup")
        return {"reply": reply, "ended": hangup}

    # ----------------------------------------------------------------- live
    def live_started(self, call_id: str) -> CallSession:
        session = self._new("live", call_id=call_id)
        self.bus.publish("call.started", {"mode": "live", "agent": "Gemini via Pipecat"}, call_id=session.id)
        return session

    def live_connected(self, call_id: str) -> None:
        self.bus.publish("call.connected", {"mode": "live"}, call_id=call_id)
