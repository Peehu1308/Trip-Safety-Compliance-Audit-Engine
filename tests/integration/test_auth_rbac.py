"""
tests/integration/test_auth_rbac.py
Integration tests for authentication and RBAC per SPEC Section 11 & 14:
  - no token → 401
  - expired / garbled token → 401
  - EMPLOYEE calling /trips/{id}/audit → 403
  - EMPLOYEE cannot view another employee's trip
  - login lockout after 5 bad attempts → 429
"""
from datetime import timedelta
import pytest
from sqlalchemy import select

from app.core.security import hash_password, create_access_token
from app.domain.enums import Role, Gender
from app.models.user import User
from tests.conftest import seed_user, seed_employee


def _auth_header(user) -> dict[str, str]:
    token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    })
    return {"Authorization": f"Bearer {token}"}


def test_missing_token_returns_401(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client
    resp = client.get(f"/trips/{trip.id}")
    assert resp.status_code == 401, resp.text


def test_garbled_token_returns_401(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client
    resp = client.get(f"/trips/{trip.id}", headers={"Authorization": "Bearer not-a-valid-jwt"})
    assert resp.status_code == 401, resp.text


def test_expired_token_returns_401(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client
    expired_token = create_access_token({"sub": "9999"}, expires_delta=timedelta(minutes=-10))
    resp = client.get(
        f"/trips/{trip.id}",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401, resp.text


def test_employee_calling_audit_returns_403(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client
    priya_user = session.scalar(select(User).where(User.username == "priya_t"))
    headers = _auth_header(priya_user)

    resp = client.post(f"/trips/{trip.id}/audit", headers=headers)
    assert resp.status_code == 403, resp.text


def test_employee_cannot_view_unrelated_trip(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client

    u_outsider = seed_user(session, "outsider_view_rbac", Role.EMPLOYEE)
    seed_employee(session, u_outsider.id, Gender.M)
    session.commit()

    headers = _auth_header(u_outsider)
    resp = client.get(f"/trips/{trip.id}", headers=headers)
    assert resp.status_code == 403, resp.text


def test_login_lockout_after_five_failed_attempts(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client

    # Reset any existing lockout state from auth_service module
    import app.services.auth_service as auth_svc
    auth_svc._failed_attempts.pop("lockout_user", None)

    # Seed a user with proper bcrypt password
    pwd_hash = hash_password("ValidPassword123")
    user = seed_user(session, "lockout_user", Role.EMPLOYEE)
    user.password_hash = pwd_hash
    session.commit()

    # 5 consecutive bad password attempts
    for _ in range(5):
        resp = client.post(
            "/auth/login",
            json={"username": "lockout_user", "password": "WrongPassword"},
        )
        assert resp.status_code == 401, resp.text

    # 6th attempt (even with correct password) → 429
    resp_locked = client.post(
        "/auth/login",
        json={"username": "lockout_user", "password": "ValidPassword123"},
    )
    assert resp_locked.status_code == 429, resp_locked.text
