"""
app/schemas/trips.py
Pydantic schemas for trip management and stop details.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.domain.enums import StopType, StopStatus, TripStatus


class StopCreate(BaseModel):
    sequence: int
    type: StopType
    employee_id: int
    planned_time: datetime
    lat: float
    lng: float


class TripCreate(BaseModel):
    driver_id: int
    vehicle_id: int
    planned_route: List[List[float]]
    default_speed_limit_kmph: int = 60
    segment_speed_limits: Optional[List[int]] = None
    stops: List[StopCreate]


class EscortUpdateRequest(BaseModel):
    escort_assigned: bool


class StopResponse(BaseModel):
    id: int
    trip_id: int
    sequence: int
    type: StopType
    employee_id: int
    planned_time: datetime
    actual_time: Optional[datetime] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    status: StopStatus
    otp_failures: int

    model_config = ConfigDict(from_attributes=True)


class TripResponse(BaseModel):
    id: int
    driver_id: int
    vehicle_id: int
    status: TripStatus
    escort_assigned: bool
    requires_escort: bool
    planned_route: Optional[List[List[float]]] = None
    segment_speed_limits: Optional[List[int]] = None
    default_speed_limit_kmph: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    stops: List[StopResponse] = []

    model_config = ConfigDict(from_attributes=True)
