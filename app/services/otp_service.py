"""
app/services/otp_service.py
OTP verification, stop completion/freeze, and unfreeze operations per SPEC 10.4.
Important: On mismatch, commit first, then return HTTP 409 body {"result": "MISMATCH", "stop_status": "FROZEN"}.
"""
from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import update

from app.core.config import settings
from app.core.db import write_tx
from app.core.exceptions import NotFound, Conflict, Forbidden, ValidationFailed, StopFrozen
from app.core.timeutil import utcnow
from app.core.security import derive_otp
from app.core.metrics import otp_attempts_total
from app.domain.enums import Role, StopType, StopStatus, ViolationType
from app.domain.dtos import ViolationCandidate
from app.models.trip import Stop
from app.models.events import OtpEvent
from app.models.user import User
import app.repositories.trip_repo as trip_repo
import app.repositories.event_repo as event_repo
import app.repositories.user_repo as user_repo
import app.services.violation_service as violation_service
import app.services.audit_log_service as audit_log_service
from app.actions.dispatcher import OutboxDispatcher

log = logging.getLogger(__name__)


@dataclass
class OtpResult:
    result: str            # "OK" or "MISMATCH"
    stop_status: str       # "COMPLETED" or "FROZEN"
    is_mismatch: bool = False


def submit_otp(trip_id: int, stop_id: int, otp: str, actor_user: User) -> OtpResult:
    """
    Submit OTP for a drop stop.
    Steps per SPEC 10.4:
      1. Load trip + stop; stop must belong to trip and be type DROP (else 422)
      2. Authz: actor is trip's driver or ADMIN (else 403)
      3. Stop.status == COMPLETED -> raise Conflict(409); FROZEN -> raise StopFrozen(423)
      4. Expected = derive_otp(trip_id, stop_id); ok = hmac.compare_digest(expected, otp)
      5. Attempt_no = count + 1; insert OtpEvent(success=ok, attempt_no)
      6. If ok:
           atomic UPDATE stops SET status='COMPLETED', actual_time=:now WHERE id=:id AND status='PENDING'
           audit_log.append("OTP_ATTEMPT", {stop_id, result:"OK", attempt_no})
         else:
           atomic UPDATE stops SET status='FROZEN', otp_failures=otp_failures+1 WHERE id=:id AND status='PENDING'
           violation_service.persist(s, trip_id, [Candidate(OTP_MISMATCH, ...)])
           audit_log.append("OTP_ATTEMPT", {stop_id, result:"MISMATCH", attempt_no})
           metrics.otp_attempts_total.labels("mismatch").inc()
      Post-commit: flush outbox.
      For MISMATCH: returns OtpResult(result='MISMATCH', stop_status='FROZEN', is_mismatch=True)
    """
    actor_username = actor_user.username
    actor_role = actor_user.role.value if hasattr(actor_user.role, "value") else str(actor_user.role)

    new_violation_ids: list[int] = []

    with write_tx() as session:
        trip = trip_repo.get_full(session, trip_id)
        if not trip:
            raise NotFound(f"Trip {trip_id} not found")

        stop = trip_repo.get_stop(session, stop_id)
        if not stop or stop.trip_id != trip_id:
            raise ValidationFailed(f"Stop {stop_id} does not belong to trip {trip_id}")

        if stop.type != StopType.DROP:
            raise ValidationFailed("OTP submission is only valid for DROP stops")

        # Authz: actor is trip's driver or ADMIN
        if actor_user.role == Role.ADMIN or actor_role == "ADMIN":
            pass
        elif actor_user.role == Role.DRIVER or actor_role == "DRIVER":
            driver = user_repo.get_driver_by_user_id(session, actor_user.id)
            if not driver or trip.driver_id != driver.id:
                raise Forbidden("Driver is not assigned to this trip")
        else:
            raise Forbidden("Only trip's driver or ADMIN can submit OTP")

        # Check current status
        if stop.status == StopStatus.COMPLETED:
            raise Conflict("Stop is already completed")
        if stop.status == StopStatus.FROZEN:
            raise StopFrozen("Stop is frozen")

        expected = derive_otp(trip_id, stop_id)
        ok = hmac.compare_digest(expected, otp)

        attempt_no = event_repo.count_otp_events(session, stop_id) + 1
        now = utcnow()

        otp_event = OtpEvent(
            trip_id=trip_id,
            stop_id=stop_id,
            actor_user_id=actor_user.id,
            success=ok,
            attempt_no=attempt_no,
            ts=now,
        )
        session.add(otp_event)
        session.flush()

        if ok:
            # Atomic update
            res = session.execute(
                update(Stop)
                .where(Stop.id == stop_id, Stop.status == StopStatus.PENDING)
                .values(status=StopStatus.COMPLETED, actual_time=now)
            )
            if res.rowcount == 0:
                fresh_stop = session.get(Stop, stop_id)
                if fresh_stop and fresh_stop.status == StopStatus.COMPLETED:
                    raise Conflict("Stop is already completed")
                elif fresh_stop and fresh_stop.status == StopStatus.FROZEN:
                    raise StopFrozen("Stop is frozen")
                else:
                    raise Conflict("Stop cannot be completed")

            audit_log_service.append(
                session,
                actor_username,
                actor_role,
                "OTP_ATTEMPT",
                "stop",
                stop_id,
                {"stop_id": stop_id, "result": "OK", "attempt_no": attempt_no},
            )
            otp_attempts_total.labels("ok").inc()
            session.flush()
            result = OtpResult(result="OK", stop_status="COMPLETED", is_mismatch=False)
        else:
            # Atomic update to FROZEN
            res = session.execute(
                update(Stop)
                .where(Stop.id == stop_id, Stop.status == StopStatus.PENDING)
                .values(status=StopStatus.FROZEN, otp_failures=Stop.otp_failures + 1)
            )
            if res.rowcount == 0:
                fresh_stop = session.get(Stop, stop_id)
                if fresh_stop and fresh_stop.status == StopStatus.COMPLETED:
                    raise Conflict("Stop is already completed")
                elif fresh_stop and fresh_stop.status == StopStatus.FROZEN:
                    raise StopFrozen("Stop is frozen")

            candidate = ViolationCandidate(
                type=ViolationType.OTP_MISMATCH.value,
                subject_key=f"stop:{stop_id}",
                details={
                    "stop_id": stop_id,
                    "attempt_no": attempt_no,
                    "employee_id": stop.employee_id,
                },
            )
            persist_res = violation_service.persist(
                session,
                trip_id,
                [candidate],
                actor=actor_username,
                actor_role=actor_role,
            )
            new_violation_ids = [v.id for v in persist_res.new]

            audit_log_service.append(
                session,
                actor_username,
                actor_role,
                "OTP_ATTEMPT",
                "stop",
                stop_id,
                {"stop_id": stop_id, "result": "MISMATCH", "attempt_no": attempt_no},
            )
            otp_attempts_total.labels("mismatch").inc()
            session.flush()
            result = OtpResult(result="MISMATCH", stop_status="FROZEN", is_mismatch=True)

    # Post-commit: flush outbox if mismatch generated violation
    if new_violation_ids:
        OutboxDispatcher().flush(new_violation_ids)

    return result


def unfreeze(trip_id: int, stop_id: int, actor: str, actor_role: str, reason: str) -> dict:
    """
    Unfreeze a stop per SPEC 10.4:
      ADMIN/APPROVER only; stop must be FROZEN;
      Refused (409) if otp_failures >= MAX_OTP_FAILURES;
      Sets status back to PENDING; audit log STOP_UNFROZEN.
    """
    with write_tx() as session:
        trip = trip_repo.get_full(session, trip_id)
        if not trip:
            raise NotFound(f"Trip {trip_id} not found")

        stop = trip_repo.get_stop(session, stop_id)
        if not stop or stop.trip_id != trip_id:
            raise ValidationFailed(f"Stop {stop_id} does not belong to trip {trip_id}")

        if stop.status != StopStatus.FROZEN:
            raise Conflict("Stop is not frozen")

        if stop.otp_failures >= settings.MAX_OTP_FAILURES:
            raise Conflict(f"Maximum OTP failures reached ({stop.otp_failures}); cannot unfreeze")

        stop.status = StopStatus.PENDING
        audit_log_service.append(
            session,
            actor,
            actor_role,
            "STOP_UNFROZEN",
            "stop",
            stop_id,
            {"reason": reason, "trip_id": trip_id},
        )
        session.flush()
        return {"status": "unfrozen", "stop_id": stop_id}
