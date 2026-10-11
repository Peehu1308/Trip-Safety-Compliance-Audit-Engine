"""
app/repositories/outbox_repo.py
DB access for the notification outbox.
UNIQUE(violation_id, channel) prevents duplicate outbox rows on re-audits.
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.models.outbox import NotificationOutbox
from app.actions.base import AlertPayload
from app.core.timeutil import utcnow


def enqueue(
    session: Session,
    violation_id: int,
    channel: str,
    alert: AlertPayload,
) -> None:
    """
    Insert an outbox row for (violation_id, channel) if not already present.
    ON CONFLICT DO NOTHING preserves idempotency across re-audits.
    """
    payload_dict = {
        "violation_id": alert.violation_id,
        "trip_id": alert.trip_id,
        "type": alert.type,
        "severity": alert.severity,
        "employee_ref": alert.employee_ref,
        "location": alert.location,
        "occurred_at": alert.occurred_at,
        "summary": alert.summary,
    }
    stmt = (
        sqlite_insert(NotificationOutbox)
        .values(
            violation_id=violation_id,
            channel=channel,
            payload_json=payload_dict,
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["violation_id", "channel"])
    )
    session.execute(stmt)


def list_outbox(
    session: Session,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[NotificationOutbox]:
    q = select(NotificationOutbox)
    if status is not None:
        q = q.where(NotificationOutbox.status == status)
    q = q.order_by(NotificationOutbox.id.desc()).offset(offset).limit(limit)
    return list(session.scalars(q).all())


def count_pending(session: Session) -> int:
    """Return count of pending notifications in outbox."""
    from sqlalchemy import func
    from app.models.outbox import OutboxStatus
    return session.scalar(
        select(func.count())
        .select_from(NotificationOutbox)
        .where(NotificationOutbox.status == OutboxStatus.PENDING)
    ) or 0

