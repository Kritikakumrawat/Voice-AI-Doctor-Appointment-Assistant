"""Wires settings, database, services and agents into one object the API uses."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.db.database import Database
from app.db.seed import seed
from app.services.calls import CallManager
from app.services.clinic import ClinicService
from app.services.events import EventBus
from app.voice.mock_agent import MockAgent
from app.voice.tools import ToolExecutor

log = logging.getLogger("app")


@dataclass
class AppContext:
    settings: Settings
    db: Database
    bus: EventBus
    clinic: ClinicService
    executor: ToolExecutor
    calls: CallManager
    live: Any = None   # set by app.voice.live_routes in live mode


def build_context(settings: Settings, do_seed: bool = True) -> AppContext:
    settings.validate()
    db = Database(settings.database_path)
    db.init_schema()
    if do_seed:
        seed(db, days=settings.seed_days, demo_appointments=settings.seed_demo_appointments)
    bus = EventBus()
    clinic = ClinicService(db, bus=bus)
    executor = ToolExecutor(clinic, bus, timeout=settings.tool_timeout_secs)
    factory = None
    if not settings.is_live:
        factory = lambda call_id: MockAgent(executor, clinic, settings.clinic_name, call_id)  # noqa: E731
    calls = CallManager(bus, factory)
    log.info("Context ready (mode=%s, db=%s)", settings.app_mode, settings.database_path)
    return AppContext(settings, db, bus, clinic, executor, calls)
