"""
app/services/violation_service.py
Single path for persisting ViolationCandidates from audit, OTP, and SOS flows.
Idempotency is guaranteed via INSERT … ON CONFLICT(dedupe_key) DO NOTHING.
Actions / notifications fire ONLY for newly inserted rows.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain.dtos import ViolationCandidate
from app.domain.severity import severity_for
from app.actions.base import AlertPayload
from app.actions.router import router
from app.core.timeutil import utcnow
import app.repositories.violation_repo as violation_repo
import app.repositories.outbox_repo as outbox_repo
import app.services.audit_log_service as audit_log_service

log = logging.getLogger(__name__)


def dedupe_key(trip_id: int, vtype, subject_key: str) -> str:
    """sha256(f'{trip_id}|{vtype}|{subject_key}').hexdigest()  – stable & unique.
    vtype may be a ViolationType enum or a plain string; normalised to its value.
    """
    # Normalize: ViolationType is a (str, Enum) so .value gives the bare string
    vtype_str = vtype.value if hasattr(vtype, 'value') else str(vtype)
    raw = f"{trip_id}|{vtype_str}|{subject_key}"
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class PersistResult:
    new: list      # newly created Violation ORM rows
    duplicates: int


def persist(
    session: Session,
    trip_id: int,
    candidates: list[ViolationCandidate],
    actor: str,
    actor_role: str,
) -> PersistResult:
    """
    For each candidate (sorted deterministically by type+subject_key):
      1. Compute dedupe_key → INSERT … ON CONFLICT DO NOTHING.
      2. If new: audit-log, enqueue outbox rows, run state actions, inc metrics.
      3. If duplicate: increment duplicate counter, skip actions.
    Returns PersistResult(new=[...], duplicates=n).
    """
    new_rows = []
    dup_count = 0

    sorted_candidates = sorted(candidates, key=lambda c: (c.type, c.subject_key))

    for c in sorted_candidates:
        dk = dedupe_key(trip_id, c.type, c.subject_key)
        sev = severity_for(c.type)

        row, is_new = violation_repo.insert_if_absent(
            session,
            trip_id=trip_id,
            vtype=c.type,
            severity=sev,    # IntEnum – repo uses .name to get the string
            dedupe_key=dk,
            subject_key=c.subject_key,
            details=c.details,
            detected_by=actor,
        )

        if is_new and row:
            # Audit log
            audit_log_service.append(
                session, actor, actor_role,
                "VIOLATION_RAISED", "violation", row.id,
                {"type": c.type, "severity": str(sev), "trip_id": trip_id, "subject_key": c.subject_key},
            )

            # Build AlertPayload (PII-free)
            emp_ref = c.details.get("employee_ref")
            occurred_at = c.details.get("start_ts") or utcnow().isoformat()
            alert = AlertPayload(
                violation_id=row.id,
                trip_id=trip_id,
                type=c.type,
                severity=str(sev),
                employee_ref=emp_ref,
                location=c.details.get("start"),   # rounded lat/lng if present
                occurred_at=occurred_at,
                summary=f"{c.type} detected on trip {trip_id}",
            )

            # Enqueue outbox rows for all relevant channels
            for ch_name in router.channels_for(int(sev)):
                outbox_repo.enqueue(session, row.id, ch_name, alert)

            # Run state actions inside the transaction
            for action in router.state_actions_for(row):
                try:
                    action.execute(session, row)
                except Exception:
                    log.exception("StateAction %s failed for violation %s", action, row.id)

            new_rows.append(row)
        else:
            dup_count += 1
            log.debug("Duplicate violation skipped: %s for trip %s", dk, trip_id)

    return PersistResult(new=new_rows, duplicates=dup_count)
