import pytest
from datetime import datetime
from app.rules.night_safety import NightSafetyRule
from app.domain.dtos import TripContext, StopDTO, EmployeeDTO, RuleConfig
from app.domain.enums import Gender, StopType, StopStatus

def make_ctx(stops, emps, escort=False):
    return TripContext(
        trip_id=1, escort_assigned=escort, stops=stops, employees=emps,
        fixes=[], otp_events=[], sos_events=[], polyline=None, segment_limits=None, default_limit=60,
        config=RuleConfig(
            local_tz="UTC", night_start="22:00", night_end="06:00",
            deviation_threshold_m=500, deviation_min_seconds=120, deviation_min_meters=0, max_gps_gap_seconds=90,
            default_speed_limit_kmph=60, overspeed_min_seconds=30, extreme_overspeed_delta_kmph=40, extreme_overspeed_min_seconds=10,
            sos_decimals=5
        )
    )

def test_f_last_drop_night():
    stop = StopDTO(1, 1, StopType.DROP, 10, datetime(2023, 1, 1, 23, 10), None, StopStatus.PENDING)
    emp = EmployeeDTO(10, "EMP-10", Gender.F)
    ctx = make_ctx([stop], {10: emp})
    cands = NightSafetyRule().evaluate(ctx)
    assert len(cands) == 1
    assert cands[0].details["reason"] == "LAST_DROP"

def test_same_with_escort():
    stop = StopDTO(1, 1, StopType.DROP, 10, datetime(2023, 1, 1, 23, 10), None, StopStatus.PENDING)
    emp = EmployeeDTO(10, "EMP-10", Gender.F)
    ctx = make_ctx([stop], {10: emp}, escort=True)
    cands = NightSafetyRule().evaluate(ctx)
    assert len(cands) == 0

def test_f_last_drop_day():
    stop = StopDTO(1, 1, StopType.DROP, 10, datetime(2023, 1, 1, 14, 0), None, StopStatus.PENDING)
    emp = EmployeeDTO(10, "EMP-10", Gender.F)
    ctx = make_ctx([stop], {10: emp})
    cands = NightSafetyRule().evaluate(ctx)
    assert len(cands) == 0

def test_m_last_drop_night():
    stop = StopDTO(1, 1, StopType.DROP, 10, datetime(2023, 1, 1, 23, 10), None, StopStatus.PENDING)
    emp = EmployeeDTO(10, "EMP-10", Gender.M)
    ctx = make_ctx([stop], {10: emp})
    cands = NightSafetyRule().evaluate(ctx)
    assert len(cands) == 0

def test_f_first_pickup_night():
    stop = StopDTO(1, 1, StopType.PICKUP, 10, datetime(2023, 1, 1, 5, 30), None, StopStatus.PENDING)
    emp = EmployeeDTO(10, "EMP-10", Gender.F)
    ctx = make_ctx([stop], {10: emp})
    cands = NightSafetyRule().evaluate(ctx)
    assert len(cands) == 1
    assert cands[0].details["reason"] == "FIRST_PICKUP"

def test_window_boundaries():
    emp = EmployeeDTO(10, "EMP-10", Gender.F)
    def check(h, m, expected):
        stop = StopDTO(1, 1, StopType.DROP, 10, datetime(2023, 1, 1, h, m), None, StopStatus.PENDING)
        ctx = make_ctx([stop], {10: emp})
        cands = NightSafetyRule().evaluate(ctx)
        assert len(cands) == expected

    check(21, 59, 0)
    check(22, 0, 1)
    check(5, 59, 1)
    check(6, 0, 0)

def test_no_stops():
    ctx = make_ctx([], {})
    assert len(NightSafetyRule().evaluate(ctx)) == 0
