"""Request bodies (validated by pydantic)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class BookingRequest(BaseModel):
    doctor_id: str = Field(..., min_length=1, max_length=20)
    date: str = Field(..., description="YYYY-MM-DD")
    start_time: str = Field(..., description="HH:MM (24h)")
    phone: str = Field(..., min_length=1, max_length=40)
    patient_name: str | None = Field(None, max_length=80)


class CancelRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=40)


class SayRequest(BaseModel):
    text: str = Field(..., max_length=500)
