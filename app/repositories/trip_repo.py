"""
app/repositories/trip_repo.py
DB access for Trip and Stop rows. No business rules here.
"""
from __future__ import annotations
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.trip import Trip, Stop


def get_full(session: Session, trip_id: int) -> Optional[Trip]:
    """Load a Trip with its stops eagerly (needed by context_builder)."""
    return session.get(Trip, trip_id)


def get_stop(session: Session, stop_id: int) -> Optional[Stop]:
    return session.get(Stop, stop_id)


def list_stops_ordered(session: Session, trip_id: int) -> list[Stop]:
    rows = session.scalars(
        select(Stop).where(Stop.trip_id == trip_id).order_by(Stop.sequence)
    ).all()
    return list(rows)


def list_trips(
    session: Session,
    limit: int = 100,
    offset: int = 0,
    driver_id: Optional[int] = None,
    employee_id: Optional[int] = None,
) -> list[Trip]:
    q = select(Trip)
    if driver_id is not None:
        q = q.where(Trip.driver_id == driver_id)
    if employee_id is not None:
        q = q.where(Trip.stops.any(Stop.employee_id == employee_id))
    q = q.order_by(Trip.id.desc()).offset(offset).limit(limit)
    return list(session.scalars(q).all())
