"""SQLite access layer.

All SQL lives in ``app/db`` and ``app/services``.  The rest of the app talks to
``Database`` only through ``connect()`` / ``transaction()``, so swapping SQLite
for Postgres later means replacing this module and the SQL in the services.

Double-booking protection has two layers:

1. ``BEGIN IMMEDIATE`` takes SQLite's write lock before we read the slot, so two
   concurrent bookings are serialised.
2. A partial unique index (``uq_active_appointment_slot``) makes it impossible to
   store two *booked* appointments for the same slot even if the code is wrong.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    speciality       TEXT NOT NULL,
    qualifications   TEXT,
    experience_years INTEGER,
    consultation_fee INTEGER NOT NULL DEFAULT 0,
    active           INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS slots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id  TEXT NOT NULL REFERENCES doctors(id),
    date       TEXT NOT NULL,              -- YYYY-MM-DD
    start_time TEXT NOT NULL,              -- HH:MM (24h)
    end_time   TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'available'
               CHECK (status IN ('available', 'booked', 'blocked')),
    UNIQUE (doctor_id, date, start_time)
);
CREATE INDEX IF NOT EXISTS idx_slots_lookup ON slots (doctor_id, date, status);

CREATE TABLE IF NOT EXISTS appointments (
    id           TEXT PRIMARY KEY,         -- APT-123456
    doctor_id    TEXT NOT NULL REFERENCES doctors(id),
    slot_id      INTEGER NOT NULL REFERENCES slots(id),
    phone        TEXT NOT NULL,            -- canonical, e.g. +919876543210
    patient_name TEXT,
    date         TEXT NOT NULL,
    start_time   TEXT NOT NULL,
    end_time     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'booked'
                 CHECK (status IN ('booked', 'cancelled')),
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_appointments_phone ON appointments (phone, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_appointment_slot
    ON appointments (slot_id) WHERE status = 'booked';
"""


class Database:
    """Thin wrapper that opens a short-lived connection per unit of work."""

    def __init__(self, path: str) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Read-only style connection (autocommit)."""
        conn = self._open()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Write transaction holding SQLite's write lock from the first statement."""
        conn = self._open()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            if self.path != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
