"""Date / time parsing and labels shared by the tools, the API and the mock agent."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4,
    "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8,
    "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def parse_date(value: str, today: date) -> date:
    """Parse ISO dates and common spoken forms.

    Supports ``2026-11-25``, ``today``, ``tomorrow``, ``day after tomorrow``,
    ``monday`` / ``next monday``, ``25 november``, ``november 25th``, ``25/11``.
    Raises ``ValueError`` when nothing matches.
    """
    text = (value or "").strip().lower()
    if not text:
        raise ValueError("empty date")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return date.fromisoformat(text)
    if text in {"today", "tonight"}:
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if "day after tomorrow" in text:
        return today + timedelta(days=2)
    for idx, name in enumerate(_WEEKDAYS):
        if re.search(rf"\b{name}\b|\b{name[:3]}\b", text):
            delta = (idx - today.weekday()) % 7
            if delta == 0 and "next" in text:
                delta = 7
            return today + timedelta(days=delta)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?([a-z]{3,9})\b", text)
    if m and m.group(2) in _MONTHS:
        return _resolve_year(_MONTHS[m.group(2)], int(m.group(1)), today)
    m = re.search(r"\b([a-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\b", text)
    if m and m.group(1) in _MONTHS:
        return _resolve_year(_MONTHS[m.group(1)], int(m.group(2)), today)
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})", text)
    if m:
        return _resolve_year(int(m.group(2)), int(m.group(1)), today)
    raise ValueError(f"could not understand the date {value!r}")


def _resolve_year(month: int, day: int, today: date) -> date:
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate >= today:
            return candidate
    raise ValueError("invalid calendar date")


def parse_time(value: str) -> str:
    """Return ``HH:MM`` (24h) from ``10:30``, ``10.30``, ``10 am``, ``2:15 pm``, ``noon``."""
    text = (value or "").strip().lower().replace(".", ":")
    if not text:
        raise ValueError("empty time")
    if text == "noon":
        return "12:00"
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m?\.?", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if not 1 <= hour <= 12 or minute > 59:
            raise ValueError(f"invalid time {value!r}")
        if m.group(3) == "p" and hour != 12:
            hour += 12
        if m.group(3) == "a" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if hour > 23 or minute > 59:
            raise ValueError(f"invalid time {value!r}")
        return f"{hour:02d}:{minute:02d}"
    raise ValueError(f"could not understand the time {value!r}")


def time_label(hhmm: str) -> str:
    """``14:30`` -> ``2:30 PM``."""
    hour, minute = (int(x) for x in hhmm.split(":"))
    suffix = "AM" if hour < 12 else "PM"
    return f"{(hour % 12) or 12}:{minute:02d} {suffix}"


def date_label(iso: str) -> str:
    """``2026-11-25`` -> ``Wed, 25 Nov``."""
    d = date.fromisoformat(iso)
    return f"{d.strftime('%a')}, {d.day} {d.strftime('%b')}"


def slot_datetime(iso_date: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{iso_date}T{hhmm}:00")
