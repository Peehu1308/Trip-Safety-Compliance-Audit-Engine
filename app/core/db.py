import os
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

if settings.DATABASE_URL.startswith("sqlite:///"):
    _path = settings.DATABASE_URL[len("sqlite:///"):]
    if _path and not _path.startswith(":memory:"):
        os.makedirs(os.path.dirname(os.path.abspath(_path)), exist_ok=True)

engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn, _):
    dbapi_conn.isolation_level = None          # we control BEGIN ourselves
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()

@event.listens_for(engine, "begin")
def _on_begin(conn):
    conn.exec_driver_sql("BEGIN IMMEDIATE")    # writers serialize; prevents stale-read hash-chain forks

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def write_tx():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
