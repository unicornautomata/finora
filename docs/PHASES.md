# FINORA delivery phases

| # | Scope | Status |
|---|---|---|
| 1 | Project audit and frontend architecture | **Done** (audit document delivered) |
| 2 | FINORA branding and design system | **Done** (this delivery) |
| 3 | Login and authentication interface | Not started. Awaiting owner go-ahead |
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
