from pydantic import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    APP_NAME: str = "Kassensystem Basic"
    DEBUG: bool = True

    # Session/Secret
    SECRET_KEY: str = "change-this-in-production-please-32bytes"
    SESSION_COOKIE_NAME: str = "ksb_session"

    # DEV-Modus (nur Admin darf toggeln; Sichtbarkeit steuert Template via Rolle)
    DEV_MODE: bool = True

    # Header-Navigation & Dashboard-Kacheln konfigurierbar (wir lesen/schreiben hier;
    # Persistenz kann später via DB/JSON erfolgen)
    HEADER_ITEMS: List[str] = [
        "Dashboard",
        "POS",
        "Katalog",
        "Kalender",
        "Kunden",
        "Mitarbeiter",
        "Berichte",
        "Ausgaben",
        "Abschluss",
        "Gast-Portal",
    ]
    DASHBOARD_TILES: List[str] = [
        "Schnellstart POS",
        "Heutige Termine",
        "Top Artikel",
        "Umsatz heute",
        "Kassenbuch",
    ]

    class Config:
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
