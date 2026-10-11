from sqlalchemy import Column, Integer, Boolean, DateTime, Float, String, ForeignKey
from app.models.base import Base

class OtpEvent(Base):
    __tablename__ = "otp_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    stop_id = Column(Integer, ForeignKey("stops.id"), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    success = Column(Boolean, nullable=False)
    attempt_no = Column(Integer, nullable=False)
    ts = Column(DateTime, nullable=False)

class SosEvent(Base):
    __tablename__ = "sos_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    location_source = Column(String, nullable=False)
    ts = Column(DateTime, nullable=False)
