# AGENTS.md

## Cursor Cloud specific instructions

### What this is
`Kassensystem Basic` is a single self-contained German POS/cash-register web app (FastAPI + Uvicorn + Jinja2, SQLite, server-rendered HTML). The whole product is one process; there are no external services (no Postgres/Redis/etc.).

### Running (dev)
Dependencies are installed into `.venv` by the startup update script. Start the dev server from the repo root:

```
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Then open `http://127.0.0.1:8000/`. `python run_server.py` also works but additionally tries to open a browser (no-op on this headless VM). No login/auth is required in the active app.

### Non-obvious gotchas
- `requirements.txt` is INCOMPLETE. It omits `itsdangerous` (required by Starlette `SessionMiddleware` — the app crashes on import without it) and `reportlab` (required for the `/berichte/*.pdf` endpoints). Always install from `requirements.lock`, which is fully pinned and includes both. The update script uses `requirements.lock` for this reason.
- The active application is `main.py` (the `main:app` object). It defines its own models and uses SQLite at `app/data/app.db`, which is auto-created and pre-seeded with demo data on startup.
- The `app/` package layer (`app/routes`, `app/services`, `app/models`, backed by `db/kassensystem.db`) is NOT wired into `main.py`; don't assume changing it affects the running app.
- No automated test suite and no lint config exist in the repo. "Testing" is manual/HTTP-level against the running server.
- Packaging files (`KassensystemBasic.spec`, `installer.iss`, `*.bat`, `install.ps1`) are Windows-only and not needed for Linux dev.

### Quick end-to-end sanity check
Create a catalog service, then post a sale:

```
curl -X POST http://127.0.0.1:8000/pos/checkout -H "Content-Type: application/json" \
  -d '{"items":[{"type":"service","id":1,"qty":1}],"payment":{"method":"bar","amounts":{"bar":15.00}}}'
```

A successful checkout returns `{"ok": true, ... "sale_id": N}`.
