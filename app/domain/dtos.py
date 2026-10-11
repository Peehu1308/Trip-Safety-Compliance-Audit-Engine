from dataclasses import dataclass
from typing import Optional, Any
from datetime import datetime
from app.domain.enums import Gender, StopType, StopStatus, ViolationType

@dataclass(frozen=True)
class EmployeeDTO:
    id: int
    ref: str
    gender: Gender

@dataclass(frozen=True)
class StopDTO:
    id: int
    sequence: int
    type: StopType
    employee_id: int
    planned_time: datetime
    actual_time: Optional[datetime]
    status: StopStatus

@dataclass(frozen=True)
class GpsFixDTO:
    ts: datetime
    lat: float
    lng: float
    speed_kmph: float

@dataclass(frozen=True)
class OtpEventDTO:
    stop_id: int
    success: bool
    attempt_no: int
    ts: datetime

@dataclass(frozen=True)
class SosEventDTO:
    id: int
    employee_id: int
    lat: Optional[float]
    lng: Optional[float]
    ts: datetime

@dataclass(frozen=True)
class Sample:
    ts: datetime
    lat: float
    lng: float
    speed_kmph: float
    deviation_m: float
    segment_idx: int
    limit_kmph: int

@dataclass(frozen=True)
class RuleConfig:
    local_tz: str
    night_start: str
    night_end: str
    deviation_threshold_m: int
    deviation_min_seconds: int
    deviation_min_meters: int
    max_gps_gap_seconds: int
    default_speed_limit_kmph: int
    overspeed_min_seconds: int
    extreme_overspeed_delta_kmph: int
    extreme_overspeed_min_seconds: int
    sos_decimals: int

@dataclass(frozen=True)
class TripContext:
    trip_id: int
    escort_assigned: bool
    stops: list[StopDTO]
    employees: dict[int, EmployeeDTO]
    fixes: list[GpsFixDTO]
    otp_events: list[OtpEventDTO]
    sos_events: list[SosEventDTO]
    polyline: Any
    segment_limits: Optional[list[int]]
    default_limit: int
    config: RuleConfig

@dataclass(frozen=True)
class ViolationCandidate:
    type: ViolationType
    subject_key: str
    details: dict
