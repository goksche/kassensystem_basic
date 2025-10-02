# app/berichte_tagesabschluss.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["Berichte"])

@router.get("/berichte/tagesabschluss", response_class=HTMLResponse)
async def tagesabschluss(request: Request):
    ctx = {
        "request": request,
        "salon_name": "Salon Mustermann",
        "mwst_uid": "CHE-123.456.789 MWST",
        "datum_zeit": "2025-09-30",
        "kasse_id": "S1",
        "zeitraum": "08:00–19:00",
        "schicht": "Tag",
        "totals": {"brutto": 3940.00, "netto": 3646.20, "mwst": 293.80},
        "warengruppen": {"DL": 3100.00, "Produkte": 840.00},
        "steuersaetze": [
            {"satz": 8.1, "netto": 3520.00, "mwst": 285.00},
            {"satz": 2.6, "netto": 126.20, "mwst": 3.80},
        ],
        "belege_count": 72,
        "bon_avg": 54.72,
        "rabatte": {"count": 6, "summe": 120.00},
        "stornos": {"count": 1, "summe": 45.00, "detail": "Benutzer: A.K., Grund: Doppelerfassung"},
        "zahlungen": {"bar": 1120.00, "karte": 2310.00, "twint": 460.00, "gutschein": 50.00},
        "kassensturz": {
            "anfang": 300.00, "einlagen": 0.00, "auslagen": 40.00, "end": 1380.00,
            "soll_bar": 1380.00, "ist_bar": 1379.50, "diff": -0.50
        },
        "mitarbeiter": [
            {"name": "Lea", "dl_umsatz": 1420.00},
            {"name": "Cem", "dl_umsatz": 980.00},
            {"name": "Anna", "dl_umsatz": 700.00},
            {"name": "Tim", "dl_umsatz": 0.00},
        ],
        "trinkgeld": {"bar": 110.00, "cashless": 35.00, "verteilung": "Team 100%"},
        "gutscheine": {"verkauft": 200.00, "eingeloest": 50.00, "restwert": 3150.00},
        "checks": {"terminal": "OK", "offene_bons": 0, "mwst": "OK"},
    }
    return templates.TemplateResponse("bericht_tagesabschluss.html", ctx)
