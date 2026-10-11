"""
app/schemas/violations.py
Pydantic schemas for violation reporting and acknowledgment.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict


class ViolationResponse(BaseModel):
    id: int
    trip_id: int
    type: str
    severity: str
    dedupe_key: str
    subject_key: str
    details: dict[str, Any]
    detected_by: str
    detected_at: datetime
    status: str
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    ack_note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ViolationAcknowledgeRequest(BaseModel):
    note: Optional[str] = None
