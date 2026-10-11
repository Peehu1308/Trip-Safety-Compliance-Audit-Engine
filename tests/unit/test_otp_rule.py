import pytest
from datetime import datetime
from app.rules.otp_drop import OtpDropRule
from app.domain.dtos import TripContext, OtpEventDTO, RuleConfig

def make_ctx(events):
    return TripContext(
        trip_id=1, escort_assigned=False, stops=[], employees={},
        fixes=[], otp_events=events, sos_events=[], polyline=None,
        segment_limits=None, default_limit=60,
        config=RuleConfig(
            local_tz="UTC", night_start="22:00", night_end="06:00",
            deviation_threshold_m=500, deviation_min_seconds=120, deviation_min_meters=0, max_gps_gap_seconds=90,
            default_speed_limit_kmph=60, overspeed_min_seconds=30, extreme_overspeed_delta_kmph=40, extreme_overspeed_min_seconds=10,
            sos_decimals=5
        )
    )

def test_failed_event_yields_candidate():
    events = [
        OtpEventDTO(stop_id=1, success=False, attempt_no=1, ts=datetime(2023, 1, 1, 10, 0, 0))
    ]
    ctx = make_ctx(events)
    cands = OtpDropRule().evaluate(ctx)
    assert len(cands) == 1
    assert cands[0].subject_key == "stop:1"
    assert cands[0].details["failed_attempts"] == 1

def test_success_only_yields_none():
    events = [
        OtpEventDTO(stop_id=1, success=True, attempt_no=1, ts=datetime(2023, 1, 1, 10, 0, 0))
    ]
    ctx = make_ctx(events)
    cands = OtpDropRule().evaluate(ctx)
    assert len(cands) == 0

def test_mixed_events():
    events = [
        OtpEventDTO(stop_id=1, success=False, attempt_no=1, ts=datetime(2023, 1, 1, 10, 0, 0)),
        OtpEventDTO(stop_id=1, success=True, attempt_no=2, ts=datetime(2023, 1, 1, 10, 1, 0))
    ]
    ctx = make_ctx(events)
    cands = OtpDropRule().evaluate(ctx)
    assert len(cands) == 1
    assert cands[0].details["failed_attempts"] == 1
