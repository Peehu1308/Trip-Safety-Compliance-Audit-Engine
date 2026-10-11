"""
tests/integration/test_demo_scenarios.py
Integration test that seeds the database with SPEC section 13 demo data,
audits trips 1-4 via the API, and asserts the expected violation set.
Also tests scripts/backup.py.
"""
import os
import pytest
from datetime import timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.models.base import Base
from app.models.trip import Trip
from app.models.user import User
from app.core.security import create_access_token
from app.domain.enums import Role
from scripts.seed import seed
from scripts.backup import backup_database
import app.core.db as db_mod


@pytest.fixture
def seeded_client(tmp_path):
    """
    Sets up a temporary SQLite database, runs scripts/seed.py,
    patches app.core.db, and returns (client, session, admin_user).
    """
    db_file = tmp_path / "seeded_test.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    from contextlib import contextmanager

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

    session = TestSession()
    # Run seed script into this test database
    seed(session=session, bind_engine=test_engine)

    admin_user = session.query(User).filter_by(username="admin").first()

    client = TestClient(app, raise_server_exceptions=False)

    yield client, session, admin_user, str(db_file)

    session.close()
    db_mod.SessionLocal = original_sl
    db_mod.WriteSession = original_ws
    db_mod.ReadSession = original_rs
    db_mod.engine = original_eng
    db_mod.write_engine = original_weng
    db_mod.read_engine = original_reng
    db_mod.write_tx = original_wtx
    test_engine.dispose()


def _auth_header(user) -> dict[str, str]:
    token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    })
    return {"Authorization": f"Bearer {token}"}


def test_seed_and_audit_trips_1_to_4(seeded_client):
    client, session, admin_user, db_file_path = seeded_client
    admin_hdr = _auth_header(admin_user)

    # -----------------------------------------------------------------------
    # Trip 1: Night, female last drop
    # Expected: exactly 1 x NIGHT_SAFETY (HIGH), reason LAST_DROP;
    #           requires_escort becomes true
    # -----------------------------------------------------------------------
    resp1 = client.post("/trips/1/audit", headers=admin_hdr)
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()
    assert data1["trip_id"] == 1
    assert data1["new"] == 1
    assert len(data1["violations"]) == 1

    v1 = data1["violations"][0]
    assert v1["type"] == "NIGHT_SAFETY"
    assert str(v1["severity"]) in ("HIGH", "2")
    assert v1["details"].get("reason") == "LAST_DROP"

    # Verify requires_escort became true on the trip row
    trip1 = session.get(Trip, 1)
    session.refresh(trip1)
    assert trip1.requires_escort is True

    # -----------------------------------------------------------------------
    # Trip 2: Route deviation
    # Expected: exactly 1 x ROUTE_DEVIATION (HIGH), max_deviation_m ≈ 845 (±15),
    #           duration_s = 240. The blip (#15) is NOT flagged.
    # -----------------------------------------------------------------------
    resp2 = client.post("/trips/2/audit", headers=admin_hdr)
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["trip_id"] == 2
    assert data2["new"] == 1
    assert len(data2["violations"]) == 1

    v2 = data2["violations"][0]
    assert v2["type"] == "ROUTE_DEVIATION"
    assert str(v2["severity"]) in ("HIGH", "2")
    d2 = v2["details"]
    assert d2["duration_s"] == 240.0
    assert 830 <= d2["max_deviation_m"] <= 860  # 845 ± 15

    # -----------------------------------------------------------------------
    # Trip 3: Over-speed
    # Expected: 1 x OVER_SPEED (MEDIUM, 45 s, max 75) +
    #           1 x EXTREME_OVER_SPEED (CRITICAL, 30 s).
    #           The single spike (#10) is NOT flagged.
    # -----------------------------------------------------------------------
    resp3 = client.post("/trips/3/audit", headers=admin_hdr)
    assert resp3.status_code == 200, resp3.text
    data3 = resp3.json()
    assert data3["trip_id"] == 3
    assert data3["new"] == 2
    assert len(data3["violations"]) == 2

    types = {v["type"]: v for v in data3["violations"]}
    assert "OVER_SPEED" in types
    assert "EXTREME_OVER_SPEED" in types

    v_over = types["OVER_SPEED"]
    assert str(v_over["severity"]) in ("MEDIUM", "1")
    assert v_over["details"]["duration_s"] == 45.0
    assert v_over["details"]["max_speed_kmph"] == 75.0

    v_ext = types["EXTREME_OVER_SPEED"]
    assert str(v_ext["severity"]) in ("CRITICAL", "3")
    assert v_ext["details"]["duration_s"] == 30.0
    assert v_ext["details"]["max_speed_kmph"] == 110.0

    # -----------------------------------------------------------------------
    # Trip 4: Clean control
    # Expected: 0 violations.
    # -----------------------------------------------------------------------
    resp4 = client.post("/trips/4/audit", headers=admin_hdr)
    assert resp4.status_code == 200, resp4.text
    data4 = resp4.json()
    assert data4["trip_id"] == 4
    assert data4["new"] == 0
    assert data4["total"] == 0
    assert len(data4["violations"]) == 0


def test_backup_script(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_file = backup_database(dest_dir=str(backup_dir))
    assert os.path.exists(backup_file)
    assert os.path.getsize(backup_file) > 0
    assert "app-" in os.path.basename(backup_file)
