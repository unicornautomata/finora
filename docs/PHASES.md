# FINORA delivery phases

Two tracks run in parallel and are numbered separately.

## Track A: UI phases (frontend design)

| # | Scope | Status |
|---|---|---|
| 1 | Project audit and frontend architecture | **Done** (audit document delivered) |
| 2 | FINORA branding and design system | **Done** (this delivery) |
| 3 | Login and authentication interface | **Done** (sign-in dialog, inline errors, lockout wording, host/connect modes, session-expiry re-sign-in). Change-own-password still needs an approved server endpoint |
| 4 | Main application shell and navigation | Not started |
| 5 | Executive financial dashboard (data limits: DECISIONS.md section 1) | Not started |
| 6 | Journal management interfaces | Not started |
| 7 | Chart of Accounts and GL management | Not started |
| 8 | Customers, vendors and company management | Not started |
| 9 | Trial Balance and financial reporting | Not started |
| 10 | Administration and user management | Not started |
| 11 | Notifications, usability and advanced UX | Not started |
| 12 | Integration, QA and production polish | Not started |

Project rename to `finora` (package, folder, zip, commands, env vars) done 2026-11-11; see DECISIONS.md section 2.

Each phase starts only when the owner says so. Every phase must keep `pytest tests -q` and
`tests/smoke_ui.py` green and follow `docs/DECISIONS.md`.

## Phase 2 deliverables (revised after the branding brief)

- Approved palette and status colours as tokens, light and dark; derived accessible tints, inks and input borders
- Typography hierarchy; Inter if installed, Segoe UI fallback (not bundled)
- New logo: ledger page with a teal checkmark; SVG/PNG/ICO files in `docs/brand/`
- Standardized `Button` (primary, secondary, danger, ghost), modern inputs, chevron dropdowns, checkbox, table styling, tooltips
- Branded dialogs (`dialogs.confirm/info/warning/error`), cards, status badges, report header
- Spacing tokens and `page_margins()`; responsive layout (scrolling pages, 3/2/1-column forms, collapsing sidebar, icon-only toolbar)
- Branding on sign-in, sidebar, window title and icon, dialogs, reports
- Lookup cache bug fixed, with regression tests
- 30 automated tests plus a live UI smoke test (including responsive behaviour)

## Track B: ERP phases (hierarchical multi-company ERP)

| # | Scope | Status |
|---|---|---|
| 1 | Architecture and database foundation | **Done** (this delivery): assessment, corporate groups, ownership, reporting lines, access model, safe migrations. No UI or endpoints yet |
| 2 | Corporate group management (API, screens, context selector, server-side company scoping) | Not started |
| 3 | Multi-company accounting (per-company charts, intercompany, consolidation) | Not started |
| 4 | Master data management | Not started |
| 5 | Inventory and warehousing | Not started |
| 6 | Sales and procurement | Not started |
| 7 | Manufacturing | Not started |
| 8 | Projects and business operations | Not started |
| 9 | Corporate intelligence | Not started |
| 10 | Integration, security and production readiness | Not started |

Details: `docs/architecture/ERP_PHASE1_ASSESSMENT.md` and `docs/IMPLEMENTATION_STATUS.md`.
