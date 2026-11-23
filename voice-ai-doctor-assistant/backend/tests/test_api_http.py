"""Real HTTP tests through FastAPI's TestClient (route wiring, CORS, error bodies).

Skipped automatically when fastapi/httpx are not installed.  Run after:
    pip install -r requirements-dev.txt
"""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    settings = Settings(database_path=str(tmp_path / "http.db"), seed_demo_appointments=False, frontend_dist=str(tmp_path / "none"))
    with TestClient(create_app(settings)) as c:
        yield c


def _slot(client, doctor="D01"):
    day = client.get(f"/api/doctors/{doctor}/availability").json()["availability"][0]
    return day["date"], day["slots"][0]["start_time"]


def test_health_and_mode(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/config").json()["app_mode"] == "mock"


def test_book_then_cancel_over_http(client):
    date, start = _slot(client)
    body = {"doctor_id": "D01", "date": date, "start_time": start, "phone": "9876543210", "patient_name": "Asha"}
    r = client.post("/api/appointments", json=body)
    assert r.status_code == 201
    appt = r.json()["appointment"]
    # same slot again -> conflict, stable error body
    r2 = client.post("/api/appointments", json={**body, "phone": "9123456780"})
    assert r2.status_code == 409 and r2.json()["error"]["code"]
    # someone else's number cannot cancel it
    wrong = client.post(f"/api/appointments/{appt['id']}/cancel", json={"phone": "9123456780"})
    assert wrong.status_code == 404
    ok = client.post(f"/api/appointments/{appt['id']}/cancel", json={"phone": "9876543210"})
    assert ok.status_code == 200 and ok.json()["appointment"]["status"] == "cancelled"


def test_invalid_phone_and_validation_errors(client):
    date, start = _slot(client)
    r = client.post("/api/appointments", json={"doctor_id": "D01", "date": date, "start_time": start, "phone": "123", "patient_name": "X"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_phone"
    r = client.post("/api/appointments", json={"doctor_id": "D01"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_mock_call_flow(client):
    call = client.post("/api/calls").json()
    assert call["greeting"]
    reply = client.post(f"/api/calls/{call['id']}/say", json={"text": "I need a cardiologist"}).json()
    assert reply["reply"]
    assert client.post(f"/api/calls/{call['id']}/end").status_code == 200


def test_cors_allows_dev_origin(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
