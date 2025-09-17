# kassensystem_basic/app/services/config_store.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from app.config import settings as app_settings


def _default_config() -> dict:
    """
    Erzeugt eine Default-Konfiguration basierend auf den Settings.
    Alle Header-Eintraege sichtbar (1), Flags wie Default.
    Keys fuer Header basieren auf href (stabiler als Label).
    """
    nav = app_settings.get_nav_items(dev=True)
    flags = app_settings.get_dash_flags(dev=True)
    return {
        "header_visibility": {item["href"]: 1 for item in nav},
        "dashboard_flags": {k: int(v) for k, v in flags.items()},
    }


def load_config() -> dict:
    path = Path(app_settings.DEV_CONFIG_PATH)
    if not path.exists():
        cfg = _default_config()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return cfg
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # Fallback auf Default, wenn Datei defekt ist
        cfg = _default_config()
        path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return cfg


def save_config(cfg: dict) -> None:
    path = Path(app_settings.DEV_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def sanitize_config(cfg: dict) -> dict:
    """
    Stellt sicher, dass nur bekannte Keys enthalten sind.
    Fehlende Keys werden mit Defaults aufgefuellt.
    """
    base = _default_config()
    hv = cfg.get("header_visibility", {})
    df = cfg.get("dashboard_flags", {})
    clean_hv = {}
    for item in app_settings.get_nav_items(dev=True):
        href = item["href"]
        clean_hv[href] = int(hv.get(href, 1))
    clean_df = {}
    for k in base["dashboard_flags"].keys():
        clean_df[k] = int(df.get(k, base["dashboard_flags"][k]))
    return {"header_visibility": clean_hv, "dashboard_flags": clean_df}


def effective_nav_items(dev: bool) -> List[dict]:
    """
    Liefert die Navigationspunkte unter Beruecksichtigung der DEV-Config (nur in DEV).
    """
    items = app_settings.get_nav_items(dev)
    if not dev:
        return items
    cfg = sanitize_config(load_config())
    vis = cfg["header_visibility"]
    return [it for it in items if int(vis.get(it["href"], 1)) == 1]


def effective_dash_flags(dev: bool) -> Dict[str, int]:
    """
    Liefert die Dashboard-Flags unter Beruecksichtigung der DEV-Config (nur in DEV).
    """
    base = app_settings.get_dash_flags(dev)
    if not dev:
        return base
    cfg = sanitize_config(load_config())
    out = dict(base)
    out.update(cfg["dashboard_flags"])
    return {k: int(v) for k, v in out.items()}
