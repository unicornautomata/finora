# ERP Phase 1: architecture assessment and database foundation

Programme: turn FINORA into a hierarchical multi-company ERP (10 ERP phases; see `docs/PHASES.md`).
This document is the Phase 1 deliverable: what exists, what must change, the database architecture, and the roadmap.
**Phase 1 delivers the data-integrity foundation. It deliberately does not add screens or HTTP endpoints for it (that is ERP Phase 2).**

## 1. How the audit was done

The attached repository is the source of truth. Reviewed: every migration, the service layer, all HTTP endpoints, the
authentication and role model, the PyQt6 client, the screen definitions, the tests and the existing documents.
Claims below that matter were checked by running code against a real database, not by reading documentation.
Evidence that shaped the plan is in `tests/test_known_gaps.py` (executable) and the findings table in section 2.4.

## 2. Assessment

### 2.1 Exists and works (preserved untouched)
- Single-ledger accounting engine: balanced journals, draft/posted separation, immutable posted journals (database triggers), reversal-based correction, gapless numbering per company and document type, optimistic locking, money as integer cents, trial balance per company.
- FastAPI service layer, token sessions with lockout, three global roles, audit log, master-data CRUD driven by definitions, responsive PyQt6 client with the FINORA design system.
- Safe-by-default SQLite configuration (WAL, foreign keys on, versioned migrations).

### 2.2 Exists only partially
| Area | State before Phase 1 |
|---|---|
| Companies | A flat table (`cocd`, name, currency, chart, tax id). No group, no hierarchy, no status, no legal name. |
| Company scoping of data | Journals and number ranges carry `cocd`. Partners have an optional `cocd`. GL accounts, GL types, charts and document types are global. |
| Audit | Recorded who and what, but not which company. |
| Access control | Global role per user only (`viewer`, `accountant`, `admin`). |

### 2.3 Documented or shown in the menu but not implemented
Everything beyond journals, master data and the trial balance: sales orders, purchasing, inventory, warehouses, manufacturing, BOMs,
projects, banking, fixed assets, budgets, consolidation, intercompany, dashboards, approval workflows, delegated permissions,
change-own-password. They appear as greyed "planned" menu items only. None is claimed as done.

### 2.4 Must be redesigned (findings)
| # | Finding | Evidence | Consequence | Fixed in |
|---|---|---|---|---|
| F1 | A journal for one company can post to an account that belongs to another company's chart. Account validity is checked, chart membership is not. | `test_company_cannot_post_to_an_account_of_another_charts` (strict xfail) | Breaks accounting isolation once companies have different charts | ERP Phase 3 |
| F2 | No endpoint checks which company a user may see. Any signed-in user can read any journal by id and list all journals. | `test_user_without_access_cannot_read_another_companys_journal`, `test_journal_list_only_shows_companies_the_user_may_access` (strict xfails) | Cross-company data leakage as soon as there is more than one company | ERP Phase 2 |
| F3 | GL accounts, partners and document types use a single global key space. | schema | Two companies cannot use the same account code or customer code. The legacy importer already has to rename colliding partner codes | ERP Phases 3 and 4 |
| F4 | Upgrades had no backup and no verification. | `Database.migrate()` before Phase 1 | An unattended upgrade could not be proven safe | **Phase 1 (done)** |
| F5 | The audit trail did not record the company. | schema | Group-level audit impossible | **Phase 1 (done)** |
| F6 | Positional inserts such as `INSERT INTO companies VALUES (...)` break whenever a table gains a column. | one test fixture used it | Any external script written that way breaks after upgrade | Documented; use named columns |

### 2.5 New database entities required
| Entity | Purpose | Phase |
|---|---|---|
| `corporate_groups`; company columns `group_id`, `legal_name`, `status`, `incorporated_on`, `dissolved_on` | group membership and lifecycle | **1 (done)** |
| `company_ownership` (+ views, triggers) | effective-dated legal ownership, percentages, voting | **1 (done)** |
| `company_reporting_lines` | operational reporting, separate from legal ownership | **1 (done)** |
| `company_roles`, `company_role_permissions`, `company_user_access`, `company_access_exclusions` | company-scoped RBAC model | **1 (done: model); enforcement 2** |
| `schema_history` | applied migrations and their backups | **1 (done)** |
| `audit_log.cocd` | company on every audited action | **1 (done)** |
| `organizational_units`, `company_settings` | divisions, branches, per-company configuration | 2 / 3 |
| `coa_templates`, `company_coa`, `consolidation_account_mappings` | per-company charts and group mapping | 3 |
| `intercompany_partners`, intercompany document links, elimination records | intercompany and consolidation | 3 |
| shared master data (`master_shares`), products, categories, units | controlled sharing, catalog | 4 |
| warehouses, locations, inventory, movements | inventory | 5 |
| sales and procurement documents, outlets, channels | trade | 6 |
| BOMs, routings, work centres, production orders | manufacturing | 7 |
| projects, tasks, WBS, budgets | projects | 8 |
| approval workflows | cross-cutting | 2 to 8 |

### 2.6 Existing functionality that could be affected
- Positional `INSERT`/`SELECT *` on `companies` and `audit_log` (F6). The repository was checked: only one test fixture did this and was corrected.
- Server start-up now upgrades an old database automatically (with backup). Hosts see a one-off delay on first start after upgrading.
- The legacy importer is unchanged and verified against the real legacy database; imported companies land in the default group.

### 2.7 Migration risks and mitigations
| Risk | Mitigation (implemented and tested) |
|---|---|
| Data loss or silent change during upgrade | Per-table row counts and content hashes plus per-company debit/credit totals are compared before COMMIT; any difference rolls the migration back |
| Half-applied schema | Each migration and its version bump run in one transaction |
| No way back | Verified backup (SQLite online backup, WAL-safe) before any upgrade of an existing database; `restore` command keeps the post-upgrade file as a safety copy |
| Existing users locked out later | Existing users are given group-wide access matching their current role, ready for when enforcement is switched on |
| Companies created by old clients | A trigger puts them in the default group automatically |
| Future PostgreSQL move | Plain SQL, no SQLite-only features in the service layer; triggers and views will need porting (noted in section 5) |

### 2.8 Implementation sequence and why
Identity and integrity first (Phase 1), then the screens that use it with scoping switched on (Phase 2), then per-company accounting (3) before
any module that posts to it (4 to 8), analytics last (9), hardening throughout and at the end (10). Scoping (2) comes before accounting (3) so
that new accounting tables are born company-scoped.

## 3. Database architecture (as implemented)

### 3.1 Principles
1. **`cocd` stays the company key.** Every existing foreign key keeps working; a group-scoped surrogate is not needed because `cocd` is unique across the installation.
2. **Additive migrations only.** No existing table is dropped or rebuilt.
3. **Effective dating, never overwriting.** Ownership and reporting records are history; the only edits allowed are closing a record earlier or voiding it (with a reason). Deleting is refused.
4. **The database enforces the hard rules**, so a bug or a direct SQL session cannot break them.
5. **Basis points** (integer, 10000 = 100.00%) for ownership and voting.

### 3.2 Ownership rules and where each is enforced
| Rule | Enforced by |
|---|---|
| No company owns itself | CHECK constraint |
| No circular ownership at any depth, at any date | trigger over a recursive view; time-aware (history in opposite directions is legal) |
| Total equity of a company at any date at most 100% | trigger (checks every date inside the new period) |
| Total voting control at any date at most 100% | trigger |
| Owner and owned company in the same corporate group | trigger; `move_company_to_group` also refuses to split existing links |
| Ownership history is never rewritten or deleted | triggers (close earlier or void only) |
| Multiple owners (joint ventures) and indirect ownership | supported; `effective_ownership_bp` sums every path |
| Legal ownership separate from operational reporting | separate table with its own single-parent and no-cycle rules |
| Unlimited nesting | verified with a 150-level chain and a 149-link loop that is still rejected |

### 3.3 Authorization model (implemented as rules, not yet enforced)
- A **grant** gives one user one role over a whole corporate group, or over one company.
- **Nothing is inherited implicitly.** A company grant covers subsidiaries only when `include_descendants` is set, and a grant can list **exclusions** (a company and everything below it).
- Grants **expire**, start later, and can be revoked; they cannot be edited (revoke and re-grant), and every change is audited with the company.
- Descendants are resolved **as of the date asked**, so a sold subsidiary leaves a parent's scope on the sale date.
- 13 roles (Group Administrator, Group Finance Director, Group Accountant, Company Administrator, Company Finance Manager, Accountant, Procurement, Warehouse, Production, Sales and Project Managers, Auditor, Viewer) with a module-by-action matrix. Read-only roles are verified to hold only `read`.
- **No silent administrator bypass**: a platform administrator needs an explicit grant to work inside a company.
- `finora/server/access.py` resolves and checks all of this. **It is not called by the HTTP endpoints yet** (finding F2); that is the first job of ERP Phase 2.

### 3.4 Pattern for company-specific data in later phases
Every company-owned table carries `cocd`. Parent tables expose `UNIQUE (cocd, id)`; children reference `(cocd, parent_id)` with a **composite foreign key**,
so a record of company A can never point at a record of company B. Controlled sharing uses an explicit share table, never a silent global key.
Consolidation writes only to its own tables and never to a company's statutory books.

### 3.5 Upgrade and recovery procedure
See the README section "Upgrading an existing installation". In short: stop FINORA, copy the database as a precaution, start the new version (it makes a verified backup and upgrades),
run `python -m finora.server.migrate check`, and if anything is wrong use `restore`.

## 4. Roadmap (ERP phases 2 to 10)
| Phase | Scope | Depends on from Phase 1 | Exit criteria |
|---|---|---|---|
| 2 Corporate group management | API and screens for groups, companies, ownership, reporting lines, hierarchy tree and table; company context selector; **server-side company scoping on every endpoint** | schema, `corporate.py`, `access.py` | F2 tests flip to passing; no endpoint returns data outside the user's companies |
| 3 Multi-company accounting | per-company charts and GL, chart templates, consolidation mappings, intercompany, consolidated reports | company-scoped access, composite FK pattern | F1 test flips to passing; consolidated trial balance reconciles to the sum of company books plus eliminations |
| 4 Master data | shared customers, vendors, products, categories, units | `master_shares` design, scoping | no duplicate shared records; per-company codes |
| 5 Inventory | warehouses, locations, stock, valuation, transfers | scoping | transfers always have matching issue and receipt |
| 6 Sales and procurement | quotations to invoices, requisitions to payments | masters, inventory | documents tied to company; AR/AP post to the right books |
| 7 Manufacturing | BOMs, routings, production orders | inventory | material consumption and costs reconcile |
| 8 Projects | WBS, budgets, costs | accounting | project cost equals posted cost |
| 9 Corporate intelligence | group and company dashboards, analytics | all data | every figure traceable to records |
| 10 Integration, security, readiness | full security, performance and migration testing, packaging | everything | evidence for each claim; no claim without a passing test |

## 5. Limitations and honest status
- Phase 1 has **no UI and no HTTP endpoints** for corporate groups. The model is tested at the service and database level only.
- **Company access is not enforced yet**: today any signed-in user can still reach every company (F2). Do not use this version for mutually distrusting companies.
- The posting guard for chart membership does not exist yet (F1).
- Concurrency is verified for ownership changes (two writers cannot create a cycle) and posting numbers; load testing is a Phase 10 item.
- The triggers and recursive views are SQLite syntax; porting to PostgreSQL is straightforward but is real work, scheduled with the Phase 10 readiness review.
- Tested on Linux with SQLite 3.37+; the Windows 10/11 target must be re-verified in Phase 10.
