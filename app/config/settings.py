import os
from typing import List, Dict

# Grundeinstellungen
APP_NAME = "Kassensystem Basic"
VERSION = "0.1.0"
DATABASE_URL = "sqlite:///./db/kassensystem.db"

# Secret fuer Session-Cookies (in PROD ueber Env setzen!)
SECRET_KEY = os.getenv("KSB_SECRET", "change-this-in-prod-very-secret")

# Default-DEV (kann per Button zur Laufzeit pro Session ueberschrieben werden)
DEFAULT_DEV_MODE: bool = os.getenv("KSB_DEV", "1") == "1"

# -------------------------------
# Header-Navigation Konfiguration
# -------------------------------

NAV_ITEMS_PROD: List[Dict] = [
    {"path": "/ui/dashboard",    "label": "Dashboard",         "visible": True},
    {"path": "/ui/pos",          "label": "Kasse",             "visible": True},
    {"path": "/ui/kalender",     "label": "Kalender (optional)","visible": True},
    {"path": "/ui/kunden",       "label": "Kunden",            "visible": True},
    {"path": "/ui/katalog",      "label": "Katalog",           "visible": True},
    {"path": "/ui/berichte",     "label": "Berichte",          "visible": True},
    {"path": "/ui/abschluss",    "label": "Tagesabschluss",    "visible": True},
    {"path": "/ui/gast",         "label": "Gast-Portal",       "visible": True},
    {"path": "/ui/einstellungen", "label": "Einstellungen",     "visible": True},
]

# DEV-Nav (im DEV per Button sichtbar – hier Reihenfolge/Sichtbarkeit steuern)
NAV_ITEMS_DEV: List[Dict] = [
    {"path": "/ui/dashboard",    "label": "Dashboard",         "visible": True},
    {"path": "/ui/pos",          "label": "Kasse",             "visible": True},
    {"path": "/ui/kalender",     "label": "Kalender (optional)","visible": True},
    {"path": "/ui/kunden",       "label": "Kunden",            "visible": True},
    {"path": "/ui/katalog",      "label": "Katalog",           "visible": True},
    {"path": "/ui/berichte",     "label": "Berichte",          "visible": True},
    {"path": "/ui/abschluss",    "label": "Tagesabschluss",    "visible": True},
    {"path": "/ui/gast",         "label": "Gast-Portal",       "visible": True},
    {"path": "/ui/einstellungen", "label": "Einstellungen",     "visible": True},
]

def get_nav_items(dev_mode: bool) -> List[Dict]:
    items = NAV_ITEMS_DEV if dev_mode else NAV_ITEMS_PROD
    return [i for i in items if i.get("visible", True)]

# -------------------------------
# Dashboard-Tiles Konfiguration
# -------------------------------
DASH_TILES_DEV: Dict[str, bool] = {
    "pos": True,
    "kalender": True,
    "kunden": True,
    "katalog": True,
    "berichte": True,
    "abschluss": True,
    "einstellungen": True,
    "gast": True,
}
DASH_TILES_PROD: Dict[str, bool] = {
    "pos": True,
    "kalender": True,
    "kunden": True,
    "katalog": True,
    "berichte": True,
    "abschluss": True,
    "einstellungen": True,
    "gast": True,
}

def get_dash_flags(dev_mode: bool) -> Dict[str, bool]:
    return DASH_TILES_DEV if dev_mode else DASH_TILES_PROD
