"""
app/api/routes/ops.py
Operational routes: health, Prometheus metrics, and notification outbox management.
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import text
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.api.deps import get_db, require_roles
from app.domain.enums import Role
from app.models.user import User
from app.models.outbox import NotificationOutbox
from app.actions.dispatcher import OutboxDispatcher
import app.repositories.outbox_repo as outbox_repo

router = APIRouter(tags=["ops"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Health check endpoint: verifies DB connectivity."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}


@router.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/notifications/outbox")
def list_outbox(
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Inspect notification outbox (ADMIN only)."""
    rows = outbox_repo.list_outbox(db, status=status, limit=limit, offset=offset)
    return [
        {
            "id": r.id,
            "violation_id": r.violation_id,
            "channel": r.channel,
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "attempts": r.attempts,
            "last_error": r.last_error,
            "payload_json": r.payload_json,
            "created_at": r.created_at,
            "sent_at": r.sent_at,
        }
        for r in rows
    ]


@router.post("/notifications/outbox/retry")
def retry_outbox(
    current_user: User = Depends(require_roles(Role.ADMIN)),
):
    """Retry failed notifications in outbox (ADMIN only)."""
    dispatcher = OutboxDispatcher()
    res = dispatcher.flush()
    return {"sent": res.sent, "failed": res.failed, "skipped": res.skipped}
