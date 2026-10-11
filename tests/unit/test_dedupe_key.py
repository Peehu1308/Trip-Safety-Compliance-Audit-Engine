"""tests/unit/test_dedupe_key.py – stable and unique dedupe key."""
from app.services.violation_service import dedupe_key


def test_stable():
    k1 = dedupe_key(1, "NIGHT_SAFETY", "stop:5:LAST_DROP")
    k2 = dedupe_key(1, "NIGHT_SAFETY", "stop:5:LAST_DROP")
    assert k1 == k2


def test_different_trip():
    k1 = dedupe_key(1, "NIGHT_SAFETY", "stop:5:LAST_DROP")
    k2 = dedupe_key(2, "NIGHT_SAFETY", "stop:5:LAST_DROP")
    assert k1 != k2


def test_different_type():
    k1 = dedupe_key(1, "NIGHT_SAFETY", "stop:5:LAST_DROP")
    k2 = dedupe_key(1, "SOS", "stop:5:LAST_DROP")
    assert k1 != k2


def test_different_subject():
    k1 = dedupe_key(1, "NIGHT_SAFETY", "stop:5:LAST_DROP")
    k2 = dedupe_key(1, "NIGHT_SAFETY", "stop:5:FIRST_PICKUP")
    assert k1 != k2


def test_is_hex_string():
    k = dedupe_key(42, "SOS", "sos:7")
    assert len(k) == 64
    int(k, 16)   # must be valid hex
