# Ledger (rewrite)

One service core, an HTTP API on top of it, and a PyQt6 desktop app that is both a client
and (optionally) the server host.

```
PyQt6 app ──HTTP──▶  FastAPI  ──▶  services.py (all business rules)  ──▶  SQLite (WAL)
future web app ─HTTP─▶ (same API)
```

## Run

    pip install -r requirements.txt

    python -m ledger.client --host     # desktop app that also hosts the server (multi-user)
    python -m ledger.client            # desktop app that connects to a server elsewhere
    python -m ledger.server --db ledger.db --host 0.0.0.0 --port 8000   # headless server

First start creates `admin` with a random password (shown once). Set `LEDGER_ADMIN_PASSWORD`
to choose it. Interactive API docs: `http://<server>:8000/docs`.
Allow a future web app's origin with `LEDGER_CORS_ORIGINS=https://app.example.com`.

## Import your old master data

    python -m ledger.server.import_legacy old/accountingdb.db --db ledger.db

## Tests

    pytest tests -q
    QT_QPA_PLATFORM=offscreen python tests/smoke_ui.py   # drives the real UI against a live server

## Layout

    ledger/server/migrations/   schema + integrity triggers (versioned)
    ledger/server/services.py   posting, numbering, reversal, auth, master data, reports
    ledger/server/definitions.py  screens/entities published at GET /meta (client and web render from it)
    ledger/server/api.py        HTTP API        host.py  runs it inside the PyQt6 process
    ledger/client/              theme, shell (sidebar/toolbar/tabs), document + master + report screens

## Key rules
- Money is integer cents, quantities integer thousandths; the API uses decimal strings.
- Journals are drafts until posted. Numbers are assigned at posting (gapless, per company and type).
- Posted journals are immutable (database triggers); corrections are reversal entries.
- Debits must equal credits, checked in the service and again by a database trigger.
- Drafts use optimistic locking (`version`), so two users cannot silently overwrite each other.
- Roles: viewer (read), accountant (read/write/post), admin (+ users).

## Before using over a network
The server speaks plain HTTP. Put it behind a TLS reverse proxy (or a VPN) before exposing it
beyond a trusted LAN. SQLite in WAL mode suits a small team; for many concurrent writers move
`db.py` to PostgreSQL (the service layer does not change).
