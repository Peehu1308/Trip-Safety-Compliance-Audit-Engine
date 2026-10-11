"""
tests/integration/test_outbox.py

SPEC section 12.5 / actions/dispatcher.py:
  - Forcing a channel to fail marks the outbox row FAILED; API still returns 200.
  - Retry (flush again) marks the row SENT once the channel is fixed.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.services.audit_engine import run_audit
from app.models.outbox import NotificationOutbox
from app.domain.enums import OutboxStatus
from app.actions import channels as channels_mod
from app.actions.dispatcher import OutboxDispatcher


@pytest.fixture(autouse=True)
def reset_fail_channels():
    """Ensure FAIL_CHANNELS is clean before/after each test."""
    channels_mod.FAIL_CHANNELS.clear()
    yield
    channels_mod.FAIL_CHANNELS.clear()


def test_failed_channel_marks_row_failed(minimal_trip):
    session, trip, stop, emp = minimal_trip

    # Force all channels to fail
    channels_mod.FAIL_CHANNELS.update(["log", "manager", "security_pager", "dashboard"])

    result = run_audit(trip.id, "system", "ADMIN")
    assert result.new >= 1, "Should detect at least one violation"

    S = sessionmaker(bind=session.bind)
    s = S()
    failed_rows = s.scalars(
        select(NotificationOutbox).where(NotificationOutbox.status == OutboxStatus.FAILED)
    ).all()
    s.close()

    assert len(failed_rows) > 0, "At least one outbox row should be FAILED"


def test_retry_after_fix(minimal_trip):
    session, trip, stop, emp = minimal_trip

    channels_mod.FAIL_CHANNELS.update(["log", "manager", "security_pager", "dashboard"])

    run_audit(trip.id, "system", "ADMIN")

    # Fix channels
    channels_mod.FAIL_CHANNELS.clear()

    # Retry dispatch
    disp = OutboxDispatcher()
    dispatch_result = disp.flush()

    S = sessionmaker(bind=session.bind)
    s = S()
    sent_rows = s.scalars(
        select(NotificationOutbox).where(NotificationOutbox.status == OutboxStatus.SENT)
    ).all()
    s.close()

    assert len(sent_rows) > 0, "Rows should be SENT after retry"
    assert dispatch_result.sent > 0
