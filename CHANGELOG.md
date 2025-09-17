# Changelog

Alle nennenswerten Änderungen dieses Projekts werden in dieser Datei festgehalten.

## [0.4] – 2025-09-18
### Neu
- **Kombi-Zahlung** im POS: zwei Zahlungsarten auswählbar, Betrag A eingeben, Restbetrag wird automatisch für Art B berechnet.
- **Checkout-Validierung**: prüft bei Kombi zwei unterschiedliche Arten und Betrags-Summe == Gesamt.

### Geändert
- **Checkout-Persistenz** robuster & schematisch tolerant:
  - Setzt Beleg-Felder per Synonymlisten (`belegnr/nummer`, `summe_brutto/brutto`, `steuer_summe`, `zahlart/zahlstatus` usw.).
  - Zieht **Lagerbestand** bei Produktpositionen ab (mit Vorabprüfung und Fehlermeldung).
  - Schreibt Positionsfelder wie `ref_id` (NOT NULL), `steuer_betrag`, `gesamtpreis`.
  - Schreibt Zahlungen in Tabelle `zahlungen` (inkl. Pflichtfeld `art` und `timestamp`).
- **Beleganzeige**: liest Summen/Nummer über Synonyme, Gesamt wird korrekt angezeigt; Zahlungen werden aufgelistet.

### Fixes
- IntegrityErrors (NOT NULL) bei `belege.belegnr`, `beleg_positionen.ref_id`, `zahlungen.art` behoben.
- Katalog/Produkte: Sichtbarkeit im POS, Produktformular (Dropdown „Kategorie“ Service/Produkt), kleinere UI-Glitches.

## [0.3] – 2025-09-17
- POS überarbeitet: Warenkorb, Steuern, Rabatte, Trinkgeld, Summen; Produkte/Services in der Kasse sichtbar.
- Button **Buchen** hinzugefügt, Checkout-Route implementiert.
- Erste Belegansicht inkl. Drucken.

## [0.2] – 2025-09-17
- **Auth & RBAC**: Login/Logout, Rollen (Owner/Admin/Mitarbeiter/Buchhaltung/Gast), Guards.
- DEV-Toggle nur für Admin/Owner; konfigurierbare Navigation & Dashboard-Kacheln (persistiert).
- Seed-User angelegt.

## [0.1] – 2025-09-**
- Initiale Basisfunktionen (POS rudimentär, Katalog, Kunden, Termine, Berichte, Abschluss).
