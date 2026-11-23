import threading

import pytest

from app.services.errors import (
    AlreadyCancelled, AppointmentNotFound, DoctorNotFound, InvalidInput, PastSlot,
    PatientConflict, SlotNotFound, SlotUnavailable,
)
from app.services.phone import InvalidPhoneError

PHONE = "98765 43210"


def test_seed_is_idempotent(db):
    from app.db.seed import seed
    from tests.conftest import NOW
    with db.connect() as c:
        before = (c.execute("SELECT COUNT(*) FROM slots").fetchone()[0], c.execute("SELECT COUNT(*) FROM doctors").fetchone()[0])
    seed(db, days=14, demo_appointments=False, today=NOW)
    seed(db, days=14, demo_appointments=False, today=NOW)
    with db.connect() as c:
        after = (c.execute("SELECT COUNT(*) FROM slots").fetchone()[0], c.execute("SELECT COUNT(*) FROM doctors").fetchone()[0])
    assert before == after and before[1] == 7 and before[0] > 100


def test_demo_seed_creates_appointments_once(tmp_path):
    from app.db.database import Database
    from app.db.seed import seed
    from tests.conftest import NOW
    d = Database(str(tmp_path / "demo.db")); d.init_schema()
    seed(d, demo_appointments=True, today=NOW)
    seed(d, demo_appointments=True, today=NOW)
    with d.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == 3


def test_find_doctors_by_name_id_and_speciality(clinic):
    assert [d["id"] for d in clinic.find_doctors(doctor="Dr. Sharma")] == ["D01"]
    assert [d["id"] for d in clinic.find_doctors(doctor="d02")] == ["D02"]
    assert [d["id"] for d in clinic.find_doctors(speciality="heart doctor")] == ["D01"]
    assert [d["id"] for d in clinic.find_doctors(speciality="skin")] == ["D03"]
    assert clinic.find_doctors(doctor="Dr. Nobody") == []
    assert len(clinic.find_doctors()) == 7


def test_availability_only_open_future_slots(clinic):
    days = clinic.get_availability("D01", max_days=3)
    assert 1 <= len(days) <= 3
    for day in days:
        assert day["date"] >= "2026-11-23"
        assert all(s["start_time"] > "10:00" for s in day["slots"] if day["date"] == "2026-11-23")


def test_availability_hides_booked_and_shows_again_after_cancel(clinic, first_slot):
    date, start = first_slot
    appt = clinic.book_appointment("D01", date, start, PHONE)
    times = [s["start_time"] for d in clinic.get_availability("D01", on_date=date) for s in d["slots"]]
    assert start not in times
    clinic.cancel_appointment(appt["id"], PHONE)
    times = [s["start_time"] for d in clinic.get_availability("D01", on_date=date) for s in d["slots"]]
    assert start in times


def test_no_slots_on_non_working_day(clinic):
    # Sunday 29 Nov 2026: Dr. Sharma does not work weekends
    assert clinic.get_availability("D01", on_date="2026-11-29") == []


def test_book_success_returns_details_and_masks_phone(clinic, first_slot):
    date, start = first_slot
    appt = clinic.book_appointment("D01", date, start, PHONE, "Asha")
    assert appt["id"].startswith("APT-") and appt["status"] == "booked"
    assert appt["doctor_name"] == "Dr. Anika Sharma" and appt["patient_name"] == "Asha"
    assert "phone" not in appt and appt["phone_masked"].endswith("210")
    assert clinic.get_appointment(appt["id"], reveal_phone=True)["phone"] == "9876543210"


def test_book_accepts_spoken_date_and_time_formats(clinic):
    appt = clinic.book_appointment("D01", "tomorrow", "10 am", "+91 98765 43210")
    assert appt["date"] == "2026-11-24" and appt["start_time"] == "10:00"


def test_double_booking_same_slot_rejected(clinic, first_slot):
    date, start = first_slot
    clinic.book_appointment("D01", date, start, PHONE)
    with pytest.raises(SlotUnavailable) as err:
        clinic.book_appointment("D01", date, start, "9123456789")
    assert err.value.details["alternatives"], "should suggest other slots"


def test_same_patient_cannot_hold_two_doctors_at_same_time(clinic):
    day = clinic.get_availability("D02", max_days=1)[0]
    s = day["slots"][0]["start_time"]
    clinic.book_appointment("D02", day["date"], s, PHONE)
    # find another doctor who has the same date+time open
    for doc in ("D05", "D06", "D01", "D04"):
        for d in clinic.get_availability(doc, on_date=day["date"]):
            if any(x["start_time"] == s for x in d["slots"]):
                with pytest.raises(PatientConflict):
                    clinic.book_appointment(doc, day["date"], s, "+91" + PHONE)
                return


def test_book_validation_errors(clinic, first_slot):
    date, start = first_slot
    with pytest.raises(InvalidPhoneError):
        clinic.book_appointment("D01", date, start, "12345")
    with pytest.raises(DoctorNotFound):
        clinic.book_appointment("D99", date, start, PHONE)
    with pytest.raises(SlotNotFound):
        clinic.book_appointment("D01", date, "03:15", PHONE)
    with pytest.raises(PastSlot):
        clinic.book_appointment("D02", "2026-11-23", "09:00", PHONE)
    with pytest.raises(InvalidInput):
        clinic.book_appointment("D01", "someday", start, PHONE)
    with pytest.raises(InvalidInput):
        clinic.book_appointment("D01", date, "teatime", PHONE)


def test_concurrent_bookings_only_one_wins(clinic, first_slot):
    date, start = first_slot
    results: list[str] = []
    def worker(i):
        try:
            clinic.book_appointment("D01", date, start, f"90000000{i:02d}")
            results.append("ok")
        except SlotUnavailable:
            results.append("taken")
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert results.count("ok") == 1 and results.count("taken") == 11
    with clinic.db.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM appointments WHERE status='booked' AND slot_id IN "
                         "(SELECT id FROM slots WHERE doctor_id='D01' AND date=? AND start_time=?)", (date, start)).fetchone()[0] == 1


def test_cancel_with_matching_number(clinic, first_slot):
    date, start = first_slot
    appt = clinic.book_appointment("D01", date, start, PHONE)
    done = clinic.cancel_appointment(appt["id"], "+91 98765 43210")   # same subscriber, other format
    assert done["status"] == "cancelled"
    with pytest.raises(AlreadyCancelled):
        clinic.cancel_appointment(appt["id"], PHONE)


def test_cancel_with_wrong_number_is_refused_and_leaves_booking(clinic, first_slot):
    date, start = first_slot
    appt = clinic.book_appointment("D01", date, start, PHONE)
    with pytest.raises(AppointmentNotFound):
        clinic.cancel_appointment(appt["id"], "9123456789")
    assert clinic.get_appointment(appt["id"])["status"] == "booked"
    # unknown ids give the identical error (no information leak)
    with pytest.raises(AppointmentNotFound) as e1:
        clinic.cancel_appointment("APT-000000", PHONE)
    with pytest.raises(AppointmentNotFound) as e2:
        clinic.cancel_appointment(appt["id"], "9123456789")
    assert e1.value.message == e2.value.message


def test_multiple_appointments_for_one_number(clinic):
    a = clinic.get_availability("D01", max_days=2)
    b = clinic.get_availability("D02", max_days=1)
    first = clinic.book_appointment("D01", a[0]["date"], a[0]["slots"][0]["start_time"], PHONE)
    second = clinic.book_appointment("D02", b[0]["date"], b[0]["slots"][-1]["start_time"], PHONE)
    other = clinic.book_appointment("D05", clinic.get_availability("D05", max_days=1)[0]["date"],
                                    clinic.get_availability("D05", max_days=1)[0]["slots"][0]["start_time"], "9123456789")
    mine = clinic.find_active_appointments(PHONE)
    assert {x["id"] for x in mine} == {first["id"], second["id"]}
    assert other["id"] not in {x["id"] for x in mine}
    clinic.cancel_appointment(first["id"], PHONE)
    assert [x["id"] for x in clinic.find_active_appointments(PHONE)] == [second["id"]]
    assert clinic.find_active_appointments("9111111112") == []


def test_events_emitted_for_booking_and_cancel(clinic, bus, first_slot):
    date, start = first_slot
    appt = clinic.book_appointment("D01", date, start, PHONE)
    clinic.cancel_appointment(appt["id"], PHONE)
    types = [e["type"] for e in bus.history_since(0)]
    assert types == ["appointment.booked", "slots.changed", "appointment.cancelled", "slots.changed"]
    assert all("phone" not in e["payload"].get("appointment", {}) for e in bus.history_since(0))


def test_list_and_overview(clinic, first_slot):
    date, start = first_slot
    appt = clinic.book_appointment("D01", date, start, PHONE, "Asha")
    assert [a["id"] for a in clinic.list_appointments(status="booked")] == [appt["id"]]
    assert clinic.list_appointments(search="asha")[0]["id"] == appt["id"]
    assert clinic.list_appointments(status="cancelled") == []
    with pytest.raises(InvalidInput):
        clinic.list_appointments(status="weird")
    ov = clinic.overview()
    assert ov["booked"] == 1 and ov["doctors"] == 7 and ov["next_appointment"]["id"] == appt["id"]
