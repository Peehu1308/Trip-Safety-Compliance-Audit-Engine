"""
app/repositories/gps_repo.py
DB access for GpsFix rows.
"""
from __future__ import annotations
from typing import Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.models.gps import GpsFix


def list_fixes(session: Session, trip_id: int) -> list[GpsFix]:
    """Return all GPS fixes for a trip, ordered by timestamp ascending."""
    rows = session.scalars(
        select(GpsFix).where(GpsFix.trip_id == trip_id).order_by(GpsFix.ts)
    ).all()
    return list(rows)


def get_latest_for_trip(session: Session, trip_id: int) -> Optional[GpsFix]:
    """Return the most recent GPS fix for a trip by timestamp."""
    return session.scalar(
        select(GpsFix).where(GpsFix.trip_id == trip_id).order_by(GpsFix.ts.desc()).limit(1)
    )


def insert_batch(session: Session, trip_id: int, fixes: list[dict[str, Any]]) -> tuple[int, int]:
    """
    Insert GPS fixes for a trip with ON CONFLICT(trip_id, ts) DO NOTHING.
    Returns (accepted_count, duplicates_ignored_count).
    """
    if not fixes:
        return 0, 0

    records = [
        {
            "trip_id": trip_id,
            "ts": f["ts"],
            "lat": f["lat"],
            "lng": f["lng"],
            "speed_kmph": f["speed_kmph"],
        }
        for f in fixes
    ]

    stmt = sqlite_insert(GpsFix).values(records).on_conflict_do_nothing(
        index_elements=["trip_id", "ts"]
    )
    res = session.execute(stmt)
    accepted = res.rowcount if res.rowcount >= 0 else 0
    duplicates = len(fixes) - accepted
    return accepted, duplicates
