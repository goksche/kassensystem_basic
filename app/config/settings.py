# kassensystem_basic/app/config/settings.py

APP_NAME: str = "Kassensystem Basic"
SECRET_KEY: str = "change-this-in-production-please-32bytes"

# DEV-Flag (wird in der Session ueberschrieben, wenn toggled)
DEFAULT_DEV_MODE: bool = True

# DB-URL (sqlite Datei liegt unter ./db/)
DATABASE_URL: str = "sqlite:///./db/kassensystem.db"

# Pfad fuer die DEV-UI-Konfiguration (JSON)
DEV_CONFIG_PATH: str = "app/config/dev_ui_config.json"


def get_nav_items(dev: bool) -> list[dict]:
    """
    Standard-Navigation (v0.1-Stil). Im DEV kann die Sichtbarkeit
    einzelner Menuepunkte per JSON-Konfig uebersteuert werden.
    """
    return [
        {"href": "/", "label": "Dashboard"},
        {"href": "/pos", "label": "Kasse"},
        {"href": "/katalog", "label": "Katalog"},
        {"href": "/kalender", "label": "Kalender"},
        {"href": "/kunden", "label": "Kunden"},
        {"href": "/mitarbeiter", "label": "Mitarbeiter"},
        {"href": "/berichte", "label": "Berichte"},
        {"href": "/ausgaben", "label": "Ausgaben"},
        {"href": "/abschluss", "label": "Abschluss"},
        {"href": "/gast_portal", "label": "Gast-Portal"},
        {"href": "/einstellungen", "label": "Einstellungen"},
    ]


def get_dash_flags(dev: bool) -> dict:
    """
    Standard-Dashboard-Kacheln (1=anzeigen). Im DEV kann per JSON uebersteuert werden.
    """
    return {
        "pos_quick": 1,
        "termine_heute": 1,
        "top_artikel": 1,
        "umsatz_heute": 1,
        "kassenbuch": 1,
    }
