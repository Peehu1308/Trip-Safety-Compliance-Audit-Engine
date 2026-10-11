"""
app/repositories/event_repo.py
DB access for OtpEvent and SosEvent rows.
"""
from __future__ import annotations
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models.events import OtpEvent, SosEvent


def list_otp_events(session: Session, trip_id: int) -> list[OtpEvent]:
    rows = session.scalars(
        select(OtpEvent).where(OtpEvent.trip_id == trip_id).order_by(OtpEvent.ts)
    ).all()
    return list(rows)


def count_otp_events(session: Session, stop_id: int) -> int:
    return session.scalar(
        select(func.count()).select_from(OtpEvent).where(OtpEvent.stop_id == stop_id)
    ) or 0


def list_sos_events(session: Session, trip_id: int) -> list[SosEvent]:
    rows = session.scalars(
        select(SosEvent).where(SosEvent.trip_id == trip_id).order_by(SosEvent.ts)
    ).all()
    return list(rows)
