from sqlalchemy import Column, Integer, String, Enum as SAEnum, JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.models.base import Base
from app.domain.enums import OutboxStatus

class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"

    id = Column(Integer, primary_key=True, autoincrement=True)
    violation_id = Column(Integer, ForeignKey("violations.id"), nullable=False)
    channel = Column(String, nullable=False)
    payload_json = Column(JSON, nullable=False)
    status = Column(SAEnum(OutboxStatus, native_enum=False), nullable=False, default=OutboxStatus.PENDING)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    sent_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("violation_id", "channel", name="uix_outbox_violation_channel"),
    )
