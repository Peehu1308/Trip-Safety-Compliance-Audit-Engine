"""
tests/integration/test_otp_flow.py
Integration tests for OTP verification flow per SPEC 10.4 and 14:
  - correct OTP completes the stop
  - wrong OTP → 409, stop FROZEN, one OTP_MISMATCH + outbox rows
  - second submit → 423
  - employee fetching someone else's OTP → 403
  - driver of another trip → 403
  - unfreeze works, then is refused after 3 failures
  - a later audit does not duplicate the OTP_MISMATCH
"""
import pytest
from sqlalchemy import select

from app.core.security import create_access_token, derive_otp
from app.domain.enums import Role, Gender, StopStatus
from app.models.trip import Stop
from app.models.user import User
from app.models.violation import Violation
from app.models.outbox import NotificationOutbox
from tests.conftest import seed_user, seed_driver, seed_employee


def _auth_header(user) -> dict[str, str]:
    token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    })
    return {"Authorization": f"Bearer {token}"}


def test_correct_otp_completes_stop(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client
    driver_user = session.scalar(select(User).where(User.username == "driver_t"))
    headers = _auth_header(driver_user)

    valid_otp = derive_otp(trip.id, stop.id)
    resp = client.post(
        f"/trips/{trip.id}/stops/{stop.id}/otp",
        json={"otp": valid_otp},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["result"] == "OK"
    assert data["stop_status"] == "COMPLETED"

    session.expire_all()
    refreshed_stop = session.get(Stop, stop.id)
    assert refreshed_stop.status == StopStatus.COMPLETED
    assert refreshed_stop.actual_time is not None


def test_wrong_otp_returns_409_and_freezes(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client
    driver_user = session.scalar(select(User).where(User.username == "driver_t"))
    headers = _auth_header(driver_user)

    # Pick a wrong OTP
    correct = derive_otp(trip.id, stop.id)
    wrong_otp = "000000" if correct != "000000" else "111111"

    resp = client.post(
        f"/trips/{trip.id}/stops/{stop.id}/otp",
        json={"otp": wrong_otp},
        headers=headers,
    )
    # SPEC: "commit first, then return HTTP 409"
    assert resp.status_code == 409, resp.text
    assert resp.json() == {"result": "MISMATCH", "stop_status": "FROZEN"}

    # Stop must be FROZEN in DB
    session.expire_all()
    refreshed_stop = session.get(Stop, stop.id)
    assert refreshed_stop.status == StopStatus.FROZEN
    assert refreshed_stop.otp_failures == 1

    # Exactly one OTP_MISMATCH violation
    violations = list(session.scalars(
        select(Violation)
        .where(Violation.trip_id == trip.id, Violation.type == "OTP_MISMATCH")
    ).all())
    assert len(violations) == 1

    # Outbox rows for this violation
    outbox_rows = list(session.scalars(
        select(NotificationOutbox)
        .where(NotificationOutbox.violation_id == violations[0].id)
    ).all())
    assert len(outbox_rows) > 0


def test_second_submit_on_frozen_stop_returns_423(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client
    driver_user = session.scalar(select(User).where(User.username == "driver_t"))
    headers = _auth_header(driver_user)

    correct = derive_otp(trip.id, stop.id)
    wrong_otp = "000000" if correct != "000000" else "111111"

    # First attempt: wrong → freeze
    client.post(
        f"/trips/{trip.id}/stops/{stop.id}/otp",
        json={"otp": wrong_otp},
        headers=headers,
    )

    # Second attempt on frozen stop → 423
    resp2 = client.post(
        f"/trips/{trip.id}/stops/{stop.id}/otp",
        json={"otp": correct},
        headers=headers,
    )
    assert resp2.status_code == 423, resp2.text
    body = resp2.json()
    assert body["error"]["code"] == "STOP_FROZEN"


def test_employee_fetching_other_otp_returns_403(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client

    # Create another employee user not associated with this stop
    u_other = seed_user(session, "other_emp_otp", Role.EMPLOYEE)
    seed_employee(session, u_other.id, Gender.M)
    session.commit()

    headers = _auth_header(u_other)
    resp = client.get(
        f"/trips/{trip.id}/stops/{stop.id}/otp",
        headers=headers,
    )
    assert resp.status_code == 403, resp.text


def test_driver_of_another_trip_returns_403(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client

    # Create a different driver
    u_other_drv = seed_user(session, "other_driver_otp", Role.DRIVER)
    seed_driver(session, u_other_drv.id)
    session.commit()

    headers = _auth_header(u_other_drv)
    correct = derive_otp(trip.id, stop.id)
    resp = client.post(
        f"/trips/{trip.id}/stops/{stop.id}/otp",
        json={"otp": correct},
        headers=headers,
    )
    assert resp.status_code == 403, resp.text


def test_unfreeze_and_failure_cap(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client
    driver_user = session.scalar(select(User).where(User.username == "driver_t"))
    drv_headers = _auth_header(driver_user)

    admin_user = seed_user(session, "admin_unfreeze", Role.ADMIN)
    session.commit()
    admin_headers = _auth_header(admin_user)

    correct = derive_otp(trip.id, stop.id)
    wrong_otp = "000000" if correct != "000000" else "111111"

    # Attempt 1: fail → freeze → unfreeze
    client.post(f"/trips/{trip.id}/stops/{stop.id}/otp", json={"otp": wrong_otp}, headers=drv_headers)
    resp = client.post(
        f"/trips/{trip.id}/stops/{stop.id}/unfreeze",
        json={"reason": "test1"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    s = session.get(Stop, stop.id)
    assert s.status == StopStatus.PENDING
    assert s.otp_failures == 1

    # Attempt 2: fail → freeze → unfreeze
    client.post(f"/trips/{trip.id}/stops/{stop.id}/otp", json={"otp": wrong_otp}, headers=drv_headers)
    client.post(f"/trips/{trip.id}/stops/{stop.id}/unfreeze", json={"reason": "test2"}, headers=admin_headers)

    # Attempt 3: fail → freeze (failures == 3 == MAX_OTP_FAILURES)
    client.post(f"/trips/{trip.id}/stops/{stop.id}/otp", json={"otp": wrong_otp}, headers=drv_headers)

    session.expire_all()
    s = session.get(Stop, stop.id)
    assert s.otp_failures == 3

    # Unfreeze after 3 failures must be refused with 409 Conflict
    resp_refused = client.post(
        f"/trips/{trip.id}/stops/{stop.id}/unfreeze",
        json={"reason": "test_refused"},
        headers=admin_headers,
    )
    assert resp_refused.status_code == 409, resp_refused.text


def test_later_audit_does_not_duplicate_otp_mismatch(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client
    driver_user = session.scalar(select(User).where(User.username == "driver_t"))
    drv_headers = _auth_header(driver_user)

    admin_user = seed_user(session, "admin_audit_otp", Role.ADMIN)
    session.commit()
    admin_headers = _auth_header(admin_user)

    correct = derive_otp(trip.id, stop.id)
    wrong_otp = "000000" if correct != "000000" else "111111"

    client.post(f"/trips/{trip.id}/stops/{stop.id}/otp", json={"otp": wrong_otp}, headers=drv_headers)

    # Run audit via API
    resp_audit = client.post(f"/trips/{trip.id}/audit", headers=admin_headers)
    assert resp_audit.status_code == 200, resp_audit.text

    # Still exactly one OTP_MISMATCH violation
    session.expire_all()
    violations = list(session.scalars(
        select(Violation)
        .where(Violation.trip_id == trip.id, Violation.type == "OTP_MISMATCH")
    ).all())
    assert len(violations) == 1
