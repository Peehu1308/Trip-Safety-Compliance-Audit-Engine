"""
app/schemas/audit.py
Pydantic schemas for audit runs, logs, and verification.
"""
from __future__ import annotations
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict
from app.schemas.violations import ViolationResponse


class AuditResponse(BaseModel):
    trip_id: int
    new: int
    duplicates: int
    total: int
    rule_failures: List[str]
    status: str
    violations: List[ViolationResponse] = []

    model_config = ConfigDict(from_attributes=True)


class AuditLogResponse(BaseModel):
    seq: int
    ts: str
    actor: str
    actor_role: str
    action: str
    entity_type: str
    entity_id: str
    payload_json: str
    prev_hash: Optional[str] = None
    entry_hash: str

    model_config = ConfigDict(from_attributes=True)


class AuditVerifyResponse(BaseModel):
    valid: bool
    checked: int
    first_broken_seq: Optional[int] = None
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
