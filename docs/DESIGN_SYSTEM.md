# FINORA design system

Code: `finora/client/design/` (tokens, stylesheet, icons, assets, brand) and `finora/client/components/`
(shared widgets). Decisions behind it: `docs/DECISIONS.md`. Logo files: `docs/brand/`.

## Rules

1. **No hex colours outside `design/`.** Screens get their look from the stylesheet through object names and
   properties (`kind`, `size`, `onDark`). A test fails the build if a hex colour appears elsewhere.
2. **Build with components:** `Button`, `Card`, `StatusChip`, `ResponsiveFormGrid`, `EmptyStateStack`,
   `ReportHeader`, `KpiTile`, `PageHeader`, `BrandHeader`, and `dialogs.confirm/info/warning/error`.
   Raw `QPushButton` and `QMessageBox` are not allowed in screens (tested).
3. **Icons come from `design.icons`** (SVG, recoloured per theme). No `QStyle` icons, no icon fonts.
4. **Never call `setStyleSheet` with colours.** Add a token and a QSS rule.
5. **Spacing uses `design.SPACE`** (xs 4, sm 8, md 12, lg 16, xl 24, xxl 32) via `page_margins()` and the components.
6. **Every screen must resize:** wrap page content in `scroll_page()`, use `ResponsiveFormGrid` for forms, give tables a stretch column.

## Brand

| Item | Value |
|---|---|
| Name | FINORA |
| Descriptor | Financial Management System |
| Tagline | Clarity in every transaction |
| Mark | Ledger page with ruled lines and a **teal checkmark** on a navy tile |
| Files | `docs/brand/finora-mark*.svg/png`, `finora-logo-horizontal*.svg/png`, `finora.ico`; regenerate with `python tools/export_brand_assets.py` |
| Where it appears | Sign-in, sidebar (with tagline), window title (`<screen> — FINORA`), window and taskbar icon, every dialog, every report header, status bar, API docs title |

## Typography hierarchy

| Role | Object name | Size / weight |
|---|---|---|
| Page title | `title` | 22 bold |
| Panel / dialog title | `h2` | 18 semibold |
| Section heading | `h3` | 15 semibold |
| Body | (default) | 13 |
| Field label | `fieldLabel` | 12 medium, `text2_strong` |
| Hint / caption | `muted`, `caption` | 13 / 11, `text2` |

Font: Inter if installed, else Segoe UI (docs/DECISIONS.md section 4).

## Controls

- **Buttons** (`Button(text, kind, icon, size)`): `primary` (teal, one per view), `secondary` (default), `danger`, `ghost`; sizes `md`, `sm`. Icons recolour by kind and by theme. Visible keyboard focus ring.
- **Inputs:** 1px outline (`border_strong`, 3:1 against the surface), 2px primary focus ring (padding compensates so nothing shifts), hover state, read-only look, `invalid` property for errors, chevron dropdowns, custom checkbox.
- **Tables:** `configure_table()` gives header style, 36px rows, zebra, hover and selection colours, no vertical grid. Numbers right-aligned.
- **Cards and panels:** `Card(title)`; `ReportHeader` for reports.
- **Status badges:** `StatusChip(text, kind)` with `success | warning | danger | info | neutral`. Soft tint plus computed readable ink; always carries words.
- **Dialogs:** `dialogs.confirm(parent, text, title, confirm_text=, cancel_text=, danger=, detail=)`, plus `info`, `warning`, `error`. Branded icon, titled, primary or danger confirm button, safe default on destructive actions.
- **Tooltips:** navy, set on every toolbar action and icon-only control.

## Responsive behaviour

- Minimum window 900x600. Below 1100px wide the sidebar hides and the toolbar becomes icon-only (tooltips remain).
- Forms flow into 3, 2 or 1 columns (880 / 560px breakpoints on the form's own width).
- Pages scroll instead of squashing; master-data screens use a splitter with a scrolling form; tabs scroll.

## Tokens (`design.palette()`)

`bg, surface, border, border_strong, text, text2, text2_strong, primary, primary_hover, primary_pressed, on_primary,
accent, link, hover, selection, row_alt, readonly, sidebar_*`, and for each of `success, warning, danger, info`:
the colour, `<kind>_soft` and `<kind>_ink`. Light and dark define identical keys. Scales: `SPACE`, `RADIUS`, `TYPE`.

    design.apply_theme(app, "light")     # or "dark"; rebuilds stylesheet, font and icon cache
    design.bus.changed.connect(fn)       # fires after a theme change (icons recolour)

## Accessibility notes

Measured against WCAG AA. Approved secondary text `#71848D` is 3.90:1, so it is for hints only; labels use
`text2_strong`. Mint on white is 3.12:1, so mint is an accent, never small text. Danger and info cannot carry
text on a solid fill, so they appear as tinted chips or accent edges. `tests/test_design.py` enforces all of this.

## Not built yet (later phases)

`Toast`, loading skeletons/spinner, sortable and paged `DataTable`, inline field-error messages, command palette,
sidebar selection sync, remembered theme and window layout.
