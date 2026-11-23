"""In-process event bus feeding the dashboard over Server-Sent Events.

Publishers (the clinic service, tool executor, voice pipeline, mock agent) call
``bus.publish(...)`` from any thread.  Each SSE client owns a ``Subscription``
with an ``asyncio.Queue`` bound to its event loop.  A bounded history lets a
reconnecting browser catch up using ``Last-Event-ID`` / ``?since=``.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, AsyncIterator

Event = dict[str, Any]


class Subscription:
    def __init__(self, bus: "EventBus", loop: asyncio.AbstractEventLoop) -> None:
        self._bus = bus
        self.loop = loop
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=1000)

    def push(self, event: Event) -> None:
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:  # slow client: drop rather than block publishers
            pass

    def close(self) -> None:
        self._bus._unsubscribe(self)


class EventBus:
    def __init__(self, history: int = 300) -> None:
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._history: deque[Event] = deque(maxlen=history)
        self._subs: list[Subscription] = []

    def publish(self, type: str, payload: dict[str, Any] | None = None, call_id: str | None = None) -> Event:
        """Publish an event; safe to call from worker threads."""
        with self._lock:
            event: Event = {
                "id": next(self._ids),
                "type": type,
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "call_id": call_id,
                "payload": payload or {},
            }
            self._history.append(event)
            subs = list(self._subs)
        for sub in subs:
            try:
                sub.loop.call_soon_threadsafe(sub.push, event)
            except RuntimeError:  # loop already closed
                self._unsubscribe(sub)
        return event

    def subscribe(self) -> Subscription:
        sub = Subscription(self, asyncio.get_running_loop())
        with self._lock:
            self._subs.append(sub)
        return sub

    def _unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    def history_since(self, since: int | None) -> list[Event]:
        with self._lock:
            items = list(self._history)
        if since is None:
            return items[-50:]
        return [e for e in items if e["id"] > since]

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)


def format_sse(event: Event) -> str:
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"


async def sse_stream(bus: EventBus, since: int | None = None, keepalive: float = 15.0) -> AsyncIterator[str]:
    """Yield SSE text frames: replayed history first, then live events."""
    sub = bus.subscribe()  # subscribe first so nothing is missed between replay and live
    last_id = since or 0
    try:
        yield "retry: 2000\n\n"
        for event in bus.history_since(since):
            last_id = max(last_id, event["id"])
            yield format_sse(event)
        while True:
            try:
                event = await asyncio.wait_for(sub.queue.get(), timeout=keepalive)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if event["id"] <= last_id:
                continue
            last_id = event["id"]
            yield format_sse(event)
    finally:
        sub.close()
