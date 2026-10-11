"""
app/api/routes/gps.py
GPS data ingestion routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, assert_driver_of_trip
from app.core.exceptions import NotFound
from app.models.user import User
from app.schemas.gps import GpsIngestRequest, GpsIngestResponse
import app.services.trip_service as trip_service
import app.repositories.trip_repo as trip_repo

router = APIRouter(prefix="/trips", tags=["gps"])


@router.post("/{id}/gps", response_model=GpsIngestResponse)
def ingest_gps(
    id: int,
    req: GpsIngestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trip = trip_repo.get_full(db, id)
    if not trip:
        raise NotFound(f"Trip {id} not found")

    assert_driver_of_trip(trip, current_user, db)
    res = trip_service.ingest_gps(id, req.fixes, current_user.username)
    return GpsIngestResponse(
        accepted=res["accepted"],
        duplicates_ignored=res["duplicates_ignored"],
    )
