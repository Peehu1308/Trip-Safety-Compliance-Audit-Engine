import pytest
from datetime import datetime, timedelta
from app.rules.over_speed import OverSpeedRule
from app.domain.dtos import TripContext, RuleConfig, GpsFixDTO
from app.domain.enums import ViolationType
from app.geo.polyline import Polyline

def make_ctx(fixes, segment_limits=[60]):
    return TripContext(
        trip_id=1, escort_assigned=False, stops=[], employees={},
        fixes=fixes, otp_events=[], sos_events=[], 
        polyline=Polyline([(28.5355, 77.3000), (28.5355, 77.4000)]),
        segment_limits=segment_limits, default_limit=60,
        config=RuleConfig(
            local_tz="UTC", night_start="22:00", night_end="06:00",
            deviation_threshold_m=500, deviation_min_seconds=120, deviation_min_meters=0, max_gps_gap_seconds=90,
            default_speed_limit_kmph=60, overspeed_min_seconds=30, extreme_overspeed_delta_kmph=40, extreme_overspeed_min_seconds=10,
            sos_decimals=5
        )
    )

def test_spike_none():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    fixes = [
        GpsFixDTO(t0, 28.5355, 77.3500, 60),
        GpsFixDTO(t0 + timedelta(seconds=15), 28.5355, 77.3500, 95), # Spike
        GpsFixDTO(t0 + timedelta(seconds=30), 28.5355, 77.3500, 60),
    ]
    ctx = make_ctx(fixes)
    assert len(OverSpeedRule().evaluate(ctx)) == 0

def test_45s_over_limit_medium():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    fixes = [GpsFixDTO(t0 + timedelta(seconds=i*15), 28.5355, 77.3500, 75) for i in range(4)] # 45s
    ctx = make_ctx(fixes)
    cands = OverSpeedRule().evaluate(ctx)
    assert len(cands) == 1
    assert cands[0].type == ViolationType.OVER_SPEED
    assert cands[0].details["duration_s"] == 45

def test_30s_extreme_only():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    fixes = [GpsFixDTO(t0 + timedelta(seconds=i*15), 28.5355, 77.3500, 110) for i in range(3)] # 30s
    ctx = make_ctx(fixes)
    cands = OverSpeedRule().evaluate(ctx)
    assert len(cands) == 1
    assert cands[0].type == ViolationType.EXTREME_OVER_SPEED

def test_per_segment_limits_respected():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    # segment limit is 80 instead of default 60
    fixes = [GpsFixDTO(t0 + timedelta(seconds=i*15), 28.5355, 77.3500, 75) for i in range(4)]
    ctx = make_ctx(fixes, segment_limits=[80])
    cands = OverSpeedRule().evaluate(ctx)
    assert len(cands) == 0 # 75 < 80, no violation
