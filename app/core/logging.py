"""
app/core/logging.py
Structured logging and PII masking per SPEC 12.2.
JSON lines: ts, level, msg, request_id, trip_id?, violation_id?, actor_id?.
A PIIFilter redacts keys phone, name, home_lat, home_lng, lat, lng, address,
password, otp, token, authorization and masks any 10+ digit run in message strings.
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
from typing import Any, Optional

from app.core.timeutil import utcnow

request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)

PII_KEYS = {
    "phone", "name", "home_lat", "home_lng", "lat", "lng",
    "address", "password", "otp", "token", "authorization",
}

DIGIT_MASK_REGEX = re.compile(r"\b\d{10,}\b")

# Regex to match key=val or key: val or "key": "val" in text
_KEY_VAL_REGEX = re.compile(
    r'(?i)\b(phone|name|home_lat|home_lng|lat|lng|address|password|otp|token|authorization)\b\s*([:=])\s*(["\']?[^"\',\s}{]+["\']?)'
)


def get_request_id() -> str:
    """Return current request id from contextvar or 'system'."""
    rid = request_id_ctx.get()
    return rid or "system"


def redact_pii_obj(obj: Any) -> Any:
    """Recursively redact sensitive keys in dicts/lists and mask digits in strings."""
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if str(k).lower() in PII_KEYS else redact_pii_obj(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [redact_pii_obj(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(redact_pii_obj(item) for item in obj)
    elif isinstance(obj, str):
        return mask_pii_str(obj)
    return obj


def mask_pii_str(msg: str) -> str:
    """Mask 10+ digit runs and sensitive key-value pairs in a message string."""
    # 1. Mask 10+ digit runs (phone numbers, account numbers, etc.)
    masked = DIGIT_MASK_REGEX.sub("[REDACTED_NUMBER]", msg)

    # 2. Redact key: value or key=value patterns for sensitive fields
    def _repl(m: re.Match) -> str:
        key, sep = m.group(1), m.group(2)
        return f"{key}{sep}[REDACTED]"

    masked = _KEY_VAL_REGEX.sub(_repl, masked)
    return masked


class PIIFilter(logging.Filter):
    """
    Logging filter that redacts sensitive keys and masks 10+ digit runs in log records.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_pii_str(record.msg)
        elif isinstance(record.msg, dict):
            record.msg = redact_pii_obj(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_pii_obj(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(redact_pii_obj(a) for a in record.args)
        return True


class JSONFormatter(logging.Formatter):
    """
    JSON lines formatter per SPEC 12.2:
    ts, level, msg, request_id, trip_id?, violation_id?, actor_id?
    """
    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        msg = mask_pii_str(msg)

        payload: dict[str, Any] = {
            "ts": utcnow().isoformat(timespec="microseconds"),
            "level": record.levelname,
            "msg": msg,
            "request_id": getattr(record, "request_id", None) or get_request_id(),
        }

        for attr in ("trip_id", "violation_id", "actor_id"):
            val = getattr(record, attr, None)
            if val is not None:
                payload[attr] = val

        return json.dumps(payload, default=str)
