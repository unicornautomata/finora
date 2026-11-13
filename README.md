# FINORA — Financial Management System

*Clarity in every transaction.*  Python package: `finora` (`finora.server`, `finora.client`).

One service core, an HTTP API on top of it, and a PyQt6 desktop app that is both a client
and (optionally) the server host.

```
PyQt6 app ──HTTP──▶  FastAPI  ──▶  services.py (all business rules)  ──▶  SQLite (WAL)
future web app ─HTTP─▶ (same API)
```

## Run

    pip install -r requirements.txt

    python -m finora.client --host     # desktop app that also hosts the server (multi-user)
    python -m finora.client            # desktop app that connects to a server elsewhere
    python -m finora.server --db finora.db --host 0.0.0.0 --port 8000   # headless server

First start creates `admin` with a random password (shown once). Set `FINORA_ADMIN_PASSWORD`
to choose it. Interactive API docs: `http://<server>:8000/docs`.
Allow a future web app's origin with `FINORA_CORS_ORIGINS=https://app.example.com`.

## Import your old master data

    python -m finora.server.import_legacy old/accountingdb.db --db finora.db

## Tests

    pytest tests -q
    QT_QPA_PLATFORM=offscreen python tests/smoke_ui.py   # drives the real UI against a live server

## Documentation

- `docs/DECISIONS.md`: binding product and engineering decisions (read first)
- `docs/DESIGN_SYSTEM.md`: tokens, components, brand, rules for building screens
- `docs/brand/`: FINORA logo files (SVG, PNG, ICO)
- `docs/PHASES.md`: the 12-phase plan and status

## Platform

First release targets **Windows 10 and 11** (Python 3.10+). The code uses PyQt6 and standard Python only and is kept cross-platform where practical; macOS and Linux get separate testing later.

## Layout

    finora/server/migrations/   schema + integrity triggers (versioned)
    finora/server/services.py   posting, numbering, reversal, auth, master data, reports
    finora/server/definitions.py  screens/entities published at GET /meta (client and web render from it)
    finora/server/api.py        HTTP API        host.py  runs it inside the PyQt6 process
    finora/client/design/       FINORA tokens, stylesheet, icons, brand
    finora/client/components/   shared widgets (Card, StatusChip, EmptyStateStack, KpiTile, ...)
    finora/client/              shell (sidebar/toolbar/tabs), document + master + report screens

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
