"""
app/services/context_builder.py
Builds a TripContext (all domain DTOs) from DB rows.
Parses planned_route into a Polyline (cached per trip_id).
Caches Employee profile via employee_cache per SPEC 12.4.
"""
from __future__ import annotations
import logging
from sqlalchemy.orm import Session

from app.domain.dtos import (
    TripContext, StopDTO, EmployeeDTO, GpsFixDTO,
    OtpEventDTO, SosEventDTO, RuleConfig,
)
from app.domain.enums import Gender
from app.core.config import settings
from app.geo.polyline import Polyline
import app.core.cache as cache
import app.repositories.trip_repo as trip_repo
import app.repositories.gps_repo as gps_repo
import app.repositories.event_repo as event_repo

log = logging.getLogger(__name__)


def _make_rule_config() -> RuleConfig:
    return RuleConfig(
        local_tz=settings.LOCAL_TZ,
        night_start=settings.NIGHT_START,
        night_end=settings.NIGHT_END,
        deviation_threshold_m=settings.DEVIATION_THRESHOLD_M,
        deviation_min_seconds=settings.DEVIATION_MIN_SECONDS,
        deviation_min_meters=settings.DEVIATION_MIN_METERS,
        max_gps_gap_seconds=settings.MAX_GPS_GAP_SECONDS,
        default_speed_limit_kmph=settings.DEFAULT_SPEED_LIMIT_KMPH,
        overspeed_min_seconds=settings.OVERSPEED_MIN_SECONDS,
        extreme_overspeed_delta_kmph=settings.EXTREME_OVERSPEED_DELTA_KMPH,
        extreme_overspeed_min_seconds=settings.EXTREME_OVERSPEED_MIN_SECONDS,
        sos_decimals=settings.SOS_COORD_DECIMALS,
    )


def _load_polyline(trip) -> tuple[Polyline | None, list[int] | None]:
    """Return (Polyline, segment_limits) from cache or trip's planned_route JSON."""
    cached = cache.get_cached_route(trip.id)
    if cached is not None:
        return cached

    try:
        points = [(p[0], p[1]) for p in trip.planned_route]
        poly = Polyline(points) if len(points) >= 2 else None
    except Exception:
        log.exception("Failed to build Polyline for trip %s", trip.id)
        poly = None

    limits = trip.segment_speed_limits  # already a list or None
    cache.set_cached_route(trip.id, poly, limits)
    return poly, limits


def invalidate_trip(trip_id: int) -> None:
    """Call this when a trip's route changes."""
    cache.invalidate_trip(trip_id)


def build(session: Session, trip) -> TripContext:
    """
    DB rows → TripContext (pure DTOs).
    Drops PII: employee name, phone and stop coordinates are not included.
    Uses route_cache and employee_cache per SPEC 12.4.
    """
    stops_orm = trip_repo.list_stops_ordered(session, trip.id)

    # Build EmployeeDTO map  {employee_id: EmployeeDTO}
    emp_map: dict[int, EmployeeDTO] = {}
    for stop in stops_orm:
        eid = stop.employee_id
        if eid not in emp_map:
            cached_emp = cache.get_cached_employee(eid)
            if cached_emp is not None:
                emp_map[eid] = cached_emp
            else:
                try:
                    from app.models.people import Employee
                    emp_orm = session.get(Employee, eid)
                    if emp_orm:
                        emp_dto = EmployeeDTO(
                            id=eid,
                            ref=f"EMP-{eid}",
                            gender=Gender(emp_orm.gender),
                        )
                        cache.set_cached_employee(eid, emp_dto)
                        emp_map[eid] = emp_dto
                except Exception:
                    log.exception("Could not load employee %s", eid)

    stops_dto = [
        StopDTO(
            id=s.id,
            sequence=s.sequence,
            type=s.type,
            employee_id=s.employee_id,
            planned_time=s.planned_time,
            actual_time=s.actual_time,
            status=s.status,
        )
        for s in stops_orm
    ]

    fixes_orm = gps_repo.list_fixes(session, trip.id)
    fixes_dto = [
        GpsFixDTO(ts=f.ts, lat=f.lat, lng=f.lng, speed_kmph=f.speed_kmph)
        for f in fixes_orm
    ]

    otp_orm = event_repo.list_otp_events(session, trip.id)
    otp_dto = [
        OtpEventDTO(stop_id=e.stop_id, success=e.success, attempt_no=e.attempt_no, ts=e.ts)
        for e in otp_orm
    ]

    sos_orm = event_repo.list_sos_events(session, trip.id)
    sos_dto = [
        SosEventDTO(id=e.id, employee_id=e.employee_id, lat=e.lat, lng=e.lng, ts=e.ts)
        for e in sos_orm
    ]

    polyline, seg_limits = _load_polyline(trip)

    return TripContext(
        trip_id=trip.id,
        escort_assigned=trip.escort_assigned,
        stops=stops_dto,
        employees=emp_map,
        fixes=fixes_dto,
        otp_events=otp_dto,
        sos_events=sos_dto,
        polyline=polyline,
        segment_limits=seg_limits,
        default_limit=trip.default_speed_limit_kmph,
        config=_make_rule_config(),
    )
