"""
scripts/backup.py
Online SQLite backup using sqlite3.Connection.backup() per SPEC 12.5.
Backs up to data/backups/app-<UTC timestamp>.db.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from datetime import datetime, timezone
import logging

from app.core.config import settings

log = logging.getLogger(__name__)


def backup_database(dest_dir: str | None = None) -> str:
    """
    Perform an online backup of the SQLite database.
    Returns the path to the created backup file.
    """
    db_url = settings.DATABASE_URL
    if not db_url.startswith("sqlite:///"):
        raise ValueError(f"Online backup is only supported for SQLite databases, got: {db_url}")

    src_path = db_url.replace("sqlite:///", "")
    if src_path.startswith(":memory:"):
        raise ValueError("Cannot backup an in-memory database via file backup")

    src_abs = os.path.abspath(src_path)
    if not os.path.exists(src_abs):
        raise FileNotFoundError(f"Source database file not found: {src_abs}")

    if dest_dir is None:
        db_dir = os.path.dirname(src_abs)
        dest_dir = os.path.join(db_dir, "backups")

    os.makedirs(dest_dir, exist_ok=True)

    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest_path = os.path.join(dest_dir, f"app-{ts_str}.db")

    log.info("Backing up SQLite database from %s to %s", src_abs, dest_path)
    src_conn = sqlite3.connect(src_abs)
    dest_conn = sqlite3.connect(dest_path)
    try:
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()

    print(f"Database backed up successfully to: {dest_path}")
    return dest_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    backup_database()
