"""
app/schemas/events.py
Pydantic schemas for OTP, SOS, and stop unfreeze operations.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class OtpSubmitRequest(BaseModel):
    otp: str = Field(..., pattern=r"^\d{6}$")


class OtpSubmitResponse(BaseModel):
    result: str
    stop_status: str


class OtpValueResponse(BaseModel):
    otp: str


class UnfreezeRequest(BaseModel):
    reason: str


class SosRequest(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None


class SosResponse(BaseModel):
    sos_event_id: int
    violation_id: Optional[int] = None
    location_source: str
