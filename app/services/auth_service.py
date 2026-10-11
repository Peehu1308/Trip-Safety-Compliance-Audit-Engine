"""
app/services/auth_service.py
Authentication service implementing login with timing-safe password verification,
in-memory rate limiting (5 failures / 15 min per username -> 429), and JWT generation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from sqlalchemy.orm import Session

from app.core.exceptions import Unauthorized, TooManyRequests
from app.core.security import verify_password, create_access_token, DUMMY_HASH
from app.core.metrics import auth_failures_total
import app.repositories.user_repo as user_repo
from app.schemas.auth import TokenResponse

log = logging.getLogger(__name__)

# In-memory failed login attempts tracker: username -> list of utc failure datetimes
_failed_attempts: Dict[str, List[datetime]] = {}
MAX_FAILURES = 5
LOCKOUT_MINUTES = 15


def _record_failure(username: str) -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=LOCKOUT_MINUTES)
    attempts = [t for t in _failed_attempts.get(username, []) if t > cutoff]
    attempts.append(now)
    _failed_attempts[username] = attempts
    auth_failures_total.inc()


def _check_rate_limit(username: str) -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=LOCKOUT_MINUTES)
    attempts = [t for t in _failed_attempts.get(username, []) if t > cutoff]
    _failed_attempts[username] = attempts
    if len(attempts) >= MAX_FAILURES:
        log.warning("Lockout triggered for username %s (failed attempts: %d)", username, len(attempts))
        raise TooManyRequests("Too many failed login attempts. Try again in 15 minutes.")


def login(session: Session, username: str, password: str) -> TokenResponse:
    """
    Authenticate user and return JWT access token.
    Timing-safe: always executes bcrypt verification.
    """
    _check_rate_limit(username)

    user = user_repo.get_by_username(session, username)
    if user is None:
        # Constant-time dummy verification
        verify_password(password, DUMMY_HASH)
        _record_failure(username)
        raise Unauthorized("Invalid username or password")

    if not verify_password(password, user.password_hash):
        _record_failure(username)
        raise Unauthorized("Invalid username or password")

    if not user.is_active:
        raise Unauthorized("Account is inactive")

    # Successful login: reset failed attempts
    _failed_attempts.pop(username, None)

    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    token_payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": role_val,
    }
    access_token = create_access_token(token_payload)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        role=role_val,
    )
