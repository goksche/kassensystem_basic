from __future__ import annotations

import json
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config.settings import DATABASE_URL

# Paket-Root: .../kassensystem_basic
PKG_ROOT = Path(__file__).resolve().parents[2]

def _normalize_sqlite_url(url: str) -> str:
    """
    Macht aus 'sqlite:///./db/kassensystem.db' einen absoluten Pfad relativ zum Paket-Root.
    Legt den DB-Ordner automatisch an.
    """
    if url.startswith("sqlite:///"):
        rel = url.replace("sqlite:///", "", 1)
        abs_path = (PKG_ROOT / rel).resolve()
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{abs_path.as_posix()}"
    return url

SQLALCHEMY_DATABASE_URL = _normalize_sqlite_url(DATABASE_URL)

# Engine + Session
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)

Base = declarative_base()

# SQLite: Foreign Keys aktivieren
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _):
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass

def get_session() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Kleine Helper fuer JSON in Konfig/Audit
def to_json(data) -> str:
    return json.dumps(data, ensure_ascii=False)
