"""
app/services/sos_service.py
SOS panic alert service per SPEC 10.5.
Creates CRITICAL violation and flushes outbox synchronously.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.config import settings
from app.core.db import write_tx
from app.core.exceptions import NotFound, Forbidden
from app.core.timeutil import utcnow
from app.core.metrics import sos_total
from app.domain.enums import ViolationType
from app.domain.dtos import ViolationCandidate
from app.models.events import SosEvent
from app.models.user import User
import app.repositories.trip_repo as trip_repo
import app.repositories.user_repo as user_repo
import app.repositories.gps_repo as gps_repo
import app.services.violation_service as violation_service
import app.services.audit_log_service as audit_log_service
from app.actions.dispatcher import OutboxDispatcher

log = logging.getLogger(__name__)


def raise_sos(
    trip_id: int,
    employee_user: User,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> dict:
    """
    Raise an SOS panic alarm.
    Steps per SPEC 10.5:
      - Authz: employee must be a passenger on this trip (appears in a stop) else 403
      - Location: request lat/lng if given -> REQUEST; else last GPS fix -> LAST_GPS; else UNKNOWN
      - Insert SosEvent
      - Persist SOS violation
      - Audit log SOS_RAISED
      - metrics.sos_total.inc()
      - OutboxDispatcher().flush(new_ids) IMMEDIATELY
      - Return {sos_event_id, violation_id, location_source}
    """
    actor_username = employee_user.username
    actor_role = employee_user.role.value if hasattr(employee_user.role, "value") else str(employee_user.role)

    with write_tx() as session:
        trip = trip_repo.get_full(session, trip_id)
        if not trip:
            raise NotFound(f"Trip {trip_id} not found")

        # Find employee profile for user
        emp = user_repo.get_employee_by_user_id(session, employee_user.id)
        if not emp:
            raise Forbidden("User has no associated employee profile")

        # Must be a passenger on this trip
        is_passenger = any(s.employee_id == emp.id for s in trip.stops)
        if not is_passenger:
            raise Forbidden("Employee is not a passenger on this trip")

        # Location source logic
        if lat is not None and lng is not None:
            resolved_lat = round(lat, settings.SOS_COORD_DECIMALS)
            resolved_lng = round(lng, settings.SOS_COORD_DECIMALS)
            location_source = "REQUEST"
        else:
            last_gps = gps_repo.get_latest_for_trip(session, trip_id)
            if last_gps:
                resolved_lat = round(last_gps.lat, settings.SOS_COORD_DECIMALS)
                resolved_lng = round(last_gps.lng, settings.SOS_COORD_DECIMALS)
                location_source = "LAST_GPS"
            else:
                resolved_lat = None
                resolved_lng = None
                location_source = "UNKNOWN"

        now = utcnow()
        sos_event = SosEvent(
            trip_id=trip_id,
            employee_id=emp.id,
            lat=resolved_lat,
            lng=resolved_lng,
            location_source=location_source,
            ts=now,
        )
        session.add(sos_event)
        session.flush()

        details = {
            "employee_id": emp.id,
            "employee_ref": emp.id,
            "location_source": location_source,
            "lat": resolved_lat,
            "lng": resolved_lng,
            "start_ts": now.isoformat(),
        }
        candidate = ViolationCandidate(
            type=ViolationType.SOS.value,
            subject_key=f"sos:{sos_event.id}",
            details=details,
        )

        persist_res = violation_service.persist(
            session,
            trip_id,
            [candidate],
            actor=actor_username,
            actor_role=actor_role,
        )
        new_violation_ids = [v.id for v in persist_res.new]
        violation_id = new_violation_ids[0] if new_violation_ids else None

        audit_log_service.append(
            session,
            actor_username,
            actor_role,
            "SOS_RAISED",
            "sos_event",
            sos_event.id,
            {
                "trip_id": trip_id,
                "location_source": location_source,
                "lat": resolved_lat,
                "lng": resolved_lng,
                "violation_id": violation_id,
            },
        )

        sos_total.inc()
        session.flush()
        res = {
            "sos_event_id": sos_event.id,
            "violation_id": violation_id,
            "location_source": location_source,
        }

    # Flush outbox immediately post-commit (CRITICAL notifications)
    if new_violation_ids:
        OutboxDispatcher().flush(new_violation_ids)

    return res
