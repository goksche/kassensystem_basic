from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session
from app.models.entities import Konfig

Money = Decimal

Q2 = Decimal("0.01")

def D(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))

def round2(x: Decimal) -> Decimal:
    return x.quantize(Q2, rounding=ROUND_HALF_UP)

def load_tax_rates(db: Session) -> Dict[str, Decimal]:
    """Liest MWST-Sätze aus Konfig ('taxes'). Fallback: CH-7.7."""
    row = db.get(Konfig, "taxes")
    if not row:
        return {"CH-7.7": D("0.077")}
    try:
        import json
        data = json.loads(row.value_json)
        return {k: D(v) for k, v in data.items()}
    except Exception:
        return {"CH-7.7": D("0.077")}

def split_discount_proportional(line_gross: List[Decimal], discount_total: Decimal) -> List[Decimal]:
    subtotal = sum(line_gross) if line_gross else D("0")
    if subtotal <= 0 or discount_total <= 0:
        return [D("0") for _ in line_gross]
    # proportional nach Brutto-Anteil
    out = []
    acc = D("0")
    for i, lg in enumerate(line_gross):
        if i < len(line_gross) - 1:
            part = (lg / subtotal) * discount_total
            part = round2(part)
            out.append(part)
            acc += part
        else:
            out.append(round2(discount_total - acc))  # Rest auf letzte Position
    return out

def summarize_cart(cart: dict, db: Session) -> dict:
    """
    Erwartet cart:
    {
      "items":[{"line_id", "typ","ref_id","name","qty","unit_price","steuer_code"}],
      "discount_percent": 0,     # optional
      "discount_amount": 0,      # optional (CHF), überschreibt percent wenn >0
      "tip": 0                   # CHF
    }
    """
    tax_rates = load_tax_rates(db)

    items = cart.get("items", [])
    line_gross = [D(i["unit_price"]) * D(i["qty"]) for i in items]
    subtotal_gross = round2(sum(line_gross))

    discount_amount = D(cart.get("discount_amount") or "0")
    discount_percent = D(cart.get("discount_percent") or "0")
    if discount_amount <= 0 and discount_percent > 0:
        discount_amount = round2(subtotal_gross * (discount_percent / D("100")))

    discount_amount = min(discount_amount, subtotal_gross)  # nicht über Subtotal

    # Rabatt proportional auf Positionen verteilen
    discounts_per_line = split_discount_proportional(line_gross, discount_amount)
    line_gross_after_discount: List[Decimal] = [
        round2(g - d) for g, d in zip(line_gross, discounts_per_line)
    ]

    # Steuer berechnen: Preise sind Brutto → Steuer = Brutto - Netto
    tax_by_code: Dict[str, Decimal] = {}
    line_tax: List[Decimal] = []
    for i, it in enumerate(items):
        code = it["steuer_code"]
        rate = tax_rates.get(code, D("0"))
        gross = line_gross_after_discount[i]
        if rate > 0:
            net = gross / (D("1") + rate)
            tax = round2(gross - net)
        else:
            tax = D("0.00")
        line_tax.append(tax)
        tax_by_code[code] = round2(tax_by_code.get(code, D("0")) + tax)

    tax_total = round2(sum(line_tax))
    tip = round2(D(cart.get("tip") or "0"))
    total_gross = round2(sum(line_gross_after_discount) + tip)

    return {
        "items": [
            {
                **it,
                "line_gross": float(round2(D(it["unit_price"]) * D(it["qty"]))),
            }
            for it in items
        ],
        "subtotal_gross": float(subtotal_gross),
        "discount_percent": float(discount_percent),
        "discount_amount": float(round2(discount_amount)),
        "tax_by_code": {k: float(round2(v)) for k, v in tax_by_code.items()},
        "tax_total": float(tax_total),
        "tip": float(tip),
        "total_gross": float(total_gross),
    }
