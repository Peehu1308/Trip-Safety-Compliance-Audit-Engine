"""
app/api/routes/events.py
Event routes: OTP fetch, OTP submit, stop unfreeze, and SOS panic button.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db,
    get_current_user,
    require_roles,
    assert_driver_of_trip,
    assert_passenger_of_trip,
)
from app.core.exceptions import NotFound, Forbidden, ValidationFailed
from app.core.security import derive_otp
from app.domain.enums import Role, StopType
from app.models.user import User
from app.schemas.events import (
    OtpSubmitRequest,
    OtpSubmitResponse,
    OtpValueResponse,
    UnfreezeRequest,
    SosRequest,
    SosResponse,
)
import app.services.otp_service as otp_service
import app.services.sos_service as sos_service
import app.repositories.trip_repo as trip_repo
import app.repositories.user_repo as user_repo

router = APIRouter(prefix="/trips", tags=["events"])


@router.get("/{id}/stops/{sid}/otp", response_model=OtpValueResponse)
def get_stop_otp(
    id: int,
    sid: int,
    current_user: User = Depends(require_roles(Role.EMPLOYEE)),
    db: Session = Depends(get_db),
):
    """
    Employee fetches OTP for their own DROP stop.
    Never logged; 403 if fetching someone else's OTP.
    """
    trip = trip_repo.get_full(db, id)
    if not trip:
        raise NotFound(f"Trip {id} not found")

    stop = trip_repo.get_stop(db, sid)
    if not stop or stop.trip_id != id:
        raise NotFound(f"Stop {sid} not found on trip {id}")

    if stop.type != StopType.DROP:
        raise ValidationFailed("OTP is only available for DROP stops")

    emp = user_repo.get_employee_by_user_id(db, current_user.id)
    if not emp or stop.employee_id != emp.id:
        raise Forbidden("You can only view OTP for your own drop stop")

    otp_value = derive_otp(id, sid)
    return OtpValueResponse(otp=otp_value)


@router.post("/{id}/stops/{sid}/otp")
def submit_stop_otp(
    id: int,
    sid: int,
    req: OtpSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Driver (own) or ADMIN submits OTP.
    On mismatch: commits first, then returns HTTP 409 body {"result": "MISMATCH", "stop_status": "FROZEN"}.
    """
    trip = trip_repo.get_full(db, id)
    if not trip:
        raise NotFound(f"Trip {id} not found")

    assert_driver_of_trip(trip, current_user, db)

    res = otp_service.submit_otp(id, sid, req.otp, current_user)
    if res.is_mismatch or res.result == "MISMATCH":
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"result": "MISMATCH", "stop_status": "FROZEN"},
        )

    return {"result": "OK", "stop_status": "COMPLETED"}


@router.post("/{id}/stops/{sid}/unfreeze")
def unfreeze_stop(
    id: int,
    sid: int,
    req: UnfreezeRequest,
    current_user: User = Depends(require_roles(Role.ADMIN, Role.APPROVER)),
    db: Session = Depends(get_db),
):
    """Admin/Approver unfreezes a frozen stop."""
    actor_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    otp_service.unfreeze(id, sid, current_user.username, actor_role, req.reason)
    return {"status": "unfrozen", "stop_id": sid}


@router.post("/{id}/sos", response_model=SosResponse, status_code=status.HTTP_201_CREATED)
def trigger_sos(
    id: int,
    req: SosRequest,
    current_user: User = Depends(require_roles(Role.EMPLOYEE)),
    db: Session = Depends(get_db),
):
    """Passenger triggers SOS panic button."""
    trip = trip_repo.get_full(db, id)
    if not trip:
        raise NotFound(f"Trip {id} not found")

    assert_passenger_of_trip(trip, current_user, db)
    res = sos_service.raise_sos(id, current_user, req.lat, req.lng)
    return SosResponse(**res)
