"""FastAPI routes.  Intentionally thin: every route calls a method on ``ApiHandlers``."""
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.api.handlers import ApiHandlers
from app.api.schemas import BookingRequest, CancelRequest, SayRequest
from app.services.events import sse_stream


def build_router(h: ApiHandlers) -> APIRouter:
    r = APIRouter(prefix="/api")

    # ---- system --------------------------------------------------------
    @r.get("/health", tags=["system"])
    def health():
        return h.health()

    @r.get("/config", tags=["system"])
    def config():
        return h.config()

    @r.get("/overview", tags=["system"])
    def overview():
        return h.overview()

    @r.get("/events", tags=["system"], summary="Server-Sent Events stream for the dashboard")
    async def events(request: Request, since: int | None = None):
        last = request.headers.get("last-event-id")
        if since is None and last and last.isdigit():
            since = int(last)
        return StreamingResponse(
            sse_stream(h.ctx.bus, since),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
        )

    # ---- doctors -------------------------------------------------------
    @r.get("/doctors", tags=["doctors"])
    def doctors(speciality: str | None = None, q: str | None = None, days: int = Query(3, ge=1, le=7)):
        return h.list_doctors(speciality, q, days)

    @r.get("/doctors/{doctor_id}/availability", tags=["doctors"])
    def doctor_availability(doctor_id: str, date: str | None = None, days: int = Query(7, ge=1, le=14)):
        return h.doctor_availability(doctor_id, date, days)

    # ---- appointments --------------------------------------------------
    @r.get("/appointments", tags=["appointments"])
    def appointments(status: str | None = None, q: str | None = None, reveal_phone: bool = False):
        return h.list_appointments(status, q, reveal_phone)

    @r.get("/appointments/lookup", tags=["appointments"], summary="Upcoming appointments for an exact phone number")
    def lookup(phone: str):
        return h.lookup_appointments(phone)

    @r.post("/appointments", status_code=201, tags=["appointments"])
    def book(body: BookingRequest):
        return h.create_appointment(body)

    @r.post("/appointments/{appointment_id}/cancel", tags=["appointments"])
    def cancel(appointment_id: str, body: CancelRequest):
        return h.cancel_appointment(appointment_id, body)

    # ---- calls (demo mode) --------------------------------------------
    @r.post("/calls", status_code=201, tags=["calls"], summary="Start a demo call (mock mode only)")
    async def start_call():
        return await h.start_call()

    @r.post("/calls/{call_id}/say", tags=["calls"], summary="Send the caller's words to the demo agent")
    async def say(call_id: str, body: SayRequest):
        return await h.say(call_id, body)

    @r.post("/calls/{call_id}/end", tags=["calls"])
    async def end_call(call_id: str):
        return h.end_call(call_id)

    return r
