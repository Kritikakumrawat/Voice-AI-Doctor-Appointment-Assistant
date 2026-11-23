"""Maps exceptions to the one consistent error body: {"error": {"code", "message", ...}}."""
from __future__ import annotations

from typing import Any

from app.services.errors import DomainError
from app.services.phone import InvalidPhoneError


def error_body(exc: Exception) -> tuple[int, dict[str, Any]]:
    if isinstance(exc, DomainError):
        body = {"code": exc.code, "message": exc.message, **exc.details}
        return exc.http_status, {"error": body}
    if isinstance(exc, InvalidPhoneError):
        return 422, {"error": {"code": "invalid_phone", "message": str(exc)}}
    return 500, {"error": {"code": "internal_error", "message": "Something went wrong on the server."}}
