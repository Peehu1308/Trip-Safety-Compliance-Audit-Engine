"""
app/api/deps.py
Authentication, authorization, and ownership dependencies per SPEC Section 11.
"""
from __future__ import annotations

from typing import Generator, Callable
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import jwt

from app.core.db import SessionLocal
from app.core.exceptions import Unauthorized, Forbidden, NotFound
from app.core.security import decode_access_token
from app.domain.enums import Role
from app.models.user import User
from app.models.trip import Trip
from app.models.people import Employee, Driver
import app.repositories.user_repo as user_repo
import app.repositories.trip_repo as trip_repo

http_bearer = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session (looks up SessionLocal lazily for test override)."""
    import app.core.db as _db_mod
    session = _db_mod.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> User:
    """
    Validate Authorization Bearer JWT and return active User.
    Raises 401 Unauthorized if missing, expired, invalid, or inactive.
    """
    if not credentials or not credentials.credentials:
        raise Unauthorized("Missing or invalid Authorization header")

    token = credentials.credentials.strip()
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token has expired")
    except Exception:
        raise Unauthorized("Invalid authentication token")

    sub = payload.get("sub")
    if not sub:
        raise Unauthorized("Invalid token subject")

    # Look up by integer user id or username
    user = None
    if sub.isdigit():
        user = user_repo.get_by_id(db, int(sub))
    if user is None:
        user = user_repo.get_by_username(db, sub)

    if not user or not user.is_active:
        raise Unauthorized("User not found or inactive")

    return user


def require_roles(*roles: Role | str) -> Callable[[User], User]:
    """
    Enforce role-based access control (RBAC).
    Raises 403 Forbidden if current user role is not permitted.
    """
    allowed = set()
    for r in roles:
        if isinstance(r, Role):
            allowed.add(r.value)
        else:
            allowed.add(str(r))

    def _role_checker(user: User = Depends(get_current_user)) -> User:
        user_role = user.role.value if hasattr(user.role, "value") else str(user.role)
        if user_role not in allowed:
            raise Forbidden(f"User role {user_role} is not authorized for this resource")
        return user

    return _role_checker


def assert_driver_of_trip(trip: Trip, user: User, db: Session) -> None:
    """
    Ownership check: ensures user is trip's assigned driver or ADMIN.
    Raises 403 Forbidden otherwise.
    """
    user_role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if user_role == Role.ADMIN.value:
        return

    if user_role == Role.DRIVER.value:
        driver = user_repo.get_driver_by_user_id(db, user.id)
        if driver and trip.driver_id == driver.id:
            return

    raise Forbidden("Driver is not assigned to this trip")


def assert_passenger_of_trip(trip: Trip, user: User, db: Session) -> Employee:
    """
    Ownership check: ensures user is a passenger on the trip (or ADMIN/APPROVER).
    Raises 403 Forbidden otherwise.
    """
    user_role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if user_role in (Role.ADMIN.value, Role.APPROVER.value):
        emp = user_repo.get_employee_by_user_id(db, user.id)
        return emp  # Can be None if pure admin

    if user_role == Role.EMPLOYEE.value:
        emp = user_repo.get_employee_by_user_id(db, user.id)
        if emp and any(s.employee_id == emp.id for s in trip.stops):
            return emp

    raise Forbidden("Employee is not a passenger on this trip")
