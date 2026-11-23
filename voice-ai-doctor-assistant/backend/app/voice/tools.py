"""The three LLM tools and the executor that runs them.

The *same* executor serves the live Gemini agent (via Pipecat function calling)
and the rule-based mock agent, so both modes perform real database operations.

Safety rules enforced in code (not only in the prompt):

* ``book_appointment`` and ``cancel_appointment`` refuse to act unless
  ``phone_confirmed`` is true, and answer with the exact read-back text instead.
* Cancelling needs the phone number that owns the booking; nothing about other
  patients is ever returned.
* Tool results are plain dicts with a ``status`` field; failures never look like success.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.services.clinic import ClinicService
from app.services.errors import DomainError
from app.services.events import EventBus
from app.services.phone import InvalidPhoneError, normalize_phone, read_back
from app.services.timeutil import date_label, time_label

log = logging.getLogger("voice.tools")

# --------------------------------------------------------------------------- argument models


class CheckAvailabilityArgs(BaseModel):
    doctor: str | None = Field(None, description="Doctor name or id, e.g. 'Dr. Sharma' or 'D01'.")
    speciality: str | None = Field(None, description="Speciality, e.g. 'cardiology' or 'skin'.")
    date: str | None = Field(None, description="Date: YYYY-MM-DD, 'today', 'tomorrow' or a weekday.")


class BookAppointmentArgs(BaseModel):
    doctor: str = Field(..., min_length=1, description="Doctor id (e.g. 'D01') or full name.")
    date: str = Field(..., min_length=1, description="Appointment date, YYYY-MM-DD.")
    time: str = Field(..., min_length=1, description="Slot start time, 24h HH:MM exactly as offered.")
    phone: str = Field(..., description="Phone number exactly as the caller said it.")
    phone_confirmed: bool = Field(False, description="True only after the caller said yes to the read-back.")
    patient_name: str | None = Field(None, description="Only if the caller gave their name.")

    @field_validator("phone", mode="before")
    @classmethod
    def _stringify(cls, v: Any) -> str:
        return "" if v is None else str(v)


class CancelAppointmentArgs(BaseModel):
    phone: str = Field(..., description="Phone number exactly as the caller said it.")
    phone_confirmed: bool = Field(False, description="True only after the caller said yes to the read-back.")
    appointment_id: str | None = Field(None, description="Appointment id (APT-xxxxxx) to cancel.")

    @field_validator("phone", mode="before")
    @classmethod
    def _stringify(cls, v: Any) -> str:
        return "" if v is None else str(v)


# --------------------------------------------------------------------------- schemas for the LLM

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "check_doctor_availability",
        "description": (
            "Look up real open appointment slots. Use before offering any time. Give a doctor "
            "(name or id) and/or a speciality, and optionally a date. Never invent slots."
        ),
        "properties": {
            "doctor": {"type": "string", "description": "Doctor name or id, e.g. 'Dr. Sharma' or 'D01'."},
            "speciality": {"type": "string", "description": "Speciality such as cardiology, dermatology, ENT, pediatrics."},
            "date": {"type": "string", "description": "YYYY-MM-DD, or 'today', 'tomorrow', or a weekday name."},
        },
        "required": [],
    },
    {
        "name": "book_appointment",
        "description": (
            "Book one slot the caller chose. First call it with phone_confirmed=false: it returns the exact "
            "digits to read back. Read them to the caller, wait for a clear yes, then call again with "
            "phone_confirmed=true. Only say the booking is done when status is 'booked'."
        ),
        "properties": {
            "doctor": {"type": "string", "description": "Doctor id (e.g. 'D01') or name."},
            "date": {"type": "string", "description": "YYYY-MM-DD of the chosen slot."},
            "time": {"type": "string", "description": "Start time of the chosen slot as 24h HH:MM."},
            "phone": {"type": "string", "description": "Phone number as the caller said it, digits only is fine."},
            "phone_confirmed": {"type": "boolean", "description": "True only after the caller confirmed the read-back."},
            "patient_name": {"type": "string", "description": "Caller's name, only if they volunteered it."},
        },
        "required": ["doctor", "date", "time", "phone", "phone_confirmed"],
    },
    {
        "name": "cancel_appointment",
        "description": (
            "Cancel the caller's appointment. Step 1: call with the spoken phone and phone_confirmed=false to "
            "get the read-back text. Step 2: after the caller confirms, call with phone_confirmed=true and no "
            "appointment_id to list their appointments. Step 3: after the caller agrees which one, call with "
            "phone_confirmed=true and that appointment_id. Only say it is cancelled when status is 'cancelled'."
        ),
        "properties": {
            "phone": {"type": "string", "description": "Phone number as the caller said it."},
            "phone_confirmed": {"type": "boolean", "description": "True only after the caller confirmed the read-back."},
            "appointment_id": {"type": "string", "description": "Appointment id such as APT-123456, once known."},
        },
        "required": ["phone", "phone_confirmed"],
    },
]

_MODELS: dict[str, type[BaseModel]] = {
    "check_doctor_availability": CheckAvailabilityArgs,
    "book_appointment": BookAppointmentArgs,
    "cancel_appointment": CancelAppointmentArgs,
}


def _safe_args_for_log(args: dict[str, Any]) -> dict[str, Any]:
    """Never put full phone numbers in logs or events."""
    out = dict(args)
    if "phone" in out and out["phone"]:
        try:
            from app.services.phone import mask_phone
            out["phone"] = mask_phone(normalize_phone(str(out["phone"])).canonical)
        except InvalidPhoneError:
            out["phone"] = "•••"
    return out


class ToolExecutor:
    """Validates tool arguments, runs them against the clinic service and reports events."""

    def __init__(self, clinic: ClinicService, bus: EventBus | None = None, timeout: float = 15.0) -> None:
        self.clinic = clinic
        self.bus = bus
        self.timeout = timeout

    # ------------------------------------------------------------------ public
    async def execute(self, name: str, raw_args: dict[str, Any] | None, call_id: str | None = None) -> dict[str, Any]:
        raw_args = dict(raw_args or {})
        self._event("tool.started", {"tool": name, "args": _safe_args_for_log(raw_args)}, call_id)
        try:
            model = _MODELS[name]
        except KeyError:
            return self._finish(name, {"status": "error", "code": "unknown_tool", "message": f"Unknown tool {name}."}, call_id)
        try:
            args = model(**raw_args)
        except ValidationError as exc:
            fields = ", ".join(str(e["loc"][0]) for e in exc.errors() if e["loc"])
            return self._finish(
                name,
                {"status": "error", "code": "invalid_arguments", "message": f"Missing or invalid: {fields}."},
                call_id,
            )
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(getattr(self, f"_{name}"), args, call_id), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            result = {"status": "error", "code": "timeout",
                      "message": "The booking system took too long to answer. Please try again in a moment."}
        except InvalidPhoneError as exc:
            result = {"status": "error", "code": "invalid_phone", "message": str(exc)}
        except DomainError as exc:
            result = exc.to_dict()
        except Exception:  # noqa: BLE001 - tools must never crash the call
            log.exception("tool %s failed", name)
            result = {"status": "error", "code": "internal_error",
                      "message": "Something went wrong on our side. Nothing was changed."}
        return self._finish(name, result, call_id)

    # ------------------------------------------------------------------ tools
    def _check_doctor_availability(self, a: CheckAvailabilityArgs, call_id: str | None) -> dict[str, Any]:
        on_date = self.clinic.parse_requested_date(a.date)
        doctors = self.clinic.find_doctors(doctor=a.doctor, speciality=a.speciality)
        if not doctors:
            asked = a.doctor or a.speciality or "that"
            known = ", ".join(f"{d['name']} ({d['speciality']})" for d in self.clinic.list_doctors())
            return {"status": "no_doctor", "message": f"No doctor matches '{asked}'.", "doctors_we_have": known}
        out, any_slots = [], False
        for d in doctors:
            days = self.clinic.get_availability(d["id"], on_date=on_date, max_days=3, per_day=8)
            any_slots = any_slots or bool(days)
            out.append({
                "doctor_id": d["id"], "name": d["name"], "speciality": d["speciality"],
                "qualifications": d["qualifications"], "consultation_fee_inr": d["consultation_fee"],
                "availability": [
                    {"date": day["date"], "label": day["date_label"],
                     "slots": [{"time": s["start_time"], "spoken": s["label"]} for s in day["slots"]],
                     "more_slots": max(0, day["total"] - len(day["slots"]))}
                    for day in days
                ],
            })
        if not any_slots:
            msg = "No open slots"
            msg += f" on {date_label(on_date)}." if on_date else " in the next 30 days."
            return {"status": "no_slots", "message": msg + " Offer another day or doctor.", "doctors": out}
        return {"status": "ok", "doctors": out}

    def _book_appointment(self, a: BookAppointmentArgs, call_id: str | None) -> dict[str, Any]:
        phone = normalize_phone(a.phone)  # InvalidPhoneError -> invalid_phone
        spoken = read_back(phone)
        if not a.phone_confirmed:
            return {"status": "needs_confirmation", "read_back": spoken,
                    "message": f"Read this number back to the caller digit by digit: {spoken}. "
                               "Ask 'Is that correct?' and call again with phone_confirmed=true only after a clear yes."}
        doctors = self.clinic.find_doctors(doctor=a.doctor)
        if len(doctors) != 1:
            return {"status": "error", "code": "doctor_not_found" if not doctors else "doctor_ambiguous",
                    "message": "I couldn't tell which doctor you mean." if doctors else f"No doctor matches '{a.doctor}'."}
        appt = self.clinic.book_appointment(doctors[0]["id"], a.date, a.time, phone.canonical, a.patient_name, call_id)
        return {"status": "booked", "appointment": self._speakable(appt), "phone_read_back": spoken}

    def _cancel_appointment(self, a: CancelAppointmentArgs, call_id: str | None) -> dict[str, Any]:
        phone = normalize_phone(a.phone)
        spoken = read_back(phone)
        if not a.phone_confirmed:
            return {"status": "needs_confirmation", "read_back": spoken,
                    "message": f"Read this number back to the caller digit by digit: {spoken}. "
                               "Ask 'Is that correct?' and call again with phone_confirmed=true only after a clear yes."}
        mine = self.clinic.find_active_appointments(phone.canonical)
        if not a.appointment_id:
            if not mine:
                return {"status": "no_match",
                        "message": "There are no upcoming appointments booked with that phone number."}
            return {"status": "found", "count": len(mine),
                    "appointments": [self._speakable(x) for x in mine],
                    "message": "Tell the caller what you found and ask which one to cancel; "
                               "then call again with appointment_id."}
        wanted = a.appointment_id.strip().upper()
        if wanted not in {x["id"] for x in mine}:
            return {"status": "no_match",
                    "message": "That appointment is not booked under this phone number."}
        appt = self.clinic.cancel_appointment(wanted, phone.canonical, call_id)
        return {"status": "cancelled", "appointment": self._speakable(appt)}

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _speakable(appt: dict[str, Any]) -> dict[str, Any]:
        return {
            "appointment_id": appt["id"], "doctor": appt["doctor_name"], "speciality": appt["speciality"],
            "date": appt["date"], "date_label": appt["date_label"], "time": appt["start_time"],
            "time_label": time_label(appt["start_time"]), "fee_inr": appt["consultation_fee"],
            "patient_name": appt["patient_name"], "status": appt["status"],
        }

    def _event(self, type: str, payload: dict[str, Any], call_id: str | None) -> None:
        if self.bus is not None:
            self.bus.publish(type, payload, call_id=call_id)

    def _finish(self, name: str, result: dict[str, Any], call_id: str | None) -> dict[str, Any]:
        self._event("tool.finished", {"tool": name, "status": result.get("status"),
                                      "code": result.get("code"), "summary": self._summary(name, result)}, call_id)
        return result

    @staticmethod
    def _summary(name: str, r: dict[str, Any]) -> str:
        status = r.get("status")
        if name == "check_doctor_availability":
            if status == "ok":
                return "Checked availability: " + ", ".join(d["name"] for d in r["doctors"])
            return r.get("message", "No availability found")
        if status == "booked":
            a = r["appointment"]
            return f"Booked {a['appointment_id']} with {a['doctor']} on {a['date_label']} at {a['time_label']}"
        if status == "cancelled":
            a = r["appointment"]
            return f"Cancelled {a['appointment_id']} ({a['doctor']}, {a['date_label']})"
        if status == "needs_confirmation":
            return "Waiting for the caller to confirm their number"
        if status == "found":
            return f"Found {r['count']} upcoming appointment(s) for this number"
        return r.get("message", status or "done")
