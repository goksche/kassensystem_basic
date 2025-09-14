from __future__ import annotations

from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import Base, engine, SessionLocal, to_json
from app.models.entities import (
    Kunde, Mitarbeiter, Service, Produkt, Konfig
)

def init_db(dev_seed: bool = False) -> None:
    """
    Erstellt alle Tabellen. Füllt DEV-Seed-Daten, wenn dev_seed=True
    (wir übergeben das in main.py passend).
    """
    Base.metadata.create_all(bind=engine)

    if not dev_seed:
        return

    with SessionLocal() as s:  # type: Session
        has_service = s.execute(select(Service.id)).first()
        has_product = s.execute(select(Produkt.id)).first()
        has_mitarb = s.execute(select(Mitarbeiter.id)).first()

        tax_key = "taxes"
        if not s.get(Konfig, tax_key):
            s.add(Konfig(key=tax_key, value_json=to_json({"CH-7.7": 0.077, "CH-2.6": 0.026, "CH-0": 0.0})))

        if not has_mitarb:
            s.add_all([
                Mitarbeiter(name="Mitarbeiter/in 1", rollen="mitarbeiter", aktiv=1),
                Mitarbeiter(name="Admin", rollen="admin", aktiv=1),
            ])

        if not has_service:
            s.add_all([
                Service(name="Haarschnitt", dauer_min=30, basispreis=Decimal("48.00"), kategorie="Service", steuer_code="CH-7.7", aktiv=1),
                Service(name="Waschen & Foehnen", dauer_min=20, basispreis=Decimal("28.00"), kategorie="Service", steuer_code="CH-7.7", aktiv=1),
                Service(name="Farbe", dauer_min=60, basispreis=Decimal("79.00"), kategorie="Service", steuer_code="CH-7.7", aktiv=1),
            ])

        if not has_product:
            s.add_all([
                Produkt(name="Pflege-Shampoo", verkaufspreis=Decimal("19.90"), einkaufspreis=Decimal("9.50"), steuer_code="CH-7.7", lagerbestand=25, aktiv=1),
                Produkt(name="Conditioner", verkaufspreis=Decimal("21.90"), einkaufspreis=Decimal("10.20"), steuer_code="CH-7.7", lagerbestand=15, aktiv=1),
            ])

        s.commit()
