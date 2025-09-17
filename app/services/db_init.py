# kassensystem_basic/app/services/db_init.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.models.base import Base, engine, SessionLocal
# Alle Modelle registrieren (Side-Effect-Import)
import app.models.entities  # noqa: F401
import app.models.user  # noqa: F401
from app.services.auth import seed_users_if_empty


def _ensure_sqlite_parent_dir() -> None:
    """Erstellt den Ordner fuer die SQLite-Datei, falls noetig."""
    try:
        db_file: Optional[str] = engine.url.database  # type: ignore[attr-defined]
        if db_file:
            Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def init_db(dev_seed: bool = True) -> None:
    """
    Initialisiert die DB-Struktur und legt (optional) Demo-User an.
    Wird beim App-Startup von main.py aufgerufen.
    """
    _ensure_sqlite_parent_dir()
    Base.metadata.create_all(bind=engine)

    if dev_seed:
        with SessionLocal() as db:
            seed_users_if_empty(db)
