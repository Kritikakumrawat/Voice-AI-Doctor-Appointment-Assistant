"""Rule-based DEMO agent used when ``APP_MODE=mock``.

It is NOT an LLM and NOT a live voice call.  It exists so the whole product can be
demonstrated without API keys.  It still does real work: every availability check,
booking and cancellation goes through the same ``ToolExecutor`` and SQLite database
that the live Gemini agent uses, including the phone read-back confirmation step.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.clinic import ClinicService, resolve_speciality
from app.services.phone import InvalidPhoneError, normalize_phone, spoken_to_digits
from app.services.timeutil import date_label, parse_date, parse_time, time_label
from app.voice.prompts import greeting
from app.voice.tools import ToolExecutor

_MONTHS = "jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december"
_WEEKDAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"
_YES = re.compile(r"\b(yes|yeah|yep|yup|correct|right|sure|ok|okay|confirm|confirmed|please do|go ahead|that's right|that is right|exactly)\b", re.I)
_NO = re.compile(r"\b(no|nope|nah|wrong|incorrect|not right|not correct|don't|do not)\b", re.I)
_EMERGENCY = re.compile(
    r"chest pain|can'?t breathe|cannot breathe|trouble breathing|heart attack|stroke|unconscious|"
    r"bleeding (heavily|badly)|overdose|suicid|emergency|not breathing", re.I)
_GOODBYE = re.compile(r"\b(bye|goodbye|that'?s all|that is all|nothing else|no thanks|no thank you|hang up)\b", re.I)
_CANCEL = re.compile(r"\b(cancel|cancellation|call off|remove my appointment)\b", re.I)
_NEVERMIND = re.compile(r"\b(never ?mind|forget it|stop|start over|go back)\b", re.I)
_ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3, "last": -1}
_ANY = re.compile(r"\b(any|earliest|soonest|whenever|first available|next available)\b", re.I)


def _find_date(text: str, today) -> str | None:
    low = text.lower()
    candidates = [
        r"day after tomorrow", r"\btomorrow\b", r"\b(today|tonight)\b",
        rf"\b(next\s+)?({_WEEKDAYS})\b", r"\b\d{4}-\d{2}-\d{2}\b",
        rf"\b\d{{1,2}}(st|nd|rd|th)?\s+(of\s+)?({_MONTHS})\b", rf"\b({_MONTHS})\s+\d{{1,2}}(st|nd|rd|th)?\b",
    ]
    for pattern in candidates:
        m = re.search(pattern, low)
        if m:
            try:
                return parse_date(m.group(0), today).isoformat()
            except ValueError:
                continue
    return None


def _find_time(text: str) -> tuple[int, int, str | None] | None:
    """Return (hour, minute, 'am'|'pm'|None) from free text."""
    low = text.lower().replace(".", ":") if re.search(r"\d\.\d", text) else text.lower()
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)", low)
    if m:
        return int(m.group(1)), int(m.group(2) or 0), "am" if m.group(3).startswith("a") else "pm"
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", low)
    if m:
        return int(m.group(1)), int(m.group(2)), None
    m = re.search(r"\b(?:at|around|for)\s+(\d{1,2})\b(?!\s*(?:st|nd|rd|th|-))", low)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1)), 0, None
    return None


@dataclass
class _State:
    stage: str = "idle"        # idle | await_phone | await_phone_confirm | await_cancel_choice | await_cancel_confirm
    intent: str | None = None  # book | cancel
    doctor_text: str | None = None
    speciality: str | None = None
    date: str | None = None
    offered: list[dict[str, Any]] = field(default_factory=list)
    chosen: dict[str, Any] | None = None
    phone: str | None = None
    patient_name: str | None = None
    found: list[dict[str, Any]] = field(default_factory=list)
    cancel_target: dict[str, Any] | None = None
    done: bool = False


class MockAgent:
    label = "Demo agent (rule-based, not an LLM)"

    def __init__(self, executor: ToolExecutor, clinic: ClinicService, clinic_name: str, call_id: str | None = None) -> None:
        self.ex, self.clinic, self.clinic_name, self.call_id = executor, clinic, clinic_name, call_id
        self.s = _State()

    # ------------------------------------------------------------------ public
    def greet(self) -> str:
        return greeting(self.clinic_name)

    @property
    def wants_hangup(self) -> bool:
        return self.s.done

    async def respond(self, text: str) -> str:
        t = (text or "").strip()
        if not t:
            return "Sorry, I didn't catch that. Could you say it again?"
        if _EMERGENCY.search(t):
            return ("That sounds like an emergency. Please call your local emergency number or go to the nearest "
                    "emergency room right now. I can't help with emergencies on this line.")
        if _NEVERMIND.search(t) and self.s.stage != "idle":
            self.s = _State()
            return "No problem, I've cleared that. How else can I help?"
        stage = self.s.stage
        if stage == "await_phone":
            return await self._on_phone(t)
        if stage == "await_phone_confirm":
            return await self._on_phone_confirm(t)
        if stage == "await_cancel_choice":
            return await self._on_cancel_choice(t)
        if stage == "await_cancel_confirm":
            return await self._on_cancel_confirm(t)
        if _GOODBYE.search(t) and not self.s.offered:
            self.s.done = True
            return "Thank you for calling. Take care, goodbye!"
        if _CANCEL.search(t):
            self.s = _State(intent="cancel", stage="await_phone")
            return "Sure, I can help with that. What phone number was the appointment booked with?"
        return await self._on_booking_message(t)

    # ---------------------------------------------------------------- booking
    async def _on_booking_message(self, t: str) -> str:
        s = self.s
        s.intent = "book"
        doc = self._find_doctor(t)
        spec = resolve_speciality(t) if not doc else None
        new_date = _find_date(t, self.clinic.today())
        tm = _find_time(t)
        low = t.lower()
        ordinal = next((v for k, v in _ORDINALS.items() if re.search(rf"\b{k}\b", low)), None)
        any_slot = bool(_ANY.search(t))

        # 1) is the caller choosing one of the slots we already offered?
        if s.offered and (tm or ordinal is not None or any_slot):
            result = await self._try_select(doc, new_date, tm, ordinal, any_slot)
            if result is not None:
                return result

        # 2) otherwise it is a (new) search
        if doc:
            s.doctor_text, s.speciality = doc["id"], None
        elif spec:
            s.speciality, s.doctor_text = spec, None
        if new_date:
            s.date = new_date
        if not s.doctor_text and not s.speciality:
            if _GOODBYE.search(t):
                s.done = True
                return "Thank you for calling. Take care, goodbye!"
            return "Happy to help. Which doctor or speciality would you like to see?"
        reply = await self._search()
        if s.offered and (tm or ordinal is not None):
            picked = await self._try_select(None, None, tm, ordinal, False)
            if picked is not None:
                return picked
        return reply

    async def _search(self) -> str:
        s = self.s
        res = await self.ex.execute(
            "check_doctor_availability",
            {"doctor": s.doctor_text, "speciality": s.speciality, "date": s.date}, self.call_id)
        s.offered = []
        if res["status"] == "no_doctor":
            return f"{res['message']} We have: {res['doctors_we_have']}. Who would you like to see?"
        if res["status"] == "error":
            return f"Sorry, I couldn't check that. {res['message']}"
        if res["status"] == "no_slots":
            s.date = None
            return res["message"].replace(" Offer another day or doctor.", "") + " Would another day or doctor work?"
        lines = []
        for d in res["doctors"]:
            parts = []
            for day in d["availability"]:
                shown = day["slots"][:4]
                for sl in day["slots"]:
                    s.offered.append({"doctor_id": d["doctor_id"], "doctor": d["name"], "date": day["date"],
                                      "date_label": day["label"], "time": sl["time"], "label": sl["spoken"]})
                more = len(day["slots"]) - len(shown) + day["more_slots"]
                parts.append(f"{day['label']}: " + ", ".join(x["spoken"] for x in shown) + (f" and {more} more" if more else ""))
            if parts:
                lines.append(f"{d['name']} ({d['speciality']}, ₹{d['consultation_fee_inr']}) has " + "; ".join(parts) + ".")
        if not lines:
            return "I couldn't find open slots for that. Would another day or doctor work?"
        return " ".join(lines) + " Which day and time suits you?"

    async def _try_select(self, doc, new_date, tm, ordinal, any_slot) -> str | None:
        s = self.s
        cands = list(s.offered)
        if doc:
            cands = [c for c in cands if c["doctor_id"] == doc["id"]]
        if new_date:
            cands = [c for c in cands if c["date"] == new_date]
        if tm:
            hour, minute, ampm = tm
            def matches(c):
                h, m = (int(x) for x in c["time"].split(":"))
                if m != minute:
                    return False
                if ampm:
                    return h == (hour % 12) + (12 if ampm == "pm" else 0)
                return h == hour or h % 12 == hour % 12
            hits = [c for c in cands if matches(c)]
            if not hits:
                hits = self._lookup_exact(doc, new_date, tm)
            cands = hits
        if ordinal is not None and cands:
            cands = [cands[ordinal]]
        elif any_slot and cands and not tm:
            cands = [cands[0]]
        if not cands:
            return None
        if len({(c["doctor_id"], c["date"], c["time"]) for c in cands}) > 1:
            docs = sorted({c["doctor"] for c in cands})
            dates = sorted({c["date_label"] for c in cands})
            if len(docs) > 1:
                s.offered = cands
                return f"More than one doctor has that time: {' and '.join(docs)}. Which doctor would you like?"
            if len(dates) > 1:
                s.offered = cands
                return f"That time is free on {' and '.join(dates)}. Which day would you like?"
            return None
        s.chosen = cands[0]
        s.intent, s.stage = "book", "await_phone"
        return (f"Great, {s.chosen['doctor']} on {s.chosen['date_label']} at {s.chosen['label']}. "
                "What's your phone number? I'll use it to identify your booking.")

    def _lookup_exact(self, doc, new_date, tm) -> list[dict[str, Any]]:
        """Time was not in the short list we read out: check the database directly."""
        s = self.s
        doctor_ids = [doc["id"]] if doc else sorted({c["doctor_id"] for c in s.offered})
        out = []
        for did in doctor_ids:
            name = next((c["doctor"] for c in s.offered if c["doctor_id"] == did), did)
            for day in self.clinic.get_availability(did, on_date=new_date or s.date, max_days=3, per_day=100):
                for sl in day["slots"]:
                    h, m = (int(x) for x in sl["start_time"].split(":"))
                    hour, minute, ampm = tm
                    ok = m == minute and ((h == (hour % 12) + (12 if ampm == "pm" else 0)) if ampm else (h % 12 == hour % 12))
                    if ok:
                        out.append({"doctor_id": did, "doctor": name, "date": day["date"], "date_label": day["date_label"],
                                    "time": sl["start_time"], "label": sl["label"]})
        return out

    def _find_doctor(self, t: str) -> dict[str, Any] | None:
        low = t.lower()
        for d in self.clinic.list_doctors():
            tokens = [x for x in re.findall(r"[a-z]+", d["name"].lower()) if x != "dr"]
            if any(re.search(rf"\b{tok}\b", low) for tok in tokens):
                return d
        return None

    # ------------------------------------------------------------------ phone
    async def _on_phone(self, t: str) -> str:
        s = self.s
        m = re.search(r"(?:my name is|name'?s|this is|call me)\s+([A-Za-z]+)", t, re.I)
        if m:
            s.patient_name = m.group(1).capitalize()
        if not spoken_to_digits(re.sub(r"(?:my name is|name'?s|this is|call me)\s+[A-Za-z]+", "", t, flags=re.I)):
            if s.patient_name and m:
                return f"Thanks {s.patient_name}. And your phone number?"
            return "I need your phone number to continue. Please say the digits one by one."
        try:
            s.phone = normalize_phone(re.sub(r"(?:my name is|name'?s|this is|call me)\s+[A-Za-z]+", "", t, flags=re.I)).canonical
        except InvalidPhoneError as exc:
            return f"{exc} Could you say the full number again?"
        return await self._read_back()

    async def _read_back(self) -> str:
        s = self.s
        if s.intent == "cancel":
            res = await self.ex.execute("cancel_appointment", {"phone": s.phone, "phone_confirmed": False}, self.call_id)
        else:
            c = s.chosen
            res = await self.ex.execute("book_appointment", {
                "doctor": c["doctor_id"], "date": c["date"], "time": c["time"], "phone": s.phone,
                "phone_confirmed": False}, self.call_id)
        if res["status"] != "needs_confirmation":
            s.stage, s.phone = "await_phone", None
            return f"{res.get('message', 'Something went wrong.')} Please say your number again."
        s.stage = "await_phone_confirm"
        return f"I heard {res['read_back']}. Is that correct?"

    async def _on_phone_confirm(self, t: str) -> str:
        s = self.s
        has_digits = len(spoken_to_digits(t).lstrip("+")) >= 7
        if has_digits:
            s.stage = "await_phone"
            return await self._on_phone(t)
        if _NO.search(t) and not _YES.search(t):
            s.stage, s.phone = "await_phone", None
            return "Sorry about that. Please say your phone number again, slowly."
        if not _YES.search(t):
            return "Sorry, was that number correct? Please say yes or no."
        if s.intent == "cancel":
            return await self._cancel_lookup()
        return await self._book()

    async def _book(self) -> str:
        s, c = self.s, self.s.chosen
        res = await self.ex.execute("book_appointment", {
            "doctor": c["doctor_id"], "date": c["date"], "time": c["time"], "phone": s.phone,
            "phone_confirmed": True, "patient_name": s.patient_name}, self.call_id)
        if res["status"] == "booked":
            a = res["appointment"]
            ident = a["appointment_id"]
            self.s = _State()
            who = f", {a['patient_name']}" if a["patient_name"] else ""
            return (f"You're all set{who}! {a['doctor']} on {a['date_label']} at {a['time_label']}. "
                    f"Your appointment ID is {ident}, and the fee is ₹{a['fee_inr']}. Anything else I can help with?")
        s.stage = "idle"
        if res.get("code") == "slot_unavailable":
            alts = res.get("alternatives", [])
            s.offered = [{"doctor_id": c["doctor_id"], "doctor": c["doctor"], "date": x["date"], "date_label": x["date_label"],
                          "time": x["start_time"], "label": x["label"]} for x in alts]
            tail = (" The next openings are " + ", ".join(f"{x['date_label']} at {x['label']}" for x in alts) + ". Would one of those work?") if alts else ""
            return f"Sorry, that slot was just taken.{tail}"
        return f"Sorry, I couldn't book that. {res.get('message', '')}"

    # ----------------------------------------------------------------- cancel
    async def _cancel_lookup(self) -> str:
        s = self.s
        res = await self.ex.execute("cancel_appointment", {"phone": s.phone, "phone_confirmed": True}, self.call_id)
        if res["status"] == "no_match":
            self.s = _State()
            return "I couldn't find any upcoming appointment booked with that number, so nothing was cancelled. Is there anything else?"
        if res["status"] != "found":
            self.s = _State()
            return f"Sorry, I couldn't look that up. {res.get('message', '')}"
        s.found = res["appointments"]
        if len(s.found) == 1:
            s.cancel_target, s.stage = s.found[0], "await_cancel_confirm"
            a = s.cancel_target
            return f"I found {a['doctor']} on {a['date_label']} at {a['time_label']}. Shall I cancel it?"
        s.stage = "await_cancel_choice"
        listing = "; ".join(f"{i + 1}. {a['doctor']} on {a['date_label']} at {a['time_label']}" for i, a in enumerate(s.found))
        return f"I found {len(s.found)} appointments: {listing}. Which one would you like to cancel?"

    async def _on_cancel_choice(self, t: str) -> str:
        s, low = self.s, t.lower()
        pick = None
        ordinal = next((v for k, v in _ORDINALS.items() if re.search(rf"\b{k}\b", low)), None)
        num = re.search(r"\b([1-9])\b", low)
        if ordinal is not None:
            pick = s.found[ordinal]
        elif num and int(num.group(1)) <= len(s.found):
            pick = s.found[int(num.group(1)) - 1]
        else:
            doc, d = self._find_doctor(t), _find_date(t, self.clinic.today())
            hits = [a for a in s.found if (not doc or a["doctor"] == doc["name"]) and (not d or a["date"] == d)]
            if (doc or d) and len(hits) == 1:
                pick = hits[0]
        if not pick:
            return "Sorry, which one? You can say first or second, or name the doctor or the day."
        s.cancel_target, s.stage = pick, "await_cancel_confirm"
        return f"Cancel {pick['doctor']} on {pick['date_label']} at {pick['time_label']}? Please say yes or no."

    async def _on_cancel_confirm(self, t: str) -> str:
        s = self.s
        if _NO.search(t) and not _YES.search(t):
            self.s = _State()
            return "Okay, I've left your appointment as it is. Anything else?"
        if not _YES.search(t):
            return "Please say yes to cancel, or no to keep the appointment."
        res = await self.ex.execute("cancel_appointment", {
            "phone": s.phone, "phone_confirmed": True, "appointment_id": s.cancel_target["appointment_id"]}, self.call_id)
        self.s = _State()
        if res["status"] == "cancelled":
            a = res["appointment"]
            return f"Done. Your appointment with {a['doctor']} on {a['date_label']} at {a['time_label']} is cancelled. Anything else?"
        return f"Sorry, I couldn't cancel that. {res.get('message', '')}"
