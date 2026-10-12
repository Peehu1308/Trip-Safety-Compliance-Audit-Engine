"""
app/api/routes/trips.py
Trip lifecycle, queries, escort assignment, completion, and audit runs.
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db,
    get_current_user,
    require_roles,
    assert_driver_of_trip,
    assert_passenger_of_trip,
)
from app.core.exceptions import NotFound, Forbidden
from app.domain.enums import Role
from app.models.user import User
from app.models.trip import Trip
from app.schemas.trips import TripCreate, TripResponse, StopResponse, EscortUpdateRequest
from app.schemas.violations import ViolationResponse
from app.schemas.audit import AuditResponse
import app.services.trip_service as trip_service
import app.services.audit_engine as audit_engine
import app.repositories.trip_repo as trip_repo
import app.repositories.user_repo as user_repo
import app.repositories.violation_repo as violation_repo

router = APIRouter(prefix="/trips", tags=["trips"])


def _project_trip_response(trip: Trip, user: User, db: Session) -> TripResponse:
    """
    Project trip response applying privacy masks (SPEC 11):
    Phone masked, coordinates only for own stops/admin.
    """
    user_role = user.role.value if hasattr(user.role, "value") else str(user.role)
    is_admin = user_role in (Role.ADMIN.value, Role.APPROVER.value)
    
    emp = None
    if user_role == Role.EMPLOYEE.value:
        emp = user_repo.get_employee_by_user_id(db, user.id)

    stops_res = []
    for s in trip.stops:
        is_own_stop = emp and s.employee_id == emp.id
        lat_val = s.lat if (is_admin or is_own_stop or user_role == Role.DRIVER.value) else None
        lng_val = s.lng if (is_admin or is_own_stop or user_role == Role.DRIVER.value) else None

        stops_res.append(
            StopResponse(
                id=s.id,
                trip_id=s.trip_id,
                sequence=s.sequence,
                type=s.type,
                employee_id=s.employee_id,
                planned_time=s.planned_time,
                actual_time=s.actual_time,
                lat=lat_val,
                lng=lng_val,
                status=s.status,
                otp_failures=s.otp_failures,
            )
        )

    return TripResponse(
        id=trip.id,
        driver_id=trip.driver_id,
        vehicle_id=trip.vehicle_id,
        status=trip.status,
        escort_assigned=trip.escort_assigned,
        requires_escort=trip.requires_escort,
        planned_route=trip.planned_route if (is_admin or user_role == Role.DRIVER.value) else None,
        segment_speed_limits=trip.segment_speed_limits,
        default_speed_limit_kmph=trip.default_speed_limit_kmph,
        created_at=trip.created_at,
        completed_at=trip.completed_at,
        stops=stops_res,
    )


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
def create_trip(
    req: TripCreate,
    current_user: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    actor_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    return trip_service.create_trip(req, current_user.username, actor_role)


@router.get("", response_model=List[TripResponse])
def list_trips(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)

    driver_id = None
    employee_id = None

    if user_role == Role.DRIVER.value:
        drv = user_repo.get_driver_by_user_id(db, current_user.id)
        if not drv:
            return []
        driver_id = drv.id
    elif user_role == Role.EMPLOYEE.value:
        emp = user_repo.get_employee_by_user_id(db, current_user.id)
        if not emp:
            return []
        employee_id = emp.id

    trips = trip_repo.list_trips(db, limit=limit, offset=offset, driver_id=driver_id, employee_id=employee_id)
    return [_project_trip_response(t, current_user, db) for t in trips]


@router.get("/{id}", response_model=TripResponse)
def get_trip(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trip = trip_repo.get_full(db, id)
    if not trip:
        raise NotFound(f"Trip {id} not found")

    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if user_role == Role.DRIVER.value:
        assert_driver_of_trip(trip, current_user, db)
    elif user_role == Role.EMPLOYEE.value:
        assert_passenger_of_trip(trip, current_user, db)

    return _project_trip_response(trip, current_user, db)


@router.patch("/{id}/escort", response_model=TripResponse)
def update_escort(
    id: int,
    req: EscortUpdateRequest,
    current_user: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    actor_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    return trip_service.set_escort(id, req.escort_assigned, current_user.username, actor_role)


@router.post("/{id}/complete", response_model=AuditResponse)
def complete_trip(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trip = trip_repo.get_full(db, id)
    if not trip:
        raise NotFound(f"Trip {id} not found")

    assert_driver_of_trip(trip, current_user, db)
    actor_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    audit_res = trip_service.complete_trip(id, current_user.username, actor_role)

    violations_rows = violation_repo.list_for_trip(db, id)
    v_responses = [ViolationResponse.model_validate(v) for v in violations_rows]

    return AuditResponse(
        trip_id=id,
        new=audit_res.new,
        duplicates=audit_res.duplicates,
        total=audit_res.total,
        rule_failures=audit_res.rule_failures,
        status=audit_res.status,
        violations=v_responses,
    )


@router.post("/{id}/audit", response_model=AuditResponse)
def audit_trip(
    id: int,
    current_user: User = Depends(require_roles(Role.ADMIN, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    actor_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    audit_res = audit_engine.run_audit(id, current_user.username, actor_role)

    violations_rows = violation_repo.list_for_trip(db, id)
    v_responses = [ViolationResponse.model_validate(v) for v in violations_rows]

    return AuditResponse(
        trip_id=id,
        new=audit_res.new,
        duplicates=audit_res.duplicates,
        total=audit_res.total,
        rule_failures=audit_res.rule_failures,
        status=audit_res.status,
        violations=v_responses,
    )


@router.get("/{id}/violations", response_model=List[ViolationResponse])
def get_trip_violations(
    id: int,
    current_user: User = Depends(require_roles(Role.ADMIN, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    trip = trip_repo.get_full(db, id)
    if not trip:
        raise NotFound(f"Trip {id} not found")

    violations_rows = violation_repo.list_for_trip(db, id)
    return [ViolationResponse.model_validate(v) for v in violations_rows]
