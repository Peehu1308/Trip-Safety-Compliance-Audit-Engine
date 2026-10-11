import pytest
from sqlalchemy.exc import OperationalError, IntegrityError, InternalError, ProgrammingError
from sqlalchemy import text
from datetime import datetime

def test_audit_log_insert_allowed(session):
    # Insert should succeed
    session.execute(text("""
        INSERT INTO audit_log (seq, ts, actor, actor_role, action, entity_type, entity_id, payload_json, prev_hash, entry_hash)
        VALUES (1, '2023-01-01', 'system', 'ADMIN', 'TEST', 'test', '1', '{}', '0', 'hash')
    """))
    session.commit()
    
    assert session.execute(text("SELECT count(*) FROM audit_log")).scalar() == 1

def test_audit_log_update_prevented(session):
    session.execute(text("""
        INSERT INTO audit_log (seq, ts, actor, actor_role, action, entity_type, entity_id, payload_json, prev_hash, entry_hash)
        VALUES (1, '2023-01-01', 'system', 'ADMIN', 'TEST', 'test', '1', '{}', '0', 'hash')
    """))
    session.commit()

    with pytest.raises((OperationalError, IntegrityError, InternalError, ProgrammingError)) as excinfo:
        session.execute(text("UPDATE audit_log SET action = 'MODIFIED' WHERE seq = 1"))
        session.commit()
    
    assert "audit_log is append-only" in str(excinfo.value)
    session.rollback()

def test_audit_log_delete_prevented(session):
    session.execute(text("""
        INSERT INTO audit_log (seq, ts, actor, actor_role, action, entity_type, entity_id, payload_json, prev_hash, entry_hash)
        VALUES (1, '2023-01-01', 'system', 'ADMIN', 'TEST', 'test', '1', '{}', '0', 'hash')
    """))
    session.commit()

    with pytest.raises((OperationalError, IntegrityError, InternalError, ProgrammingError)) as excinfo:
        session.execute(text("DELETE FROM audit_log WHERE seq = 1"))
        session.commit()
    
    assert "audit_log is append-only" in str(excinfo.value)
    session.rollback()
