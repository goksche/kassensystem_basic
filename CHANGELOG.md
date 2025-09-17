# Changelog

## v0.3 — 2025-09-17
- **Kasse (POS):** Sichtbare Listen für Services & Produkte; neuer Warenkorb mit Mengen ±, Entfernen, „Warenkorb leeren“.
- **Rabatt/Trinkgeld:** Live-Berechnung (Betrag + %), Gesamtsumme inkl. Steueranteil je CH-Steuercode (7.7 / 2.6 / 0).
- **Buchen-Button:** Clientseitiger Abschluss + optionaler Server-Checkout.
- **Backend-Checkout:** `POST /pos/checkout` + `app/services/checkout.py`
  - Belegnummer-Erzeugung (Fallback, nutzt vorhandene Nummernlogik wenn verfügbar)
  - Anlage von Beleg/Positionen/Zahlungen (felderagnostisch), Lagerabzug bei Produkten
- **Katalog-Fixes:** Produkt/Service-Formulare vereinheitlicht, Kategorie-Dropdown, Feldnamen stabilisiert.
- **RBAC/DEV:** bleibt wie in v0.2 (Admin/Owner DEV-Toggle).

## v0.2 — 2025-09-xx
- **Auth & RBAC:** Login/Logout, Rollen-Guards, DEV-Toggle nur für Admin/Owner.
- **Navigation & Dashboard:** konfigurierbar und persistent im DEV-Modus.

## v0.1 — Initial
- Basisfunktionen: POS, Katalog, Kunden, Mitarbeiter, Kalender/Termine, Ausgaben, Berichte, Tagesabschluss, CSV-Exporte.
