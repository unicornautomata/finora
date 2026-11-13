# FINORA – Product and engineering decisions

These decisions are binding for every development phase. Change one only by editing this file
and recording why.

Recorded: 2026-11-11 (before Phase 2). Source: product owner.

## 1. Dashboard data (affects Phase 5)

The dashboard uses **only data the current database and API already support**:

- Trial Balance totals, total debit and total credit
- Journal entry counts, and counts of draft, posted and reversed journals
- Recent transactions, where the existing API supports it

**Not allowed yet:** an account-category column, any schema change, or figures that need
account classification (revenue, expense, assets, liabilities). That enhancement is a possible
future phase, after its accounting implications are reviewed. No mock or placeholder numbers,
ever; every figure must be traceable to an API response.

## 2. Product and package name: `finora`

*Amended 2026-11-11: the product owner asked for everything to be renamed to FINORA, which supersedes the
earlier "keep `ledger`" decision. The rename was done in one controlled step with every import, test, script
and document updated together.*

- The Python package is **`finora`** (`finora.server`, `finora.client`). Project folder and delivery file: `finora` / `finora.zip`.
- Start commands: `python -m finora.client`, `python -m finora.server`. Default database file: `finora.db`.
- Environment variables: `FINORA_ADMIN_PASSWORD`, `FINORA_CORS_ORIGINS`, `FINORA_FONT`. The old `LEDGER_*` names are no longer read.
- **FINORA** is the official product name in the UI, login screen, application and window titles, branding, documentation and reports.
- The word "ledger" is still used where it means the accounting concept (for example "post to the ledger"), not the product.

## 3. Colours

Approved palette (implemented in `finora/client/design/tokens.py`, enforced by `tests/test_design.py`):

| Role | Hex |
|---|---|
| Primary navy | `#102B3A` |
| Secondary teal | `#137C78` |
| Accent mint | `#17A398` |
| Background | `#F3F6F8` |
| Card background | `#FFFFFF` |
| Primary text | `#243E4A` |
| Secondary text | `#71848D` |
| Borders | `#E0E7EA` (decorative dividers; form controls use the derived `border_strong`, 3:1) |
| Success | `#16A36A` |
| Warning | `#E9A23B` |
| Danger | `#D9534F` |
| Information | `#2684C7` |

**Usage rules that follow from measured contrast (WCAG AA = 4.5:1 for small text):**

- Primary buttons: teal with white text (5.02:1).
- Mint is an accent only (focus, active-item edge on the navy sidebar, charts). White on mint is 3.12:1, so never put small text on mint.
- Secondary text `#71848D` is 3.90:1 on white and 3.59:1 on the page background. It is kept exactly as approved but **only for hints, captions, placeholders and disabled text**. Meaningful small text (form labels, table headers, KPI labels) uses the derived token `text2_strong`, the same hue darkened just enough to pass.
- Status colours are never used as solid fills carrying text, except success and warning with navy text. Danger and info cannot reach AA with either white or navy text, so no text-on-fill token exists for them.
- Status chips use a soft tint of the status colour with a computed `*_ink` text colour that passes 4.5:1.
- Dark mode is derived from the same palette. It is provisional until the owner supplies dark values.

## 4. Typography

*Amended 2026-11-11 by the product owner's Phase 2 brief: "Inter where available, Segoe UI as fallback".
This supersedes the earlier "Segoe UI default" wording. Inter is still **not bundled**.*

- The app uses **Inter if it is installed** on the machine, otherwise **Segoe UI** (the Windows default), otherwise the system font. On a Windows 10/11 PC without Inter the result is Segoe UI, as originally decided.
- To force a font: `design.set_font_family("Segoe UI")` or the `FINORA_FONT` environment variable. No screen needs to change.
- Bundling Inter is a separate future decision (it needs the font files and the SIL OFL licence shipped with the app).
- Type hierarchy (px): caption 11, small/labels 12, body 13, h3 section 15, h2 title 18, h1 page 22 (bold).

## 5. Platforms

- **First official release: Windows 10 and Windows 11.** Python 3.10 or newer on Windows (older bundled SQLite lacks features the server uses; the server now fails fast with a clear message).
- The architecture stays cross-platform where practical: PyQt6 and Python only, **no Windows-specific UI dependencies** (guarded by a test that scans the client for `windll`, `winreg` and `win32*`).
- Do not compromise the Windows release for premature macOS or Linux support. Separate macOS and Linux compatibility testing is a future phase.

## Standing guardrails (all phases)

- The existing API, services, database, authentication and accounting rules remain the source of truth.
- Keep PyQt6 + FastAPI + SQLite. No migration to React, Electron or another framework.
- Do not change database schemas or remove existing functionality.
- No mock data in accounting workflows.
- Backend additions only if additive, read-only and approved first.
