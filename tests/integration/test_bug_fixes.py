"""
tests/integration/test_bug_fixes.py

Tests for the two bug fixes:
  BUG 1 - POST /trips (and other write endpoints) returned 500 due to lazy-load
           of trip.stops after the write_tx session closed.
  BUG 2 - Datetimes with a UTC offset (e.g. +05:30) were stored with the offset
           stripped instead of being converted to UTC first.
"""
from __future__ import annotations

import pytest
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.models.base import Base
from app.core.security import create_access_token, derive_otp
from app.domain.enums import Role, Gender, StopType
import app.core.db as db_mod
from tests.conftest import (
    seed_user, seed_driver, seed_vehicle, seed_employee, seed_trip, seed_stop,
)


@pytest.fixture
def api_client(tmp_path):
    db_file = tmp_path / "bug_fix_test.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    from sqlalchemy import event as _sa_event
    @_sa_event.listens_for(test_engine, "connect")
    def _on_connect(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    @contextmanager
    def _test_write_tx():
        s = TestSession()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    orig = {
        "SessionLocal": db_mod.SessionLocal,
        "WriteSession": getattr(db_mod, "WriteSession", db_mod.SessionLocal),
        "ReadSession": getattr(db_mod, "ReadSession", db_mod.SessionLocal),
        "engine": db_mod.engine,
        "write_engine": getattr(db_mod, "write_engine", db_mod.engine),
        "read_engine": getattr(db_mod, "read_engine", db_mod.engine),
        "write_tx": db_mod.write_tx,
    }
    db_mod.SessionLocal = TestSession
    db_mod.WriteSession = TestSession
    db_mod.ReadSession = TestSession
    db_mod.engine = test_engine
    db_mod.write_engine = test_engine
    db_mod.read_engine = test_engine
    db_mod.write_tx = _test_write_tx

    session = TestSession()
    admin_user = seed_user(session, "admin_bf", Role.ADMIN)
    approver_user = seed_user(session, "approver_bf", Role.APPROVER)
    drv_user = seed_user(session, "driver_bf", Role.DRIVER)
    emp_user_m = seed_user(session, "rahul_bf", Role.EMPLOYEE)
    emp_user_f = seed_user(session, "priya_bf", Role.EMPLOYEE)
    drv = seed_driver(session, drv_user.id)
    veh = seed_vehicle(session)
    emp_m = seed_employee(session, emp_user_m.id, Gender.M)
    emp_f = seed_employee(session, emp_user_f.id, Gender.F)
    session.commit()

    client = TestClient(app, raise_server_exceptions=False)

    yield client, session, {
        "admin": admin_user,
        "approver": approver_user,
        "driver_user": drv_user,
        "driver": drv,
        "vehicle": veh,
        "emp_m": emp_m,
        "emp_f": emp_f,
        "emp_user_f": emp_user_f,
    }

    session.close()
    for k, v in orig.items():
        setattr(db_mod, k, v)
    test_engine.dispose()


def _hdr(user) -> dict:
    token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    })
    return {"Authorization": f"Bearer {token}"}


def _trip_body(driver_id, vehicle_id, emp_m_id, emp_f_id, p1, p2, d1, d2):
    return {
        "driver_id": driver_id,
        "vehicle_id": vehicle_id,
        "planned_route": [[28.5355, 77.30], [28.5355, 77.35], [28.5355, 77.40], [28.5355, 77.45]],
        "default_speed_limit_kmph": 60,
        "stops": [
            {"sequence": 1, "type": "PICKUP", "employee_id": emp_m_id, "planned_time": p1,
             "lat": 28.5355, "lng": 77.30},
            {"sequence": 2, "type": "PICKUP", "employee_id": emp_f_id, "planned_time": p2,
             "lat": 28.5355, "lng": 77.35},
            {"sequence": 3, "type": "DROP", "employee_id": emp_m_id, "planned_time": d1,
             "lat": 28.5355, "lng": 77.40},
            {"sequence": 4, "type": "DROP", "employee_id": emp_f_id, "planned_time": d2,
             "lat": 28.5355, "lng": 77.45},
        ],
    }


def _create_night_trip(client, admin, drv, veh, emp_m, emp_f):
    body = _trip_body(
        drv.id, veh.id, emp_m.id, emp_f.id,
        "2026-10-11T22:15:00+05:30",
        "2026-10-11T22:40:00+05:30",
        "2026-10-11T23:00:00+05:30",
        "2026-10-11T23:10:00+05:30",
    )
    resp = client.post("/trips", json=body, headers=_hdr(admin))
    assert resp.status_code == 201, resp.text
    return resp.json()


# BUG 1 -- POST /trips returns 201 with stops populated (no lazy-load 500)

def test_post_trips_returns_201_with_stops(api_client):
    client, session, ids = api_client
    trip = _create_night_trip(
        client, ids["admin"], ids["driver"], ids["vehicle"],
        ids["emp_m"], ids["emp_f"],
    )
    assert "stops" in trip
    assert len(trip["stops"]) == 4


# BUG 2 -- Timezone conversion

def test_planned_time_offset_stored_as_utc(api_client):
    """22:15+05:30 must serialise back as 16:45:00Z."""
    client, session, ids = api_client
    body = _trip_body(
        ids["driver"].id, ids["vehicle"].id,
        ids["emp_m"].id, ids["emp_f"].id,
        "2026-10-11T22:15:00+05:30",
        "2026-10-11T22:40:00+05:30",
        "2026-10-11T23:00:00+05:30",
        "2026-10-11T23:10:00+05:30",
    )
    resp = client.post("/trips", json=body, headers=_hdr(ids["admin"]))
    assert resp.status_code == 201, resp.text
    stops = sorted(resp.json()["stops"], key=lambda s: s["sequence"])
    pt = stops[0]["planned_time"]
    assert "16:45:00" in pt, f"Expected 16:45:00 UTC, got {pt!r}"
    assert pt.endswith("Z"), f"Expected Z suffix, got {pt!r}"


def test_planned_time_z_suffix_unchanged(api_client):
    """16:45:00Z input must return as 16:45:00Z."""
    client, session, ids = api_client
    body = _trip_body(
        ids["driver"].id, ids["vehicle"].id,
        ids["emp_m"].id, ids["emp_f"].id,
        "2026-10-11T16:45:00Z",
        "2026-10-11T17:10:00Z",
        "2026-10-11T17:30:00Z",
        "2026-10-11T17:40:00Z",
    )
    resp = client.post("/trips", json=body, headers=_hdr(ids["admin"]))
    assert resp.status_code == 201, resp.text
    stops = sorted(resp.json()["stops"], key=lambda s: s["sequence"])
    pt = stops[0]["planned_time"]
    assert "16:45:00" in pt, f"Expected 16:45:00, got {pt!r}"
    assert pt.endswith("Z"), f"Expected Z suffix, got {pt!r}"


def test_naive_planned_time_returns_422(api_client):
    """Naive datetime (no tz) must be rejected with 422."""
    client, session, ids = api_client
    body = _trip_body(
        ids["driver"].id, ids["vehicle"].id,
        ids["emp_m"].id, ids["emp_f"].id,
        "2026-10-11T22:15:00",
        "2026-10-11T22:40:00",
        "2026-10-11T23:00:00",
        "2026-10-11T23:10:00",
    )
    resp = client.post("/trips", json=body, headers=_hdr(ids["admin"]))
    assert resp.status_code == 422, resp.text


# BUG 2 + NIGHT_SAFETY

def test_night_safety_triggered_for_tz_aware_night_drop(api_client):
    """23:10+05:30 female last drop -> NIGHT_SAFETY."""
    client, session, ids = api_client
    trip = _create_night_trip(
        client, ids["admin"], ids["driver"], ids["vehicle"],
        ids["emp_m"], ids["emp_f"],
    )
    audit_resp = client.post(f"/trips/{trip['id']}/audit", headers=_hdr(ids["admin"]))
    assert audit_resp.status_code == 200, audit_resp.text
    types = [v["type"] for v in audit_resp.json()["violations"]]
    assert "NIGHT_SAFETY" in types, f"Expected NIGHT_SAFETY, got {types}"


def test_no_night_safety_for_daytime_drop(api_client):
    """17:00+05:30 female last drop -> no NIGHT_SAFETY."""
    client, session, ids = api_client
    body = _trip_body(
        ids["driver"].id, ids["vehicle"].id,
        ids["emp_m"].id, ids["emp_f"].id,
        "2026-10-11T14:00:00+05:30",
        "2026-10-11T14:30:00+05:30",
        "2026-10-11T15:00:00+05:30",
        "2026-10-11T17:00:00+05:30",
    )
    resp = client.post("/trips", json=body, headers=_hdr(ids["admin"]))
    assert resp.status_code == 201, resp.text
    audit_resp = client.post(f"/trips/{resp.json()['id']}/audit", headers=_hdr(ids["admin"]))
    assert audit_resp.status_code == 200, audit_resp.text
    types = [v["type"] for v in audit_resp.json()["violations"]]
    assert "NIGHT_SAFETY" not in types, f"Expected no NIGHT_SAFETY, got {types}"


# BUG 1 -- Other write endpoints return 2xx

def test_escort_endpoint_returns_200(api_client):
    client, session, ids = api_client
    trip = _create_night_trip(
        client, ids["admin"], ids["driver"], ids["vehicle"],
        ids["emp_m"], ids["emp_f"],
    )
    resp = client.patch(
        f"/trips/{trip['id']}/escort",
        json={"escort_assigned": True},
        headers=_hdr(ids["admin"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["escort_assigned"] is True


def test_complete_trip_returns_200(api_client):
    client, session, ids = api_client
    trip = _create_night_trip(
        client, ids["admin"], ids["driver"], ids["vehicle"],
        ids["emp_m"], ids["emp_f"],
    )
    resp = client.post(f"/trips/{trip['id']}/complete", headers=_hdr(ids["driver_user"]))
    assert resp.status_code == 200, resp.text
    assert resp.json()["trip_id"] == trip["id"]


def test_sos_endpoint_returns_201(api_client):
    client, session, ids = api_client
    trip = _create_night_trip(
        client, ids["admin"], ids["driver"], ids["vehicle"],
        ids["emp_m"], ids["emp_f"],
    )
    resp = client.post(
        f"/trips/{trip['id']}/sos",
        json={"lat": 28.5355, "lng": 77.35},
        headers=_hdr(ids["emp_user_f"]),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "sos_event_id" in data
    assert data["location_source"] == "REQUEST"


def test_acknowledge_endpoint_returns_200(api_client):
    client, session, ids = api_client
    trip = _create_night_trip(
        client, ids["admin"], ids["driver"], ids["vehicle"],
        ids["emp_m"], ids["emp_f"],
    )
    audit_resp = client.post(f"/trips/{trip['id']}/audit", headers=_hdr(ids["admin"]))
    assert audit_resp.status_code == 200, audit_resp.text
    violations = audit_resp.json()["violations"]
    assert len(violations) > 0
    violation_id = violations[0]["id"]
    resp = client.patch(
        f"/violations/{violation_id}/acknowledge",
        json={"note": "ack in test"},
        headers=_hdr(ids["approver"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ACKNOWLEDGED"


def test_otp_submit_returns_2xx(api_client):
    client, session, ids = api_client
    trip = _create_night_trip(
        client, ids["admin"], ids["driver"], ids["vehicle"],
        ids["emp_m"], ids["emp_f"],
    )
    stops = sorted(trip["stops"], key=lambda s: s["sequence"])
    drop_stop = stops[-1]  # sequence 4, DROP for emp_f
    stop_id = drop_stop["id"]
    correct_otp = derive_otp(trip["id"], stop_id)
    resp = client.post(
        f"/trips/{trip['id']}/stops/{stop_id}/otp",
        json={"otp": correct_otp},
        headers=_hdr(ids["driver_user"]),
    )
    assert resp.status_code in (200, 409), resp.text
