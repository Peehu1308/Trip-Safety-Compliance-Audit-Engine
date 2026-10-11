"""
tests/integration/test_sos_flow.py
Integration tests for SOS panic workflow per SPEC 10.5 & 14:
  - SOS creates CRITICAL violation and outbox to security_pager/manager/log immediately
  - location source logic (REQUEST / LAST_GPS / UNKNOWN)
  - non-passenger → 403
  - audit afterwards does not duplicate the SOS violation
"""
from datetime import datetime, timezone
import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.domain.enums import Role, Gender
from app.models.violation import Violation
from app.models.outbox import NotificationOutbox
from app.models.gps import GpsFix
from app.models.user import User
from tests.conftest import seed_user, seed_employee


def _auth_header(user) -> dict[str, str]:
    token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    })
    return {"Authorization": f"Bearer {token}"}


def test_sos_creates_critical_violation_and_outbox(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client
    priya_user = session.scalar(select(User).where(User.username == "priya_t"))
    headers = _auth_header(priya_user)

    resp = client.post(
        f"/trips/{trip.id}/sos",
        json={"lat": 28.535512, "lng": 77.351234},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["location_source"] == "REQUEST"
    assert data["violation_id"] is not None

    # Verify CRITICAL violation in DB
    session.expire_all()
    violation = session.get(Violation, data["violation_id"])
    assert violation is not None
    assert violation.type == "SOS" or str(violation.type) == "SOS"
    sev = violation.severity
    sev_name = sev.name if hasattr(sev, 'name') else str(sev)
    assert sev_name == "CRITICAL"

    # Verify outbox channels for CRITICAL: security_pager, manager, log
    outbox_rows = list(session.scalars(
        select(NotificationOutbox)
        .where(NotificationOutbox.violation_id == violation.id)
    ).all())
    channels = {r.channel for r in outbox_rows}
    assert channels == {"security_pager", "manager", "log"}


def test_sos_location_source_fallback(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client
    priya_user = session.scalar(select(User).where(User.username == "priya_t"))
    headers = _auth_header(priya_user)

    # 1. No GPS fixes, no coords → UNKNOWN
    resp1 = client.post(f"/trips/{trip.id}/sos", json={}, headers=headers)
    assert resp1.status_code == 201, resp1.text
    assert resp1.json()["location_source"] == "UNKNOWN"

    # 2. Add a GPS fix → next SOS uses LAST_GPS
    fix = GpsFix(
        trip_id=trip.id,
        ts=datetime(2026, 10, 9, 17, 30, tzinfo=timezone.utc),
        lat=28.5350,
        lng=77.3400,
        speed_kmph=40.0,
    )
    session.add(fix)
    session.commit()

    resp2 = client.post(f"/trips/{trip.id}/sos", json={}, headers=headers)
    assert resp2.status_code == 201, resp2.text
    assert resp2.json()["location_source"] == "LAST_GPS"


def test_non_passenger_sos_returns_403(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client

    u_outsider = seed_user(session, "outsider_sos", Role.EMPLOYEE)
    seed_employee(session, u_outsider.id, Gender.M)
    session.commit()

    headers = _auth_header(u_outsider)
    resp = client.post(f"/trips/{trip.id}/sos", json={}, headers=headers)
    assert resp.status_code == 403, resp.text


def test_audit_after_sos_does_not_duplicate_violation(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client
    priya_user = session.scalar(select(User).where(User.username == "priya_t"))
    emp_headers = _auth_header(priya_user)

    admin_user = seed_user(session, "admin_sos_audit", Role.ADMIN)
    session.commit()
    admin_headers = _auth_header(admin_user)

    # Trigger SOS
    resp = client.post(
        f"/trips/{trip.id}/sos",
        json={"lat": 28.5355, "lng": 77.35},
        headers=emp_headers,
    )
    assert resp.status_code == 201, resp.text
    sos_v_id = resp.json()["violation_id"]

    # Run audit
    resp_audit = client.post(f"/trips/{trip.id}/audit", headers=admin_headers)
    assert resp_audit.status_code == 200, resp_audit.text

    # Still exactly one SOS violation
    session.expire_all()
    sos_violations = list(session.scalars(
        select(Violation)
        .where(Violation.trip_id == trip.id, Violation.type == "SOS")
    ).all())
    assert len(sos_violations) == 1
    assert sos_violations[0].id == sos_v_id
