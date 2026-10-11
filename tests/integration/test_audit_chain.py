"""
tests/integration/test_audit_chain.py
Integration tests for audit log hash chain and verification per SPEC 10.6, 11 & 14:
  - chain verifies after many events
  - modify a row with a raw sqlite connection (after dropping trigger) -> reports right first_broken_seq
  - deleting a middle row is detected (seq gap)
  - RBAC on /audit/log and /audit/verify
"""
import pytest
from sqlalchemy import text

from app.core.security import create_access_token
from app.domain.enums import Role
from app.models.user import User
import app.services.audit_log_service as audit_log_service
from tests.conftest import seed_user


def _auth_header(user) -> dict[str, str]:
    token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    })
    return {"Authorization": f"Bearer {token}"}


def test_chain_verifies_after_many_events(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client

    admin_user = seed_user(session, "admin_audit", Role.ADMIN)
    session.commit()
    admin_hdr = _auth_header(admin_user)

    # Append 6 audit entries
    for i in range(1, 7):
        audit_log_service.append(
            session=session,
            actor="admin_audit",
            actor_role="ADMIN",
            action=f"ACTION_{i}",
            entity_type="trip",
            entity_id=trip.id,
            payload={"step": i, "detail": f"test_payload_{i}"},
        )
    session.commit()

    # 1. Test GET /audit/log
    resp = client.get("/audit/log?limit=10&offset=0", headers=admin_hdr)
    assert resp.status_code == 200, resp.text
    entries = resp.json()
    assert len(entries) >= 6

    # Verify sequential hashes and prev_hash linking
    for idx, entry in enumerate(entries):
        assert entry["seq"] == idx + 1
        if idx == 0:
            assert entry["prev_hash"] == "0" * 64
        else:
            assert entry["prev_hash"] == entries[idx - 1]["entry_hash"]

    # 2. Test GET /audit/verify
    verify_resp = client.get("/audit/verify", headers=admin_hdr)
    assert verify_resp.status_code == 200, verify_resp.text
    verify_data = verify_resp.json()
    assert verify_data["valid"] is True
    assert verify_data["checked"] >= 6
    assert verify_data["first_broken_seq"] is None
    assert verify_data["reason"] is None


def test_chain_detects_row_modification(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client

    admin_user = seed_user(session, "admin_audit_mod", Role.ADMIN)
    session.commit()
    admin_hdr = _auth_header(admin_user)

    # Append 5 entries
    for i in range(1, 6):
        audit_log_service.append(
            session=session,
            actor="admin_audit_mod",
            actor_role="ADMIN",
            action=f"EVENT_{i}",
            entity_type="trip",
            entity_id=trip.id,
            payload={"num": i},
        )
    session.commit()

    # Initial verification should be valid
    res_before = client.get("/audit/verify", headers=admin_hdr)
    assert res_before.json()["valid"] is True

    # Drop trigger and tamper row with seq=3
    session.execute(text("DROP TRIGGER IF EXISTS audit_log_no_update"))
    session.execute(text("UPDATE audit_log SET action = 'TAMPERED_ACTION' WHERE seq = 3"))
    session.commit()

    # Verification must detect tampering at seq=3
    verify_resp = client.get("/audit/verify", headers=admin_hdr)
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["valid"] is False
    assert verify_data["first_broken_seq"] == 3
    assert "Hash mismatch at seq 3" in verify_data["reason"]


def test_chain_detects_deleted_middle_row(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client

    admin_user = seed_user(session, "admin_audit_del", Role.ADMIN)
    session.commit()
    admin_hdr = _auth_header(admin_user)

    # Append 4 entries
    for i in range(1, 5):
        audit_log_service.append(
            session=session,
            actor="admin_audit_del",
            actor_role="ADMIN",
            action=f"STEP_{i}",
            entity_type="stop",
            entity_id=stop.id,
            payload={"seq_val": i},
        )
    session.commit()

    # Drop trigger and delete middle row with seq=2
    session.execute(text("DROP TRIGGER IF EXISTS audit_log_no_delete"))
    session.execute(text("DELETE FROM audit_log WHERE seq = 2"))
    session.commit()

    # Verification must detect the sequence gap
    verify_resp = client.get("/audit/verify", headers=admin_hdr)
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["valid"] is False
    assert "seq gap" in verify_data["reason"].lower()
    assert verify_data["first_broken_seq"] == 3


def test_chain_detects_prev_hash_tampering(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client

    admin_user = seed_user(session, "admin_audit_phash", Role.ADMIN)
    session.commit()
    admin_hdr = _auth_header(admin_user)

    for i in range(1, 4):
        audit_log_service.append(
            session=session,
            actor="admin_audit_phash",
            actor_role="ADMIN",
            action=f"ACT_{i}",
            entity_type="trip",
            entity_id=trip.id,
            payload={"k": i},
        )
    session.commit()

    # Drop trigger and tamper prev_hash of row 2
    session.execute(text("DROP TRIGGER IF EXISTS audit_log_no_update"))
    session.execute(text(f"UPDATE audit_log SET prev_hash = '{"f" * 64}' WHERE seq = 2"))
    session.commit()

    verify_resp = client.get("/audit/verify", headers=admin_hdr)
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["valid"] is False
    assert verify_data["first_broken_seq"] == 2
    assert "prev_hash mismatch" in verify_data["reason"]


def test_audit_rbac_endpoints(minimal_trip_client):
    client, session, trip, stop, emp = minimal_trip_client

    emp_user = seed_user(session, "emp_audit_test", Role.EMPLOYEE)
    drv_user = seed_user(session, "drv_audit_test", Role.DRIVER)
    appr_user = seed_user(session, "appr_audit_test", Role.APPROVER)
    admin_user = seed_user(session, "admin_audit_test", Role.ADMIN)
    session.commit()

    # 1. Anonymous -> 401
    assert client.get("/audit/log").status_code == 401
    assert client.get("/audit/verify").status_code == 401

    # 2. EMPLOYEE and DRIVER -> 403
    for u in (emp_user, drv_user):
        hdr = _auth_header(u)
        assert client.get("/audit/log", headers=hdr).status_code == 403
        assert client.get("/audit/verify", headers=hdr).status_code == 403

    # 3. APPROVER and ADMIN -> 200
    for u in (appr_user, admin_user):
        hdr = _auth_header(u)
        assert client.get("/audit/log", headers=hdr).status_code == 200
        assert client.get("/audit/verify", headers=hdr).status_code == 200
