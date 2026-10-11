from sqlalchemy import Column, Integer, String, Enum as SAEnum, JSON, DateTime, ForeignKey, Index, DDL, event
from app.models.base import Base
from app.domain.enums import ViolationType, Severity, ViolationStatus

class Violation(Base):
    __tablename__ = "violations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    type = Column(SAEnum(ViolationType, native_enum=False), nullable=False)
    severity = Column(SAEnum(Severity, native_enum=False), nullable=False)
    dedupe_key = Column(String, unique=True, nullable=False)
    subject_key = Column(String, nullable=False)
    details = Column(JSON, nullable=False)
    detected_by = Column(String, nullable=False)
    detected_at = Column(DateTime, nullable=False)
    status = Column(SAEnum(ViolationStatus, native_enum=False), nullable=False, default=ViolationStatus.OPEN)
    acknowledged_by = Column(String, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    ack_note = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_violations_trip_id", "trip_id"),
        Index("idx_violations_severity_type_status", "severity", "type", "status"),
    )

violation_core_immutable = DDL('''\
CREATE TRIGGER violations_core_immutable
BEFORE UPDATE OF trip_id, type, severity, dedupe_key, subject_key, details, detected_by, detected_at ON violations
BEGIN SELECT RAISE(ABORT, 'violation core fields are immutable'); END;
''')

violation_no_delete = DDL('''\
CREATE TRIGGER violations_no_delete
BEFORE DELETE ON violations
BEGIN SELECT RAISE(ABORT, 'violations cannot be deleted'); END;
''')

event.listen(Violation.__table__, 'after_create', violation_core_immutable)
event.listen(Violation.__table__, 'after_create', violation_no_delete)
