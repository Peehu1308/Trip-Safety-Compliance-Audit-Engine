from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, UniqueConstraint, Index
from app.models.base import Base

class GpsFix(Base):
    __tablename__ = "gps_fixes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    ts = Column(DateTime, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    speed_kmph = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("trip_id", "ts", name="uix_gps_fix_trip_ts"),
        Index("idx_gps_fixes_trip_ts", "trip_id", "ts"),
    )
