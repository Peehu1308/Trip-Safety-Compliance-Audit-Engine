"""
app/repositories/violation_repo.py
DB access for Violation rows. INSERT … ON CONFLICT(dedupe_key) DO NOTHING is the
idempotency mechanism. No business rules.
"""
from __future__ import annotations
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models.violation import Violation
from app.core.timeutil import utcnow


def insert_if_absent(
    session: Session,
    trip_id: int,
    vtype: str,
    severity,          # Severity IntEnum or int; stored as its .name string
    dedupe_key: str,
    subject_key: str,
    details: dict,
    detected_by: str,
) -> tuple[Optional[Violation], bool]:
    """
    Insert violation if dedupe_key not present.
    Returns (row, is_new).
    Uses INSERT … ON CONFLICT DO NOTHING for atomicity.
    """
    # Severity is an IntEnum; SAEnum stores the member name ("MEDIUM"/"HIGH"/"CRITICAL")
    severity_name = severity.name if hasattr(severity, "name") else str(severity)
    stmt = (
        sqlite_insert(Violation)
        .values(
            trip_id=trip_id,
            type=vtype,
            severity=severity_name,
            dedupe_key=dedupe_key,
            subject_key=subject_key,
            details=details,
            detected_by=detected_by,
            detected_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )
    result = session.execute(stmt)
    if result.rowcount == 1:
        # Fetch the newly inserted row
        row = session.scalar(select(Violation).where(Violation.dedupe_key == dedupe_key))
        return row, True
    else:
        row = session.scalar(select(Violation).where(Violation.dedupe_key == dedupe_key))
        return row, False


def count_for_trip(session: Session, trip_id: int) -> int:
    return session.scalar(
        select(func.count()).select_from(Violation).where(Violation.trip_id == trip_id)
    ) or 0


def get_by_id(session: Session, violation_id: int) -> Optional[Violation]:
    return session.get(Violation, violation_id)


def list_for_trip(session: Session, trip_id: int) -> list[Violation]:
    return list(session.scalars(
        select(Violation).where(Violation.trip_id == trip_id).order_by(Violation.id.asc())
    ).all())


def list_violations(
    session: Session,
    severity: Optional[str] = None,
    vtype: Optional[str] = None,
    status: Optional[str] = None,
    trip_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Violation]:
    q = select(Violation)
    if severity is not None:
        q = q.where(Violation.severity == severity)
    if vtype is not None:
        q = q.where(Violation.type == vtype)
    if status is not None:
        q = q.where(Violation.status == status)
    if trip_id is not None:
        q = q.where(Violation.trip_id == trip_id)
    q = q.order_by(Violation.id.desc()).offset(offset).limit(limit)
    return list(session.scalars(q).all())
