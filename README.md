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

Recorded results for the current delivery: `docs/TEST_RESULTS_ERP_PHASE1.txt`.

    pytest tests -q
    QT_QPA_PLATFORM=offscreen python tests/smoke_ui.py   # drives the real UI against a live server

## Install

Requires Python 3.10 or newer (Windows 10/11 is the first release target; older Python ships an SQLite too old for the server).

    pip install -r requirements.txt
    python -m finora.client --host        # desktop app that also hosts the server

## Upgrading an existing installation (multi-company foundation, schema version 2)

Nothing is deleted or renumbered: existing companies join a default corporate group, existing users keep their reach, journals and balances are untouched.

1. Close FINORA on every computer that uses the database. Copy the `.db` file somewhere safe as an extra precaution.
2. Preview: `python -m finora.server.migrate upgrade --db finora.db --dry-run`
3. Start the new version as usual (or run `python -m finora.server.migrate upgrade --db finora.db`). It first writes a verified backup next to the database
   (`finora.db.bak-v1-<time>`), then upgrades in a single transaction and compares every existing table and every company's debit/credit totals
   before committing. If anything differs, the upgrade is rolled back and your data is unchanged.
4. Verify: `python -m finora.server.migrate check --db finora.db` and `python -m finora.server.migrate status --db finora.db`.
5. To go back: stop FINORA, then `python -m finora.server.migrate restore --db finora.db --backup finora.db.bak-v1-<time>`.
   The post-upgrade file is kept as `finora.db.before-restore-<time>`.

New code must use named columns in `INSERT` statements (for example `INSERT INTO companies(cocd, name, ...)`); positional inserts break when tables gain columns.

## Documentation

- `docs/architecture/ERP_PHASE1_ASSESSMENT.md`: architecture assessment, database design, roadmap, known limitations
- `docs/IMPLEMENTATION_STATUS.md`: honest status of every module

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
