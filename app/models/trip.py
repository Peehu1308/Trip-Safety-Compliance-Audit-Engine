from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey,Float, Enum as SAEnum, JSON, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.base import Base
from app.domain.enums import TripStatus, StopType, StopStatus

class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=False)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    status = Column(SAEnum(TripStatus, native_enum=False), nullable=False, default=TripStatus.SCHEDULED)
    escort_assigned = Column(Boolean, nullable=False, default=False)
    requires_escort = Column(Boolean, nullable=False, default=False)
    planned_route = Column(JSON, nullable=False)
    segment_speed_limits = Column(JSON, nullable=True)
    default_speed_limit_kmph = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    driver = relationship("Driver")
    vehicle = relationship("Vehicle")
    stops = relationship("Stop", back_populates="trip", order_by="Stop.sequence", lazy="selectin")

class Stop(Base):
    __tablename__ = "stops"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    sequence = Column(Integer, nullable=False)
    type = Column(SAEnum(StopType, native_enum=False), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    planned_time = Column(DateTime, nullable=False)
    actual_time = Column(DateTime, nullable=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    status = Column(SAEnum(StopStatus, native_enum=False), nullable=False, default=StopStatus.PENDING)
    otp_failures = Column(Integer, nullable=False, default=0)
    
    trip = relationship("Trip", back_populates="stops")
    employee = relationship("Employee")
    
    __table_args__ = (
        UniqueConstraint("trip_id", "sequence", name="uix_stop_trip_seq"),
    )
