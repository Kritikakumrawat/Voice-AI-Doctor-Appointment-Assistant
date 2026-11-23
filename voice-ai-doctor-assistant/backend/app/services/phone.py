"""Phone number handling.

The caller is identified *only* by the number they say out loud, so this module
is deliberately careful:

* ``spoken_to_digits`` understands "nine eight double seven ..." as well as
  "98 77 ...", because speech-to-text returns either.
* ``normalize_phone`` accepts 10-15 digits and keeps an explicit ``+`` country code.
* ``phones_match`` decides whether two stored/spoken numbers are the same person.
* ``read_back`` produces the digit-by-digit text the agent reads to the caller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MIN_DIGITS = 10
MAX_DIGITS = 15

_DIGIT_WORDS = {
    "zero": "0", "oh": "0", "o": "0",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9",
}
_DIGIT_NAMES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_MULTIPLIERS = {"double": 2, "triple": 3}
_TOKEN = re.compile(r"\+|\d|[a-zA-Z]+")


class InvalidPhoneError(ValueError):
    """The spoken number cannot be a valid phone number."""

    code = "invalid_phone"


@dataclass(frozen=True)
class PhoneNumber:
    canonical: str      # "+919876543210" or "9876543210"
    digits: str         # digits only
    has_plus: bool

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.canonical


def spoken_to_digits(text: str) -> str:
    """Convert free text such as ``"plus nine one 98765 double four 3210"`` to digits.

    Everything that is not a digit, a digit word, ``+`` or ``plus`` is ignored.
    A leading ``+`` (or the word "plus") is preserved.
    """
    out: list[str] = []
    multiplier = 1
    plus = False
    for token in _TOKEN.findall(text or ""):
        low = token.lower()
        if token == "+" or low == "plus":
            if not out:
                plus = True
            continue
        if low in _MULTIPLIERS:
            multiplier = _MULTIPLIERS[low]
            continue
        if token.isdigit():
            out.append(token * multiplier)
            multiplier = 1
        elif low in _DIGIT_WORDS:
            out.append(_DIGIT_WORDS[low] * multiplier)
            multiplier = 1
        else:
            multiplier = 1
    digits = "".join(out)
    return ("+" if plus and digits else "") + digits


def normalize_phone(raw: str) -> PhoneNumber:
    """Validate and normalise a phone number.

    Raises ``InvalidPhoneError`` with a caller-friendly message.
    """
    if raw is None or not str(raw).strip():
        raise InvalidPhoneError("I didn't catch a phone number. Could you say it again?")
    cleaned = spoken_to_digits(str(raw))
    has_plus = cleaned.startswith("+")
    digits = cleaned.lstrip("+")
    if len(digits) < MIN_DIGITS:
        raise InvalidPhoneError(
            f"That number has only {len(digits)} digits. A phone number needs at least {MIN_DIGITS}."
        )
    if len(digits) > MAX_DIGITS:
        raise InvalidPhoneError(
            f"That number has {len(digits)} digits, which is too many. The maximum is {MAX_DIGITS}."
        )
    if len(set(digits)) == 1:
        raise InvalidPhoneError("That doesn't look like a real phone number. Could you repeat it?")
    return PhoneNumber(canonical=("+" if has_plus else "") + digits, digits=digits, has_plus=has_plus)


def phones_match(a: str, b: str) -> bool:
    """True when two canonical numbers belong to the same subscriber.

    Equal digits always match.  If exactly one side was given without a ``+``
    country code we compare the last 10 digits, so "+91 98765 43210" and
    "98765 43210" are treated as the same number.  Two numbers that both carry
    an explicit country code must match completely.
    """
    a_plus, b_plus = a.startswith("+"), b.startswith("+")
    da, db = a.lstrip("+"), b.lstrip("+")
    if da == db:
        return True
    if a_plus and b_plus:
        return False
    return len(da) >= MIN_DIGITS and len(db) >= MIN_DIGITS and da[-10:] == db[-10:]


def _groups(digits: str) -> list[str]:
    """Group digits as country-code + 5 + 5 (the usual way Indian numbers are said)."""
    if len(digits) >= 10:
        head, tail = digits[:-10], digits[-10:]
        parts = [head] if head else []
        parts += [tail[:5], tail[5:]]
        return parts
    return [digits]


def format_display(phone: PhoneNumber | str) -> str:
    """``+91 98765 43210`` style string for the UI."""
    p = phone if isinstance(phone, PhoneNumber) else normalize_phone(phone)
    return ("+" if p.has_plus else "") + " ".join(_groups(p.digits))


def read_back(phone: PhoneNumber | str) -> str:
    """Text for the agent to speak: ``plus 9 1, 9 8 7 6 5, 4 3 2 1 0``."""
    p = phone if isinstance(phone, PhoneNumber) else normalize_phone(phone)
    groups = [" ".join(g) for g in _groups(p.digits)]
    text = ", ".join(groups)
    return ("plus " + text) if p.has_plus else text


def read_back_words(phone: PhoneNumber | str) -> str:
    """Same as ``read_back`` but with digit words (used in the mock demo)."""
    p = phone if isinstance(phone, PhoneNumber) else normalize_phone(phone)
    groups = [" ".join(_DIGIT_NAMES[int(c)] for c in g) for g in _groups(p.digits)]
    text = ", ".join(groups)
    return ("plus " + text) if p.has_plus else text


def mask_phone(canonical: str, visible: int = 3) -> str:
    """Hide all but the last ``visible`` digits: ``+91 ••••• ••210``."""
    try:
        shown = format_display(canonical)
    except InvalidPhoneError:
        return "•••"
    total = sum(ch.isdigit() for ch in shown)
    seen = 0
    chars: list[str] = []
    for ch in shown:
        if ch.isdigit():
            seen += 1
            chars.append(ch if seen > total - visible else "•")
        else:
            chars.append(ch)
    return "".join(chars)
