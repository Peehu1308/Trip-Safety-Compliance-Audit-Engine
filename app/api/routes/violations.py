"""
app/api/routes/violations.py
Violation listing and acknowledgment routes.
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, require_roles
from app.core.db import write_tx
from app.core.exceptions import NotFound
from app.core.timeutil import utcnow
from app.domain.enums import Role, ViolationStatus
from app.models.user import User
from app.schemas.violations import ViolationResponse, ViolationAcknowledgeRequest
import app.repositories.violation_repo as violation_repo
import app.services.audit_log_service as audit_log_service

router = APIRouter(prefix="/violations", tags=["violations"])


@router.get("", response_model=List[ViolationResponse])
def list_violations(
    severity: Optional[str] = None,
    type: Optional[str] = Query(None, alias="type"),
    status: Optional[str] = None,
    trip_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_roles(Role.ADMIN, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    """List violations with filters (ADMIN/APPROVER only)."""
    rows = violation_repo.list_violations(
        db,
        severity=severity,
        vtype=type,
        status=status,
        trip_id=trip_id,
        limit=limit,
        offset=offset,
    )
    return [ViolationResponse.model_validate(r) for r in rows]


@router.patch("/{id}/acknowledge", response_model=ViolationResponse)
def acknowledge_violation(
    id: int,
    req: ViolationAcknowledgeRequest,
    current_user: User = Depends(require_roles(Role.APPROVER)),
):
    """
    Acknowledge a violation (APPROVER only).
    Updates only lifecycle fields (status, acknowledged_by, acknowledged_at, ack_note).
    Audit logged.
    """
    actor_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    ack_time = utcnow()

    with write_tx() as session:
        row = violation_repo.get_by_id(session, id)
        if not row:
            raise NotFound(f"Violation {id} not found")

        row.status = ViolationStatus.ACKNOWLEDGED
        row.acknowledged_by = current_user.username
        row.acknowledged_at = ack_time
        row.ack_note = req.note

        audit_log_service.append(
            session,
            current_user.username,
            actor_role,
            "VIOLATION_ACKNOWLEDGED",
            "violation",
            id,
            {"ack_note": req.note},
        )
        res = ViolationResponse.model_validate(row)

    return res
