"""
tests/conftest.py
Shared fixtures for all tests.
  - engine / session: in-memory SQLite with all tables + triggers created
  - db_session: alias for session
  - minimal_trip: factory for a seeded trip + female stop (night time)
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.models.base import Base
import app.models  # noqa: F401  – ensures all models are registered


# ---------------------------------------------------------------------------
# In-memory SQLite engine for testing.
# We deliberately do NOT attach the BEGIN IMMEDIATE listener here; SQLAlchemy's
# autobegin is sufficient for tests.  The production WAL/FK pragmas are kept.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def engine():
    # StaticPool: every call to engine.connect() returns the SAME underlying
    # connection, so all threads (including TestClient workers) see the same
    # in-memory schema and seed data.
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    from sqlalchemy import event as sa_event

    @sa_event.listens_for(eng, "connect")
    def _on_connect(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture(scope="function")
def session(engine) -> Session:
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Alias used by some integration tests
@pytest.fixture(scope="function")
def db_session(session):
    return session


@pytest.fixture(autouse=True)
def _reset_caches():
    from app.core.cache import clear_all_caches
    clear_all_caches()
    yield
    clear_all_caches()



# ---------------------------------------------------------------------------
# Patch helper – used by integration tests to redirect DB calls to test engine
# ---------------------------------------------------------------------------

def make_patch_db(engine):
    """Return a pytest fixture that patches app.core.db to use the test engine."""
    @pytest.fixture(autouse=True)
    def _patch(monkeypatch):
        from contextlib import contextmanager
        import app.core.db as db_mod

        TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        monkeypatch.setattr(db_mod, "SessionLocal", TestSession)
        monkeypatch.setattr(db_mod, "WriteSession", TestSession)
        monkeypatch.setattr(db_mod, "ReadSession", TestSession)
        monkeypatch.setattr(db_mod, "engine", engine)
        monkeypatch.setattr(db_mod, "write_engine", engine)
        monkeypatch.setattr(db_mod, "read_engine", engine)

        @contextmanager
        def _test_write_tx():
            s = TestSession()
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise
            finally:
                s.close()

        monkeypatch.setattr(db_mod, "write_tx", _test_write_tx)
        yield

    return _patch


# ---------------------------------------------------------------------------
# Seed helpers (used by minimal_trip and can be called from integration tests)
# ---------------------------------------------------------------------------

def seed_user(session, username, role):
    from app.models.user import User
    u = User(username=username, password_hash="hash", role=role, is_active=True)
    session.add(u)
    session.flush()
    return u


def seed_employee(session, user_id, gender):
    from app.models.people import Employee
    e = Employee(user_id=user_id, name="Test Person", gender=gender, phone="9999999999")
    session.add(e)
    session.flush()
    return e


def seed_driver(session, user_id):
    from app.models.people import Driver
    d = Driver(user_id=user_id, name="Driver One", license_no="DL123")
    session.add(d)
    session.flush()
    return d


def seed_vehicle(session):
    from app.models.people import Vehicle
    v = Vehicle(reg_no="KA01AB1234", model="Toyota Innova")
    session.add(v)
    session.flush()
    return v


def seed_trip(session, driver_id, vehicle_id, planned_route=None, escort=False):
    from app.models.trip import Trip
    from app.domain.enums import TripStatus
    from datetime import datetime
    route = planned_route or [[28.5355, 77.30], [28.5355, 77.40]]
    t = Trip(
        driver_id=driver_id,
        vehicle_id=vehicle_id,
        status=TripStatus.SCHEDULED,
        escort_assigned=escort,
        planned_route=route,
        segment_speed_limits=[60],
        default_speed_limit_kmph=60,
        created_at=datetime(2026, 10, 9, 16, 0),
    )
    session.add(t)
    session.flush()
    return t


def seed_stop(session, trip_id, employee_id, sequence, stype, planned_time):
    from app.models.trip import Stop
    from app.domain.enums import StopStatus
    s = Stop(
        trip_id=trip_id,
        sequence=sequence,
        type=stype,
        employee_id=employee_id,
        planned_time=planned_time,
        lat=28.5355, lng=77.35,
        status=StopStatus.PENDING,
    )
    session.add(s)
    session.flush()
    return s


@pytest.fixture
def minimal_trip(engine):
    """
    A minimal seeded trip with one female DROP stop at 17:40 UTC = 23:10 IST (night).
    Patches app.core.db to use the test engine.
    Returns (session, trip, stop, employee).
    """
    from datetime import datetime
    from contextlib import contextmanager
    from sqlalchemy.orm import sessionmaker
    import app.core.db as db_mod
    from app.domain.enums import Role, Gender, StopType

    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    @contextmanager
    def _test_write_tx():
        s = TestSession()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # Patch globally for the duration of this fixture
    original_session = db_mod.SessionLocal
    original_write_session = getattr(db_mod, "WriteSession", db_mod.SessionLocal)
    original_read_session = getattr(db_mod, "ReadSession", db_mod.SessionLocal)
    original_engine = db_mod.engine
    original_write_engine = getattr(db_mod, "write_engine", db_mod.engine)
    original_read_engine = getattr(db_mod, "read_engine", db_mod.engine)
    original_write_tx = db_mod.write_tx

    db_mod.SessionLocal = TestSession
    db_mod.WriteSession = TestSession
    db_mod.ReadSession = TestSession
    db_mod.engine = engine
    db_mod.write_engine = engine
    db_mod.read_engine = engine
    db_mod.write_tx = _test_write_tx

    session = TestSession()

    u_drv = seed_user(session, "driver_t", Role.DRIVER)
    u_emp = seed_user(session, "priya_t", Role.EMPLOYEE)

    drv = seed_driver(session, u_drv.id)
    veh = seed_vehicle(session)
    emp = seed_employee(session, u_emp.id, Gender.F)

    trip = seed_trip(session, drv.id, veh.id)
    stop = seed_stop(session, trip.id, emp.id, 1, StopType.DROP,
                     datetime(2026, 10, 9, 17, 40))  # 23:10 IST

    session.commit()

    yield session, trip, stop, emp

    session.close()
    db_mod.SessionLocal = original_session
    db_mod.WriteSession = original_write_session
    db_mod.ReadSession = original_read_session
    db_mod.engine = original_engine
    db_mod.write_engine = original_write_engine
    db_mod.read_engine = original_read_engine
    db_mod.write_tx = original_write_tx



# ---------------------------------------------------------------------------
# HTTP client fixture that uses a temp-file SQLite DB so TestClient threads
# and write_tx() sessions all share the same persistent DB file.
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_trip_client(tmp_path):
    """
    Yields (client, session, trip, stop, emp) using a temp-file SQLite DB.
    Both `get_db` and `write_tx` are patched to use this file so that
    all threads (including FastAPI request workers) share the same data.
    """
    from datetime import datetime
    from contextlib import contextmanager
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine as _create_engine
    from sqlalchemy.orm import sessionmaker
    import app.core.db as db_mod
    from app.main import app
    from app.domain.enums import Role, Gender, StopType

    db_file = tmp_path / "test.db"
    test_engine = _create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )

    from sqlalchemy import event as _event

    @_event.listens_for(test_engine, "connect")
    def _on_connect(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    @contextmanager
    def _test_write_tx():
        s = TestSession()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # Patch app.core.db so that all services and deps use test DB
    original_sl = db_mod.SessionLocal
    original_ws = getattr(db_mod, "WriteSession", db_mod.SessionLocal)
    original_rs = getattr(db_mod, "ReadSession", db_mod.SessionLocal)
    original_eng = db_mod.engine
    original_weng = getattr(db_mod, "write_engine", db_mod.engine)
    original_reng = getattr(db_mod, "read_engine", db_mod.engine)
    original_wtx = db_mod.write_tx

    db_mod.SessionLocal = TestSession
    db_mod.WriteSession = TestSession
    db_mod.ReadSession = TestSession
    db_mod.engine = test_engine
    db_mod.write_engine = test_engine
    db_mod.read_engine = test_engine
    db_mod.write_tx = _test_write_tx

    # Seed minimal data
    session = TestSession()
    u_drv = seed_user(session, "driver_t", Role.DRIVER)
    u_emp = seed_user(session, "priya_t", Role.EMPLOYEE)
    drv = seed_driver(session, u_drv.id)
    veh = seed_vehicle(session)
    emp = seed_employee(session, u_emp.id, Gender.F)
    trip = seed_trip(session, drv.id, veh.id)
    stop = seed_stop(
        session, trip.id, emp.id, 1, StopType.DROP,
        datetime(2026, 10, 9, 17, 40),  # 23:10 IST
    )
    session.commit()

    client = TestClient(app, raise_server_exceptions=False)

    yield client, session, trip, stop, emp

    session.close()
    db_mod.SessionLocal = original_sl
    db_mod.WriteSession = original_ws
    db_mod.ReadSession = original_rs
    db_mod.engine = original_eng
    db_mod.write_engine = original_weng
    db_mod.read_engine = original_reng
    db_mod.write_tx = original_wtx
    test_engine.dispose()
