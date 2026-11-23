"""Clinic business logic: doctors, availability, booking, cancellation.

This is the only module that writes appointments.  Both the REST API and the
voice tools call it, so rules such as "never double book" and "only the phone
number that made a booking can cancel it" are enforced in one place.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import date as date_cls, datetime, timedelta
from typing import Any, Callable

from app.db.database import Database
from app.services.errors import (
    AlreadyCancelled,
    AppointmentNotFound,
    DoctorNotFound,
    InvalidInput,
    PastSlot,
    PatientConflict,
    SlotNotFound,
    SlotUnavailable,
)
from app.services.events import EventBus
from app.services.phone import mask_phone, normalize_phone, phones_match
from app.services.timeutil import date_label, parse_date, parse_time, slot_datetime, time_label

SPECIALITY_ALIASES: dict[str, list[str]] = {
    "cardiology": ["cardiology", "cardiologist", "cardiac", "heart"],
    "general medicine": [
        "general medicine", "general physician", "general practitioner", "family doctor",
        "physician", "gp", "fever", "cold", "general",
    ],
    "dermatology": ["dermatology", "dermatologist", "skin", "acne", "rash", "hair"],
    "orthopedics": [
        "orthopedics", "orthopaedics", "orthopedic", "orthopaedic", "orthopedist",
        "ortho", "bone", "joint", "knee", "fracture", "back pain",
    ],
    "pediatrics": ["pediatrics", "paediatrics", "pediatrician", "paediatrician", "child", "children", "kids", "baby"],
    "ent": ["ent", "ear nose and throat", "ear nose throat", "ear", "nose", "throat"],
    "gynecology": ["gynecology", "gynaecology", "gynecologist", "gynaecologist", "obstetrics", "pregnancy", "women"],
}


def resolve_speciality(text: str | None) -> str | None:
    """Map free text ("heart doctor", "skin") to a canonical speciality key."""
    if not text:
        return None
    low = text.lower()
    best: tuple[int, str] | None = None
    for canonical, aliases in SPECIALITY_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", low):
                if best is None or len(alias) > best[0]:
                    best = (len(alias), canonical)
    return best[1] if best else None


def _name_tokens(text: str) -> list[str]:
    low = re.sub(r"\bdr\b\.?", " ", text.lower())
    return [t for t in re.findall(r"[a-z]+", low) if t]


class ClinicService:
    def __init__(
        self,
        db: Database,
        bus: EventBus | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        self.bus = bus
        self._clock = clock or datetime.now

    # ------------------------------------------------------------------ utils
    def now(self) -> datetime:
        return self._clock()

    def today(self) -> date_cls:
        return self.now().date()

    def _emit(self, type: str, payload: dict[str, Any], call_id: str | None = None) -> None:
        if self.bus is not None:
            self.bus.publish(type, payload, call_id=call_id)

    @staticmethod
    def _doctor_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "speciality": row["speciality"],
            "qualifications": row["qualifications"],
            "experience_years": row["experience_years"],
            "consultation_fee": row["consultation_fee"],
            "currency": "INR",
            "active": bool(row["active"]),
        }

    @staticmethod
    def _slot_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "date": row["date"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "label": time_label(row["start_time"]),
        }

    def _appointment_dict(self, row: sqlite3.Row, reveal_phone: bool = False) -> dict[str, Any]:
        data = {
            "id": row["id"],
            "doctor_id": row["doctor_id"],
            "doctor_name": row["doctor_name"],
            "speciality": row["speciality"],
            "consultation_fee": row["consultation_fee"],
            "patient_name": row["patient_name"],
            "date": row["date"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "date_label": date_label(row["date"]),
            "time_label": time_label(row["start_time"]),
            "phone_masked": mask_phone(row["phone"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if reveal_phone:
            data["phone"] = row["phone"]
        return data

    _APPT_SELECT = """
        SELECT a.*, d.name AS doctor_name, d.speciality AS speciality,
               d.consultation_fee AS consultation_fee
        FROM appointments a JOIN doctors d ON d.id = a.doctor_id
    """

    # --------------------------------------------------------------- doctors
    def list_doctors(self, speciality: str | None = None, query: str | None = None) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM doctors WHERE active = 1 ORDER BY name").fetchall()
        doctors = [self._doctor_dict(r) for r in rows]
        if speciality:
            wanted = resolve_speciality(speciality) or speciality.lower()
            doctors = [d for d in doctors if wanted in d["speciality"].lower()]
        if query:
            q = query.lower().strip()
            doctors = [
                d for d in doctors
                if q in d["name"].lower() or q in d["speciality"].lower() or q in (d["qualifications"] or "").lower()
            ]
        return doctors

    def specialities(self) -> list[str]:
        return sorted({d["speciality"] for d in self.list_doctors()})

    def get_doctor(self, doctor_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM doctors WHERE id = ? AND active = 1", (doctor_id,)).fetchone()
        if row is None:
            raise DoctorNotFound(f"No doctor with id {doctor_id!r}.")
        return self._doctor_dict(row)

    def find_doctors(self, doctor: str | None = None, speciality: str | None = None) -> list[dict[str, Any]]:
        """Resolve a spoken doctor name / id and/or speciality to doctor records."""
        doctors = self.list_doctors()
        if doctor and doctor.strip():
            ident = doctor.strip().lower()
            exact = [d for d in doctors if d["id"].lower() == ident]
            if exact:
                doctors = exact
            else:
                tokens = _name_tokens(doctor)
                if not tokens:
                    doctors = []
                else:
                    doctors = [d for d in doctors if all(t in _name_tokens(d["name"]) or
                                                          any(n.startswith(t) for n in _name_tokens(d["name"]))
                                                          for t in tokens)]
        if speciality and speciality.strip():
            wanted = resolve_speciality(speciality) or speciality.strip().lower()
            doctors = [d for d in doctors if wanted in d["speciality"].lower()]
        return doctors

    # --------------------------------------------------------- availability
    _UPCOMING = "(s.date > :today OR (s.date = :today AND s.start_time > :now_time))"

    def get_availability(
        self,
        doctor_id: str,
        on_date: str | None = None,
        max_days: int = 3,
        per_day: int = 12,
        horizon_days: int = 30,
    ) -> list[dict[str, Any]]:
        """Open, future slots grouped by day.  Never returns booked / blocked / past slots."""
        now = self.now()
        params: dict[str, Any] = {
            "doctor_id": doctor_id,
            "today": now.date().isoformat(),
            "now_time": now.strftime("%H:%M"),
            "last": (now.date() + timedelta(days=horizon_days)).isoformat(),
        }
        sql = f"""SELECT s.* FROM slots s
                  WHERE s.doctor_id = :doctor_id AND s.status = 'available'
                    AND {self._UPCOMING} AND s.date <= :last"""
        if on_date:
            params["on_date"] = on_date
            sql += " AND s.date = :on_date"
        sql += " ORDER BY s.date, s.start_time"
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        days: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            days.setdefault(row["date"], []).append(self._slot_dict(row))
        result = []
        for day, slots in list(days.items())[: (1 if on_date else max_days)]:
            result.append({"date": day, "date_label": date_label(day), "slots": slots[:per_day], "total": len(slots)})
        return result

    def doctors_with_availability(
        self, speciality: str | None = None, query: str | None = None, days: int = 3, per_day: int = 12
    ) -> list[dict[str, Any]]:
        out = []
        for doc in self.list_doctors(speciality=speciality, query=query):
            avail = self.get_availability(doc["id"], max_days=days, per_day=per_day)
            doc = dict(doc)
            doc["availability"] = avail
            doc["open_slots"] = self.count_open_slots(doc["id"])
            out.append(doc)
        return out

    def count_open_slots(self, doctor_id: str | None = None) -> int:
        now = self.now()
        params: dict[str, Any] = {"today": now.date().isoformat(), "now_time": now.strftime("%H:%M")}
        sql = f"SELECT COUNT(*) FROM slots s WHERE s.status='available' AND {self._UPCOMING}"
        if doctor_id:
            sql += " AND s.doctor_id = :doctor_id"
            params["doctor_id"] = doctor_id
        with self.db.connect() as conn:
            return int(conn.execute(sql, params).fetchone()[0])

    def parse_requested_date(self, value: str | None) -> str | None:
        if not value or not str(value).strip():
            return None
        try:
            return parse_date(str(value), self.today()).isoformat()
        except ValueError as exc:
            raise InvalidInput(f"I couldn't understand the date '{value}'. Please give a day like 'tomorrow' or '25 November'.") from exc

    # -------------------------------------------------------------- booking
    def book_appointment(
        self,
        doctor_id: str,
        date: str,
        start_time: str,
        phone: str,
        patient_name: str | None = None,
        call_id: str | None = None,
    ) -> dict[str, Any]:
        """Atomically reserve a slot.  Raises a ``DomainError`` subclass on any problem."""
        canonical = normalize_phone(phone).canonical  # raises InvalidPhoneError
        try:
            iso_date = parse_date(date, self.today()).isoformat()
            hhmm = parse_time(start_time)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc
        name = (patient_name or "").strip()[:80] or None
        now = self.now()

        try:
            appointment_id = self._reserve(doctor_id, iso_date, hhmm, canonical, name, now)
        except SlotUnavailable as exc:
            exc.details["alternatives"] = self._alternatives(doctor_id)
            raise
        appt = self.get_appointment(appointment_id)
        self._emit("appointment.booked", {"appointment": appt}, call_id)
        self._emit("slots.changed", {"doctor_id": doctor_id, "date": iso_date})
        return appt

    def _reserve(self, doctor_id: str, iso_date: str, hhmm: str, canonical: str, name: str | None, now: datetime) -> str:
        with self.db.transaction() as conn:
            doctor = conn.execute("SELECT id FROM doctors WHERE id = ? AND active = 1", (doctor_id,)).fetchone()
            if doctor is None:
                raise DoctorNotFound(f"No doctor with id {doctor_id!r}.")
            slot = conn.execute(
                "SELECT * FROM slots WHERE doctor_id = ? AND date = ? AND start_time = ?",
                (doctor_id, iso_date, hhmm),
            ).fetchone()
            if slot is None:
                raise SlotNotFound(f"That doctor has no slot on {date_label(iso_date)} at {time_label(hhmm)}.")
            if slot_datetime(iso_date, hhmm) <= now:
                raise PastSlot("That time has already passed.")
            clash = conn.execute(
                "SELECT phone FROM appointments WHERE status = 'booked' AND date = ? AND start_time = ?",
                (iso_date, hhmm),
            ).fetchall()
            if any(phones_match(r["phone"], canonical) for r in clash):
                raise PatientConflict("This phone number already has an appointment at that time.")
            claimed = conn.execute(
                "UPDATE slots SET status = 'booked' WHERE id = ? AND status = 'available'", (slot["id"],)
            )
            if claimed.rowcount != 1:
                raise SlotUnavailable(f"The {time_label(hhmm)} slot on {date_label(iso_date)} was just taken.")
            stamp = now.isoformat(timespec="seconds")
            for _ in range(10):
                appointment_id = f"APT-{secrets.randbelow(900000) + 100000}"
                try:
                    conn.execute(
                        """INSERT INTO appointments
                           (id, doctor_id, slot_id, phone, patient_name, date, start_time, end_time,
                            status, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'booked', ?, ?)""",
                        (appointment_id, doctor_id, slot["id"], canonical, name, iso_date,
                         slot["start_time"], slot["end_time"], stamp, stamp),
                    )
                    return appointment_id
                except sqlite3.IntegrityError as exc:
                    if "appointments.id" in str(exc) or "PRIMARY" in str(exc):
                        continue  # id collision, try another
                    raise SlotUnavailable("That slot was just taken.") from exc
            raise RuntimeError("could not allocate an appointment id")

    def _alternatives(self, doctor_id: str, limit: int = 3) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for day in self.get_availability(doctor_id, max_days=3, per_day=limit):
            for slot in day["slots"]:
                out.append({"date": day["date"], "date_label": day["date_label"],
                            "start_time": slot["start_time"], "label": slot["label"]})
        return out[:limit]

    # ----------------------------------------------------------- cancelling
    def find_active_appointments(self, phone: str) -> list[dict[str, Any]]:
        """Upcoming booked appointments for exactly this spoken number."""
        canonical = normalize_phone(phone).canonical
        now = self.now()
        with self.db.connect() as conn:
            rows = conn.execute(
                self._APPT_SELECT + " WHERE a.status = 'booked' ORDER BY a.date, a.start_time"
            ).fetchall()
        return [
            self._appointment_dict(r)
            for r in rows
            if phones_match(r["phone"], canonical) and slot_datetime(r["date"], r["start_time"]) > now
        ]

    def cancel_appointment(self, appointment_id: str, phone: str, call_id: str | None = None) -> dict[str, Any]:
        """Cancel one appointment, but only for the phone number that owns it."""
        canonical = normalize_phone(phone).canonical
        with self.db.transaction() as conn:
            row = conn.execute(self._APPT_SELECT + " WHERE a.id = ?", (appointment_id.strip().upper(),)).fetchone()
            # Same answer for "does not exist" and "belongs to someone else": never leak other patients' data.
            if row is None or not phones_match(row["phone"], canonical):
                raise AppointmentNotFound("I couldn't find an appointment with that ID for this phone number.")
            if row["status"] != "booked":
                raise AlreadyCancelled("That appointment has already been cancelled.")
            stamp = self.now().isoformat(timespec="seconds")
            conn.execute("UPDATE appointments SET status = 'cancelled', updated_at = ? WHERE id = ?", (stamp, row["id"]))
            conn.execute("UPDATE slots SET status = 'available' WHERE id = ?", (row["slot_id"],))
        appt = self.get_appointment(row["id"])
        self._emit("appointment.cancelled", {"appointment": appt}, call_id)
        self._emit("slots.changed", {"doctor_id": appt["doctor_id"], "date": appt["date"]})
        return appt

    # -------------------------------------------------------------- queries
    def get_appointment(self, appointment_id: str, reveal_phone: bool = False) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(self._APPT_SELECT + " WHERE a.id = ?", (appointment_id,)).fetchone()
        if row is None:
            raise AppointmentNotFound(f"No appointment {appointment_id}.")
        return self._appointment_dict(row, reveal_phone)

    def list_appointments(
        self, status: str | None = None, search: str | None = None, reveal_phone: bool = False, limit: int = 200
    ) -> list[dict[str, Any]]:
        if status and status not in {"booked", "cancelled"}:
            raise InvalidInput("status must be 'booked' or 'cancelled'.")
        sql = self._APPT_SELECT
        params: list[Any] = []
        if status:
            sql += " WHERE a.status = ?"
            params.append(status)
        sql += " ORDER BY a.date, a.start_time LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        items = [self._appointment_dict(r, reveal_phone) for r in rows]
        if search:
            q = search.lower().strip()
            items = [
                a for a in items
                if q in a["id"].lower() or q in a["doctor_name"].lower() or q in (a["patient_name"] or "").lower()
                or q in a["speciality"].lower()
            ]
        return items

    def overview(self) -> dict[str, Any]:
        now = self.now()
        with self.db.connect() as conn:
            booked = conn.execute("SELECT COUNT(*) FROM appointments WHERE status='booked'").fetchone()[0]
            cancelled = conn.execute("SELECT COUNT(*) FROM appointments WHERE status='cancelled'").fetchone()[0]
            doctors = conn.execute("SELECT COUNT(*) FROM doctors WHERE active=1").fetchone()[0]
        upcoming = [
            a for a in self.list_appointments(status="booked")
            if slot_datetime(a["date"], a["start_time"]) > now
        ]
        return {
            "doctors": doctors,
            "open_slots": self.count_open_slots(),
            "booked": booked,
            "cancelled": cancelled,
            "next_appointment": upcoming[0] if upcoming else None,
        }
