import pytest
from datetime import datetime, timedelta
from app.rules.route_deviation import RouteDeviationRule
from app.domain.dtos import TripContext, RuleConfig, GpsFixDTO
from app.geo.polyline import Polyline

def make_ctx(fixes):
    return TripContext(
        trip_id=1, escort_assigned=False, stops=[], employees={},
        fixes=fixes, otp_events=[], sos_events=[], 
        polyline=Polyline([(28.5355, 77.3000), (28.5355, 77.4000)]),
        segment_limits=[60], default_limit=60,
        config=RuleConfig(
            local_tz="UTC", night_start="22:00", night_end="06:00",
            deviation_threshold_m=500, deviation_min_seconds=120, deviation_min_meters=0, max_gps_gap_seconds=90,
            default_speed_limit_kmph=60, overspeed_min_seconds=30, extreme_overspeed_delta_kmph=40, extreme_overspeed_min_seconds=10,
            sos_decimals=5
        )
    )

def test_800m_4min_flagged():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    fixes = [GpsFixDTO(t0 + timedelta(seconds=i*15), 28.5355 + 0.0072, 77.3500, 40) for i in range(17)] # 240s
    ctx = make_ctx(fixes)
    cands = RouteDeviationRule().evaluate(ctx)
    assert len(cands) == 1
    assert cands[0].details["duration_s"] == 240
    assert cands[0].details["max_deviation_m"] >= 790

def test_1200m_blip_not_flagged():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    fixes = [
        GpsFixDTO(t0, 28.5355, 77.3500, 40),
        GpsFixDTO(t0 + timedelta(seconds=15), 28.5355 + 0.0108, 77.3500, 40),
        GpsFixDTO(t0 + timedelta(seconds=30), 28.5355, 77.3500, 40),
    ]
    ctx = make_ctx(fixes)
    assert len(RouteDeviationRule().evaluate(ctx)) == 0

def test_400m_10min_not_flagged():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    # 0.0036 lat is approx 400m < 500m threshold
    fixes = [GpsFixDTO(t0 + timedelta(seconds=i*15), 28.5355 + 0.0036, 77.3500, 40) for i in range(41)]
    ctx = make_ctx(fixes)
    assert len(RouteDeviationRule().evaluate(ctx)) == 0

def test_unsorted_input():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    fixes = [GpsFixDTO(t0 + timedelta(seconds=i*15), 28.5355 + 0.0072, 77.3500, 40) for i in range(17)]
    ctx_sorted = make_ctx(fixes)
    ctx_unsorted = make_ctx(list(reversed(fixes)))
    
    assert len(RouteDeviationRule().evaluate(ctx_sorted)) == 1
    assert len(RouteDeviationRule().evaluate(ctx_unsorted)) == 1

def test_empty_gps():
    ctx = make_ctx([])
    assert len(RouteDeviationRule().evaluate(ctx)) == 0

def test_gps_gap_splits_run():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    fixes = [GpsFixDTO(t0 + timedelta(seconds=i*15), 28.5355 + 0.0072, 77.3500, 40) for i in range(9)] # 120s
    t1 = fixes[-1].ts + timedelta(seconds=100)
    fixes.extend([GpsFixDTO(t1 + timedelta(seconds=i*15), 28.5355 + 0.0072, 77.3500, 40) for i in range(9)]) # 120s
    ctx = make_ctx(fixes)
    cands = RouteDeviationRule().evaluate(ctx)
    assert len(cands) == 2
