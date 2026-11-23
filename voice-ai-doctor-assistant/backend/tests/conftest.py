"""Shared fixtures: a fresh seeded database and a frozen clock (Mon 23 Nov 2026, 10:00)."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.db.database import Database
from app.db.seed import seed
from app.services.clinic import ClinicService
from app.services.events import EventBus

NOW = datetime(2026, 11, 23, 10, 0)


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def db(tmp_path) -> Database:
    database = Database(str(tmp_path / "test.db"))
    database.init_schema()
    seed(database, days=14, demo_appointments=False, today=NOW)
    return database


@pytest.fixture()
def clinic(db, bus) -> ClinicService:
    return ClinicService(db, bus=bus, clock=lambda: NOW)


@pytest.fixture()
def first_slot(clinic):
    """First open slot of Dr. Sharma (D01) as (date, start_time)."""
    day = clinic.get_availability("D01", max_days=1)[0]
    return day["date"], day["slots"][0]["start_time"]
