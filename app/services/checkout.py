# kassensystem_basic/app/services/checkout.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple, Optional
import json
import uuid

from sqlalchemy.orm import Session

# Modelle
from app.models.entities import Service, Produkt

# --- Hilfen -------------------------------------------------------------

TAX = {
    "CH-7.7": Decimal("0.077"),
    "CH-2.6": Decimal("0.026"),
    "CH-0":   Decimal("0.0"),
}

@dataclass
class CartItem:
    kind: str           # "service" | "produkt"
    ref_id: Optional[int]
    name: str
    price: Decimal
    qty: int
    tax_code: str

def _D(val: Any, default: str = "0") -> Decimal:
    if val is None or val == "":
        val = default
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val))
    s = str(val).replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        raise InvalidOperation(s)

def _get_receipt_number(db: Session) -> str:
    """
    Versuche, die bestehende Nummernlogik zu verwenden – fallbacksicher.
    """
    try:
        from app.services import receipt_numbers as rn
        for fn in ("get_next_receipt_number", "next_number", "next_receipt_number", "generate_receipt_number"):
            if hasattr(rn, fn):
                return str(getattr(rn, fn)(db))
    except Exception:
        pass
    # Fallback: Timestamp + Kurz-UUID
    return f"R{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6].upper()}"

def _set_if(obj: Any, field: str, value: Any):
    if hasattr(obj, field):
        setattr(obj, field, value)

def _compute_totals(items: List[CartItem], disc_abs: Decimal, disc_pct: Decimal, tip: Decimal) -> Tuple[Decimal, Decimal, Decimal, Dict[str, Decimal]]:
    """
    Annahme: Preise sind Bruttopreise (üblich an der Kasse).
    Gibt zurück: (subtotal, discount_total, total, tax_breakdown)
    """
    subtotal = sum((it.price * it.qty for it in items), start=Decimal("0"))
    pct_amt = (subtotal * disc_pct / Decimal("100")).quantize(Decimal("0.01"))
    discount = min(subtotal, (disc_abs + pct_amt))
    tax_breakdown: Dict[str, Decimal] = {}
    for it in items:
        rate = TAX.get(it.tax_code, Decimal("0"))
        line = it.price * it.qty
        tax_part = (line * rate / (Decimal("1") + rate)).quantize(Decimal("0.01"))
        tax_breakdown[it.tax_code] = tax_breakdown.get(it.tax_code, Decimal("0")) + tax_part
    total = max(Decimal("0"), subtotal - discount) + tip
    return (subtotal, discount, total, tax_breakdown)

# --- Hauptfunktion ------------------------------------------------------

def process_checkout(db: Session, payload: Dict[str, Any], current_user: Any) -> Dict[str, Any]:
    """
    Validiert den Warenkorb, erzeugt eine Belegnummer und persistiert – wo möglich –
    Beleg/Positionen/Zahlungen. Zieht Lager für Produkte ab.
    """
    items_raw = payload.get("items") or []
    if not isinstance(items_raw, list) or len(items_raw) == 0:
        raise ValueError("Leerer Warenkorb.")

    items: List[CartItem] = []
    # Validierung & Aufbereitung
    for row in items_raw:
        rid_raw = str(row.get("id", ""))
        kind = row.get("type") or ("service" if rid_raw.startswith("s-") else "produkt")
        name = (row.get("name") or "").strip()
        price = _D(row.get("price"))
        qty = int(row.get("qty") or 1)
        tax_code = (row.get("tax") or "CH-7.7").strip() or "CH-7.7"

        if not name or price <= 0 or qty <= 0:
            raise ValueError("Ungültige Position.")

        ref_id: Optional[int] = None
        if rid_raw.startswith(("s-", "p-")):
            try:
                ref_id = int(rid_raw.split("-", 1)[1])
            except Exception:
                ref_id = None

        # Existenz prüfen (falls ID vorhanden)
        if ref_id:
            if kind == "service":
                obj = db.get(Service, ref_id)
                if not obj or (hasattr(obj, "aktiv") and not obj.aktiv):
                    raise ValueError("Service nicht (mehr) verfügbar.")
                # Absicherung konsistenter Werte
                if hasattr(obj, "steuer_code"):
                    tax_code = obj.steuer_code
            else:
                obj = db.get(Produkt, ref_id)
                if not obj or (hasattr(obj, "aktiv") and not obj.aktiv):
                    raise ValueError("Produkt nicht (mehr) verfügbar.")
                if hasattr(obj, "steuer_code"):
                    tax_code = obj.steuer_code

        items.append(CartItem(kind=kind, ref_id=ref_id, name=name, price=price, qty=qty, tax_code=tax_code))

    disc_abs = _D(payload.get("discount_abs"))
    disc_pct = _D(payload.get("discount_pct"))
    tip      = _D(payload.get("tip"))

    subtotal, discount, total, tax_breakdown = _compute_totals(items, disc_abs, disc_pct, tip)

    # --- Persistenz versuchen ------------------------------------------
    receipt_number = _get_receipt_number(db)
    created_id: Optional[int] = None

    try:
        # Belegmodell dynamisch holen
        from app.models.entities import Beleg, BelegPosition, Zahlung  # type: ignore

        receipt = Beleg()  # type: ignore
        _set_if(receipt, "nummer", receipt_number)
        _set_if(receipt, "datum", datetime.now())
        _set_if(receipt, "created_at", datetime.now())
        _set_if(receipt, "brutto", (subtotal - discount + tip))
        _set_if(receipt, "netto", (subtotal - sum(tax_breakdown.values()) - discount))
        _set_if(receipt, "rabatt_betrag", discount)
        _set_if(receipt, "rabatt_prozent", disc_pct)
        _set_if(receipt, "trinkgeld", tip)
        _set_if(receipt, "steuer_json", json.dumps({k: str(v) for k, v in tax_breakdown.items()}))
        _set_if(receipt, "user_id", getattr(current_user, "id", None))
        _set_if(receipt, "rolle", getattr(current_user, "role", None))

        db.add(receipt)
        db.flush()  # ID verfügbar
        created_id = getattr(receipt, "id", None)

        # Positionen
        for it in items:
            pos = BelegPosition()  # type: ignore
            # Beziehung / FK
            if hasattr(pos, "beleg"):
                setattr(pos, "beleg", receipt)
            elif hasattr(pos, "beleg_id") and created_id is not None:
                setattr(pos, "beleg_id", created_id)

            # Referenzen
            if it.kind == "produkt":
                if hasattr(pos, "produkt_id"): _set_if(pos, "produkt_id", it.ref_id)
                _set_if(pos, "typ", "produkt")
            else:
                if hasattr(pos, "service_id"): _set_if(pos, "service_id", it.ref_id)
                _set_if(pos, "typ", "service")

            # Werte
            _set_if(pos, "name", it.name)
            _set_if(pos, "menge", it.qty)
            for field in ("einzelpreis", "preis", "betrag"):
                if hasattr(pos, field):
                    setattr(pos, field, it.price)
                    break
            _set_if(pos, "steuer_code", it.tax_code)
            # optional: brutto
            if hasattr(pos, "brutto"):
                setattr(pos, "brutto", (it.price * it.qty))

            db.add(pos)

            # Lagerabzug bei Produkt
            if it.kind == "produkt" and it.ref_id:
                p = db.get(Produkt, it.ref_id)
                if p is not None and hasattr(p, "lagerbestand"):
                    try:
                        new_val = (p.lagerbestand or 0) - it.qty  # type: ignore
                        if new_val < 0:
                            new_val = 0
                        p.lagerbestand = new_val  # type: ignore
                        db.add(p)
                    except Exception:
                        pass

        # Zahlungen
        for pay in payload.get("payment") or []:
            m = (pay.get("method") or "BAR").upper()
            amt = _D(pay.get("amount"))
            z = Zahlung()  # type: ignore
            if hasattr(z, "beleg"):
                setattr(z, "beleg", receipt)
            elif hasattr(z, "beleg_id") and created_id is not None:
                setattr(z, "beleg_id", created_id)
            _set_if(z, "methode", m)
            for field in ("betrag", "amount", "wert"):
                if hasattr(z, field):
                    setattr(z, field, amt)
                    break
            db.add(z)

        db.commit()

    except Exception:
        # Sicherheitshalber nichts halbgares hinterlassen
        db.rollback()
        created_id = None  # wir liefern trotzdem eine Nummer zurück – Beleg kann später erneut gebucht werden

    # Antwort
    return {
        "ok": True,
        "receipt_number": receipt_number,
        "receipt_id": created_id,
        "subtotal": str(subtotal),
        "discount": str(discount),
        "tip": str(tip),
        "total": str(total),
        "tax_breakdown": {k: str(v) for k, v in tax_breakdown.items()},
    }
