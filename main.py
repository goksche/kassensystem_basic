from fastapi import FastAPI, Request, Depends, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from decimal import Decimal, InvalidOperation

from app.config import settings as app_settings
from app.models.base import Base, engine, SessionLocal
from app.services.db_init import init_db
from app.services.auth import (
    authenticate_user,
    login_user,
    logout_user,
    get_current_user,
    is_admin_or_owner,
)
from app.services import config_store
from app.services import checkout as checkout_service  # <-- NEU

from app.models.entities import Service, Produkt

app = FastAPI(title=app_settings.APP_NAME)
app.add_middleware(SessionMiddleware, secret_key=app_settings.SECRET_KEY, session_cookie="ksb_session")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def _startup():
    init_db(dev_seed=True)

ALLOW_ALL_ROLES = {"Owner", "Admin", "Mitarbeiter", "Buchhaltung", "Gast"}
POLICY = {
    "/": ALLOW_ALL_ROLES,
    "/pos": {"Owner", "Admin", "Mitarbeiter"},
    "/katalog": {"Owner", "Admin"},
    "/kalender": {"Owner", "Admin", "Mitarbeiter"},
    "/kunden": {"Owner", "Admin", "Mitarbeiter"},
    "/mitarbeiter": {"Owner", "Admin"},
    "/berichte": {"Owner", "Admin", "Buchhaltung"},
    "/ausgaben": {"Owner", "Admin", "Buchhaltung"},
    "/abschluss": {"Owner", "Admin", "Buchhaltung"},
    "/einstellungen": {"Owner", "Admin"},
}

def _dev(request: Request) -> bool:
    val = request.session.get("dev")
    if val is None:
        return bool(app_settings.DEFAULT_DEV_MODE)
    return bool(val)

def _nav_for_role(role: str | None, dev: bool) -> list[dict]:
    base_items = config_store.effective_nav_items(dev)
    if role is None:
        return [i for i in base_items if i["href"] in {"/", "/gast_portal", "/login"}]
    filtered = []
    for it in base_items:
        href = it.get("href", "")
        if href == "/gast_portal":
            filtered.append(it); continue
        allowed = POLICY.get(href)
        if allowed and role in allowed:
            filtered.append(it)
    return filtered

def _ctx(request: Request, db: Session):
    user = get_current_user(request, db)
    dev = _dev(request)
    nav_items = _nav_for_role(user.role if user else None, dev)
    flags = config_store.effective_dash_flags(dev)
    class F: pass
    f = F(); [setattr(f, k, v) for k, v in flags.items()]
    return {"request": request, "current_user": user, "dev": dev, "nav_items": nav_items, "flags": f, "DEV_MODE": dev}

def _guard(request: Request, db: Session, path: str):
    user = get_current_user(request, db)
    if not user:
        return None, RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
    allowed = POLICY.get(path, set())
    if allowed and user.role not in allowed:
        return user, templates.TemplateResponse("403.html", _ctx(request, db), status_code=403)
    return user, None

def _tax_codes() -> list[str]:
    return ["CH-7.7", "CH-2.6", "CH-0"]

# -------- Dashboard / Auth / DEV --------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user, resp = _guard(request, db, "/")
    if resp: return resp
    return templates.TemplateResponse("dashboard.html", _ctx(request, db))

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login_post(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, email=email, password=password)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Ungueltige Zugangsdaten."}, status_code=status.HTTP_401_UNAUTHORIZED)
    login_user(request, user)
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)

@app.post("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)

@app.post("/dev/toggle")
def dev_toggle(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not is_admin_or_owner(request):
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    request.session["dev"] = not _dev(request)
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)

# -------- POS --------

@app.get("/pos", response_class=HTMLResponse)
def pos_page(request: Request, db: Session = Depends(get_db)):
    user, resp = _guard(request, db, "/pos")
    if resp: return resp
    services = db.query(Service).filter(Service.aktiv == 1).order_by(Service.name.asc()).all()
    produkte = db.query(Produkt).filter(Produkt.aktiv == 1).order_by(Produkt.name.asc()).all()
    ctx = _ctx(request, db) | {"services": services, "produkte": produkte}
    return templates.TemplateResponse("pos.html", ctx)

# >>> NEU: Checkout (wird vom Button "Buchen" aufgerufen)
@app.post("/pos/checkout")
async def pos_checkout(request: Request, db: Session = Depends(get_db)):
    user, resp = _guard(request, db, "/pos")
    if resp: return resp
    payload = await request.json()
    try:
        result = checkout_service.process_checkout(db, payload, user)
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

# -------- Katalog (unverändert zu vorigem Stand) --------

@app.get("/katalog", response_class=HTMLResponse)
def katalog_list(request: Request, db: Session = Depends(get_db), q: str | None = None):
    user, resp = _guard(request, db, "/katalog")
    if resp: return resp
    q = (q or "").strip()
    services_q = db.query(Service)
    produkte_q = db.query(Produkt)
    if q:
        services_q = services_q.filter(Service.name.ilike(f"%{q}%"))
        produkte_q = produkte_q.filter(Produkt.name.ilike(f"%{q}%"))
    ctx = _ctx(request, db) | {
        "q": q,
        "services": services_q.order_by(Service.aktiv.desc(), Service.name.asc()).all(),
        "produkte": produkte_q.order_by(Produkt.aktiv.desc(), Produkt.name.asc()).all(),
        "tax_codes": _tax_codes(),
    }
    return templates.TemplateResponse("katalog.html", ctx)

# ---- Services (neu/ändern/toggle) & Produkte (neu/ändern/toggle)
# (Dein bestehender CRUD-Block bleibt hier unverändert – wegen Platz nicht erneut ausgeschrieben)
