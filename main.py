from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import json
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse as StarletteRedirectResponse

from sqlalchemy import (
    Column, Integer, Float, String, DateTime, Boolean, ForeignKey, create_engine
)
from sqlalchemy.orm import Session, relationship, sessionmaker, declarative_base

# ------------------------------------------------------------------------------
# DB Base
# ------------------------------------------------------------------------------
Base = declarative_base()
engine = create_engine("sqlite:///app/data/app.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ------------------------------------------------------------------------------
# Entities
# ------------------------------------------------------------------------------
class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    basispreis = Column(Float, default=0.0)
    steuer_code = Column(String(10), default="S1")      # S1=8.1%, S2=2.6%
    aktiv = Column(Boolean, default=True)
    warengruppe = Column(String(4), default="DL")       # DL/PR/TA

class Produkt(Base):
    __tablename__ = "produkte"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    verkaufspreis = Column(Float, default=0.0)
    steuer_code = Column(String(10), default="S1")
    lagerbestand = Column(Integer, default=0)
    aktiv = Column(Boolean, default=True)
    warengruppe = Column(String(4), default="PR")       # DL/PR/TA

# ------------------------------------------------------------------------------
# Verkaufsjournal (Charge 1)
# ------------------------------------------------------------------------------
class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow)
    kassen_id = Column(String(20), default="K1")
    brutto_summe = Column(Float, default=0.0)
    rabatt_summe = Column(Float, default=0.0)
    storno = Column(Boolean, default=False)
    storno_grund = Column(String(250), nullable=True)

    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    payments = relationship("SalePayment", back_populates="sale", cascade="all, delete-orphan")

class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    typ = Column(String(10), nullable=False)            # 'service'|'produkt'
    ref_id = Column(Integer, nullable=False)
    name_snapshot = Column(String(250), nullable=False)
    menge = Column(Integer, default=1)
    vk_brutto = Column(Float, default=0.0)
    steuer_code = Column(String(10), default="S1")      # S1/S2
    warengruppe = Column(String(4), default="DL")       # DL/PR/TA

    sale = relationship("Sale", back_populates="items")

class SalePayment(Base):
    __tablename__ = "sale_payments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    art = Column(String(12), nullable=False)            # bar/karte/twint/gutschein/guthaben/offen
    betrag = Column(Float, default=0.0)

    sale = relationship("Sale", back_populates="payments")

# ------------------------------------------------------------------------------
# App / Templates / Middleware
# ------------------------------------------------------------------------------
APP_VERSION = "v0.44 + charge1 (pdf)"
app = FastAPI(title="Kassensystem Basic")
app.add_middleware(SessionMiddleware, secret_key="dev-secret", session_cookie="ksb_session")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

class CatalogAliasMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        p = request.url.path
        if p.startswith("/catalog"):
            new_p = "/katalog" + p[len("/catalog"):]
            return StarletteRedirectResponse(str(request.url.replace(path=new_p)), status_code=307)
        return await call_next(request)

app.add_middleware(CatalogAliasMiddleware)

# ------------------------------------------------------------------------------
# Settings (Datei)
# ------------------------------------------------------------------------------
SETTINGS_PATH = Path("app/data/settings.json")
DEFAULT_SETTINGS = {
    "company": {
        "name": "", "vat_number": "", "address": "", "city": "", "phone": "",
        "receipt_date_format": "%d.%m.%Y %H:%M"
    },
    "vat": {"rate1": 8.1, "rate2": 2.6},
    "kasse": {"id": "K1"}
}

def load_settings() -> dict:
    try:
        if SETTINGS_PATH.exists():
            with SETTINGS_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
                out = DEFAULT_SETTINGS | data
                out["company"] = DEFAULT_SETTINGS["company"] | out.get("company", {})
                out["vat"] = DEFAULT_SETTINGS["vat"] | out.get("vat", {})
                out["kasse"] = DEFAULT_SETTINGS["kasse"] | out.get("kasse", {})
                return out
    except Exception:
        pass
    return json.loads(json.dumps(DEFAULT_SETTINGS))

def save_settings(data: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def vat_choices() -> list[tuple[str, str]]:
    cfg = load_settings()
    r1 = float(cfg["vat"].get("rate1", 0.0))
    r2 = float(cfg["vat"].get("rate2", 0.0))
    return [("S1", f"Satz 1 ({r1:.1f}%)"), ("S2", f"Satz 2 ({r2:.1f}%)")]

def _to_cents(val):
    if val in (None, ""): return 0
    try:
        return int(Decimal(str(val)).scaleb(2).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return 0

def _to_float(val) -> float:
    return float(_to_cents(val)) / 100.0

# ------------------------------------------------------------------------------
# DB Setup & Startup
# ------------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def _startup():
    Path("app/data").mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------------------
# DEV Toggle / Header-Kontext
# ------------------------------------------------------------------------------
def _dev(request: Request) -> bool:
    v = request.session.get("dev")
    return bool(v) if v is not None else True  # default: DEV an

@app.post("/dev/toggle")
def dev_toggle(request: Request):
    cur = request.session.get("dev")
    if cur is None:
        cur = True
    request.session["dev"] = not bool(cur)
    ref = request.headers.get("referer") or "/"
    return RedirectResponse(ref, status_code=303)

def _ctx(request: Request, extra: Optional[dict] = None):
    cfg = {
        "DEV_MODE": _dev(request),
        "APP_VERSION": APP_VERSION
    }
    base = {"request": request} | cfg
    return base if not extra else base | extra

# ------------------------------------------------------------------------------
# Seiten
# ------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", _ctx(request))

# Katalog
@app.get("/katalog", response_class=HTMLResponse)
def katalog(request: Request, db: Session = Depends(get_db)):
    services = db.query(Service).order_by(Service.name.asc()).all()
    produkte = db.query(Produkt).order_by(Produkt.name.asc()).all()
    return templates.TemplateResponse("katalog.html", _ctx(request, {"services": services, "produkte": produkte}))

@app.get("/katalog/service/neu", response_class=HTMLResponse)
def service_new_form(request: Request):
    return templates.TemplateResponse("service_form.html",
        _ctx(request, {"item": None, "mode":"new", "vat_choices": vat_choices()}))

@app.post("/katalog/service/neu", response_class=HTMLResponse)
def service_new_post(
    request: Request,
    name: str = Form(...),
    preis_chf: str = Form("0"),
    tax_code: str = Form("S1"),
    warengruppe: str = Form("DL"),
    aktiv: bool = Form(False),
    db: Session = Depends(get_db),
):
    item = Service(name=name.strip(), basispreis=_to_float(preis_chf),
                   steuer_code=tax_code, warengruppe=warengruppe, aktiv=1 if aktiv else 0)
    db.add(item); db.commit()
    return RedirectResponse("/katalog", status_code=302)

@app.get("/katalog/service/{sid}", response_class=HTMLResponse)
def service_edit_form(sid: int, request: Request, db: Session = Depends(get_db)):
    item = db.query(Service).get(sid)
    if not item: return HTMLResponse("Not found", status_code=404)
    return templates.TemplateResponse("service_form.html",
        _ctx(request, {"item": item, "mode":"edit", "vat_choices": vat_choices()}))

@app.post("/katalog/service/{sid}", response_class=HTMLResponse)
def service_edit_post(
    sid: int,
    request: Request,
    name: str = Form(...),
    preis_chf: str = Form("0"),
    tax_code: str = Form("S1"),
    warengruppe: str = Form("DL"),
    aktiv: bool = Form(False),
    db: Session = Depends(get_db),
):
    item = db.query(Service).get(sid)
    if not item: return HTMLResponse("Not found", status_code=404)
    item.name = name.strip()
    item.basispreis = _to_float(preis_chf)
    item.steuer_code = tax_code
    item.warengruppe = warengruppe
    item.aktiv = 1 if aktiv else 0
    db.commit()
    return RedirectResponse("/katalog", status_code=302)

@app.get("/katalog/produkt/neu", response_class=HTMLResponse)
def produkt_new_form(request: Request):
    return templates.TemplateResponse("product_form.html",
        _ctx(request, {"item": None, "mode":"new", "vat_choices": vat_choices()}))

@app.post("/katalog/produkt/neu", response_class=HTMLResponse)
def produkt_new_post(
    request: Request,
    name: str = Form(...),
    preis_chf: str = Form("0"),
    tax_code: str = Form("S1"),
    warengruppe: str = Form("PR"),
    aktiv: bool = Form(False),
    db: Session = Depends(get_db),
):
    item = Produkt(name=name.strip(), verkaufspreis=_to_float(preis_chf),
                   steuer_code=tax_code, warengruppe=warengruppe, aktiv=1 if aktiv else 0)
    db.add(item); db.commit()
    return RedirectResponse("/katalog", status_code=302)

@app.get("/katalog/produkt/{pid}", response_class=HTMLResponse)
def produkt_edit_form(pid: int, request: Request, db: Session = Depends(get_db)):
    item = db.query(Produkt).get(pid)
    if not item: return HTMLResponse("Not found", status_code=404)
    return templates.TemplateResponse("product_form.html",
        _ctx(request, {"item": item, "mode":"edit", "vat_choices": vat_choices()}))

@app.post("/katalog/produkt/{pid}", response_class=HTMLResponse)
def produkt_edit_post(
    pid: int,
    request: Request,
    name: str = Form(...),
    preis_chf: str = Form("0"),
    tax_code: str = Form("S1"),
    warengruppe: str = Form("PR"),
    aktiv: bool = Form(False),
    db: Session = Depends(get_db),
):
    item = db.query(Produkt).get(pid)
    if not item: return HTMLResponse("Not found", status_code=404)
    item.name = name.strip()
    item.verkaufspreis = _to_float(preis_chf)
    item.steuer_code = tax_code
    item.warengruppe = warengruppe
    item.aktiv = 1 if aktiv else 0
    db.commit()
    return RedirectResponse("/katalog", status_code=302)

# POS
@app.get("/pos", response_class=HTMLResponse)
def pos_page(request: Request, db: Session = Depends(get_db)):
    services = db.query(Service).filter(Service.aktiv==1).order_by(Service.name.asc()).all()
    produkte = db.query(Produkt).filter(Produkt.aktiv==1).order_by(Produkt.name.asc()).all()
    return templates.TemplateResponse("pos.html",
        _ctx(request, {"services": services, "produkte": produkte}))

@app.post("/pos/checkout")
async def pos_checkout(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    items = list(payload.get("items") or [])
    pay = payload.get("payment") or {}
    if not items:
        return JSONResponse({"ok": False, "error": "Warenkorb ist leer."}, status_code=400)

    cfg = load_settings()
    kassen_id = cfg["kasse"].get("id", "K1")

    norm = []
    total = 0.0
    for r in items:
        t = (r.get("type") or "").lower().strip()
        iid = int(r.get("id") or 0); qty = int(r.get("qty") or 0)
        if iid <= 0 or qty <= 0: return JSONResponse({"ok": False, "error":"Ungültige Position."}, status_code=400)
        if t == "service":
            s = db.query(Service).get(iid)
            if not s: return JSONResponse({"ok": False, "error":"Service nicht gefunden."}, status_code=400)
            price = float(s.basispreis or 0.0); code = s.steuer_code or "S1"; grp = s.warengruppe or "DL"; name = s.name
        else:
            p = db.query(Produkt).get(iid)
            if not p: return JSONResponse({"ok": False, "error":"Produkt nicht gefunden."}, status_code=400)
            price = float(p.verkaufspreis or 0.0); code = p.steuer_code or "S1"; grp = p.warengruppe or "PR"; name = p.name
        lt = round(price * qty, 2); total += lt
        norm.append({"type":t,"id":iid,"qty":qty,"price":price,"total":lt,"tax_code":code,"grp":grp,"name":name})

    total = round(total, 2)
    if total <= 0: return JSONResponse({"ok": False, "error":"Ungültiges Total."}, status_code=400)

    method = (pay.get("method") or "").lower().strip()
    am = pay.get("amounts") or {}
    bar = float(am.get("bar") or 0); karte = float(am.get("karte") or 0); twint = float(am.get("twint") or 0)

    if method not in {"bar","karte","twint","kombi"}:
        return JSONResponse({"ok": False, "error":"Ungültige Zahlart."}, status_code=400)
    if any(x<0 for x in (bar,karte,twint)):
        return JSONResponse({"ok": False, "error":"Negative Beträge nicht erlaubt."}, status_code=400)
    if method=="kombi":
        if round(bar+karte+twint,2)!=total:
            return JSONResponse({"ok": False, "error":"Kombi-Beträge ≠ Total."}, status_code=400)
    elif method=="bar":
        if round(bar,2)!=total: return JSONResponse({"ok": False, "error":"Barbetrag ≠ Total."}, status_code=400)
        karte=twint=0.0
    elif method=="karte":
        if round(karte,2)!=total: return JSONResponse({"ok": False, "error":"Kartenbetrag ≠ Total."}, status_code=400)
        bar=twint=0.0
    elif method=="twint":
        if round(twint,2)!=total: return JSONResponse({"ok": False, "error":"Twintbetrag ≠ Total."}, status_code=400)
        bar=karte=0.0

    sale = Sale(ts=datetime.utcnow(), kassen_id=kassen_id, brutto_summe=total, rabatt_summe=0.0, storno=False)
    db.add(sale); db.flush()

    for n in norm:
        db.add(SaleItem(
            sale_id=sale.id, typ=n["type"], ref_id=n["id"], name_snapshot=n["name"],
            menge=n["qty"], vk_brutto=n["price"], steuer_code=n["tax_code"], warengruppe=n["grp"]
        ))

    if bar:   db.add(SalePayment(sale_id=sale.id, art="bar",   betrag=round(bar,2)))
    if karte: db.add(SalePayment(sale_id=sale.id, art="karte", betrag=round(karte,2)))
    if twint: db.add(SalePayment(sale_id=sale.id, art="twint", betrag=round(twint,2)))

    db.commit()

    return JSONResponse({
        "ok": True,
        "items": norm,
        "total": total,
        "sale_id": sale.id,
        "payment": {"method": method, "amounts":{"bar":round(bar,2),"karte":round(karte,2),"twint":round(twint,2)}}
    })

# Beleg (unverändert)
@app.post("/beleg/preview", response_class=HTMLResponse)
async def beleg_preview(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    items = list(payload.get("items") or [])
    total = float(payload.get("total") or 0.0)
    payment = payload.get("payment") or {}

    cfg = load_settings()
    r1 = float(cfg["vat"].get("rate1", 0.0))
    r2 = float(cfg["vat"].get("rate2", 0.0))

    vat_totals = {"S1":0.0,"S2":0.0}
    for it in items:
        code = (it.get("tax_code") or "S1").upper()
        gross = float(it.get("total") or 0.0)
        rate = r1 if code=="S1" else r2
        tax = round(gross - (gross/(1.0+rate/100.0)), 2)
        vat_totals[code]+=tax

    meta = {
        "title": app.title, "ts": datetime.now(),
        "company": {
            "name": load_settings()["company"].get("name",""),
            "city": load_settings()["company"].get("city",""),
            "vat_number": load_settings()["company"].get("vat_number",""),
        },
        "vat": {"rate1": r1, "rate2": r2, "S1": vat_totals["S1"], "S2": vat_totals["S2"]},
        "method": (payment.get("method") or "").upper(),
        "bar": float((payment.get("amounts") or {}).get("bar") or 0),
        "karte": float((payment.get("amounts") or {}).get("karte") or 0),
        "twint": float((payment.get("amounts") or {}).get("twint") or 0),
        "period": None
    }
    return templates.TemplateResponse("beleg.html",
        {"request": request, "items": items, "total": total, "m": meta})

# Einstellungen
@app.get("/einstellungen", response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse("einstellungen.html", _ctx(request, {"cfg": load_settings(), "saved": False}))

@app.post("/einstellungen", response_class=HTMLResponse)
def settings_save(
    request: Request,
    company_name: str = Form(""),
    vat_number: str = Form(""),
    address: str = Form(""),
    city: str = Form(""),
    phone: str = Form(""),
    vat_rate1: str = Form("8.1"),
    vat_rate2: str = Form("2.6"),
    kassen_id: str = Form("K1"),
):
    cfg = load_settings()
    cfg["company"]["name"] = company_name.strip()
    cfg["company"]["vat_number"] = vat_number.strip()
    cfg["company"]["address"] = address.strip()
    cfg["company"]["city"] = city.strip()
    cfg["company"]["phone"] = phone.strip()
    try: cfg["vat"]["rate1"] = float(str(vat_rate1).replace(",", "."))
    except: pass
    try: cfg["vat"]["rate2"] = float(str(vat_rate2).replace(",", "."))
    except: pass
    cfg["kasse"]["id"] = (kassen_id or "K1").strip() or "K1"
    save_settings(cfg)
    return RedirectResponse("/einstellungen?saved=1", status_code=303)

# ------------------------------------------------------------------------------
# Berichte (Listen)
# ------------------------------------------------------------------------------
def _parse_dates(von: str|None, bis: str|None):
    def _p(s):
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except: pass
        return None
    dv = _p(von) if von else None
    dbis = _p(bis) if bis else None
    return dv, dbis

@app.get("/berichte/kassenbuch", response_class=HTMLResponse)
def rep_kassenbuch(request: Request, von: str|None=None, bis: str|None=None, db: Session = Depends(get_db)):
    dv, dbis = _parse_dates(von, bis)
    q = db.query(Sale)
    if dv: q = q.filter(Sale.ts >= dv)
    if dbis: q = q.filter(Sale.ts <= dbis)
    sales = q.order_by(Sale.ts.desc()).all()

    belege = len(sales)
    storno_cnt = sum(1 for s in sales if s.storno)
    rabatt_sum = round(sum(s.rabatt_summe or 0 for s in sales), 2)
    zahlungen = {"bar":0.0,"karte":0.0,"twint":0.0,"gutschein":0.0,"guthaben":0.0,"offen":0.0}
    for s in sales:
        for p in s.payments:
            if p.art in zahlungen:
                zahlungen[p.art] += float(p.betrag or 0)
    cfg = load_settings()
    r1 = float(cfg["vat"].get("rate1", 0.0))
    r2 = float(cfg["vat"].get("rate2", 0.0))
    u_satz = {"S1":0.0,"S2":0.0}
    for s in sales:
        for it in s.items:
            gross = float(it.vk_brutto or 0) * int(it.menge or 0)
            u_satz[it.steuer_code or "S1"] += gross

    ctx = _ctx(request, {
        "sales": sales, "belege": belege, "storno_cnt": storno_cnt, "rabatt_sum": rabatt_sum,
        "zahlungen": {k:round(v,2) for k,v in zahlungen.items()},
        "u_satz": {"S1": round(u_satz["S1"],2), "S2": round(u_satz["S2"],2)},
        "r1": r1, "r2": r2, "von": von, "bis": bis
    })
    return templates.TemplateResponse("berichte_kassenbuch.html", ctx)

@app.get("/berichte/zahlungsarten", response_class=HTMLResponse)
def rep_zahlungsarten(request: Request, von: str|None=None, bis: str|None=None, db: Session = Depends(get_db)):
    dv, dbis = _parse_dates(von, bis)
    q = db.query(Sale)
    if dv: q = q.filter(Sale.ts >= dv)
    if dbis: q = q.filter(Sale.ts <= dbis)
    sales = q.all()
    counts = {"bar":[0,0.0],"karte":[0,0.0],"twint":[0,0.0],"gutschein":[0,0.0],"guthaben":[0,0.0],"offen":[0,0.0]}
    for s in sales:
        arts = set()
        for p in s.payments:
            if p.art in counts:
                counts[p.art][1] += float(p.betrag or 0)
                arts.add(p.art)
        for a in arts:
            counts[a][0] += 1
    ctx = _ctx(request, {"counts": counts, "von": von, "bis": bis})
    return templates.TemplateResponse("berichte_zahlungsarten.html", ctx)

@app.get("/berichte/mwst", response_class=HTMLResponse)
def rep_mwst(request: Request, von: str|None=None, bis: str|None=None, db: Session = Depends(get_db)):
    dv, dbis = _parse_dates(von, bis)
    q = db.query(Sale)
    if dv: q = q.filter(Sale.ts >= dv)
    if dbis: q = q.filter(Sale.ts <= dbis)
    sales = q.all()

    cfg = load_settings()
    r1 = float(cfg["vat"].get("rate1", 0.0))
    r2 = float(cfg["vat"].get("rate2", 0.0))
    sums = {"S1":0.0,"S2":0.0}
    groups = {"DL":0.0,"PR":0.0,"TA":0.0}
    for s in sales:
        for it in s.items:
            gross = float(it.vk_brutto or 0) * int(it.menge or 0)
            sums[it.steuer_code or "S1"] += gross
            groups[it.warengruppe or "DL"] += gross

    def _split(gross, rate):
        net = round(gross/(1.0+rate/100.0), 2)
        tax = round(gross-net, 2)
        return net, tax, round(gross, 2)

    s1 = _split(sums["S1"], r1)
    s2 = _split(sums["S2"], r2)
    total = round(sums["S1"]+sums["S2"], 2)
    anteile = {k: (0.0 if total==0 else round(v/total*100.0,1)) for k,v in groups.items()}

    ctx = _ctx(request, {"r1":r1,"r2":r2, "s1":s1, "s2":s2,
                         "groups": {k: round(v,2) for k,v in groups.items()},
                         "anteile": anteile, "von":von, "bis":bis})
    return templates.TemplateResponse("berichte_mwst.html", ctx)

# ------------------------------------------------------------------------------
# PDF-Export Helfer
# ------------------------------------------------------------------------------
def _pdf_response(buf: BytesIO, filename: str) -> Response:
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )

def _ensure_reportlab():
    try:
        from reportlab.lib.pagesizes import A4  # noqa
        return True, None
    except Exception as e:
        return False, e

def _pdf_set_styles():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate
    styles = getSampleStyleSheet()
    return colors, A4, styles, mm, SimpleDocTemplate

# Kassenbuch PDF
@app.get("/berichte/kassenbuch.pdf")
def rep_kassenbuch_pdf(request: Request, von: str|None=None, bis: str|None=None, db: Session = Depends(get_db)):
    ok, err = _ensure_reportlab()
    if not ok:
        return PlainTextResponse("PDF-Export benötigt 'reportlab' (pip install reportlab).", status_code=501)

    dv, dbis = _parse_dates(von, bis)
    q = db.query(Sale)
    if dv: q = q.filter(Sale.ts >= dv)
    if dbis: q = q.filter(Sale.ts <= dbis)
    sales = q.order_by(Sale.ts.asc()).all()

    # Aggregation wie HTML
    belege = len(sales)
    storno_cnt = sum(1 for s in sales if s.storno)
    rabatt_sum = round(sum(s.rabatt_summe or 0 for s in sales), 2)
    zahlungen = {"bar":0.0,"karte":0.0,"twint":0.0,"gutschein":0.0,"guthaben":0.0,"offen":0.0}
    for s in sales:
        for p in s.payments:
            if p.art in zahlungen:
                zahlungen[p.art] += float(p.betrag or 0)

    cfg = load_settings()
    r1 = float(cfg["vat"].get("rate1", 0.0))
    r2 = float(cfg["vat"].get("rate2", 0.0))
    u_satz = {"S1":0.0,"S2":0.0}
    for s in sales:
        for it in s.items:
            u_satz[it.steuer_code or "S1"] += float(it.vk_brutto or 0) * int(it.menge or 0)

    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    colors, A4, styles, mm, SimpleDocTemplate = _pdf_set_styles()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=12*mm, bottomMargin=12*mm)
    story = []
    title = f"Kassenbuch ({von or '-'} bis {bis or '-'})"
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 6))

    head = [
        ["Belege", str(belege)],
        ["Stornos", str(storno_cnt)],
        ["Rabatte (CHF)", f"{rabatt_sum:.2f}"],
        [f"Umsatz S1 ({r1:.1f}%)", f"{u_satz['S1']:.2f}"],
        [f"Umsatz S2 ({r2:.1f}%)", f"{u_satz['S2']:.2f}"],
    ]
    t1 = Table(head, colWidths=[70*mm, 40*mm])
    t1.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.25,colors.grey),
                            ("BACKGROUND",(0,0),(-1,0),colors.whitesmoke)]))
    story.append(t1)
    story.append(Spacer(1, 8))

    pay_rows = [["Zahlungsart", "Summe (CHF)"]] + [[k.capitalize(), f"{v:.2f}"] for k,v in zahlungen.items()]
    t2 = Table(pay_rows, colWidths=[70*mm, 40*mm])
    t2.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.25,colors.grey),
                            ("BACKGROUND",(0,0),(-1,0),colors.whitesmoke)]))
    story.append(t2)
    story.append(Spacer(1, 8))

    rows = [["Datum/Uhrzeit","Kasse","Brutto (CHF)","Rabatt","Zahlungen"]]
    for s in sales:
        pays = ", ".join([f"{p.art}:{p.betrag:.2f}" for p in s.payments])
        rows.append([s.ts.strftime("%d.%m.%Y %H:%M"), s.kassen_id, f"{(s.brutto_summe or 0):.2f}",
                     f"{(s.rabatt_summe or 0):.2f}", pays or "-"])
    t3 = Table(rows, colWidths=[35*mm, 20*mm, 30*mm, 25*mm, 60*mm], repeatRows=1)
    t3.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.25,colors.grey),
                            ("BACKGROUND",(0,0),(-1,0),colors.whitesmoke),
                            ("ALIGN",(2,1),(3,-1),"RIGHT")]))
    story.append(t3)

    doc.build(story)
    return _pdf_response(buf, "kassenbuch.pdf")

# Zahlungsarten PDF
@app.get("/berichte/zahlungsarten.pdf")
def rep_zahlungsarten_pdf(request: Request, von: str|None=None, bis: str|None=None, db: Session = Depends(get_db)):
    ok, err = _ensure_reportlab()
    if not ok:
        return PlainTextResponse("PDF-Export benötigt 'reportlab' (pip install reportlab).", status_code=501)

    dv, dbis = _parse_dates(von, bis)
    q = db.query(Sale)
    if dv: q = q.filter(Sale.ts >= dv)
    if dbis: q = q.filter(Sale.ts <= dbis)
    sales = q.all()
    counts = {"bar":[0,0.0],"karte":[0,0.0],"twint":[0,0.0],"gutschein":[0,0.0],"guthaben":[0,0.0],"offen":[0,0.0]}
    for s in sales:
        arts = set()
        for p in s.payments:
            if p.art in counts:
                counts[p.art][1] += float(p.betrag or 0)
                arts.add(p.art)
        for a in arts:
            counts[a][0] += 1

    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    colors, A4, styles, mm, SimpleDocTemplate = _pdf_set_styles()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=12*mm, bottomMargin=12*mm)
    story = []
    story.append(Paragraph(f"Zahlungsarten ({von or '-'} bis {bis or '-'})", styles["Title"]))
    story.append(Spacer(1, 6))

    rows = [["Art", "# Belege", "Summe (CHF)"]]
    for k,(cnt,summe) in counts.items():
        rows.append([k.capitalize(), str(cnt), f"{summe:.2f}"])
    from reportlab.platypus import Table
    t = Table(rows, colWidths=[60*mm, 30*mm, 40*mm], repeatRows=1)
    t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.25,colors.grey),
                           ("BACKGROUND",(0,0),(-1,0),colors.whitesmoke),
                           ("ALIGN",(1,1),(-1,-1),"RIGHT")]))
    story.append(t)

    doc.build(story)
    return _pdf_response(buf, "zahlungsarten.pdf")

# MWST/Warengruppen PDF
@app.get("/berichte/mwst.pdf")
def rep_mwst_pdf(request: Request, von: str|None=None, bis: str|None=None, db: Session = Depends(get_db)):
    ok, err = _ensure_reportlab()
    if not ok:
        return PlainTextResponse("PDF-Export benötigt 'reportlab' (pip install reportlab).", status_code=501)

    dv, dbis = _parse_dates(von, bis)
    q = db.query(Sale)
    if dv: q = q.filter(Sale.ts >= dv)
    if dbis: q = q.filter(Sale.ts <= dbis)
    sales = q.all()

    cfg = load_settings()
    r1 = float(cfg["vat"].get("rate1", 0.0))
    r2 = float(cfg["vat"].get("rate2", 0.0))
    sums = {"S1":0.0,"S2":0.0}
    groups = {"DL":0.0,"PR":0.0,"TA":0.0}
    for s in sales:
        for it in s.items:
            gross = float(it.vk_brutto or 0) * int(it.menge or 0)
            sums[it.steuer_code or "S1"] += gross
            groups[it.warengruppe or "DL"] += gross

    def _split(gross, rate):
        net = round(gross/(1.0+rate/100.0), 2)
        tax = round(gross-net, 2)
        return net, tax, round(gross, 2)
    s1 = _split(sums["S1"], r1); s2 = _split(sums["S2"], r2)
    total = round(sums["S1"]+sums["S2"], 2)
    anteile = {k: (0.0 if total==0 else round(v/total*100.0,1)) for k,v in groups.items()}

    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    colors, A4, styles, mm, SimpleDocTemplate = _pdf_set_styles()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=12*mm, bottomMargin=12*mm)
    story = []
    story.append(Paragraph(f"MWST & Warengruppen ({von or '-'} bis {bis or '-'})", styles["Title"]))
    story.append(Spacer(1, 6))

    t1 = Table([
        [f"S1 ({r1:.1f}%) Netto", f"{s1[0]:.2f}", "MWST", f"{s1[1]:.2f}", "Brutto", f"{s1[2]:.2f}"],
        [f"S2 ({r2:.1f}%) Netto", f"{s2[0]:.2f}", "MWST", f"{s2[1]:.2f}", "Brutto", f"{s2[2]:.2f}"],
    ], colWidths=[35*mm, 25*mm, 18*mm, 25*mm, 22*mm, 25*mm])
    t1.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.25,colors.grey),
                            ("BACKGROUND",(0,0),(-1,0),colors.whitesmoke),
                            ("ALIGN",(1,0),(-1,-1),"RIGHT")]))
    story.append(t1)
    story.append(Spacer(1, 8))

    t2 = Table([
        ["Warengruppe","Brutto (CHF)","Anteil %"],
        ["DL", f"{groups['DL']:.2f}", f"{anteile['DL']:.1f}"],
        ["PR", f"{groups['PR']:.2f}", f"{anteile['PR']:.1f}"],
        ["TA", f"{groups['TA']:.2f}", f"{anteile['TA']:.1f}"],
    ], colWidths=[40*mm, 40*mm, 30*mm], repeatRows=1)
    t2.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.25,colors.grey),
                            ("BACKGROUND",(0,0),(-1,0),colors.whitesmoke),
                            ("ALIGN",(1,1),(-1,-1),"RIGHT")]))
    story.append(t2)

    doc.build(story)
    return _pdf_response(buf, "mwst_warengruppen.pdf")

# ------------------------------------------------------------------------------
# Dev-Server
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
