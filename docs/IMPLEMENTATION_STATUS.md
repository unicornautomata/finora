# Implementation status by module

Status words: **Working** = connected to real data and tested. **Foundation** = database and service layer tested, no screen or endpoint yet.
**Prototype** = works for a single company only. **Not started**. A menu item or screen alone never counts as complete.

| Navigation group | Module | Status | Notes |
|---|---|---|---|
| Corporate Management | Corporate groups, ownership, reporting lines | **Foundation** (ERP Phase 1) | schema, rules and queries tested; API and screens in ERP Phase 2 |
| Corporate Management | Company hierarchy / ownership structure views | Not started | ERP Phase 2 |
| Corporate Management | Companies | Prototype | flat master-data screen; new columns (group, status, legal name) exist but are not editable in the UI yet |
| Corporate Management | Group dashboard | Not started | ERP Phase 9 |
| Finance | Journals (Purchases, Sales, CDJ, CRJ, General) | Prototype | full lifecycle works for one company |
| Finance | Chart of Accounts, GL Types, GL Accounts | Prototype | global, not per company (finding F1/F3), ERP Phase 3 |
| Finance | Trial Balance | Working (per company) | consolidated version in ERP Phase 3 |
| Finance | Accounts payable/receivable, banking, fixed assets, budgets, consolidation, intercompany | Not started | ERP Phase 3 and later |
| Sales and CRM | Customers | Prototype | global key space |
| Sales and CRM | Orders, quotations, invoices, channels, outlets | Not started | ERP Phase 6 |
| Procurement | Suppliers | Prototype | global key space |
| Procurement | Requisitions to goods receipts | Not started | ERP Phase 6 |
| Inventory and Warehousing | Everything | Not started | ERP Phase 5 |
| Manufacturing | Everything | Not started | ERP Phase 7 |
| Projects | Everything | Not started | ERP Phase 8 |
| Administration | Users | Working | global roles |
| Administration | Roles and permissions, company access | **Foundation** (ERP Phase 1) | rules and role matrix tested; not enforced by endpoints; screens in ERP Phase 2 |
| Administration | Approval workflows | Not started | ERP Phases 2 to 8 |
| Administration | Audit logs | Foundation | company recorded on audited actions; no viewer yet |
| Platform | Safe migrations, backup and restore | **Working** (ERP Phase 1) | tested against an old-format database |
| Platform | Sign-in, session expiry, status bar, design system | Working | UI Phases 1 to 3 |
