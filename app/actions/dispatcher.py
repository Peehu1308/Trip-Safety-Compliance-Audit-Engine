"""
app/actions/dispatcher.py
OutboxDispatcher: flush PENDING/FAILED outbox rows after commit.
Never raises – a failing channel records FAILED + last_error.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    sent: int = 0
    failed: int = 0
    skipped: int = 0


class OutboxDispatcher:
    """
    Flush outbox rows post-commit (after the transaction that created them).
    SPEC 10.1: flush([violation_ids]) → DispatchResult; never raises.
    """

    MAX_ATTEMPTS = 5

    def flush(self, violation_ids: list[int] | None = None) -> DispatchResult:
        from app.core.db import SessionLocal
        from app.models.outbox import NotificationOutbox
        from app.domain.enums import OutboxStatus
        from app.actions.channels import CHANNEL_REGISTRY
        from app.actions.base import AlertPayload
        from sqlalchemy import select, and_, or_

        result = DispatchResult()
        session = SessionLocal()
        try:
            q = select(NotificationOutbox).where(
                or_(
                    NotificationOutbox.status == OutboxStatus.PENDING,
                    NotificationOutbox.status == OutboxStatus.FAILED,
                ),
                NotificationOutbox.attempts < self.MAX_ATTEMPTS,
            )
            if violation_ids is not None:
                q = q.where(NotificationOutbox.violation_id.in_(violation_ids))

            rows = session.scalars(q).all()
            for row in rows:
                channel = CHANNEL_REGISTRY.get(row.channel)
                if channel is None:
                    log.warning("Unknown channel %s – skipping", row.channel)
                    result.skipped += 1
                    continue

                # Rebuild AlertPayload from stored JSON
                payload_data = row.payload_json if isinstance(row.payload_json, dict) else json.loads(row.payload_json)
                alert = AlertPayload(**payload_data)

                row.attempts += 1
                try:
                    channel.send(alert)
                    row.status = OutboxStatus.SENT
                    from app.core.timeutil import utcnow
                    row.sent_at = utcnow()
                    result.sent += 1
                except Exception as exc:
                    row.status = OutboxStatus.FAILED
                    row.last_error = str(exc)[:512]
                    result.failed += 1
                    log.warning("Channel %s failed: %s", row.channel, exc)

            session.commit()
        except Exception:
            log.exception("OutboxDispatcher.flush error")
            session.rollback()
        finally:
            session.close()

        return result
