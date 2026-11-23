"""End-to-end conversations with the demo agent against the real database."""
import asyncio

import pytest

from app.voice.mock_agent import MockAgent
from app.voice.tools import ToolExecutor


@pytest.fixture()
def agent(clinic, bus):
    return MockAgent(ToolExecutor(clinic, bus, timeout=5), clinic, "Meridian Health Clinic", call_id="t1")


def talk(agent, *lines):
    async def go():
        return [await agent.respond(x) for x in lines]
    return asyncio.run(go())


def test_full_booking_conversation(agent, clinic):
    r = talk(agent,
             "Hi, I'd like to see a cardiologist",
             "tomorrow at 10:30 am",
             "my name is Asha and my number is nine eight seven six five four three two one zero",
             "yes that's right")
    assert "Dr. Anika Sharma" in r[0] and "Which day" in r[0]
    assert "10:30 AM" in r[1] and "phone number" in r[1]
    assert "9 8 7 6 5, 4 3 2 1 0" in r[2] and "Is that correct" in r[2]
    assert "APT-" in r[3] and "10:30 AM" in r[3]
    appts = clinic.list_appointments(status="booked")
    assert len(appts) == 1 and appts[0]["date"] == "2026-11-24" and appts[0]["start_time"] == "10:30"
    assert appts[0]["patient_name"] == "Asha"


def test_booking_does_not_happen_before_confirmation(agent, clinic):
    talk(agent, "book Dr Sharma tomorrow at 9 am", "9876543210")
    assert clinic.list_appointments() == []


def test_wrong_readback_asks_again_then_books_correct_number(agent, clinic):
    r = talk(agent, "book a skin doctor on thursday", "the first one", "9876543210", "no", "9123456789", "yes")
    assert "Is that correct" in r[2]
    assert "again" in r[3].lower()
    assert "9 1 2 3 4, 5 6 7 8 9" in r[4]
    appt = clinic.list_appointments(status="booked", reveal_phone=True)[0]
    assert appt["phone"] == "9123456789"


def test_invalid_phone_is_rejected_with_reason(agent, clinic):
    r = talk(agent, "book Dr Mehta tomorrow at 10 am", "12345")
    assert "5 digits" in r[1] and clinic.list_appointments() == []


def test_full_cancellation_conversation(agent, clinic):
    talk(agent, "book Dr Sharma tomorrow at 9 am", "9876543210", "yes")
    assert len(clinic.list_appointments(status="booked")) == 1
    r = talk(agent, "I need to cancel my appointment", "9876543210", "yes", "yes please")
    assert "phone number was the appointment booked" in r[0]
    assert "Is that correct" in r[1]
    assert "Dr. Anika Sharma" in r[2] and "cancel it" in r[2]
    assert "cancelled" in r[3]
    assert clinic.list_appointments(status="cancelled")[0]["doctor_name"] == "Dr. Anika Sharma"
    assert clinic.list_appointments(status="booked") == []


def test_cancel_with_unknown_number_changes_nothing(agent, clinic):
    talk(agent, "book Dr Sharma tomorrow at 9 am", "9876543210", "yes")
    r = talk(agent, "cancel my appointment", "9123456789", "yes")
    assert "couldn't find" in r[2] and "Sharma" not in r[2]
    assert len(clinic.list_appointments(status="booked")) == 1


def test_cancel_chooses_between_multiple_appointments(agent, clinic):
    talk(agent, "book Dr Sharma tomorrow at 9 am", "9876543210", "yes")
    talk(agent, "book Dr Mehta on wednesday at 10 am", "9876543210", "yes")
    r = talk(agent, "cancel please", "9876543210", "yes", "the second one", "yes")
    assert "2 appointments" in r[2]
    assert "Dr. Rohan Mehta" in r[3]
    left = clinic.list_appointments(status="booked")
    assert len(left) == 1 and left[0]["doctor_name"] == "Dr. Anika Sharma"


def test_declining_cancellation_keeps_booking(agent, clinic):
    talk(agent, "book Dr Sharma tomorrow at 9 am", "9876543210", "yes")
    talk(agent, "cancel", "9876543210", "yes", "no")
    assert len(clinic.list_appointments(status="booked")) == 1


def test_slot_taken_between_offer_and_confirmation(agent, clinic):
    talk(agent, "book Dr Sharma tomorrow at 9 am", "9876543210")           # waiting for yes
    clinic.book_appointment("D01", "2026-11-24", "09:00", "9000000099")      # someone else wins the slot
    r = talk(agent, "yes")
    assert "just taken" in r[0] and "next openings" in r[0]
    assert len(clinic.list_appointments(status="booked")) == 1


def test_availability_only_question(agent):
    r = talk(agent, "what slots does the pediatrician have on friday")
    assert "Dr. Sana Iqbal" in r[0] and "Fri, 27 Nov" in r[0]


def test_unknown_doctor_and_no_slots(agent):
    assert "No doctor matches" in talk(agent, "book Dr. Strange tomorrow")[0] or "Which doctor" in talk(agent, "x")[0]
    r = talk(agent, "availability for Dr Sharma on sunday")
    assert "No open slots" in r[0]


def test_emergency_is_redirected(agent):
    assert "emergency" in talk(agent, "I have chest pain")[0].lower()


def test_goodbye_hangs_up(agent):
    talk(agent, "bye")
    assert agent.wants_hangup
