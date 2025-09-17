# kassensystem_basic/app/models/base.py
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings as app_settings

Base = declarative_base()


def _build_engine():
    url = app_settings.DATABASE_URL

    # SQLite: Pfad absolut machen und Ordner sicherstellen
    if url.startswith("sqlite:///"):
        rel = url[len("sqlite:///"):]  # z. B. ./db/kassensystem.db
        db_file = Path(rel)
        if not db_file.is_absolute():
            db_file = Path.cwd() / db_file
        db_file.parent.mkdir(parents=True, exist_ok=True)
        abs_url = f"sqlite:///{db_file.as_posix()}"
        return create_engine(
            abs_url,
            connect_args={"check_same_thread": False},  # nur für SQLite
            future=True,
            pool_pre_ping=True,
        )

    # Andere DBs (Postgres/MySQL)
    return create_engine(url, future=True, pool_pre_ping=True)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Iterator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
