"""
tests/integration/test_failure_isolation.py

SPEC section 12.5 / audit_engine.run_audit():
  - If one rule raises, the audit returns PARTIAL.
  - Other rules' violations are still persisted.
"""
import pytest
from unittest.mock import patch

from app.services.audit_engine import run_audit
from app.rules.night_safety import NightSafetyRule


def test_failing_rule_gives_partial(minimal_trip):
    session, trip, stop, emp = minimal_trip
    trip_id = trip.id

    def boom(self, ctx):
        raise RuntimeError("Simulated rule failure")

    with patch.object(NightSafetyRule, "evaluate", boom):
        result = run_audit(trip_id, "system", "ADMIN")

    assert result.status == "PARTIAL"
    assert NightSafetyRule.code in result.rule_failures


def test_other_rules_persist_when_one_fails(minimal_trip):
    """
    NightSafetyRule raises; other rules should still run.
    The minimal_trip has no OTP events/SOS, so total may be 0.
    The key: audit does NOT raise – transaction completed.
    """
    session, trip, stop, emp = minimal_trip
    trip_id = trip.id

    def boom_ns(self, ctx):
        raise RuntimeError("NS boom")

    with patch.object(NightSafetyRule, "evaluate", boom_ns):
        result = run_audit(trip_id, "system", "ADMIN")

    assert result.status == "PARTIAL"
    assert result.rule_failures == [NightSafetyRule.code]
    # No unhandled exception = other rules ran fine
