"""API handlers + error mapping + SSE stream (no web server needed)."""
import asyncio
import json

import pytest

from app.api.errors import error_body
from app.api.handlers import ApiHandlers
from app.api.schemas import BookingRequest, CancelRequest, SayRequest
from app.config import Settings
from app.context import build_context
from app.services.errors import ApiError
from app.services.events import EventBus, sse_stream
from app.services.phone import InvalidPhoneError


@pytest.fixture()
def api(tmp_path):
    ctx = build_context(Settings(database_path=str(tmp_path / "api.db"), seed_demo_appointments=False))
    return ApiHandlers(ctx)


def first_slot(api, doctor="D01"):
    day = api.doctor_availability(doctor)["availability"][0]
    return day["date"], day["slots"][0]["start_time"]


def test_health_and_config(api):
    assert api.health()["status"] == "ok"
    cfg = api.config()
    assert cfg["app_mode"] == "mock" and "no LLM" in cfg["stack"]["llm"]


def test_doctors_list_filter_search(api):
    all_docs = api.list_doctors()
    assert len(all_docs["doctors"]) == 7 and "Cardiology" in all_docs["specialities"]
    assert [d["id"] for d in api.list_doctors(speciality="Dermatology")["doctors"]] == ["D03"]
    assert [d["id"] for d in api.list_doctors(q="mehta")["doctors"]] == ["D02"]
    assert all(d["availability"] for d in all_docs["doctors"][:1])


def test_rest_booking_and_cancel_roundtrip(api):
    date, start = first_slot(api)
    res = api.create_appointment(BookingRequest(doctor_id="D01", date=date, start_time=start, phone="98765 43210", patient_name="Asha"))
    appt = res["appointment"]
    assert appt["status"] == "booked" and "phone" not in appt
    listed = api.list_appointments(status="booked")["appointments"]
    assert [a["id"] for a in listed] == [appt["id"]]
    assert api.list_appointments(reveal_phone=True)["appointments"][0]["phone"] == "9876543210"
    assert api.lookup_appointments("9876543210")["count"] == 1
    assert api.lookup_appointments("9111111112")["count"] == 0
    with pytest.raises(Exception) as err:
        api.cancel_appointment(appt["id"], CancelRequest(phone="9111111112"))
    assert error_body(err.value) == (404, {"error": {"code": "appointment_not_found", "message": err.value.message}})
    done = api.cancel_appointment(appt["id"], CancelRequest(phone="+91 9876543210"))
    assert done["appointment"]["status"] == "cancelled"
    assert api.overview()["cancelled"] == 1


def test_error_bodies_are_consistent(api):
    date, start = first_slot(api)
    for exc_call, status, code in [
        (lambda: api.create_appointment(BookingRequest(doctor_id="D01", date=date, start_time=start, phone="12")), 422, "invalid_phone"),
        (lambda: api.create_appointment(BookingRequest(doctor_id="D99", date=date, start_time=start, phone="9876543210")), 404, "doctor_not_found"),
        (lambda: api.doctor_availability("D99"), 404, "doctor_not_found"),
        (lambda: api.list_appointments(status="nope"), 422, "invalid_input"),
    ]:
        with pytest.raises((InvalidPhoneError, Exception)) as err:
            exc_call()
        s, body = error_body(err.value)
        assert (s, body["error"]["code"]) == (status, code)
    api.create_appointment(BookingRequest(doctor_id="D01", date=date, start_time=start, phone="9876543210"))
    with pytest.raises(Exception) as err:
        api.create_appointment(BookingRequest(doctor_id="D01", date=date, start_time=start, phone="9123456789"))
    s, body = error_body(err.value)
    assert s == 409 and body["error"]["code"] == "slot_unavailable" and body["error"]["alternatives"]


def test_demo_call_lifecycle_and_events(api):
    async def go():
        call = await api.start_call()
        cid = call["call_id"]
        assert call["mode"] == "mock" and "virtual assistant" in call["greeting"]
        r1 = await api.say(cid, SayRequest(text="book Dr Sharma tomorrow at 9 am"))
        r2 = await api.say(cid, SayRequest(text="9876543210"))
        r3 = await api.say(cid, SayRequest(text="yes"))
        assert "APT-" in r3["reply"]
        api.end_call(cid)
        with pytest.raises(ApiError) as err:
            await api.say(cid, SayRequest(text="hello"))
        assert err.value.code == "call_ended"
        with pytest.raises(ApiError):
            await api.say(cid, SayRequest(text="   "))
    asyncio.run(go())
    types = [e["type"] for e in api.ctx.bus.history_since(0)]
    for needed in ("call.started", "transcript", "tool.started", "appointment.booked", "call.ended"):
        assert needed in types
    assert api.ctx.clinic.overview()["booked"] == 1


def test_live_mode_rejects_demo_calls_and_fails_fast_without_keys(tmp_path):
    from app.config import ConfigError
    with pytest.raises(ConfigError) as err:
        build_context(Settings(app_mode="live", database_path=str(tmp_path / "x.db")))
    assert "ELEVENLABS_API_KEY" in str(err.value) and "GOOGLE_API_KEY" in str(err.value)
    with pytest.raises(ConfigError):
        Settings(app_mode="banana").validate()


def test_sse_stream_replays_and_streams(api):
    bus: EventBus = api.ctx.bus
    bus.publish("hello", {"n": 1})

    async def go():
        stream = sse_stream(bus, since=None, keepalive=0.05)
        frames = [await stream.__anext__() for _ in range(2)]        # retry hint + replayed event
        bus.publish("live", {"n": 2})
        frames.append(await stream.__anext__())
        # next frame without new events is a keep-alive comment
        frames.append(await stream.__anext__())
        await stream.aclose()
        return frames
    frames = asyncio.run(go())
    assert frames[0].startswith("retry:")
    assert "event: hello" in frames[1]
    live = [f for f in frames if "event: live" in f][0]
    assert json.loads(live.split("data: ")[1])["payload"] == {"n": 2}
    assert frames[-1].startswith(": keep-alive")
    assert bus.subscriber_count == 0
