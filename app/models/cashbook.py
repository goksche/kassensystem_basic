# kassensystem_basic/app/models/cashbook.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, Text, Index
from app.models.base import Base

class KassenbuchEintrag(Base):
    __tablename__ = "kassenbuch"

    id = Column(Integer, primary_key=True)
    datum = Column(Date, nullable=False, index=True)
    typ = Column(String(20), nullable=False)  # START | EINLAGE | ENTNAHME | IST
    betrag = Column(Numeric(10, 2), nullable=False, default=0)
    notiz = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

Index("ix_kassenbuch_datum_typ", KassenbuchEintrag.datum, KassenbuchEintrag.typ)
