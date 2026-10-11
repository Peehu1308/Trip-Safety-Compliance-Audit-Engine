"""
app/repositories/audit_repo.py
Repository for audit_log entries. DB access only; no business rules.
"""
from __future__ import annotations

from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def last(session: Session) -> Optional[AuditLog]:
    """Return the last AuditLog row ordered by seq DESC, or None."""
    return session.scalar(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1))


def insert(session: Session, entry: AuditLog) -> AuditLog:
    """Insert a new audit_log row."""
    session.add(entry)
    session.flush()
    return entry


def list_entries(session: Session, limit: int = 100, offset: int = 0) -> List[AuditLog]:
    """Return audit log entries ordered by seq ASC with pagination."""
    return list(
        session.scalars(
            select(AuditLog).order_by(AuditLog.seq.asc()).offset(offset).limit(limit)
        ).all()
    )


def get_all(session: Session) -> List[AuditLog]:
    """Return all audit log entries ordered by seq ASC."""
    return list(session.scalars(select(AuditLog).order_by(AuditLog.seq.asc())).all())


def count(session: Session) -> int:
    """Return total count of audit_log rows."""
    return session.scalar(select(func.count()).select_from(AuditLog)) or 0
