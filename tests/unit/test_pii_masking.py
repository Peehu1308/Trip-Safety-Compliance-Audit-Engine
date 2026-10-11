"""
tests/unit/test_pii_masking.py
Unit tests for PII masking, log filters, candidate details safety,
and validation error input-stripping per SPEC 12.1, 12.2 & 14.
"""
import json
import logging
import pytest
from fastapi.testclient import TestClient

from app.core.logging import PIIFilter, JSONFormatter, mask_pii_str, redact_pii_obj
from app.main import app
from app.domain.dtos import (
    TripContext, StopDTO, EmployeeDTO, GpsFixDTO, OtpEventDTO, SosEventDTO, RuleConfig
)
from app.domain.enums import Gender, StopType, StopStatus
from app.rules.night_safety import NightSafetyRule
from app.rules.otp_drop import OtpDropRule
from app.rules.sos import SosRule
from app.rules.route_deviation import RouteDeviationRule
from app.rules.over_speed import OverSpeedRule
from datetime import datetime


def test_pii_filter_masks_ten_plus_digits():
    # 10 digits masked
    msg = "Driver called 9876543210 regarding trip"
    masked = mask_pii_str(msg)
    assert "9876543210" not in masked
    assert "[REDACTED_NUMBER]" in masked

    # 12 digits masked
    msg2 = "Device IMEI 123456789012 reported"
    masked2 = mask_pii_str(msg2)
    assert "123456789012" not in masked2
    assert "[REDACTED_NUMBER]" in masked2

    # <10 digits preserved
    msg3 = "Trip ID 12345 at sequence 3"
    masked3 = mask_pii_str(msg3)
    assert "12345" in masked3


def test_pii_filter_redacts_sensitive_keys_in_text():
    sample = "User info: phone: 9999999999, password: SecretPassword123, otp: 654321, lat: 28.5355, lng: 77.34"
    masked = mask_pii_str(sample)
    assert "SecretPassword123" not in masked
    assert "654321" not in masked
    assert "9999999999" not in masked


def test_pii_filter_redacts_dict_and_args():
    f = PIIFilter()
    data = {
        "phone": "9876543210",
        "name": "Priya Sharma",
        "password": "mypassword",
        "otp": "123456",
        "lat": 28.5355,
        "lng": 77.34,
        "home_lat": 28.53,
        "home_lng": 77.30,
        "trip_id": 42,
    }

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg=data,
        args=(),
        exc_info=None,
    )
    f.filter(record)

    assert record.msg["phone"] == "[REDACTED]"
    assert record.msg["name"] == "[REDACTED]"
    assert record.msg["password"] == "[REDACTED]"
    assert record.msg["otp"] == "[REDACTED]"
    assert record.msg["lat"] == "[REDACTED]"
    assert record.msg["lng"] == "[REDACTED]"
    assert record.msg["trip_id"] == 42


def test_json_formatter_structure_and_masking():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.WARNING,
        pathname="test.py",
        lineno=12,
        msg="Alert for driver phone 9876543210 on trip",
        args=(),
        exc_info=None,
    )
    record.trip_id = 99
    record.violation_id = 7
    record.actor_id = "admin"

    output = formatter.format(record)
    parsed = json.loads(output)

    assert "ts" in parsed
    assert parsed["level"] == "WARNING"
    assert parsed["trip_id"] == 99
    assert parsed["violation_id"] == 7
    assert parsed["actor_id"] == "admin"
    assert "9876543210" not in parsed["msg"]
    assert "[REDACTED_NUMBER]" in parsed["msg"]


def test_candidate_details_never_contain_name_or_phone():
    config = RuleConfig(
        local_tz="Asia/Kolkata",
        night_start="22:00",
        night_end="06:00",
        deviation_threshold_m=500.0,
        deviation_min_seconds=120,
        deviation_min_meters=0.0,
        max_gps_gap_seconds=90,
        default_speed_limit_kmph=60,
        overspeed_min_seconds=30,
        extreme_overspeed_delta_kmph=40,
        extreme_overspeed_min_seconds=10,
        sos_decimals=5,
    )

    ctx = TripContext(
        trip_id=1,
        escort_assigned=False,
        stops=[
            StopDTO(id=1, sequence=1, type=StopType.DROP, employee_id=10,
                    planned_time=datetime(2026, 10, 9, 17, 30), actual_time=None, status=StopStatus.PENDING)
        ],
        employees={10: EmployeeDTO(id=10, ref="EMP-10", gender=Gender.F)},
        fixes=[],
        otp_events=[OtpEventDTO(stop_id=1, success=False, attempt_no=1, ts=datetime(2026, 10, 9, 17, 35))],
        sos_events=[SosEventDTO(id=5, employee_id=10, lat=28.5355, lng=77.34, ts=datetime(2026, 10, 9, 17, 36))],
        polyline=None,
        segment_limits=None,
        default_limit=60,
        config=config,
    )

    rules = [NightSafetyRule(), OtpDropRule(), SosRule(), RouteDeviationRule(), OverSpeedRule()]
    all_candidates = []
    for r in rules:
        all_candidates.extend(r.evaluate(ctx))

    for c in all_candidates:
        details_keys = set(c.details.keys())
        assert "name" not in details_keys, f"Found 'name' in candidate {c.type} details: {c.details}"
        assert "phone" not in details_keys, f"Found 'phone' in candidate {c.type} details: {c.details}"


def test_validation_errors_never_echo_request_input():
    client = TestClient(app, raise_server_exceptions=False)

    # 1. POST /auth/login with invalid structure and secret password
    secret_pass = "MySuperSecretPassword#999"
    resp_invalid = client.post(
        "/auth/login",
        json={"username": ["not", "a", "string"], "password": secret_pass},
    )
    assert resp_invalid.status_code == 422
    data = resp_invalid.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_FAILED"

    # Confirm sensitive password input is NOT present in error response
    assert secret_pass not in resp_invalid.text
    for issue in data["error"].get("details", []):
        assert "input" not in issue, f"Found 'input' in issue: {issue}"
        assert "loc" in issue
        assert "msg" in issue

    # 2. POST /auth/login with missing password
    resp_missing = client.post(
        "/auth/login",
        json={"username": "test_user"},
    )
    assert resp_missing.status_code == 422
    data_missing = resp_missing.json()
    assert data_missing["error"]["code"] == "VALIDATION_FAILED"
    for issue in data_missing["error"].get("details", []):
        assert "input" not in issue
        assert "loc" in issue
        assert "msg" in issue


def test_cache_route_and_employee_behavior():
    import app.core.cache as cache
    from app.geo.polyline import Polyline

    cache.clear_all_caches()

    # Route cache miss then hit
    assert cache.get_cached_route(101) is None
    poly = Polyline([(28.5, 77.3), (28.6, 77.4)])
    cache.set_cached_route(101, poly, [60])
    cached = cache.get_cached_route(101)
    assert cached is not None
    assert cached[0] == poly
    assert cached[1] == [60]

    # Invalidate route
    cache.invalidate_trip(101)
    assert cache.get_cached_route(101) is None

    # Employee cache miss then hit
    assert cache.get_cached_employee(202) is None
    emp_dto = EmployeeDTO(id=202, ref="EMP-202", gender=Gender.M)
    cache.set_cached_employee(202, emp_dto)
    cached_emp = cache.get_cached_employee(202)
    assert cached_emp is not None
    assert cached_emp.ref == "EMP-202"

    # Invalidate employee
    cache.invalidate_employee(202)
    assert cache.get_cached_employee(202) is None


def test_ops_health_and_metrics_endpoints(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client

    # 1. Health check
    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    assert resp_health.json() == {"status": "ok", "db": "ok"}
    assert resp_health.headers.get("X-Request-ID") is not None

    # 2. Metrics check
    resp_metrics = client.get("/metrics")
    assert resp_metrics.status_code == 200
    text_metrics = resp_metrics.text
    assert "http_requests_total" in text_metrics
    assert 'route="/health"' in text_metrics
    assert "outbox_pending" in text_metrics


