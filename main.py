# kassensystem_basic/main.py

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path
import datetime
import uuid
from decimal import Decimal
import io
import csv
import json
from collections import defaultdict

from app.config.settings import (
    APP_NAME,
    SECRET_KEY,
    DEFAULT_DEV_MODE,
    get_nav_items,
    get_dash_flags,
)
from app.services.db_init import init_db
from app.services.pricing import summarize_cart, round2, load_tax_rates
from app.services.receipt_numbers import next_receipt_number
from app.models.base import get_session, SessionLocal
from app.models.entities import (
    Service, Produkt, Beleg, BelegPosition, Zahlung,
    Kunde, Kassenbuch, Abschluss, Ausgabe, Konfig,
    Mitarbeiter, Termin,
)

# ---------------- App / Pfade ----------------
app = FastAPI(title=APP_NAME)
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Session-Middleware
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# -------------- Helpers (Rolle/DEV) --------------
ALLOWED_ROLES = {"Owner", "Admin", "Mitarbeiter", "Buchhaltung", "Gast"}

def get_role(request: Request) -> str:
    return request.session.get("role", "Mitarbeiter")

def set_role(request: Request, role: str) -> None:
    request.session["role"] = role

def ensure_role(request: Request, allowed: set[str]) -> None:
    if get_role(request) not in allowed:
        raise HTTPException(status_code=403, detail="Keine Berechtigung.")

def effective_dev_mode(request: Request) -> bool:
    return request.session.get("dev_mode", DEFAULT_DEV_MODE)

def set_dev_mode(request: Request, value: bool) -> None:
    request.session["dev_mode"] = value

def ensure_cart(request: Request) -> dict:
    cart = request.session.get("cart")
    if not cart:
        cart = {"items": [], "discount_percent": 0, "discount_amount": 0, "tip": 0, "kunde": None}
        request.session["cart"] = cart
    if "kunde" not in cart:
        cart["kunde"] = None
        request.session["cart"] = cart
    return cart

def get_konfig_json(key: str, default):
    with SessionLocal() as db:
        row = db.get(Konfig, key)
        if not row:
            return default
        try:
            return json.loads(row.value_json)
        except Exception:
            return default

def set_konfig_json(key: str, value) -> None:
    with SessionLocal() as db:
        row = db.get(Konfig, key)
        payload = json.dumps(value)
        if not row:
            row = Konfig(key=key, value_json=payload)
        else:
            row.value_json = payload
        db.add(row)
        db.commit()

def nav_items_effective(dev: bool):
    if dev:
        dev_nav = get_konfig_json("dev_nav", None)
        if isinstance(dev_nav, list) and all(isinstance(x, dict) and "href" in x and "label" in x for x in dev_nav):
            return dev_nav
    return get_nav_items(dev)

def dash_flags_effective(dev: bool):
    if dev:
        conf = get_konfig_json("dev_dashboard", None)
        if isinstance(conf, dict):
            return conf
    return get_dash_flags(dev)

def ctx(request: Request, title: str = None) -> dict:
    role = get_role(request)
    dev = effective_dev_mode(request)
    return {
        "request": request,
        "title": title or "Kassensystem Basic",
        "role": role,
        "year": datetime.datetime.now().year,
        "env": "DEV" if dev else "PROD",
        "nav_items": nav_items_effective(dev),
    }

def _day_bounds(date_str: str | None):
    if not date_str:
        d = datetime.date.today()
    else:
        d = datetime.date.fromisoformat(date_str)
    start = datetime.datetime.combine(d, datetime.time.min)
    end = datetime.datetime.combine(d, datetime.time.max)
    return d, start, end

def _range_bounds(date_from: str | None, date_to: str | None):
    if not date_from and not date_to:
        today = datetime.date.today()
        first = today.replace(day=1)
        last_day = (first.replace(month=first.month % 12 + 1, day=1) - datetime.timedelta(days=1)).day
        last = today.replace(day=last_day)
    else:
        first = datetime.date.fromisoformat(date_from) if date_from else datetime.date.min
        last = datetime.date.fromisoformat(date_to) if date_to else datetime.date.max
    start = datetime.datetime.combine(first, datetime.time.min)
    end = datetime.datetime.combine(last, datetime.time.max)
    return first, last, start, end

# -------------- Startup --------------
@app.on_event("startup")
def _startup():
    init_db(dev_seed=DEFAULT_DEV_MODE)

# -------------- DEV-Toggle nur fuer Admin --------------
@app.post("/ui/dev/toggle")
async def toggle_dev(request: Request):
    if get_role(request) != "Admin":
        raise HTTPException(status_code=403, detail="Nur Admin darf den DEV-Modus umschalten.")
    current = effective_dev_mode(request)
    set_dev_mode(request, not current)
    next_url = "/ui/dashboard"
    try:
        form = await request.form()
        next_url = form.get("next") or next_url
    except Exception:
        pass
    return RedirectResponse(url=next_url, status_code=303)

# -------------- Demo-Login (Prototyp) --------------
@app.get("/ui/login/{role_name}")
def login_as(role_name: str, request: Request):
    nice = role_name.capitalize()
    if nice not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Unbekannte Rolle.")
    set_role(request, nice)
    return RedirectResponse(url="/ui/dashboard", status_code=303)

# -------------- UI: Dashboard / POS / Quittung / Gast / Kalender --------------
@app.get("/", response_class=HTMLResponse)
@app.get("/ui/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    dev = effective_dev_mode(request)
    flags = dash_flags_effective(dev)
    return templates.TemplateResponse("dashboard.html", ctx(request, "Dashboard") | {"flags": flags})

@app.get("/ui/pos", response_class=HTMLResponse)
def pos(request: Request):
    return templates.TemplateResponse("pos.html", ctx(request, "Kasse"))

@app.get("/ui/receipt/{beleg_id}", response_class=HTMLResponse)
def ui_receipt(beleg_id: int, request: Request, session = next(get_session())):
    beleg = session.get(Beleg, beleg_id)
    if not beleg:
        raise HTTPException(status_code=404, detail="Beleg nicht gefunden")
    positionen = session.query(BelegPosition).filter(BelegPosition.beleg_id == beleg_id).all()
    kunde_name = None
    if beleg.kunde_id:
        k = session.get(Kunde, beleg.kunde_id)
        if k: kunde_name = k.name
    pos_view = [
        {
            "name": p.typ.capitalize() + (" #" + str(p.ref_id)),
            "typ": p.typ,
            "steuer_code": p.steuer_code,
            "menge": float(p.menge),
            "einzelpreis": float(p.einzelpreis),
            "gesamtpreis": float(p.gesamtpreis),
        }
        for p in positionen
    ]
    return templates.TemplateResponse("receipt.html", ctx(request, "Quittung") | {
        "beleg": beleg,
        "positionen": pos_view,
        "kunde_name": kunde_name,
    })

@app.get("/ui/gast", response_class=HTMLResponse)
def gast(request: Request):
    return templates.TemplateResponse("gast_portal.html", ctx(request, "Gast-Portal"))

@app.get("/ui/kalender", response_class=HTMLResponse)
def kalender(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    today = datetime.date.today().isoformat()
    with SessionLocal() as db:
        staff = db.query(Mitarbeiter).order_by(Mitarbeiter.name).all()
        services = db.query(Service).filter(Service.aktiv == 1).order_by(Service.name).all()
    return templates.TemplateResponse(
        "kalender.html",
        ctx(request, "Kalender") | {"date_str": today, "staff": staff, "services": services}
    )

# -------------- KUNDEN --------------
@app.get("/ui/kunden", response_class=HTMLResponse)
def kunden_list(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter", "Buchhaltung"})
    q = (request.query_params.get("q") or "").strip().lower()
    with SessionLocal() as db:
        qry = db.query(Kunde)
        if q:
            qry = qry.filter(
                (Kunde.name.ilike(f"%{q}%")) | (Kunde.telefon.ilike(f"%{q}%")) | (Kunde.email.ilike(f"%{q}%"))
            )
        kunden = qry.order_by(Kunde.name).all()
    return templates.TemplateResponse("kunden_list.html", ctx(request, "Kunden") | {"kunden": kunden, "q": q})

@app.get("/ui/kunden/new", response_class=HTMLResponse)
def kunden_new_form(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    return templates.TemplateResponse("kunden_form.html", ctx(request, "Kunde anlegen"))

@app.post("/ui/kunden/new")
async def kunden_new(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name ist Pflicht.")
    telefon = (form.get("telefon") or "").strip() or None
    email = (form.get("email") or "").strip() or None
    bemerkungen = (form.get("bemerkungen") or "").strip() or None
    status = form.get("status") or "aktiv"
    punkte_raw = form.get("punkte")
    punkte = int(punkte_raw) if punkte_raw not in (None, "",) else 0
    with SessionLocal() as db:
        db.add(Kunde(name=name, telefon=telefon, email=email, bemerkungen=bemerkungen, kundenstatus=status, punkte=punkte))
        db.commit()
    return RedirectResponse(url="/ui/kunden", status_code=303)

@app.get("/ui/kunden/{kid}/edit", response_class=HTMLResponse)
def kunden_edit_form(kid: int, request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    with SessionLocal() as db:
        k = db.get(Kunde, kid)
        if not k:
            raise HTTPException(status_code=404, detail="Kunde nicht gefunden")
    return templates.TemplateResponse("kunden_edit.html", ctx(request, "Kunde bearbeiten") | {"item": k})

@app.post("/ui/kunden/{kid}/edit")
async def kunden_edit(kid: int, request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    form = await request.form()
    with SessionLocal() as db:
        k = db.get(Kunde, kid)
        if not k:
            raise HTTPException(status_code=404, detail="Kunde nicht gefunden")
        k.name = (form.get("name") or "").strip() or k.name
        k.telefon = (form.get("telefon") or "").strip() or None
        k.email = (form.get("email") or "").strip() or None
        k.bemerkungen = (form.get("bemerkungen") or "").strip() or None
        k.kundenstatus = form.get("status") or k.kundenstatus
        punkte_raw = form.get("punkte")
        k.punkte = int(punkte_raw) if punkte_raw not in (None, "",) else k.punkte
        db.add(k)
        db.commit()
    return RedirectResponse(url="/ui/kunden", status_code=303)

@app.post("/ui/kunden/{kid}/status")
async def kunden_status_toggle(kid: int, request: Request):
    ensure_role(request, {"Admin", "Owner"})
    with SessionLocal() as db:
        k = db.get(Kunde, kid)
        if not k:
            raise HTTPException(status_code=404, detail="Kunde nicht gefunden")
        k.kundenstatus = "inaktiv" if (k.kundenstatus or "aktiv") == "aktiv" else "aktiv"
        db.add(k)
        db.commit()
    return RedirectResponse(url="/ui/kunden", status_code=303)

# -------------- MITARBEITER (einfach) --------------
@app.get("/ui/mitarbeiter", response_class=HTMLResponse)
def staff_list(request: Request):
    ensure_role(request, {"Admin", "Owner"})
    with SessionLocal() as db:
        staff = db.query(Mitarbeiter).order_by(Mitarbeiter.name).all()
    return templates.TemplateResponse("mitarbeiter_list.html", ctx(request, "Mitarbeiter") | {"staff": staff})

@app.get("/ui/mitarbeiter/new", response_class=HTMLResponse)
def staff_new_form(request: Request):
    ensure_role(request, {"Admin", "Owner"})
    return templates.TemplateResponse("mitarbeiter_form.html", ctx(request, "Mitarbeiter anlegen"))

@app.post("/ui/mitarbeiter/new")
async def staff_new(request: Request):
    ensure_role(request, {"Admin", "Owner"})
    form = await request.form()
    name = (form.get("name") or "").strip()
    rollen = (form.get("rollen") or "").strip() or None
    if not name:
        raise HTTPException(status_code=400, detail="Name ist Pflicht.")
    with SessionLocal() as db:
        db.add(Mitarbeiter(name=name, rollen=rollen))
        db.commit()
    return RedirectResponse(url="/ui/mitarbeiter", status_code=303)

@app.get("/ui/mitarbeiter/{mid}/edit", response_class=HTMLResponse)
def staff_edit_form(mid: int, request: Request):
    ensure_role(request, {"Admin", "Owner"})
    with SessionLocal() as db:
        m = db.get(Mitarbeiter, mid)
        if not m: raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    return templates.TemplateResponse("mitarbeiter_form.html", ctx(request, "Mitarbeiter bearbeiten") | {"item": m})

@app.post("/ui/mitarbeiter/{mid}/edit")
async def staff_edit(mid: int, request: Request):
    ensure_role(request, {"Admin", "Owner"})
    form = await request.form()
    with SessionLocal() as db:
        m = db.get(Mitarbeiter, mid)
        if not m: raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
        m.name = (form.get("name") or m.name).strip()
        m.rollen = (form.get("rollen") or "").strip() or None
        db.add(m); db.commit()
    return RedirectResponse(url="/ui/mitarbeiter", status_code=303)

# -------------- KATALOG --------------
@app.get("/ui/katalog", response_class=HTMLResponse)
def katalog(request: Request):
    with SessionLocal() as db:
        services = db.query(Service).order_by(Service.name).all()
        produkte = db.query(Produkt).order_by(Produkt.name).all()
        tax_codes = list(load_tax_rates(db).keys())
    return templates.TemplateResponse(
        "katalog.html",
        ctx(request, "Katalog") | {
            "services": services,
            "produkte": produkte,
            "tax_codes": tax_codes,
            "can_edit": get_role(request) in {"Admin", "Owner"},
        }
    )

@app.get("/ui/katalog/service/new", response_class=HTMLResponse)
def service_new_form(request: Request):
    ensure_role(request, {"Admin", "Owner"})
    with SessionLocal() as db:
        tax_codes = list(load_tax_rates(db).keys())
    return templates.TemplateResponse("service_form.html", ctx(request, "Service anlegen") | {"tax_codes": tax_codes})

@app.post("/ui/katalog/service/new")
async def service_new(request: Request):
    ensure_role(request, {"Admin", "Owner"})
    form = await request.form()
    name = (form.get("name") or "").strip()
    dauer_min = int(form.get("dauer_min") or "0")
    basispreis = Decimal(str(form.get("basispreis") or "0"))
    kategorie = (form.get("kategorie") or "").strip() or None
    steuer_code = form.get("steuer_code") or "CH-7.7"
    material = form.get("materialkosten")
    materialkosten = Decimal(str(material)) if material not in (None, "",) else None
    aktiv = 1 if form.get("aktiv") == "1" else 0
    if not name or dauer_min <= 0 or basispreis < 0:
        raise HTTPException(status_code=400, detail="Pflichtfelder fehlen.")
    with SessionLocal() as db:
        db.add(Service(
            name=name, dauer_min=dauer_min, basispreis=basispreis,
            kategorie=kategorie, steuer_code=steuer_code,
            materialkosten=materialkosten, aktiv=aktiv
        ))
        db.commit()
    return RedirectResponse(url="/ui/katalog", status_code=303)

@app.get("/ui/katalog/service/{sid}/edit", response_class=HTMLResponse)
def service_edit_form(sid: int, request: Request):
    ensure_role(request, {"Admin", "Owner"})
    with SessionLocal() as db:
        obj = db.get(Service, sid)
        if not obj:
            raise HTTPException(status_code=404, detail="Service nicht gefunden")
        tax_codes = list(load_tax_rates(db).keys())
    return templates.TemplateResponse(
        "service_edit.html",
        ctx(request, "Service bearbeiten") | {"item": obj, "tax_codes": tax_codes}
    )

@app.post("/ui/katalog/service/{sid}/edit")
async def service_edit(sid: int, request: Request):
    ensure_role(request, {"Admin", "Owner"})
    form = await request.form()
    with SessionLocal() as db:
        obj = db.get(Service, sid)
        if not obj:
            raise HTTPException(status_code=404, detail="Service nicht gefunden")
        obj.name = (form.get("name") or "").strip() or obj.name
        obj.dauer_min = int(form.get("dauer_min") or obj.dauer_min)
        obj.basispreis = Decimal(str(form.get("basispreis") or obj.basispreis))
        obj.kategorie = (form.get("kategorie") or "").strip() or None
        obj.steuer_code = form.get("steuer_code") or obj.steuer_code
        material = form.get("materialkosten")
        obj.materialkosten = Decimal(str(material)) if material not in (None, "",) else None
        obj.aktiv = 1 if form.get("aktiv") == "1" else 0
        db.add(obj)
        db.commit()
    return RedirectResponse(url="/ui/katalog", status_code=303)

@app.post("/ui/katalog/service/{sid}/toggle")
async def service_toggle(sid: int, request: Request):
    ensure_role(request, {"Admin", "Owner"})
    with SessionLocal() as db:
        obj = db.get(Service, sid)
        if not obj:
            raise HTTPException(status_code=404, detail="Service nicht gefunden")
        obj.aktiv = 0 if obj.aktiv else 1
        db.add(obj)
        db.commit()
    return RedirectResponse(url="/ui/katalog", status_code=303)

@app.get("/ui/katalog/produkt/new", response_class=HTMLResponse)
def produkt_new_form(request: Request):
    ensure_role(request, {"Admin", "Owner"})
    with SessionLocal() as db:
        tax_codes = list(load_tax_rates(db).keys())
    return templates.TemplateResponse("product_form.html", ctx(request, "Produkt anlegen") | {"tax_codes": tax_codes})

@app.post("/ui/katalog/produkt/new")
async def produkt_new(request: Request):
    ensure_role(request, {"Admin", "Owner"})
    form = await request.form()
    name = (form.get("name") or "").strip()
    vk = Decimal(str(form.get("vk") or "0"))
    ek_raw = form.get("ek")
    ek = Decimal(str(ek_raw)) if ek_raw not in (None, "",) else None
    steuer_code = form.get("steuer_code") or "CH-7.7"
    lager_raw = form.get("lager")
    lager = int(lager_raw) if lager_raw not in (None, "",) else None
    aktiv = 1 if form.get("aktiv") == "1" else 0
    if not name or vk < 0:
        raise HTTPException(status_code=400, detail="Pflichtfelder fehlen.")
    with SessionLocal() as db:
        db.add(Produkt(
            name=name, verkaufspreis=vk, einkaufspreis=ek,
            steuer_code=steuer_code, lagerbestand=lager, aktiv=aktiv
        ))
        db.commit()
    return RedirectResponse(url="/ui/katalog", status_code=303)

@app.get("/ui/katalog/produkt/{pid}/edit", response_class=HTMLResponse)
def produkt_edit_form(pid: int, request: Request):
    ensure_role(request, {"Admin", "Owner"})
    with SessionLocal() as db:
        obj = db.get(Produkt, pid)
        if not obj:
            raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
        tax_codes = list(load_tax_rates(db).keys())
    return templates.TemplateResponse(
        "product_edit.html",
        ctx(request, "Produkt bearbeiten") | {"item": obj, "tax_codes": tax_codes}
    )

@app.post("/ui/katalog/produkt/{pid}/edit")
async def produkt_edit(pid: int, request: Request):
    ensure_role(request, {"Admin", "Owner"})
    form = await request.form()
    with SessionLocal() as db:
        obj = db.get(Produkt, pid)
        if not obj:
            raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
        obj.name = (form.get("name") or "").strip() or obj.name
        obj.verkaufspreis = Decimal(str(form.get("vk") or obj.verkaufspreis))
        ek_raw = form.get("ek")
        obj.einkaufspreis = Decimal(str(ek_raw)) if ek_raw not in (None, "",) else None
        obj.steuer_code = form.get("steuer_code") or obj.steuer_code
        lager_raw = form.get("lager")
        obj.lagerbestand = int(lager_raw) if lager_raw not in (None, "",) else None
        obj.aktiv = 1 if form.get("aktiv") == "1" else 0
        db.add(obj)
        db.commit()
    return RedirectResponse(url="/ui/katalog", status_code=303)

@app.post("/ui/katalog/produkt/{pid}/toggle")
async def produkt_toggle(pid: int, request: Request):
    ensure_role(request, {"Admin", "Owner"})
    with SessionLocal() as db:
        obj = db.get(Produkt, pid)
        if not obj:
            raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
        obj.aktiv = 0 if obj.aktiv else 1
        db.add(obj)
        db.commit()
    return RedirectResponse(url="/ui/katalog", status_code=303)

# -------------- Einstellungen (Konfiguration) --------------
@app.get("/ui/einstellungen", response_class=HTMLResponse)
def einstellungen(request: Request):
    ensure_role(request, {"Admin", "Owner"})
    dev = effective_dev_mode(request)

    current_nav = nav_items_effective(True) if dev else nav_items_effective(False)
    current_flags = dash_flags_effective(True) if dev else dash_flags_effective(False)
    taxes = get_konfig_json("taxes", {"CH-7.7": 0.077})
    payments = get_konfig_json("payments_enabled", ["bar", "karte", "twint", "rechnung"])
    return templates.TemplateResponse(
        "einstellungen.html",
        ctx(request, "Einstellungen") | {
            "dev": dev,
            "current_nav": current_nav,
            "current_flags": current_flags,
            "taxes_json": json.dumps(taxes, ensure_ascii=False, indent=2),
            "payments": payments,
        }
    )

@app.post("/ui/einstellungen/save")
async def einstellungen_save(request: Request):
    ensure_role(request, {"Admin", "Owner"})
    form = await request.form()

    payments = []
    for key in ("bar", "karte", "twint", "rechnung"):
        if form.get(f"pay_{key}") == "1":
            payments.append(key)
    if not payments:
        payments = ["bar"]
    set_konfig_json("payments_enabled", payments)

    taxes_raw = form.get("taxes_json") or "{}"
    try:
        taxes = json.loads(taxes_raw)
        set_konfig_json("taxes", taxes)
    except Exception:
        pass

    dev = effective_dev_mode(request)
    if dev:
        nav_items = []
        menu_defs = [
            ("/ui/dashboard", "Dashboard", "nav_dashboard"),
            ("/ui/pos", "Kasse", "nav_pos"),
            ("/ui/kalender", "Kalender", "nav_kalender"),
            ("/ui/kunden", "Kunden", "nav_kunden"),
            ("/ui/katalog", "Katalog", "nav_katalog"),
            ("/ui/berichte", "Berichte", "nav_berichte"),
            ("/ui/mitarbeiter", "Mitarbeiter", "nav_staff"),
            ("/ui/ausgaben", "Ausgaben", "nav_ausgaben"),
            ("/ui/abschluss", "Abschluss", "nav_abschluss"),
            ("/ui/gast", "Gast", "nav_gast"),
            ("/ui/einstellungen", "Einstellungen", "nav_settings"),
        ]
        for href, label, field in menu_defs:
            if form.get(field) == "1":
                nav_items.append({"href": href, "label": label})
        if nav_items:
            set_konfig_json("dev_nav", nav_items)

        flags = {}
        for k, v in form.items():
            if k.startswith("flag_"):
                flags[k.replace("flag_", "", 1)] = 1 if v == "1" else 0
        if flags:
            set_konfig_json("dev_dashboard", flags)

    return RedirectResponse(url="/ui/einstellungen", status_code=303)

# -------------- Kleine API --------------
@app.get("/api/health")
def api_health(request: Request):
    return {"status": "ok", "env": "DEV" if effective_dev_mode(request) else "PROD", "role": get_role(request)}

@app.get("/api/config")
def api_config(request: Request):
    return {
        "payments": get_konfig_json("payments_enabled", ["bar", "karte", "twint", "rechnung"]),
        "taxes": get_konfig_json("taxes", {"CH-7.7": 0.077}),
        "dev_nav": get_konfig_json("dev_nav", None),
        "dev_dashboard": get_konfig_json("dev_dashboard", None),
    }

@app.get("/api/katalog/services")
def api_services(request: Request, session = next(get_session())):
    items = session.query(Service).filter(Service.aktiv == 1).order_by(Service.name).all()
    return [
        {"id": s.id, "name": s.name, "dauer_min": int(s.dauer_min), "preis": float(s.basispreis), "steuer_code": s.steuer_code}
        for s in items
    ]

@app.get("/api/katalog/produkte")
def api_produkte(request: Request, session = next(get_session())):
    items = session.query(Produkt).filter(Produkt.aktiv == 1).order_by(Produkt.name).all()
    return [
        {"id": p.id, "name": p.name, "preis": float(p.verkaufspreis), "steuer_code": p.steuer_code, "lager": p.lagerbestand}
        for p in items
    ]

@app.get("/api/kunden")
def api_kunden(request: Request, session = next(get_session())):
    q = (request.query_params.get("q") or "").strip().lower()
    qry = session.query(Kunde)
    if q:
        qry = qry.filter(
            (Kunde.name.ilike(f"%{q}%")) | (Kunde.telefon.ilike(f"%{q}%")) | (Kunde.email.ilike(f"%{q}%"))
        )
    items = qry.order_by(Kunde.name).limit(50).all()
    return [
        {"id": k.id, "name": k.name, "telefon": k.telefon, "email": k.email, "status": k.kundenstatus}
        for k in items
    ]

@app.get("/api/staff")
def api_staff(request: Request, session = next(get_session())):
    items = session.query(Mitarbeiter).order_by(Mitarbeiter.name).all()
    return [{"id": m.id, "name": m.name} for m in items]

# -------------- CART / CHECKOUT mit Lagerprüfung --------------
@app.post("/api/cart/reset")
async def cart_reset(request: Request):
    request.session["cart"] = {"items": [], "discount_percent": 0, "discount_amount": 0, "tip": 0, "kunde": None}
    return {"ok": True}

@app.get("/api/cart/summary")
def cart_summary(request: Request):
    ensure_cart(request)
    with SessionLocal() as db:
        data = summarize_cart(request.session["cart"], db)
    data["kunde"] = request.session["cart"].get("kunde")
    return data

@app.post("/api/cart/add_item")
async def cart_add_item(request: Request):
    data = await request.json()
    typ = data.get("typ")
    ref_id = int(data.get("ref_id"))
    qty = Decimal(str(data.get("qty") or "1"))
    if typ not in ("service", "produkt"):
        raise HTTPException(status_code=400, detail="typ muss 'service' oder 'produkt' sein")

    with SessionLocal() as db:
        if typ == "service":
            obj = db.get(Service, ref_id)
            if not obj: raise HTTPException(status_code=404, detail="Service nicht gefunden")
            name = obj.name
            price = obj.basispreis
            steuer_code = obj.steuer_code
        else:
            obj = db.get(Produkt, ref_id)
            if not obj: raise HTTPException(status_code=404, detail="Produkt nicht gefunden")
            name = obj.name
            price = obj.verkaufspreis
            steuer_code = obj.steuer_code

    cart = ensure_cart(request)
    line = {
        "line_id": uuid.uuid4().hex,
        "typ": typ,
        "ref_id": ref_id,
        "name": name,
        "qty": float(qty),
        "unit_price": float(price),
        "steuer_code": steuer_code,
    }
    cart["items"].append(line)
    request.session["cart"] = cart
    return {"ok": True, "line_id": line["line_id"]}

@app.post("/api/cart/update_qty")
async def cart_update_qty(request: Request):
    data = await request.json()
    line_id = data.get("line_id")
    qty = Decimal(str(data.get("qty")))
    cart = ensure_cart(request)
    for it in list(cart["items"]):
        if it["line_id"] == line_id:
            if qty <= 0:
                cart["items"].remove(it)
            else:
                it["qty"] = float(qty)
            break
    request.session["cart"] = cart
    return {"ok": True}

@app.post("/api/cart/apply_discount")
async def cart_apply_discount(request: Request):
    data = await request.json()
    amount = Decimal(str(data.get("amount") or "0"))
    percent = Decimal(str(data.get("percent") or "0"))
    cart = ensure_cart(request)
    if amount > 0:
        cart["discount_amount"] = float(round2(amount))
        cart["discount_percent"] = 0.0
    else:
        cart["discount_percent"] = float(percent)
        cart["discount_amount"] = 0.0
    request.session["cart"] = cart
    return {"ok": True}

@app.post("/api/cart/set_tip")
async def cart_set_tip(request: Request):
    data = await request.json()
    amount = Decimal(str(data.get("amount") or "0"))
    cart = ensure_cart(request)
    cart["tip"] = float(round2(amount))
    request.session["cart"] = cart
    return {"ok": True}

@app.post("/api/cart/set_customer")
async def cart_set_customer(request: Request):
    data = await request.json()
    kid = data.get("kunde_id")
    if kid in (None, "",):
        cart = ensure_cart(request)
        cart["kunde"] = None
        request.session["cart"] = cart
        return {"ok": True, "kunde": None}
    kid = int(kid)
    with SessionLocal() as db:
        k = db.get(Kunde, kid)
        if not k:
            raise HTTPException(status_code=404, detail="Kunde nicht gefunden")
        cart = ensure_cart(request)
        cart["kunde"] = {"id": k.id, "name": k.name}
        request.session["cart"] = cart
        return {"ok": True, "kunde": cart["kunde"]}

@app.post("/api/cart/checkout")
async def cart_checkout(request: Request):
    data = await request.json()
    payments = data.get("payments") or []
    kunde_id = data.get("kunde_id")
    mitarbeiter_id = data.get("mitarbeiter_id")

    cart = ensure_cart(request)
    if not kunde_id and cart.get("kunde"):
        kunde_id = cart["kunde"]["id"]

    prod_need: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for it in cart["items"]:
        if it["typ"] == "produkt":
            prod_need[int(it["ref_id"])] += Decimal(str(it["qty"]))

    with SessionLocal() as db:
        for pid, need in prod_need.items():
            p = db.get(Produkt, pid)
            if not p:
                raise HTTPException(status_code=404, detail=f"Produkt {pid} nicht gefunden")
            if p.lagerbestand is not None and p.lagerbestand < int(need):
                raise HTTPException(status_code=400, detail=f"Nicht genügend Lager für '{p.name}'. Verfügbar: {p.lagerbestand}, benötigt: {int(need)}.")

        summary = summarize_cart(cart, db)
        total = Decimal(str(summary["total_gross"]))

        if not payments:
            raise HTTPException(status_code=400, detail="Keine Zahlungen übergeben.")
        paid = sum(Decimal(str(p["betrag"])) for p in payments)
        if paid < total:
            raise HTTPException(status_code=400, detail="Zahlbetrag kleiner als Gesamtbetrag.")
        if paid > total:
            over = paid - total
            payments[-1]["betrag"] = float(Decimal(str(payments[-1]["betrag"])) - over)

        belegnr = next_receipt_number(db)

        beleg = Beleg(
            belegnr=belegnr,
            kunde_id=int(kunde_id) if kunde_id else None,
            mitarbeiter_id=mitarbeiter_id,
            summe_brutto=Decimal(str(summary["subtotal_gross"])),
            rabatt_betrag=Decimal(str(summary["discount_amount"])),
            trinkgeld=Decimal(str(summary["tip"])),
            steuer_summe=Decimal(str(summary["tax_total"])),
            zahlstatus="bezahlt" if paid >= total else "teilbezahlt",
            zahlart=payments[0]["art"] if len(payments) == 1 else None,
        )
        db.add(beleg)
        db.flush()

        rates = load_tax_rates(db)
        for it in cart["items"]:
            qty = Decimal(str(it["qty"]))
            up = Decimal(str(it["unit_price"]))
            gross = round2(qty * up)
            rate = rates.get(it["steuer_code"], Decimal("0"))
            tax = round2(gross - (gross / (Decimal("1") + rate)) if rate > 0 else Decimal("0"))
            db.add(BelegPosition(
                beleg_id=beleg.id,
                typ=it["typ"],
                ref_id=it["ref_id"],
                menge=qty,
                einzelpreis=up,
                steuer_code=it["steuer_code"],
                steuer_betrag=tax,
                gesamtpreis=gross,
            ))

        for pmt in payments:
            db.add(Zahlung(
                beleg_id=beleg.id,
                art=pmt["art"],
                betrag=Decimal(str(pmt["betrag"])),
            ))

        for pid, need in prod_need.items():
            p = db.get(Produkt, pid)
            if p and p.lagerbestand is not None:
                p.lagerbestand = int(p.lagerbestand) - int(need)
                if p.lagerbestand < 0:
                    p.lagerbestand = 0
                db.add(p)

        db.commit()
        created_id = beleg.id

    request.session["cart"] = {"items": [], "discount_percent": 0, "discount_amount": 0, "tip": 0, "kunde": None}
    return {"ok": True, "beleg_id": created_id, "belegnr": belegnr}

# -------------- AUSGABEN --------------
@app.get("/ui/ausgaben", response_class=HTMLResponse)
def ui_ausgaben(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter", "Buchhaltung"})
    date_from = request.query_params.get("from")
    date_to = request.query_params.get("to")
    first, last, start, end = _range_bounds(date_from, date_to)

    with SessionLocal() as db:
        rows = db.query(Ausgabe).filter(Ausgabe.datum >= first, Ausgabe.datum <= last).order_by(Ausgabe.datum.desc()).all()
        total = sum((a.betrag or Decimal("0")) for a in rows)
    return templates.TemplateResponse(
        "ausgaben_list.html",
        ctx(request, "Ausgaben") | {"rows": rows, "date_from": first.isoformat(), "date_to": last.isoformat(), "total": float(round2(total))}
    )

@app.get("/ui/ausgaben/new", response_class=HTMLResponse)
def ausgabe_new_form(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    return templates.TemplateResponse("ausgaben_form.html", ctx(request, "Ausgabe erfassen"))

@app.post("/ui/ausgaben/new")
async def ausgabe_new(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    form = await request.form()
    datum = datetime.date.fromisoformat(form.get("datum"))
    kategorie = (form.get("kategorie") or "").strip() or None
    betrag = Decimal(str(form.get("betrag") or "0"))
    zahlart = form.get("zahlart") or "bar"
    belegt = 1 if form.get("belegt") == "1" else 0
    with SessionLocal() as db:
        db.add(Ausgabe(datum=datum, kategorie=kategorie, betrag=betrag, zahlart=zahlart, belegt=belegt))
        db.commit()
    return RedirectResponse(url="/ui/ausgaben", status_code=303)

@app.get("/ui/ausgaben/{aid}/edit", response_class=HTMLResponse)
def ausgabe_edit_form(aid: int, request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    with SessionLocal() as db:
        a = db.get(Ausgabe, aid)
        if not a:
            raise HTTPException(status_code=404, detail="Ausgabe nicht gefunden")
    return templates.TemplateResponse("ausgaben_edit.html", ctx(request, "Ausgabe bearbeiten") | {"item": a})

@app.post("/ui/ausgaben/{aid}/edit")
async def ausgabe_edit(aid: int, request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    form = await request.form()
    with SessionLocal() as db:
        a = db.get(Ausgabe, aid)
        if not a:
            raise HTTPException(status_code=404, detail="Ausgabe nicht gefunden")
        a.datum = datetime.date.fromisoformat(form.get("datum"))
        a.kategorie = (form.get("kategorie") or "").strip() or None
        a.betrag = Decimal(str(form.get("betrag") or "0"))
        a.zahlart = form.get("zahlart") or a.zahlart
        a.belegt = 1 if form.get("belegt") == "1" else 0
        db.add(a)
        db.commit()
    return RedirectResponse(url="/ui/ausgaben", status_code=303)

@app.post("/ui/ausgaben/{aid}/delete")
async def ausgabe_delete(aid: int, request: Request):
    ensure_role(request, {"Admin", "Owner"})
    with SessionLocal() as db:
        a = db.get(Ausgabe, aid)
        if a:
            db.delete(a)
            db.commit()
    return RedirectResponse(url="/ui/ausgaben", status_code=303)

# -------------- ABSCHLUSS / KASSENBUCH / EXPORT --------------
@app.get("/ui/abschluss", response_class=HTMLResponse)
def ui_abschluss(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter", "Buchhaltung"})
    d = datetime.date.today().isoformat()
    return templates.TemplateResponse("abschluss.html", ctx(request, "Tagesabschluss") | {"date_str": d})

@app.get("/api/abschluss/preview")
def api_abschluss_preview(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter", "Buchhaltung"})
    date_str = request.query_params.get("date")
    d, start, end = _day_bounds(date_str)

    with SessionLocal() as db:
        payments = db.query(Zahlung).filter(Zahlung.timestamp >= start, Zahlung.timestamp <= end).all()
        sum_bar = sum((p.betrag for p in payments if p.art == "bar"), Decimal("0"))
        sum_karte = sum((p.betrag for p in payments if p.art == "karte"), Decimal("0"))
        sum_twint = sum((p.betrag for p in payments if p.art == "twint"), Decimal("0"))
        sum_rechnung = sum((p.betrag for p in payments if p.art == "rechnung"), Decimal("0"))

        belege = db.query(Beleg).filter(Beleg.timestamp >= start, Beleg.timestamp <= end).all()
        tip = sum((b.trinkgeld or Decimal("0")) for b in belege)
        brutto = sum((b.summe_brutto or Decimal("0")) for b in belege)

        ausgaben = db.query(Ausgabe).filter(Ausgabe.datum == d).all()
        exp_bar = sum((a.betrag for a in ausgaben if a.zahlart == "bar"), Decimal("0"))
        exp_karte = sum((a.betrag for a in ausgaben if a.zahlart == "karte"), Decimal("0"))
        exp_twint = sum((a.betrag for a in ausgaben if a.zahlart == "twint"), Decimal("0"))
        exp_rechnung = sum((a.betrag for a in ausgaben if a.zahlart == "rechnung"), Decimal("0"))
        exp_total = exp_bar + exp_karte + exp_twint + exp_rechnung

        kb = db.query(Kassenbuch).filter(Kassenbuch.datum == d).first()
        startfloat = kb.startfloat if kb else Decimal("0")
        einlagen = kb.einlagen if kb else Decimal("0")
        entnahmen = kb.entnahmen if kb else Decimal("0")
        bar_ist = kb.bar_ist if kb else None

        bar_soll = startfloat + einlagen - entnahmen + sum_bar - exp_bar
        differenz = (bar_ist - bar_soll) if (bar_ist is not None) else None

        ab = db.query(Abschluss).filter(Abschluss.datum == d).first()
        finalized = bool(ab)

        return {
            "date": d.isoformat(),
            "payments": {
                "bar": float(round2(sum_bar)),
                "karte": float(round2(sum_karte)),
                "twint": float(round2(sum_twint)),
                "rechnung": float(round2(sum_rechnung)),
            },
            "belege": {
                "anzahl": len(belege),
                "summe_brutto": float(round2(brutto)),
                "trinkgeld": float(round2(tip)),
            },
            "ausgaben": {
                "bar": float(round2(exp_bar)),
                "karte": float(round2(exp_karte)),
                "twint": float(round2(exp_twint)),
                "rechnung": float(round2(exp_rechnung)),
                "total": float(round2(exp_total)),
            },
            "kassenbuch": {
                "startfloat": float(round2(startfloat)),
                "einlagen": float(round2(einlagen)),
                "entnahmen": float(round2(entnahmen)),
                "bar_soll": float(round2(bar_soll)),
                "bar_ist": (float(round2(bar_ist)) if bar_ist is not None else None),
                "differenz": (float(round2(differenz)) if differenz is not None else None),
            },
            "finalized": finalized,
        }

@app.post("/api/abschluss/kassenbuch/set_startfloat")
async def api_kb_set_startfloat(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    data = await request.json()
    date_str = data.get("date")
    amount = Decimal(str(data.get("amount") or "0"))
    d, _, _ = _day_bounds(date_str)
    with SessionLocal() as db:
        kb = db.query(Kassenbuch).filter(Kassenbuch.datum == d).first()
        if not kb:
            kb = Kassenbuch(datum=d, startfloat=amount, einlagen=Decimal("0"), entnahmen=Decimal("0"))
        else:
            kb.startfloat = amount
        db.add(kb)
        db.commit()
    return {"ok": True}

@app.post("/api/abschluss/kassenbuch/add_entry")
async def api_kb_add_entry(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    data = await request.json()
    date_str = data.get("date")
    kind = data.get("kind")  # "einlage" | "entnahme"
    amount = Decimal(str(data.get("amount") or "0"))
    if kind not in ("einlage", "entnahme"):
        raise HTTPException(status_code=400, detail="kind muss 'einlage' oder 'entnahme' sein.")
    d, _, _ = _day_bounds(date_str)
    with SessionLocal() as db:
        kb = db.query(Kassenbuch).filter(Kassenbuch.datum == d).first()
        if not kb:
            kb = Kassenbuch(datum=d, startfloat=Decimal("0"), einlagen=Decimal("0"), entnahmen=Decimal("0"))
        if kind == "einlage":
            kb.einlagen = (kb.einlagen or Decimal("0")) + amount
        else:
            kb.entnahmen = (kb.entnahmen or Decimal("0")) + amount
        db.add(kb)
        db.commit()
    return {"ok": True}

@app.post("/api/abschluss/finalize")
async def api_abschluss_finalize(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    data = await request.json()
    date_str = data.get("date")
    bar_ist = Decimal(str(data.get("bar_ist") or "0"))
    d, start, end = _day_bounds(date_str)

    with SessionLocal() as db:
        payments = db.query(Zahlung).filter(Zahlung.timestamp >= start, Zahlung.timestamp <= end).all()
        sum_bar = sum((p.betrag for p in payments if p.art == "bar"), Decimal("0"))
        sum_karte = sum((p.betrag for p in payments if p.art == "karte"), Decimal("0"))
        sum_twint = sum((p.betrag for p in payments if p.art == "twint"), Decimal("0"))
        belege = db.query(Beleg).filter(Beleg.timestamp >= start, Beleg.timestamp <= end).all()
        tip = sum((b.trinkgeld or Decimal("0")) for b in belege)

        ausgaben = db.query(Ausgabe).filter(Ausgabe.datum == d).all()
        exp_bar = sum((a.betrag for a in ausgaben if a.zahlart == "bar"), Decimal("0"))

        kb = db.query(Kassenbuch).filter(Kassenbuch.datum == d).first()
        if not kb:
            kb = Kassenbuch(datum=d, startfloat=Decimal("0"), einlagen=Decimal("0"), entnahmen=Decimal("0"))
        bar_soll = (kb.startfloat or Decimal("0")) + (kb.einlagen or Decimal("0")) - (kb.entnahmen or Decimal("0")) + sum_bar - exp_bar
        kb.bar_soll = round2(bar_soll)
        kb.bar_ist = round2(bar_ist)
        kb.differenz = round2(bar_ist - bar_soll)
        db.add(kb)

        ab = db.query(Abschluss).filter(Abschluss.datum == d).first()
        payload_sig = {"finalized_by": get_role(request), "ts": datetime.datetime.utcnow().isoformat()}
        if not ab:
            ab = Abschluss(
                datum=d,
                summe_bar=round2(sum_bar),
                summe_twint=round2(sum_twint),
                summe_karte=round2(sum_karte),
                trinkgeld=round2(tip),
                differenz=kb.differenz,
                signaturen=json.dumps(payload_sig),
                pdf_path=None,
            )
        else:
            ab.summe_bar = round2(sum_bar)
            ab.summe_twint = round2(sum_twint)
            ab.summe_karte = round2(sum_karte)
            ab.trinkgeld = round2(tip)
            ab.differenz = kb.differenz
            ab.signaturen = json.dumps(payload_sig)
        db.add(ab)
        db.commit()
    return {"ok": True}

@app.get("/ui/abschluss/export")
def ui_abschluss_export(request: Request):
    ensure_role(request, {"Admin", "Owner", "Buchhaltung"})
    date_str = request.query_params.get("date")
    d, start, end = _day_bounds(date_str)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["BelegNr", "Datum/Uhrzeit", "SummeBrutto", "Trinkgeld", "Steuer", "Zahlstatus"])
    with SessionLocal() as db:
        belege = db.query(Beleg).filter(Beleg.timestamp >= start, Beleg.timestamp <= end).order_by(Beleg.timestamp.asc()).all()
        for b in belege:
            writer.writerow([
                b.belegnr,
                b.timestamp.isoformat(sep=" ", timespec="seconds"),
                f"{(b.summe_brutto or Decimal('0')):.2f}",
                f"{(b.trinkgeld or Decimal('0')):.2f}",
                f"{(b.steuer_summe or Decimal('0')):.2f}",
                b.zahlstatus or "",
            ])
    output.seek(0)
    filename = f"abschluss_{d.isoformat()}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)

# -------------- BERICHTE --------------
@app.get("/ui/berichte", response_class=HTMLResponse)
def ui_berichte(request: Request):
    ensure_role(request, {"Admin", "Owner", "Buchhaltung"})
    today = datetime.date.today()
    first = today.replace(day=1).isoformat()
    last = today.isoformat()
    return templates.TemplateResponse("berichte.html", ctx(request, "Berichte") | {"date_from": first, "date_to": last})

@app.get("/api/reports/overview")
def api_reports_overview(request: Request):
    ensure_role(request, {"Admin", "Owner", "Buchhaltung"})
    date_from = request.query_params.get("from")
    date_to = request.query_params.get("to")
    first, last, start, end = _range_bounds(date_from, date_to)

    with SessionLocal() as db:
        pays = db.query(Zahlung).filter(Zahlung.timestamp >= start, Zahlung.timestamp <= end).all()
        pay_sum = defaultdict(lambda: Decimal("0"))
        for p in pays:
            pay_sum[p.art] += p.betrag or Decimal("0")

        belege = db.query(Beleg).filter(Beleg.timestamp >= start, Beleg.timestamp <= end).all()
        rev_brutto = sum((b.summe_brutto or Decimal("0")) for b in belege)
        tips = sum((b.trinkgeld or Decimal("0")) for b in belege)
        tax_total = sum((b.steuer_summe or Decimal("0")) for b in belege)

        by_day = defaultdict(lambda: Decimal("0"))
        for b in belege:
            d = b.timestamp.date().isoformat()
            by_day[d] += (b.summe_brutto or Decimal("0")) + (b.trinkgeld or Decimal("0"))

        pos = db.query(BelegPosition).filter(BelegPosition.timestamp >= start, BelegPosition.timestamp <= end).all()
        top_map = defaultdict(lambda: Decimal("0"))
        for p in pos:
            key = (p.typ, p.ref_id)
            top_map[key] += p.gesamtpreis or Decimal("0")

        names = {}
        for (typ, rid) in top_map.keys():
            if typ == "service":
                s = db.get(Service, rid); names[(typ, rid)] = s.name if s else f"Service #{rid}"
            else:
                pr = db.get(Produkt, rid); names[(typ, rid)] = pr.name if pr else f"Produkt #{rid}"

        top_items = sorted(
            [{"typ": t, "ref_id": rid, "name": names[(t, rid)], "umsatz": float(round2(val))} for (t, rid), val in top_map.items()],
            key=lambda x: x["umsatz"], reverse=True
        )[:10]

        aus = db.query(Ausgabe).filter(Ausgabe.datum >= first, Ausgabe.datum <= last).all()
        aus_total = sum((a.betrag or Decimal("0")) for a in aus)

    return {
        "from": first.isoformat(),
        "to": last.isoformat(),
        "payments": {k: float(round2(v)) for k, v in pay_sum.items()},
        "umsatz_brutto": float(round2(rev_brutto)),
        "trinkgeld": float(round2(tips)),
        "mwst_summe": float(round2(tax_total)),
        "by_day": [{"date": d, "amount": float(round2(v))} for d, v in sorted(by_day.items())],
        "top": top_items,
        "ausgaben_total": float(round2(aus_total)),
        "ergebnis": float(round2(rev_brutto + tips - aus_total)),
    }

@app.get("/ui/berichte/export")
def ui_reports_export(request: Request):
    ensure_role(request, {"Admin", "Owner", "Buchhaltung"})
    date_from = request.query_params.get("from")
    date_to = request.query_params.get("to")
    first, last, start, end = _range_bounds(date_from, date_to)

    output = io.StringIO()
    w = csv.writer(output, delimiter=";")
    w.writerow(["Datum", "BelegNr", "Brutto", "Trinkgeld", "Steuer", "Zahlstatus"])
    with SessionLocal() as db:
        belege = db.query(Beleg).filter(Beleg.timestamp >= start, Beleg.timestamp <= end).order_by(Beleg.timestamp.asc()).all()
        for b in belege:
            w.writerow([
                b.timestamp.date().isoformat(),
                b.belegnr,
                f"{(b.summe_brutto or Decimal('0')):.2f}",
                f"{(b.trinkgeld or Decimal('0')):.2f}",
                f"{(b.steuer_summe or Decimal('0')):.2f}",
                b.zahlstatus or "",
            ])
    output.seek(0)
    filename = f"berichte_{first.isoformat()}_{last.isoformat()}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)

# -------------- TERMINE (Kalender) --------------
@app.get("/api/termine/day")
def api_termine_day(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    date_str = request.query_params.get("date")
    d, start, end = _day_bounds(date_str)
    with SessionLocal() as db:
        rows = db.query(Termin).filter(Termin.start >= start, Termin.start <= end).order_by(Termin.start.asc()).all()
        result = []
        for t in rows:
            kunde_name = None
            staff_name = None
            if t.kunde_id:
                k = db.get(Kunde, t.kunde_id); kunde_name = k.name if k else None
            if t.mitarbeiter_id:
                m = db.get(Mitarbeiter, t.mitarbeiter_id); staff_name = m.name if m else None
            services = []
            try:
                if t.ressourcen:
                    data = json.loads(t.ressourcen)
                    services = data.get("services", [])
            except Exception:
                pass
            service_names = []
            for sid in services:
                s = db.get(Service, sid)
                if s: service_names.append(s.name)
            result.append({
                "id": t.id,
                "start": t.start.isoformat(),
                "ende": t.ende.isoformat() if t.ende else None,
                "kunde": kunde_name,
                "mitarbeiter": staff_name,
                "services": service_names,
                "zustand": t.zustand or "gebucht",
                "bemerkung": t.bemerkungen if hasattr(t, "bemerkungen") else None
            })
        return result

@app.get("/ui/termin/new", response_class=HTMLResponse)
def termin_new_form(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    with SessionLocal() as db:
        staff = db.query(Mitarbeiter).order_by(Mitarbeiter.name).all()
        services = db.query(Service).filter(Service.aktiv == 1).order_by(Service.name).all()
        kunden = db.query(Kunde).order_by(Kunde.name).all()
    return templates.TemplateResponse("termin_form.html", ctx(request, "Termin anlegen") | {"staff": staff, "services": services, "kunden": kunden})

@app.post("/ui/termin/new")
async def termin_new(request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    form = await request.form()
    kid = int(form.get("kunde_id")) if form.get("kunde_id") else None
    mid = int(form.get("mitarbeiter_id")) if form.get("mitarbeiter_id") else None
    date = datetime.date.fromisoformat(form.get("datum"))
    start_time = datetime.time.fromisoformat(form.get("start"))
    dauer_min = int(form.get("dauer_min") or "0")
    end_dt = datetime.datetime.combine(date, start_time) + datetime.timedelta(minutes=dauer_min)
    start_dt = datetime.datetime.combine(date, start_time)
    services_raw = form.getlist("services") if hasattr(form, "getlist") else (form.get("services") or "").split(",")
    services = [int(x) for x in services_raw if str(x).strip()]
    bemerkung = (form.get("bemerkung") or "").strip() or None

    with SessionLocal() as db:
        # einfacher Konflikt-Check: gleicher Mitarbeiter & overlap
        if mid:
            overlap = db.query(Termin).filter(
                Termin.mitarbeiter_id == mid,
                Termin.start < end_dt,
                Termin.ende > start_dt
            ).first()
            if overlap:
                raise HTTPException(status_code=400, detail="Termin-Konflikt für diesen Mitarbeiter.")
        t = Termin(
            kunde_id=kid,
            mitarbeiter_id=mid,
            start=start_dt,
            ende=end_dt,
            zustand="gebucht",
            ressourcen=json.dumps({"services": services}),
        )
        # optionales Bemerkungen-Feld abfangen, falls vorhanden
        if hasattr(Termin, "bemerkungen"):
            setattr(t, "bemerkungen", bemerkung)
        db.add(t); db.commit()
    return RedirectResponse(url=f"/ui/kalender?date={date.isoformat()}", status_code=303)

@app.get("/ui/termin/{tid}/edit", response_class=HTMLResponse)
def termin_edit_form(tid: int, request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    with SessionLocal() as db:
        t = db.get(Termin, tid)
        if not t: raise HTTPException(status_code=404, detail="Termin nicht gefunden")
        staff = db.query(Mitarbeiter).order_by(Mitarbeiter.name).all()
        services = db.query(Service).filter(Service.aktiv == 1).order_by(Service.name).all()
        kunden = db.query(Kunde).order_by(Kunde.name).all()
        selected = []
        try:
            if t.ressourcen:
                selected = json.loads(t.ressourcen).get("services", [])
        except Exception:
            selected = []
    return templates.TemplateResponse(
        "termin_edit.html",
        ctx(request, "Termin bearbeiten") | {"item": t, "staff": staff, "services": services, "kunden": kunden, "selected_services": selected}
    )

@app.post("/ui/termin/{tid}/edit")
async def termin_edit(tid: int, request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    form = await request.form()
    kid = int(form.get("kunde_id")) if form.get("kunde_id") else None
    mid = int(form.get("mitarbeiter_id")) if form.get("mitarbeiter_id") else None
    date = datetime.date.fromisoformat(form.get("datum"))
    start_time = datetime.time.fromisoformat(form.get("start"))
    dauer_min = int(form.get("dauer_min") or "0")
    end_dt = datetime.datetime.combine(date, start_time) + datetime.timedelta(minutes=dauer_min)
    start_dt = datetime.datetime.combine(date, start_time)
    services_raw = form.getlist("services") if hasattr(form, "getlist") else (form.get("services") or "").split(",")
    services = [int(x) for x in services_raw if str(x).strip()]
    zustand = form.get("zustand") or "gebucht"
    bemerkung = (form.get("bemerkung") or "").strip() or None

    with SessionLocal() as db:
        t = db.get(Termin, tid)
        if not t: raise HTTPException(status_code=404, detail="Termin nicht gefunden")
        if mid:
            overlap = db.query(Termin).filter(
                Termin.id != tid,
                Termin.mitarbeiter_id == mid,
                Termin.start < end_dt,
                Termin.ende > start_dt
            ).first()
            if overlap:
                raise HTTPException(status_code=400, detail="Termin-Konflikt für diesen Mitarbeiter.")
        t.kunde_id = kid
        t.mitarbeiter_id = mid
        t.start = start_dt
        t.ende = end_dt
        t.zustand = zustand
        t.ressourcen = json.dumps({"services": services})
        if hasattr(Termin, "bemerkungen"):
            setattr(t, "bemerkungen", bemerkung)
        db.add(t); db.commit()
    return RedirectResponse(url=f"/ui/kalender?date={date.isoformat()}", status_code=303)

@app.post("/ui/termin/{tid}/status")
async def termin_status(tid: int, request: Request):
    ensure_role(request, {"Admin", "Owner", "Mitarbeiter"})
    form = await request.form()
    status = form.get("zustand") or "gebucht"
    with SessionLocal() as db:
        t = db.get(Termin, tid)
        if not t: raise HTTPException(status_code=404, detail="Termin nicht gefunden")
        t.zustand = status
        db.add(t); db.commit()
    return RedirectResponse(url=f"/ui/kalender?date={t.start.date().isoformat()}", status_code=303)
