"""
app/core/security.py
Security primitives: bcrypt password hashing, JWT creation/decoding, and HMAC OTP derivation.
"""
from __future__ import annotations

import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt

from app.core.config import settings


DUMMY_HASH = bcrypt.hashpw(b"dummy_password_for_timing_safety", bcrypt.gensalt()).decode("utf-8")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_TTL_MIN)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])


def derive_otp(trip_id: int, stop_id: int) -> str:
    """
    SPEC 10.4:
    derive_otp(trip_id, stop_id) -> str:
    int.from_bytes(hmac.new(OTP_SECRET, f"{trip_id}:{stop_id}".encode(), sha256).digest()[:4], "big") % 10**6,
    zero-padded to 6 digits.
    """
    secret = settings.OTP_SECRET.encode("utf-8")
    msg = f"{trip_id}:{stop_id}".encode("utf-8")
    h = hmac.new(secret, msg, hashlib.sha256).digest()
    num = int.from_bytes(h[:4], "big") % 1000000
    return f"{num:06d}"
