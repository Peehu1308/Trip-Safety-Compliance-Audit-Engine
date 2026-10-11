"""
app/services/audit_engine.py
Orchestrates a full trip audit in a single atomic transaction.
Failure semantics: one failing rule does not abort the others (PARTIAL status).
A DB error rolls back the entire transaction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import perf_counter

from app.core.db import write_tx
from app.core.exceptions import NotFound
from app.rules.registry import ACTIVE_RULES
import app.repositories.trip_repo as trip_repo
import app.repositories.violation_repo as violation_repo
import app.services.context_builder as context_builder
import app.services.violation_service as violation_service
import app.services.audit_log_service as audit_log_service
from app.actions.dispatcher import OutboxDispatcher

log = logging.getLogger(__name__)


@dataclass
class AuditResult:
    trip_id: int
    new: int
    duplicates: int
    total: int
    rule_failures: list[str]
    violations: list = field(default_factory=list)

    @property
    def status(self) -> str:
        return "PARTIAL" if self.rule_failures else "OK"


def run_audit(trip_id: int, actor: str, actor_role: str) -> AuditResult:
    """
    Run all active rules against the trip in one atomic transaction.
    Candidates from all rules are persisted idempotently; a re-audit never
    double-writes or double-notifies (dedupe_key + outbox UNIQUE).
    Post-commit: flush the outbox for newly inserted violations.
    """
    t0 = perf_counter()

    with write_tx() as session:
        trip = trip_repo.get_full(session, trip_id)
        if trip is None:
            raise NotFound(f"Trip {trip_id} not found")

        ctx = context_builder.build(session, trip)

        candidates = []
        failures: list[str] = []

        for rule in ACTIVE_RULES:
            try:
                rule_candidates = rule.evaluate(ctx)
                candidates.extend(rule_candidates)
            except Exception:
                log.exception("Rule %s failed for trip %s", rule.code, trip_id)
                failures.append(rule.code)

        res = violation_service.persist(session, trip_id, candidates, actor, actor_role)

        audit_log_service.append(
            session, actor, actor_role,
            "AUDIT_RUN", "trip", trip_id,
            {
                "new": len(res.new),
                "duplicates": res.duplicates,
                "rule_failures": failures,
            },
        )

        # Collect new violation IDs before session closes
        new_ids = [v.id for v in res.new]
        new_violations_snapshot = list(res.new)

    # Post-commit: dispatch outbox (never raises)
    OutboxDispatcher().flush(new_ids)

    duration = perf_counter() - t0

    # Count total violations (new read after commit)
    with write_tx() as session:
        total = violation_repo.count_for_trip(session, trip_id)

    log.info(
        "Audit complete trip=%s new=%d dup=%d total=%d failures=%s duration=%.3fs",
        trip_id, len(new_ids), res.duplicates, total, failures, duration,
    )

    return AuditResult(
        trip_id=trip_id,
        new=len(new_ids),
        duplicates=res.duplicates,
        total=total,
        rule_failures=failures,
        violations=new_violations_snapshot,
    )
