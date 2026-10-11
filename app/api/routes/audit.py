"""
app/api/routes/audit.py
Audit log inspection and verification routes (SPEC 11).
"""
from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.domain.enums import Role
from app.models.user import User
import app.repositories.audit_repo as audit_repo
import app.services.audit_log_service as audit_log_service
from app.schemas.audit import AuditLogResponse, AuditVerifyResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/log", response_model=List[AuditLogResponse])
def get_audit_log(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_roles(Role.ADMIN, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    """Retrieve audit log entries (ADMIN/APPROVER only)."""
    rows = audit_repo.list_entries(db, limit=limit, offset=offset)
    return [AuditLogResponse.model_validate(r) for r in rows]


@router.get("/verify", response_model=AuditVerifyResponse)
def verify_audit_log(
    current_user: User = Depends(require_roles(Role.ADMIN, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    """Verify hash chain integrity (ADMIN/APPROVER only)."""
    res = audit_log_service.verify(db)
    return AuditVerifyResponse(
        valid=res.valid,
        checked=res.checked,
        first_broken_seq=res.first_broken_seq,
        reason=res.reason,
    )
