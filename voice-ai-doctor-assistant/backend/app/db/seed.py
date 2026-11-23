"""Idempotent seed data: doctors, rolling availability and a few demo appointments.

Safe to run on every start-up:
* doctors use ``INSERT OR IGNORE`` (existing edits are kept),
* slots are unique per (doctor, date, start) so re-running only adds missing days,
* demo appointments are created only when the appointments table is empty.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.db.database import Database

# (id, name, speciality, qualifications, years, fee INR, weekdays 0=Mon, windows, minutes)
DOCTORS = [
    ("D01", "Dr. Anika Sharma", "Cardiology", "MD, DM (Cardiology)", 14, 1200,
     (0, 1, 2, 3, 4), [("09:00", "12:30")], 30),
    ("D02", "Dr. Rohan Mehta", "General Medicine", "MBBS, MD (Medicine)", 9, 600,
     (0, 1, 2, 3, 4, 5), [("09:00", "13:00"), ("16:00", "19:00")], 20),
    ("D03", "Dr. Priya Nair", "Dermatology", "MD (Dermatology)", 11, 900,
     (1, 3, 5), [("10:00", "13:00"), ("15:00", "17:30")], 30),
    ("D04", "Dr. Arjun Kulkarni", "Orthopedics", "MS (Orthopaedics)", 16, 1000,
     (0, 2, 4), [("10:00", "13:00"), ("16:00", "18:00")], 30),
    ("D05", "Dr. Sana Iqbal", "Pediatrics", "MD (Pediatrics)", 8, 700,
     (0, 1, 2, 3, 4, 5), [("09:30", "12:30")], 30),
    ("D06", "Dr. Vikram Desai", "ENT", "MS (ENT)", 12, 800,
     (1, 2, 4, 5), [("11:00", "14:00"), ("17:00", "19:00")], 30),
    ("D07", "Dr. Meera Joshi", "Gynecology", "MD, DGO", 13, 1000,
     (0, 1, 3, 4), [("10:00", "13:00")], 30),
]

# Fake numbers, only used for the demo appointments shown on a fresh install.
DEMO_APPOINTMENTS = [
    ("D01", 1, 1, "9000000001", "Demo patient 1"),
    ("D03", 2, 0, "+919000000002", "Demo patient 2"),
    ("D02", 1, 3, "9000000003", None),
]


def _frange(start: str, end: str, minutes: int):
    cur = datetime.strptime(start, "%H:%M")
    stop = datetime.strptime(end, "%H:%M")
    step = timedelta(minutes=minutes)
    while cur + step <= stop:
        yield cur.strftime("%H:%M"), (cur + step).strftime("%H:%M")
        cur += step


def seed(db: Database, days: int = 14, demo_appointments: bool = True, today: datetime | None = None) -> None:
    today = (today or datetime.now()).date()
    with db.transaction() as conn:
        for (did, name, spec, quals, years, fee, weekdays, windows, minutes) in DOCTORS:
            conn.execute(
                """INSERT OR IGNORE INTO doctors
                   (id, name, speciality, qualifications, experience_years, consultation_fee, active)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (did, name, spec, quals, years, fee),
            )
            for offset in range(days):
                day = today + timedelta(days=offset)
                if day.weekday() not in weekdays:
                    continue
                for w_start, w_end in windows:
                    for start, end in _frange(w_start, w_end, minutes):
                        conn.execute(
                            """INSERT OR IGNORE INTO slots (doctor_id, date, start_time, end_time, status)
                               VALUES (?, ?, ?, ?, 'available')""",
                            (did, day.isoformat(), start, end),
                        )
        existing = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]

    if demo_appointments and existing == 0:
        # Imported here to avoid a circular import at module load time.
        from app.services.clinic import ClinicService

        clinic = ClinicService(db, bus=None, clock=lambda: today_as_datetime(today))
        for doctor_id, day_offset, slot_index, phone, name in DEMO_APPOINTMENTS:
            for day in clinic.get_availability(doctor_id, max_days=14, per_day=50):
                if day["date"] >= (today + timedelta(days=day_offset)).isoformat() and len(day["slots"]) > slot_index:
                    slot = day["slots"][slot_index]
                    clinic.book_appointment(doctor_id, day["date"], slot["start_time"], phone, name)
                    break


def today_as_datetime(d) -> datetime:
    return datetime.combine(d, datetime.min.time())
