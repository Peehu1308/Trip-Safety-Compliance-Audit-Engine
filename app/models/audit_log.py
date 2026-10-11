from sqlalchemy import Column, Integer, String, DDL, event
from app.models.base import Base

class AuditLog(Base):
    __tablename__ = "audit_log"

    seq = Column(Integer, primary_key=True, unique=True)
    ts = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    actor_role = Column(String, nullable=False)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    payload_json = Column(String, nullable=False)
    prev_hash = Column(String, nullable=False)
    entry_hash = Column(String, nullable=False)

audit_log_no_update = DDL('''\
CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
''')

audit_log_no_delete = DDL('''\
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
''')

event.listen(AuditLog.__table__, 'after_create', audit_log_no_update)
event.listen(AuditLog.__table__, 'after_create', audit_log_no_delete)
