"""
app/services/audit_log_service.py
Append-only tamper-evident audit log service using SHA-256 hash chains per SPEC 10.6.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.audit_log import AuditLog
import app.repositories.audit_repo as audit_repo

log = logging.getLogger(__name__)


@dataclass
class VerifyResult:
    valid: bool
    checked: int
    first_broken_seq: Optional[int] = None
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "checked": self.checked,
            "first_broken_seq": self.first_broken_seq,
            "reason": self.reason,
        }

    def __getitem__(self, item: str):
        return getattr(self, item)


def canonical(obj: Any) -> str:
    """Return canonical JSON representation: sorted keys, compact separators."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_entry_hash(
    seq: int,
    ts: str,
    actor: str,
    actor_role: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload_json: str,
    prev_hash: str,
) -> str:
    """
    Compute entry_hash = sha256(prev_hash + body).
    where body is canonical JSON of:
    {"seq": seq, "ts": ts, "actor": actor, "actor_role": actor_role, "action": action,
     "entity_type": entity_type, "entity_id": str(entity_id), "payload": payload_json}
    """
    body = canonical({
        "seq": seq,
        "ts": ts,
        "actor": actor,
        "actor_role": actor_role,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "payload": payload_json,
    })
    return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()


def append(
    session: Session,
    actor: str,
    actor_role: str,
    action: str,
    entity_type: str,
    entity_id: object,
    payload: dict,
) -> AuditLog:
    """
    Append an entry to the tamper-evident audit log per SPEC 10.6.
    Runs inside the caller's BEGIN IMMEDIATE transaction.
    """
    last_row = audit_repo.last(session)
    seq = 1 if not last_row else last_row.seq + 1
    prev_hash = "0" * 64 if not last_row else last_row.entry_hash
    ts = utcnow().isoformat(timespec="microseconds")
    payload_json = canonical(payload)

    entry_hash = compute_entry_hash(
        seq=seq,
        ts=ts,
        actor=str(actor),
        actor_role=str(actor_role),
        action=str(action),
        entity_type=str(entity_type),
        entity_id=str(entity_id),
        payload_json=payload_json,
        prev_hash=prev_hash,
    )

    row = AuditLog(
        seq=seq,
        ts=ts,
        actor=str(actor),
        actor_role=str(actor_role),
        action=str(action),
        entity_type=str(entity_type),
        entity_id=str(entity_id),
        payload_json=payload_json,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    return audit_repo.insert(session, row)


def verify(session: Session) -> VerifyResult:
    """
    Walk by seq ascending; check seq contiguity, prev_hash links, recomputed entry_hash. O(N).
    """
    entries = audit_repo.get_all(session)
    if not entries:
        return VerifyResult(valid=True, checked=0, first_broken_seq=None, reason=None)

    expected_seq = 1
    expected_prev_hash = "0" * 64

    for i, row in enumerate(entries):
        # 1. Contiguity check
        if row.seq != expected_seq:
            return VerifyResult(
                valid=False,
                checked=i,
                first_broken_seq=row.seq,
                reason=f"seq gap: expected {expected_seq}, got {row.seq}",
            )

        # 2. prev_hash link check
        if row.prev_hash != expected_prev_hash:
            return VerifyResult(
                valid=False,
                checked=i,
                first_broken_seq=row.seq,
                reason=f"prev_hash mismatch at seq {row.seq}",
            )

        # 3. Hash integrity check
        recomputed = compute_entry_hash(
            seq=row.seq,
            ts=row.ts,
            actor=row.actor,
            actor_role=row.actor_role,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            payload_json=row.payload_json,
            prev_hash=row.prev_hash,
        )
        if row.entry_hash != recomputed:
            return VerifyResult(
                valid=False,
                checked=i,
                first_broken_seq=row.seq,
                reason=f"Hash mismatch at seq {row.seq}",
            )

        expected_prev_hash = row.entry_hash
        expected_seq = row.seq + 1

    return VerifyResult(
        valid=True,
        checked=len(entries),
        first_broken_seq=None,
        reason=None,
    )
