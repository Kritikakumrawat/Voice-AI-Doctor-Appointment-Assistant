"""Domain errors.  Every error has a stable ``code`` the voice agent and API can act on."""
from __future__ import annotations


class DomainError(Exception):
    code = "error"
    http_status = 400

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        return {"status": "error", "code": self.code, "message": self.message, **self.details}


class DoctorNotFound(DomainError):
    code = "doctor_not_found"
    http_status = 404


class SlotNotFound(DomainError):
    code = "slot_not_found"
    http_status = 404


class SlotUnavailable(DomainError):
    code = "slot_unavailable"
    http_status = 409


class PastSlot(DomainError):
    code = "slot_in_past"
    http_status = 409


class PatientConflict(DomainError):
    """The same phone number already has an appointment at that time."""

    code = "patient_conflict"
    http_status = 409


class AppointmentNotFound(DomainError):
    code = "appointment_not_found"
    http_status = 404


class InvalidInput(DomainError):
    code = "invalid_input"
    http_status = 422


class AlreadyCancelled(DomainError):
    code = "already_cancelled"
    http_status = 409


class ApiError(DomainError):
    """HTTP-level error raised by API handlers (not by business logic)."""

    def __init__(self, status: int, code: str, message: str, **details: object) -> None:
        super().__init__(message, **details)
        self.http_status = status
        self.code = code
