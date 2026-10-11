"""
app/services/trip_service.py
Trip lifecycle management, escort updates, completion, and GPS batch ingestion.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List
from sqlalchemy.orm import Session

from app.core.db import write_tx
from app.core.exceptions import NotFound, ValidationFailed
from app.core.timeutil import utcnow
from app.domain.enums import TripStatus, StopType
from app.models.trip import Trip, Stop
import app.repositories.trip_repo as trip_repo
import app.repositories.user_repo as user_repo
import app.repositories.gps_repo as gps_repo
import app.services.audit_log_service as audit_log_service
from app.services.audit_engine import run_audit, AuditResult
from app.schemas.trips import TripCreate

log = logging.getLogger(__name__)


def create_trip(dto: TripCreate, actor: str, actor_role: str) -> Trip:
    """
    Validate and create a trip with stops.
    Validations (SPEC 10.7):
      - route >= 2 points
      - limits list length = points - 1 if given
      - stop sequences unique and 1..n
      - planned_time non-decreasing by sequence
      - each employee has exactly one PICKUP and one DROP, pickup sequence < drop sequence
      - employees/driver/vehicle exist
      - Audit TRIP_CREATED
    """
    if len(dto.planned_route) < 2:
        raise ValidationFailed("Planned route must have at least 2 points")

    for pt in dto.planned_route:
        if len(pt) < 2:
            raise ValidationFailed("Each point in planned route must have [lat, lng]")

    if dto.segment_speed_limits is not None:
        if len(dto.segment_speed_limits) != len(dto.planned_route) - 1:
            raise ValidationFailed("segment_speed_limits length must equal len(planned_route) - 1")

    if not dto.stops:
        raise ValidationFailed("Trip must have at least one stop")

    seqs = [s.sequence for s in dto.stops]
    if sorted(seqs) != list(range(1, len(dto.stops) + 1)):
        raise ValidationFailed("Stop sequences must be unique and form 1..n")

    sorted_stops = sorted(dto.stops, key=lambda s: s.sequence)
    for i in range(len(sorted_stops) - 1):
        if sorted_stops[i].planned_time > sorted_stops[i + 1].planned_time:
            raise ValidationFailed("Stop planned_time must be non-decreasing by sequence")

    emp_stops: dict[int, list[Any]] = {}
    for s in sorted_stops:
        emp_stops.setdefault(s.employee_id, []).append(s)

    for emp_id, s_list in emp_stops.items():
        pickups = [s for s in s_list if s.type == StopType.PICKUP]
        drops = [s for s in s_list if s.type == StopType.DROP]
        if len(pickups) != 1 or len(drops) != 1:
            raise ValidationFailed(f"Employee {emp_id} must have exactly one PICKUP and one DROP")
        if pickups[0].sequence >= drops[0].sequence:
            raise ValidationFailed(f"Employee {emp_id} PICKUP sequence must precede DROP sequence")

    with write_tx() as session:
        driver = user_repo.get_driver_by_id(session, dto.driver_id)
        if not driver:
            raise ValidationFailed(f"Driver {dto.driver_id} not found")

        vehicle = user_repo.get_vehicle_by_id(session, dto.vehicle_id)
        if not vehicle:
            raise ValidationFailed(f"Vehicle {dto.vehicle_id} not found")

        for emp_id in emp_stops.keys():
            emp = user_repo.get_employee_by_id(session, emp_id)
            if not emp:
                raise ValidationFailed(f"Employee {emp_id} not found")

        trip = Trip(
            driver_id=dto.driver_id,
            vehicle_id=dto.vehicle_id,
            status=TripStatus.SCHEDULED,
            escort_assigned=False,
            requires_escort=False,
            planned_route=dto.planned_route,
            segment_speed_limits=dto.segment_speed_limits,
            default_speed_limit_kmph=dto.default_speed_limit_kmph,
            created_at=utcnow(),
        )
        session.add(trip)
        session.flush()

        for s in sorted_stops:
            stop_row = Stop(
                trip_id=trip.id,
                sequence=s.sequence,
                type=s.type,
                employee_id=s.employee_id,
                planned_time=s.planned_time,
                lat=s.lat,
                lng=s.lng,
            )
            session.add(stop_row)
        session.flush()

        audit_log_service.append(
            session,
            actor,
            actor_role,
            "TRIP_CREATED",
            "trip",
            trip.id,
            {"driver_id": trip.driver_id, "vehicle_id": trip.vehicle_id, "stops_count": len(dto.stops)},
        )

        trip_id = trip.id

    with write_tx() as session:
        created_trip = trip_repo.get_full(session, trip_id)
        # Detach/load eagerly before return
        _ = list(created_trip.stops)
        return created_trip


def set_escort(trip_id: int, flag: bool, actor: str, actor_role: str) -> Trip:
    """Set escort_assigned on trip and audit log ESCORT_ASSIGNED."""
    with write_tx() as session:
        trip = trip_repo.get_full(session, trip_id)
        if not trip:
            raise NotFound(f"Trip {trip_id} not found")

        trip.escort_assigned = flag
        audit_log_service.append(
            session,
            actor,
            actor_role,
            "ESCORT_ASSIGNED",
            "trip",
            trip.id,
            {"escort_assigned": flag},
        )

    with write_tx() as session:
        trip = trip_repo.get_full(session, trip_id)
        _ = list(trip.stops)
        return trip


def complete_trip(trip_id: int, actor: str, actor_role: str) -> AuditResult:
    """
    Complete trip and run audit.
    Idempotent if already COMPLETED (just re-audits).
    """
    with write_tx() as session:
        trip = trip_repo.get_full(session, trip_id)
        if not trip:
            raise NotFound(f"Trip {trip_id} not found")

        if trip.status != TripStatus.COMPLETED:
            trip.status = TripStatus.COMPLETED
            trip.completed_at = utcnow()
            audit_log_service.append(
                session,
                actor,
                actor_role,
                "TRIP_COMPLETED",
                "trip",
                trip.id,
                {},
            )

    return run_audit(trip_id, actor, actor_role)


def ingest_gps(trip_id: int, fixes: List[Any], actor: str) -> dict[str, int]:
    """
    Ingest batch of GPS fixes.
    Validations: lat in [-90,90], lng in [-180,180], 0 <= speed <= 300, tz-aware ts, batch <= MAX_GPS_BATCH.
    Returns {accepted, duplicates_ignored}.
    """
    from app.core.config import settings

    if len(fixes) > settings.MAX_GPS_BATCH:
        raise ValidationFailed(f"Batch size {len(fixes)} exceeds maximum {settings.MAX_GPS_BATCH}")

    fix_dicts = []
    for f in fixes:
        ts = f.ts if hasattr(f, "ts") else f["ts"]
        lat = f.lat if hasattr(f, "lat") else f["lat"]
        lng = f.lng if hasattr(f, "lng") else f["lng"]
        speed = f.speed_kmph if hasattr(f, "speed_kmph") else f["speed_kmph"]

        if not (-90.0 <= lat <= 90.0):
            raise ValidationFailed(f"Invalid lat {lat}")
        if not (-180.0 <= lng <= 180.0):
            raise ValidationFailed(f"Invalid lng {lng}")
        if not (0.0 <= speed <= 300.0):
            raise ValidationFailed(f"Invalid speed_kmph {speed}")

        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if ts.tzinfo is None:
            raise ValidationFailed(f"Timestamp {ts} must be timezone-aware")

        fix_dicts.append({
            "ts": ts,
            "lat": lat,
            "lng": lng,
            "speed_kmph": speed,
        })

    with write_tx() as session:
        trip = trip_repo.get_full(session, trip_id)
        if not trip:
            raise NotFound(f"Trip {trip_id} not found")

        accepted, duplicates = gps_repo.insert_batch(session, trip_id, fix_dicts)

    return {"accepted": accepted, "duplicates_ignored": duplicates}
