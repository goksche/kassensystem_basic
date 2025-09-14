from __future__ import annotations
from typing import Tuple
from sqlalchemy.orm import Session
from app.models.entities import Konfig
import json

DEFAULT_CONF = {"prefix": "KS-", "next_number": 10001}

def _load_receipt_conf(db: Session) -> dict:
    row = db.get(Konfig, "receipt")
    if not row:
        row = Konfig(key="receipt", value_json=json.dumps(DEFAULT_CONF))
        db.add(row)
        db.commit()
        return DEFAULT_CONF
    try:
        return json.loads(row.value_json)
    except Exception:
        return DEFAULT_CONF

def next_receipt_number(db: Session) -> str:
    """Liest Konfig, inkrementiert next_number atomar und liefert string 'PREFIXNNNN'."""
    conf = _load_receipt_conf(db)
    prefix = conf.get("prefix", "KS-")
    next_no = int(conf.get("next_number", 10001))
    new_no = next_no + 1

    # persistieren
    row = db.get(Konfig, "receipt")
    row.value_json = json.dumps({"prefix": prefix, "next_number": new_no})
    db.add(row)
    db.commit()

    return f"{prefix}{next_no}"
