"""Framework-independent request handlers.

Routes in ``routes.py`` only translate HTTP <-> these methods, so all behaviour can be
tested without a web server.  Handlers return plain dicts and raise ``DomainError``s.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import __version__
from app.api.schemas import BookingRequest, CancelRequest, SayRequest
from app.context import AppContext
from app.services.errors import ApiError, InvalidInput
from app.services.phone import normalize_phone


class ApiHandlers:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # ---------------------------------------------------------------- system
    def health(self) -> dict[str, Any]:
        with self.ctx.db.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok", "mode": self.ctx.settings.app_mode, "version": __version__,
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    def config(self) -> dict[str, Any]:
        s = self.ctx.settings
        missing = s.missing_live_requirements() if s.is_live else []
        return {
            "app_mode": s.app_mode,
            "clinic_name": s.clinic_name,
            "live_ready": s.is_live and not missing,
            "missing": missing,
            "stack": ({"transport": "Pipecat SmallWebRTC", "stt": f"ElevenLabs {s.elevenlabs_stt_model}",
                       "llm": f"Gemini {s.llm_model}", "tts": f"ElevenLabs {s.elevenlabs_tts_model}"}
                      if s.is_live else {"transport": "HTTP (typed / browser speech)", "stt": "none",
                                         "llm": "Rule-based demo agent (no LLM)", "tts": "none"}),
        }

    def overview(self) -> dict[str, Any]:
        return {**self.ctx.clinic.overview(), "active_calls": len(self.ctx.calls.active())}

    # --------------------------------------------------------------- doctors
    def list_doctors(self, speciality: str | None = None, q: str | None = None, days: int = 3) -> dict[str, Any]:
        days = max(1, min(int(days), 7))
        return {"doctors": self.ctx.clinic.doctors_with_availability(speciality, q, days=days),
                "specialities": self.ctx.clinic.specialities()}

    def doctor_availability(self, doctor_id: str, date: str | None = None, days: int = 7) -> dict[str, Any]:
        doctor = self.ctx.clinic.get_doctor(doctor_id)
        iso = self.ctx.clinic.parse_requested_date(date)
        availability = self.ctx.clinic.get_availability(doctor_id, on_date=iso, max_days=max(1, min(int(days), 14)), per_day=40)
        return {"doctor": doctor, "date": iso, "availability": availability}

    # ---------------------------------------------------------- appointments
    def list_appointments(self, status: str | None = None, q: str | None = None, reveal_phone: bool = False) -> dict[str, Any]:
        items = self.ctx.clinic.list_appointments(status=status or None, search=q, reveal_phone=reveal_phone)
        return {"appointments": items, "count": len(items)}

    def create_appointment(self, body: BookingRequest) -> dict[str, Any]:
        appt = self.ctx.clinic.book_appointment(body.doctor_id, body.date, body.start_time, body.phone, body.patient_name)
        return {"appointment": appt}

    def cancel_appointment(self, appointment_id: str, body: CancelRequest) -> dict[str, Any]:
        return {"appointment": self.ctx.clinic.cancel_appointment(appointment_id, body.phone)}

    def lookup_appointments(self, phone: str) -> dict[str, Any]:
        """Exact-number lookup (same rule the voice agent uses)."""
        if not phone:
            raise InvalidInput("phone is required.")
        normalize_phone(phone)
        items = self.ctx.clinic.find_active_appointments(phone)
        return {"appointments": items, "count": len(items)}

    # ----------------------------------------------------------------- calls
    async def start_call(self) -> dict[str, Any]:
        if self.ctx.settings.is_live:
            raise ApiError(409, "use_webrtc", "Live mode calls start over WebRTC (POST /api/offer).")
        session, greeting = await self.ctx.calls.start_mock()
        return {**session.public(), "greeting": greeting}

    async def say(self, call_id: str, body: SayRequest) -> dict[str, Any]:
        return await self.ctx.calls.say(call_id, body.text)

    def end_call(self, call_id: str) -> dict[str, Any]:
        session = self.ctx.calls.end(call_id)
        live = self.ctx.live
        if live is not None:
            live.request_hangup(call_id)
        return session.public()
