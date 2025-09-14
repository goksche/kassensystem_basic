from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, Numeric, ForeignKey, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship

from .base import Base

# ---------- Kern-Entities ----------

class Kunde(Base):
    __tablename__ = "kunden"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    telefon = Column(String(100))
    email = Column(String(200))
    bemerkungen = Column(Text)
    kundenstatus = Column(String(50), default="aktiv")
    punkte = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    belege = relationship("Beleg", back_populates="kunde", cascade="all, delete-orphan")

class Mitarbeiter(Base):
    __tablename__ = "mitarbeiter"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    rollen = Column(String(200), nullable=False)  # z. B. "mitarbeiter,admin"
    provision_schema = Column(Text)               # JSON
    verfuegbarkeit = Column(Text)                 # JSON
    aktiv = Column(Integer, default=1)

    belege = relationship("Beleg", back_populates="mitarbeiter", cascade="all, delete-orphan")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    dauer_min = Column(Integer, nullable=False)
    basispreis = Column(Numeric(10, 2), nullable=False)
    kategorie = Column(String(100))
    steuer_code = Column(String(50), nullable=False)  # z. B. "CH-7.7"
    materialkosten = Column(Numeric(10, 2))
    aktiv = Column(Integer, default=1)

class Produkt(Base):
    __tablename__ = "produkte"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    verkaufspreis = Column(Numeric(10, 2), nullable=False)
    einkaufspreis = Column(Numeric(10, 2))
    steuer_code = Column(String(50), nullable=False)
    lagerbestand = Column(Integer)
    aktiv = Column(Integer, default=1)

# ---------- Termine (optional) ----------
class Termin(Base):
    __tablename__ = "termine"
    id = Column(Integer, primary_key=True)
    kunde_id = Column(Integer, ForeignKey("kunden.id", ondelete="CASCADE"), nullable=False)
    mitarbeiter_id = Column(Integer, ForeignKey("mitarbeiter.id", ondelete="SET NULL"))
    start_ts = Column(DateTime, nullable=False)
    ende_ts = Column(DateTime, nullable=False)
    zustand = Column(String(20), nullable=False)  # gebucht|no-show|erledigt
    ressourcen = Column(Text)
    bemerkung = Column(Text)

class TerminService(Base):
    __tablename__ = "termine_services"
    termin_id = Column(Integer, ForeignKey("termine.id", ondelete="CASCADE"), primary_key=True)
    service_id = Column(Integer, ForeignKey("services.id", ondelete="CASCADE"), primary_key=True)
    preis_override = Column(Numeric(10, 2))

# ---------- Kasse / Belege ----------
class Beleg(Base):
    __tablename__ = "belege"
    id = Column(Integer, primary_key=True)
    belegnr = Column(String(50), nullable=False, unique=True)
    kunde_id = Column(Integer, ForeignKey("kunden.id", ondelete="SET NULL"))
    mitarbeiter_id = Column(Integer, ForeignKey("mitarbeiter.id", ondelete="SET NULL"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    summe_brutto = Column(Numeric(10, 2), nullable=False)
    rabatt_betrag = Column(Numeric(10, 2), default=0)
    trinkgeld = Column(Numeric(10, 2), default=0)
    steuer_summe = Column(Numeric(10, 2), nullable=False)
    zahlstatus = Column(String(20), default="offen")  # offen|bezahlt|teilbezahlt|storniert
    zahlart = Column(String(20))  # optionaler Sammelwert, wenn kein Split

    kunde = relationship("Kunde", back_populates="belege")
    mitarbeiter = relationship("Mitarbeiter", back_populates="belege")
    positionen = relationship("BelegPosition", back_populates="beleg", cascade="all, delete-orphan")
    zahlungen = relationship("Zahlung", back_populates="beleg", cascade="all, delete-orphan")

class BelegPosition(Base):
    __tablename__ = "beleg_positionen"
    id = Column(Integer, primary_key=True)
    beleg_id = Column(Integer, ForeignKey("belege.id", ondelete="CASCADE"), nullable=False)
    typ = Column(String(20), nullable=False)  # service|produkt
    ref_id = Column(Integer, nullable=False)  # service_id oder produkt_id
    menge = Column(Numeric(10, 3), nullable=False, default=1)
    einzelpreis = Column(Numeric(10, 2), nullable=False)
    steuer_code = Column(String(50), nullable=False)
    steuer_betrag = Column(Numeric(10, 2), nullable=False)
    gesamtpreis = Column(Numeric(10, 2), nullable=False)  # inkl. Steuer

    beleg = relationship("Beleg", back_populates="positionen")

class Zahlung(Base):
    __tablename__ = "zahlungen"
    id = Column(Integer, primary_key=True)
    beleg_id = Column(Integer, ForeignKey("belege.id", ondelete="CASCADE"), nullable=False)
    art = Column(String(20), nullable=False)  # bar|twint|karte|rechnung
    betrag = Column(Numeric(10, 2), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    beleg = relationship("Beleg", back_populates="zahlungen")

# ---------- Kassenbuch & Abschluss ----------
class Kassenbuch(Base):
    __tablename__ = "kassenbuch"
    id = Column(Integer, primary_key=True)
    datum = Column(Date, nullable=False)
    startfloat = Column(Numeric(10, 2), nullable=False)
    einlagen = Column(Numeric(10, 2), default=0)
    entnahmen = Column(Numeric(10, 2), default=0)
    bar_ist = Column(Numeric(10, 2))
    bar_soll = Column(Numeric(10, 2))
    differenz = Column(Numeric(10, 2))

class Abschluss(Base):
    __tablename__ = "abschluesse"
    id = Column(Integer, primary_key=True)
    datum = Column(Date, nullable=False, unique=True)
    summe_bar = Column(Numeric(10, 2), nullable=False)
    summe_twint = Column(Numeric(10, 2), nullable=False)
    summe_karte = Column(Numeric(10, 2), nullable=False)
    trinkgeld = Column(Numeric(10, 2), nullable=False)
    differenz = Column(Numeric(10, 2), nullable=False)
    signaturen = Column(Text)   # JSON
    pdf_path = Column(Text)

# ---------- Ausgaben / Konfig / Audit ----------
class Ausgabe(Base):
    __tablename__ = "ausgaben"
    id = Column(Integer, primary_key=True)
    datum = Column(Date, nullable=False)
    kategorie = Column(String(100), nullable=False)
    betrag = Column(Numeric(10, 2), nullable=False)
    zahlart = Column(String(20), nullable=False)  # bar|twint|karte|rechnung
    belegt = Column(Integer, default=0)           # 0/1
    kassenbezug = Column(Integer, default=0)      # 0/1
    bemerkung = Column(Text)

class Konfig(Base):
    __tablename__ = "konfig"
    key = Column(String(100), primary_key=True)
    value_json = Column(Text, nullable=False)

class Audit(Base):
    __tablename__ = "audit"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    aktion = Column(String(100), nullable=False)
    ziel_typ = Column(String(100), nullable=False)
    ziel_id = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)
    details_json = Column(Text)
