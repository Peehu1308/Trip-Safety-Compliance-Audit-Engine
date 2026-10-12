"""
app/schemas/gps.py
Pydantic schemas for GPS data ingestion.
"""
from __future__ import annotations
from datetime import datetime
from typing import List
from pydantic import BaseModel, Field, field_validator
from app.core.timeutil import ensure_utc


class GpsFixIn(BaseModel):
    ts: datetime
    lat: float = Field(..., ge=-90.0, le=90.0)
    lng: float = Field(..., ge=-180.0, le=180.0)
    speed_kmph: float = Field(..., ge=0.0, le=300.0)

    @field_validator("ts")
    @classmethod
    def validate_ts(cls, v: datetime) -> datetime:
        return ensure_utc(v)


class GpsIngestRequest(BaseModel):
    fixes: List[GpsFixIn]


class GpsIngestResponse(BaseModel):
    accepted: int
    duplicates_ignored: int
