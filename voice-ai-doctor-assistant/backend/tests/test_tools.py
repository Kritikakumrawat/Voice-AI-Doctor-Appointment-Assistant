"""ToolExecutor: validation, read-back enforcement, error shapes, events."""
import asyncio

import pytest

from app.voice.tools import ToolExecutor, TOOL_SPECS

PHONE = "98765 43210"


@pytest.fixture()
def ex(clinic, bus):
    return ToolExecutor(clinic, bus, timeout=5)


def run(coro):
    return asyncio.run(coro)


def test_tool_names_are_exact():
    assert [t["name"] for t in TOOL_SPECS] == ["check_doctor_availability", "book_appointment", "cancel_appointment"]


def test_availability_by_speciality_and_date(ex):
    r = run(ex.execute("check_doctor_availability", {"speciality": "cardiology", "date": "tomorrow"}))
    assert r["status"] == "ok" and r["doctors"][0]["doctor_id"] == "D01"
    day = r["doctors"][0]["availability"][0]
    assert day["date"] == "2026-11-24" and day["slots"][0]["time"] == "09:00"


def test_availability_no_slots_and_no_doctor_and_bad_date(ex):
    assert run(ex.execute("check_doctor_availability", {"doctor": "Sharma", "date": "2026-11-29"}))["status"] == "no_slots"
    assert run(ex.execute("check_doctor_availability", {"doctor": "Dr. Who"}))["status"] == "no_doctor"
    bad = run(ex.execute("check_doctor_availability", {"date": "whenever-ish"}))
    assert bad["status"] == "error" and bad["code"] == "invalid_input"


def test_booking_requires_readback_confirmation(ex, clinic):
    args = {"doctor": "D01", "date": "2026-11-24", "time": "09:00", "phone": PHONE}
    r = run(ex.execute("book_appointment", {**args, "phone_confirmed": False}))
    assert r["status"] == "needs_confirmation" and r["read_back"] == "9 8 7 6 5, 4 3 2 1 0"
    assert clinic.list_appointments() == []                       # nothing written
    r = run(ex.execute("book_appointment", {**args, "phone_confirmed": True, "patient_name": "Asha"}))
    assert r["status"] == "booked" and r["appointment"]["doctor"] == "Dr. Anika Sharma"
    assert len(clinic.list_appointments()) == 1


def test_booking_error_paths(ex):
    base = {"doctor": "D01", "date": "2026-11-24", "time": "09:00", "phone_confirmed": True}
    assert run(ex.execute("book_appointment", {**base, "phone": "123"}))["code"] == "invalid_phone"
    assert run(ex.execute("book_appointment", {**base, "phone": PHONE, "doctor": "Nobody"}))["code"] == "doctor_not_found"
    assert run(ex.execute("book_appointment", {**base, "phone": PHONE, "time": "03:00"}))["code"] == "slot_not_found"
    assert run(ex.execute("book_appointment", {"doctor": "D01"}))["code"] == "invalid_arguments"
    assert run(ex.execute("book_appointment", {**base, "phone": PHONE}))["status"] == "booked"
    again = run(ex.execute("book_appointment", {**base, "phone": "9123456789"}))
    assert again["code"] == "slot_unavailable" and again["alternatives"]


def test_unknown_tool_does_not_crash(ex):
    assert run(ex.execute("drop_tables", {}))["code"] == "unknown_tool"


def test_cancel_three_step_flow(ex, clinic):
    booked = run(ex.execute("book_appointment", {"doctor": "D01", "date": "2026-11-24", "time": "09:00",
                                                  "phone": PHONE, "phone_confirmed": True}))
    apt = booked["appointment"]["appointment_id"]
    r = run(ex.execute("cancel_appointment", {"phone": PHONE, "phone_confirmed": False}))
    assert r["status"] == "needs_confirmation"
    r = run(ex.execute("cancel_appointment", {"phone": PHONE, "phone_confirmed": True}))
    assert r["status"] == "found" and r["appointments"][0]["appointment_id"] == apt
    assert clinic.get_appointment(apt)["status"] == "booked"      # lookup alone cancels nothing
    r = run(ex.execute("cancel_appointment", {"phone": PHONE, "phone_confirmed": True, "appointment_id": apt}))
    assert r["status"] == "cancelled" and clinic.get_appointment(apt)["status"] == "cancelled"


def test_cancel_with_wrong_number_never_reveals_or_cancels(ex, clinic):
    booked = run(ex.execute("book_appointment", {"doctor": "D01", "date": "2026-11-24", "time": "09:00",
                                                  "phone": PHONE, "phone_confirmed": True}))
    apt = booked["appointment"]["appointment_id"]
    r = run(ex.execute("cancel_appointment", {"phone": "9123456789", "phone_confirmed": True}))
    assert r["status"] == "no_match" and "Sharma" not in str(r) and apt not in str(r)
    r = run(ex.execute("cancel_appointment", {"phone": "9123456789", "phone_confirmed": True, "appointment_id": apt}))
    assert r["status"] == "no_match"
    assert clinic.get_appointment(apt)["status"] == "booked"


def test_events_never_contain_full_phone(ex, bus):
    run(ex.execute("book_appointment", {"doctor": "D01", "date": "2026-11-24", "time": "09:00",
                                         "phone": PHONE, "phone_confirmed": True}))
    dump = str(bus.history_since(0))
    assert "9876543210" not in dump and "98765 43210" not in dump
    assert any(e["type"] == "tool.finished" and e["payload"]["status"] == "booked" for e in bus.history_since(0))


def test_tool_timeout_is_reported(clinic, bus, monkeypatch):
    import time
    ex = ToolExecutor(clinic, bus, timeout=0.05)
    monkeypatch.setattr(clinic, "find_doctors", lambda **k: time.sleep(0.3) or [])
    r = run(ex.execute("check_doctor_availability", {"doctor": "x"}))
    assert r["status"] == "error" and r["code"] == "timeout"
