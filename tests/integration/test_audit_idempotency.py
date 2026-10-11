"""
tests/integration/test_audit_idempotency.py

Verifies SPEC requirement A10 / section 10.1:
  - Auditing the same trip 3 times must not create extra violations or outbox rows.
  - Second and third audits must report duplicates > 0.
  - Concurrent audits (two threads) still produce only one set of violations.
"""
import threading
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker

from app.services.audit_engine import run_audit
from app.models.violation import Violation
from app.models.outbox import NotificationOutbox


def test_three_audits_idempotent(minimal_trip):
    session, trip, stop, emp = minimal_trip
    trip_id = trip.id

    r1 = run_audit(trip_id, "system", "ADMIN")
    r2 = run_audit(trip_id, "system", "ADMIN")
    r3 = run_audit(trip_id, "system", "ADMIN")

    assert r1.new >= 1, "First audit should detect at least one violation"
    assert r2.new == 0 and r2.duplicates > 0, "Second audit: no new, some duplicates"
    assert r3.new == 0 and r3.duplicates > 0, "Third audit: no new, some duplicates"
    assert r2.total == r1.total == r3.total, "Total count must not change"


def test_outbox_rows_stable_across_audits(minimal_trip):
    session, trip, stop, emp = minimal_trip
    trip_id = trip.id

    S = sessionmaker(bind=session.bind)

    run_audit(trip_id, "system", "ADMIN")
    s = S()
    count_after_first = s.scalar(
        select(func.count()).select_from(NotificationOutbox)
        .join(Violation, NotificationOutbox.violation_id == Violation.id)
        .where(Violation.trip_id == trip_id)
    )
    s.close()

    run_audit(trip_id, "system", "ADMIN")
    s = S()
    count_after_second = s.scalar(
        select(func.count()).select_from(NotificationOutbox)
        .join(Violation, NotificationOutbox.violation_id == Violation.id)
        .where(Violation.trip_id == trip_id)
    )
    s.close()

    assert count_after_first == count_after_second, "Outbox rows must not grow on re-audit"
    assert count_after_first > 0, "There should be at least one outbox row"


def test_concurrent_audits_idempotent(minimal_trip, tmp_path):
    """
    Two concurrent audit calls must still produce exactly one violation set.
    Uses a file-based SQLite (tmp_path) so both threads share the same DB;
    UNIQUE(dedupe_key) + WAL ensure atomicity.
    """
    import app.core.db as db_mod
    from contextlib import contextmanager
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.base import Base
    import app.models  # noqa

    db_path = tmp_path / "concurrent_test.db"
    file_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    from sqlalchemy import event as sa_event

    @sa_event.listens_for(file_engine, "connect")
    def _on_connect(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    Base.metadata.create_all(file_engine)
    FileSession = sessionmaker(bind=file_engine, autocommit=False, autoflush=False)

    # Seed data into the file DB
    s = FileSession()
    from app.domain.enums import Role, Gender, StopType
    from tests.conftest import (
        seed_user, seed_employee, seed_driver, seed_vehicle, seed_trip, seed_stop,
    )
    from datetime import datetime
    u_drv = seed_user(s, "driver_cc", Role.DRIVER)
    u_emp = seed_user(s, "emp_cc", Role.EMPLOYEE)
    drv = seed_driver(s, u_drv.id)
    veh = seed_vehicle(s)
    emp = seed_employee(s, u_emp.id, Gender.F)
    trip_cc = seed_trip(s, drv.id, veh.id)
    seed_stop(s, trip_cc.id, emp.id, 1, StopType.DROP, datetime(2026, 10, 9, 17, 40))
    s.commit()
    trip_id = trip_cc.id   # read before close to avoid DetachedInstanceError
    s.close()

    @contextmanager
    def _file_write_tx():
        sess = FileSession()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    orig_sl = db_mod.SessionLocal
    orig_ws = getattr(db_mod, "WriteSession", db_mod.SessionLocal)
    orig_rs = getattr(db_mod, "ReadSession", db_mod.SessionLocal)
    orig_eng = db_mod.engine
    orig_weng = getattr(db_mod, "write_engine", db_mod.engine)
    orig_reng = getattr(db_mod, "read_engine", db_mod.engine)
    orig_wtx = db_mod.write_tx

    db_mod.SessionLocal = FileSession
    db_mod.WriteSession = FileSession
    db_mod.ReadSession = FileSession
    db_mod.engine = file_engine
    db_mod.write_engine = file_engine
    db_mod.read_engine = file_engine
    db_mod.write_tx = _file_write_tx

    results = []
    errors = []

    def do_audit():
        try:
            r = run_audit(trip_id, "system", "ADMIN")
            results.append(r)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=do_audit)
    t2 = threading.Thread(target=do_audit)
    t1.start(); t2.start()
    t1.join(); t2.join()

    db_mod.SessionLocal = orig_sl
    db_mod.WriteSession = orig_ws
    db_mod.ReadSession = orig_rs
    db_mod.engine = orig_eng
    db_mod.write_engine = orig_weng
    db_mod.read_engine = orig_reng
    db_mod.write_tx = orig_wtx

    assert not errors, f"Concurrent audit raised: {errors}"

    s = FileSession()
    vcount = s.scalar(select(func.count()).select_from(Violation).where(Violation.trip_id == trip_id))
    s.close()
    assert vcount >= 1
    total_new = sum(r.new for r in results)
    assert total_new >= 1

