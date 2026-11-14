-- 002: multi-company foundation (ERP Phase 1).
-- ADDITIVE ONLY: no existing table is dropped or rebuilt, and no existing row is changed except for
-- backfilling the new group/legal-name columns. The migration runner snapshots and verifies every
-- pre-existing accounting table before this is committed (see finora/server/migrate.py).

-- ===== applied-migration history (also records the pre-upgrade backup path) =====
CREATE TABLE schema_history (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    backup_path TEXT
);
INSERT INTO schema_history(version, name, applied_at) VALUES
    (1, 'init (recorded retroactively)', strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    (2, 'multicompany_foundation', strftime('%Y-%m-%dT%H:%M:%SZ','now'));

-- ===== corporate groups =====
CREATE TABLE corporate_groups (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ===== companies: identity stays the existing `cocd` key; everything that references it keeps working =====
ALTER TABLE companies ADD COLUMN group_id INTEGER REFERENCES corporate_groups(id);
ALTER TABLE companies ADD COLUMN legal_name TEXT;
ALTER TABLE companies ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE companies ADD COLUMN incorporated_on TEXT;
ALTER TABLE companies ADD COLUMN dissolved_on TEXT;
CREATE INDEX ix_companies_group ON companies(group_id);

CREATE TRIGGER trg_company_status_ins BEFORE INSERT ON companies
WHEN NEW.status NOT IN ('active','inactive','dissolved','acquired')
BEGIN SELECT RAISE(ABORT, 'invalid company status'); END;
CREATE TRIGGER trg_company_status_upd BEFORE UPDATE OF status ON companies
WHEN NEW.status NOT IN ('active','inactive','dissolved','acquired')
BEGIN SELECT RAISE(ABORT, 'invalid company status'); END;
CREATE TRIGGER trg_company_dates_ins BEFORE INSERT ON companies
WHEN (NEW.incorporated_on IS NOT NULL AND date(NEW.incorporated_on) IS NOT NEW.incorporated_on)
  OR (NEW.dissolved_on IS NOT NULL AND date(NEW.dissolved_on) IS NOT NEW.dissolved_on)
  OR (NEW.incorporated_on IS NOT NULL AND NEW.dissolved_on IS NOT NULL AND NEW.dissolved_on < NEW.incorporated_on)
BEGIN SELECT RAISE(ABORT, 'invalid company dates'); END;
CREATE TRIGGER trg_company_dates_upd BEFORE UPDATE OF incorporated_on, dissolved_on ON companies
WHEN (NEW.incorporated_on IS NOT NULL AND date(NEW.incorporated_on) IS NOT NEW.incorporated_on)
  OR (NEW.dissolved_on IS NOT NULL AND date(NEW.dissolved_on) IS NOT NEW.dissolved_on)
  OR (NEW.incorporated_on IS NOT NULL AND NEW.dissolved_on IS NOT NULL AND NEW.dissolved_on < NEW.incorporated_on)
BEGIN SELECT RAISE(ABORT, 'invalid company dates'); END;

-- Existing installations: every existing company joins one default group (nothing is deleted or renumbered).
INSERT INTO corporate_groups(code, name, description)
SELECT 'DEFAULT', 'Default corporate group', 'Created by the multi-company migration for the companies that already existed'
WHERE EXISTS (SELECT 1 FROM companies);
UPDATE companies SET group_id = (SELECT id FROM corporate_groups WHERE code = 'DEFAULT'), legal_name = name
WHERE group_id IS NULL;

-- Backward compatibility: a company created through the existing API (no group given) lands in the default group.
CREATE TRIGGER trg_company_default_group AFTER INSERT ON companies
WHEN NEW.group_id IS NULL
BEGIN
    INSERT OR IGNORE INTO corporate_groups(code, name, description)
    VALUES ('DEFAULT', 'Default corporate group', 'Assigned automatically to companies created without a group');
    UPDATE companies SET group_id = (SELECT id FROM corporate_groups WHERE code = 'DEFAULT'),
                         legal_name = COALESCE(legal_name, name)
    WHERE cocd = NEW.cocd;
END;

-- ===== legal ownership: effective-dated, history is never rewritten =====
-- Percentages are integer basis points (10000 = 100.00%).
CREATE TABLE company_ownership (
    id INTEGER PRIMARY KEY,
    parent_company TEXT NOT NULL REFERENCES companies(cocd),
    child_company  TEXT NOT NULL REFERENCES companies(cocd),
    ownership_bp INTEGER NOT NULL CHECK (ownership_bp BETWEEN 0 AND 10000),
    voting_bp    INTEGER NOT NULL CHECK (voting_bp BETWEEN 0 AND 10000),
    relationship TEXT NOT NULL DEFAULT 'subsidiary'
        CHECK (relationship IN ('subsidiary','associate','joint_venture','investment')),
    effective_from TEXT NOT NULL CHECK (date(effective_from) = effective_from),
    effective_to   TEXT CHECK (effective_to IS NULL OR date(effective_to) = effective_to),
    acquisition_date TEXT CHECK (acquisition_date IS NULL OR date(acquisition_date) = acquisition_date),
    note TEXT,
    recorded_by TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    voided_at TEXT, voided_by TEXT, void_reason TEXT,
    CHECK (parent_company <> child_company),
    CHECK (ownership_bp > 0 OR voting_bp > 0),
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    CHECK ((voided_at IS NULL) = (voided_by IS NULL))
);
CREATE UNIQUE INDEX ux_own_key ON company_ownership(parent_company, child_company, effective_from) WHERE voided_at IS NULL;
CREATE INDEX ix_own_child ON company_ownership(child_company);
CREATE INDEX ix_own_parent ON company_ownership(parent_company);

CREATE VIEW v_ownership_active AS SELECT * FROM company_ownership WHERE voided_at IS NULL;

-- Every ancestor -> descendant path with the period in which the whole path existed. Set semantics (UNION)
-- make the recursion terminate at any depth, so nesting is unlimited.
CREATE VIEW v_ownership_paths AS
WITH RECURSIVE p(anc, dsc, f, t) AS (
    SELECT parent_company, child_company, effective_from, effective_to FROM company_ownership WHERE voided_at IS NULL
    UNION
    SELECT p.anc, o.child_company, MAX(p.f, o.effective_from),
           CASE WHEN p.t IS NULL THEN o.effective_to WHEN o.effective_to IS NULL THEN p.t ELSE MIN(p.t, o.effective_to) END
    FROM p JOIN company_ownership o ON o.parent_company = p.dsc AND o.voided_at IS NULL
    WHERE MAX(p.f, o.effective_from) <
          COALESCE(CASE WHEN p.t IS NULL THEN o.effective_to WHEN o.effective_to IS NULL THEN p.t ELSE MIN(p.t, o.effective_to) END, '9999-12-31')
)
SELECT anc, dsc, f, t FROM p;

CREATE TRIGGER trg_own_same_group BEFORE INSERT ON company_ownership
WHEN (SELECT group_id FROM companies WHERE cocd = NEW.parent_company)
     IS NOT (SELECT group_id FROM companies WHERE cocd = NEW.child_company)
BEGIN SELECT RAISE(ABORT, 'owner and owned company must belong to the same corporate group'); END;

CREATE TRIGGER trg_own_no_cycle BEFORE INSERT ON company_ownership
WHEN NEW.voided_at IS NULL AND EXISTS (
    SELECT 1 FROM v_ownership_paths v
    WHERE v.anc = NEW.child_company AND v.dsc = NEW.parent_company
      AND v.f < COALESCE(NEW.effective_to, '9999-12-31') AND NEW.effective_from < COALESCE(v.t, '9999-12-31'))
BEGIN SELECT RAISE(ABORT, 'ownership would create a circular structure'); END;

CREATE TRIGGER trg_own_equity_total BEFORE INSERT ON company_ownership
WHEN NEW.voided_at IS NULL AND EXISTS (
    SELECT 1 FROM (
        SELECT NEW.effective_from AS d
        UNION
        SELECT o.effective_from FROM v_ownership_active o
         WHERE o.child_company = NEW.child_company AND o.effective_from > NEW.effective_from
           AND o.effective_from < COALESCE(NEW.effective_to, '9999-12-31')
    ) pts
    WHERE NEW.ownership_bp + (SELECT COALESCE(SUM(o.ownership_bp), 0) FROM v_ownership_active o
            WHERE o.child_company = NEW.child_company AND o.effective_from <= pts.d
              AND COALESCE(o.effective_to, '9999-12-31') > pts.d) > 10000)
BEGIN SELECT RAISE(ABORT, 'total ownership of a company cannot exceed 100% at any date'); END;

CREATE TRIGGER trg_own_voting_total BEFORE INSERT ON company_ownership
WHEN NEW.voided_at IS NULL AND EXISTS (
    SELECT 1 FROM (
        SELECT NEW.effective_from AS d
        UNION
        SELECT o.effective_from FROM v_ownership_active o
         WHERE o.child_company = NEW.child_company AND o.effective_from > NEW.effective_from
           AND o.effective_from < COALESCE(NEW.effective_to, '9999-12-31')
    ) pts
    WHERE NEW.voting_bp + (SELECT COALESCE(SUM(o.voting_bp), 0) FROM v_ownership_active o
            WHERE o.child_company = NEW.child_company AND o.effective_from <= pts.d
              AND COALESCE(o.effective_to, '9999-12-31') > pts.d) > 10000)
BEGIN SELECT RAISE(ABORT, 'total voting control of a company cannot exceed 100% at any date'); END;

-- History protection: a record may only be closed earlier or voided (once); never rewritten or deleted.
CREATE TRIGGER trg_own_history BEFORE UPDATE ON company_ownership
WHEN NEW.parent_company IS NOT OLD.parent_company OR NEW.child_company IS NOT OLD.child_company
  OR NEW.ownership_bp IS NOT OLD.ownership_bp OR NEW.voting_bp IS NOT OLD.voting_bp
  OR NEW.relationship IS NOT OLD.relationship OR NEW.effective_from IS NOT OLD.effective_from
  OR NEW.recorded_by IS NOT OLD.recorded_by OR NEW.recorded_at IS NOT OLD.recorded_at
  OR (NEW.effective_to IS NOT OLD.effective_to
      AND (NEW.effective_to IS NULL OR (OLD.effective_to IS NOT NULL AND NEW.effective_to > OLD.effective_to)))
  OR (OLD.voided_at IS NOT NULL AND (NEW.voided_at IS NOT OLD.voided_at OR NEW.voided_by IS NOT OLD.voided_by))
BEGIN SELECT RAISE(ABORT, 'ownership records are history: they can only be closed earlier or voided, never rewritten'); END;
CREATE TRIGGER trg_own_no_delete BEFORE DELETE ON company_ownership
BEGIN SELECT RAISE(ABORT, 'ownership history cannot be deleted; void the record instead'); END;

-- ===== operational reporting lines (separate from legal ownership) =====
CREATE TABLE company_reporting_lines (
    id INTEGER PRIMARY KEY,
    company    TEXT NOT NULL REFERENCES companies(cocd),
    reports_to TEXT NOT NULL REFERENCES companies(cocd),
    effective_from TEXT NOT NULL CHECK (date(effective_from) = effective_from),
    effective_to   TEXT CHECK (effective_to IS NULL OR date(effective_to) = effective_to),
    note TEXT,
    recorded_by TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    voided_at TEXT, voided_by TEXT, void_reason TEXT,
    CHECK (company <> reports_to),
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    CHECK ((voided_at IS NULL) = (voided_by IS NULL))
);
CREATE INDEX ix_rep_company ON company_reporting_lines(company);

CREATE VIEW v_reporting_paths AS
WITH RECURSIVE p(anc, dsc, f, t) AS (
    SELECT reports_to, company, effective_from, effective_to FROM company_reporting_lines WHERE voided_at IS NULL
    UNION
    SELECT p.anc, o.company, MAX(p.f, o.effective_from),
           CASE WHEN p.t IS NULL THEN o.effective_to WHEN o.effective_to IS NULL THEN p.t ELSE MIN(p.t, o.effective_to) END
    FROM p JOIN company_reporting_lines o ON o.reports_to = p.dsc AND o.voided_at IS NULL
    WHERE MAX(p.f, o.effective_from) <
          COALESCE(CASE WHEN p.t IS NULL THEN o.effective_to WHEN o.effective_to IS NULL THEN p.t ELSE MIN(p.t, o.effective_to) END, '9999-12-31')
)
SELECT anc, dsc, f, t FROM p;

CREATE TRIGGER trg_rep_same_group BEFORE INSERT ON company_reporting_lines
WHEN (SELECT group_id FROM companies WHERE cocd = NEW.company)
     IS NOT (SELECT group_id FROM companies WHERE cocd = NEW.reports_to)
BEGIN SELECT RAISE(ABORT, 'both companies must belong to the same corporate group'); END;
CREATE TRIGGER trg_rep_single_parent BEFORE INSERT ON company_reporting_lines
WHEN NEW.voided_at IS NULL AND EXISTS (
    SELECT 1 FROM company_reporting_lines r WHERE r.company = NEW.company AND r.voided_at IS NULL
      AND r.effective_from < COALESCE(NEW.effective_to, '9999-12-31') AND NEW.effective_from < COALESCE(r.effective_to, '9999-12-31'))
BEGIN SELECT RAISE(ABORT, 'a company can report to only one company at a time'); END;
CREATE TRIGGER trg_rep_no_cycle BEFORE INSERT ON company_reporting_lines
WHEN NEW.voided_at IS NULL AND EXISTS (
    SELECT 1 FROM v_reporting_paths v
    WHERE v.anc = NEW.company AND v.dsc = NEW.reports_to
      AND v.f < COALESCE(NEW.effective_to, '9999-12-31') AND NEW.effective_from < COALESCE(v.t, '9999-12-31'))
BEGIN SELECT RAISE(ABORT, 'reporting line would create a circular structure'); END;
CREATE TRIGGER trg_rep_history BEFORE UPDATE ON company_reporting_lines
WHEN NEW.company IS NOT OLD.company OR NEW.reports_to IS NOT OLD.reports_to
  OR NEW.effective_from IS NOT OLD.effective_from OR NEW.recorded_by IS NOT OLD.recorded_by
  OR NEW.recorded_at IS NOT OLD.recorded_at
  OR (NEW.effective_to IS NOT OLD.effective_to
      AND (NEW.effective_to IS NULL OR (OLD.effective_to IS NOT NULL AND NEW.effective_to > OLD.effective_to)))
  OR (OLD.voided_at IS NOT NULL AND (NEW.voided_at IS NOT OLD.voided_at OR NEW.voided_by IS NOT OLD.voided_by))
BEGIN SELECT RAISE(ABORT, 'reporting lines are history: they can only be closed earlier or voided'); END;
CREATE TRIGGER trg_rep_no_delete BEFORE DELETE ON company_reporting_lines
BEGIN SELECT RAISE(ABORT, 'reporting history cannot be deleted; void the record instead'); END;

-- ===== company-scoped authorization model (definitions only; enforcement is wired in ERP Phase 2) =====
CREATE TABLE company_roles (
    role_code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    scope_level TEXT NOT NULL CHECK (scope_level IN ('group','company')),
    is_read_only INTEGER NOT NULL DEFAULT 0 CHECK (is_read_only IN (0,1))
);
CREATE TABLE company_role_permissions (
    role_code TEXT NOT NULL REFERENCES company_roles(role_code) ON DELETE CASCADE,
    module TEXT NOT NULL CHECK (module IN ('corporate','finance','sales','procurement','inventory','manufacturing','projects','reports','admin')),
    action TEXT NOT NULL CHECK (action IN ('read','write','post','approve','admin')),
    PRIMARY KEY (role_code, module, action)
);
INSERT INTO company_roles(role_code, name, scope_level, is_read_only) VALUES
  ('GROUP_ADMIN','Group Administrator','group',0),
  ('GROUP_FINANCE_DIRECTOR','Group Finance Director','group',0),
  ('GROUP_ACCOUNTANT','Group Accountant','group',0),
  ('COMPANY_ADMIN','Company Administrator','company',0),
  ('COMPANY_FINANCE_MANAGER','Company Finance Manager','company',0),
  ('ACCOUNTANT','Accountant','company',0),
  ('PROCUREMENT_MANAGER','Procurement Manager','company',0),
  ('WAREHOUSE_MANAGER','Warehouse Manager','company',0),
  ('PRODUCTION_MANAGER','Production Manager','company',0),
  ('SALES_MANAGER','Sales Manager','company',0),
  ('PROJECT_MANAGER','Project Manager','company',0),
  ('AUDITOR','Auditor','group',1),
  ('VIEWER','Viewer','company',1);
INSERT INTO company_role_permissions(role_code, module, action) VALUES
  ('GROUP_ADMIN','corporate','read'),
  ('GROUP_ADMIN','corporate','write'),
  ('GROUP_ADMIN','corporate','post'),
  ('GROUP_ADMIN','corporate','approve'),
  ('GROUP_ADMIN','corporate','admin'),
  ('GROUP_ADMIN','finance','read'),
  ('GROUP_ADMIN','finance','write'),
  ('GROUP_ADMIN','finance','post'),
  ('GROUP_ADMIN','finance','approve'),
  ('GROUP_ADMIN','finance','admin'),
  ('GROUP_ADMIN','sales','read'),
  ('GROUP_ADMIN','sales','write'),
  ('GROUP_ADMIN','sales','post'),
  ('GROUP_ADMIN','sales','approve'),
  ('GROUP_ADMIN','sales','admin'),
  ('GROUP_ADMIN','procurement','read'),
  ('GROUP_ADMIN','procurement','write'),
  ('GROUP_ADMIN','procurement','post'),
  ('GROUP_ADMIN','procurement','approve'),
  ('GROUP_ADMIN','procurement','admin'),
  ('GROUP_ADMIN','inventory','read'),
  ('GROUP_ADMIN','inventory','write'),
  ('GROUP_ADMIN','inventory','post'),
  ('GROUP_ADMIN','inventory','approve'),
  ('GROUP_ADMIN','inventory','admin'),
  ('GROUP_ADMIN','manufacturing','read'),
  ('GROUP_ADMIN','manufacturing','write'),
  ('GROUP_ADMIN','manufacturing','post'),
  ('GROUP_ADMIN','manufacturing','approve'),
  ('GROUP_ADMIN','manufacturing','admin'),
  ('GROUP_ADMIN','projects','read'),
  ('GROUP_ADMIN','projects','write'),
  ('GROUP_ADMIN','projects','post'),
  ('GROUP_ADMIN','projects','approve'),
  ('GROUP_ADMIN','projects','admin'),
  ('GROUP_ADMIN','reports','read'),
  ('GROUP_ADMIN','reports','write'),
  ('GROUP_ADMIN','reports','post'),
  ('GROUP_ADMIN','reports','approve'),
  ('GROUP_ADMIN','reports','admin'),
  ('GROUP_ADMIN','admin','read'),
  ('GROUP_ADMIN','admin','write'),
  ('GROUP_ADMIN','admin','post'),
  ('GROUP_ADMIN','admin','approve'),
  ('GROUP_ADMIN','admin','admin'),
  ('GROUP_FINANCE_DIRECTOR','corporate','read'),
  ('GROUP_FINANCE_DIRECTOR','finance','read'),
  ('GROUP_FINANCE_DIRECTOR','finance','write'),
  ('GROUP_FINANCE_DIRECTOR','finance','post'),
  ('GROUP_FINANCE_DIRECTOR','finance','approve'),
  ('GROUP_FINANCE_DIRECTOR','reports','read'),
  ('GROUP_FINANCE_DIRECTOR','reports','approve'),
  ('GROUP_FINANCE_DIRECTOR','sales','read'),
  ('GROUP_FINANCE_DIRECTOR','procurement','read'),
  ('GROUP_FINANCE_DIRECTOR','inventory','read'),
  ('GROUP_ACCOUNTANT','corporate','read'),
  ('GROUP_ACCOUNTANT','finance','read'),
  ('GROUP_ACCOUNTANT','finance','write'),
  ('GROUP_ACCOUNTANT','finance','post'),
  ('GROUP_ACCOUNTANT','reports','read'),
  ('COMPANY_ADMIN','finance','read'),
  ('COMPANY_ADMIN','finance','write'),
  ('COMPANY_ADMIN','finance','post'),
  ('COMPANY_ADMIN','finance','approve'),
  ('COMPANY_ADMIN','sales','read'),
  ('COMPANY_ADMIN','sales','write'),
  ('COMPANY_ADMIN','sales','approve'),
  ('COMPANY_ADMIN','procurement','read'),
  ('COMPANY_ADMIN','procurement','write'),
  ('COMPANY_ADMIN','procurement','approve'),
  ('COMPANY_ADMIN','inventory','read'),
  ('COMPANY_ADMIN','inventory','write'),
  ('COMPANY_ADMIN','inventory','approve'),
  ('COMPANY_ADMIN','manufacturing','read'),
  ('COMPANY_ADMIN','manufacturing','write'),
  ('COMPANY_ADMIN','manufacturing','approve'),
  ('COMPANY_ADMIN','projects','read'),
  ('COMPANY_ADMIN','projects','write'),
  ('COMPANY_ADMIN','projects','approve'),
  ('COMPANY_ADMIN','reports','read'),
  ('COMPANY_ADMIN','reports','write'),
  ('COMPANY_ADMIN','reports','approve'),
  ('COMPANY_ADMIN','admin','read'),
  ('COMPANY_ADMIN','admin','write'),
  ('COMPANY_ADMIN','corporate','read'),
  ('COMPANY_FINANCE_MANAGER','finance','read'),
  ('COMPANY_FINANCE_MANAGER','finance','write'),
  ('COMPANY_FINANCE_MANAGER','finance','post'),
  ('COMPANY_FINANCE_MANAGER','finance','approve'),
  ('COMPANY_FINANCE_MANAGER','reports','read'),
  ('COMPANY_FINANCE_MANAGER','sales','read'),
  ('COMPANY_FINANCE_MANAGER','procurement','read'),
  ('COMPANY_FINANCE_MANAGER','inventory','read'),
  ('ACCOUNTANT','finance','read'),
  ('ACCOUNTANT','finance','write'),
  ('ACCOUNTANT','finance','post'),
  ('ACCOUNTANT','reports','read'),
  ('PROCUREMENT_MANAGER','procurement','read'),
  ('PROCUREMENT_MANAGER','procurement','write'),
  ('PROCUREMENT_MANAGER','procurement','approve'),
  ('PROCUREMENT_MANAGER','inventory','read'),
  ('PROCUREMENT_MANAGER','finance','read'),
  ('WAREHOUSE_MANAGER','inventory','read'),
  ('WAREHOUSE_MANAGER','inventory','write'),
  ('WAREHOUSE_MANAGER','inventory','approve'),
  ('WAREHOUSE_MANAGER','procurement','read'),
  ('PRODUCTION_MANAGER','manufacturing','read'),
  ('PRODUCTION_MANAGER','manufacturing','write'),
  ('PRODUCTION_MANAGER','manufacturing','approve'),
  ('PRODUCTION_MANAGER','inventory','read'),
  ('PRODUCTION_MANAGER','inventory','write'),
  ('PRODUCTION_MANAGER','procurement','read'),
  ('SALES_MANAGER','sales','read'),
  ('SALES_MANAGER','sales','write'),
  ('SALES_MANAGER','sales','approve'),
  ('SALES_MANAGER','inventory','read'),
  ('SALES_MANAGER','reports','read'),
  ('PROJECT_MANAGER','projects','read'),
  ('PROJECT_MANAGER','projects','write'),
  ('PROJECT_MANAGER','projects','approve'),
  ('PROJECT_MANAGER','finance','read'),
  ('PROJECT_MANAGER','procurement','read'),
  ('PROJECT_MANAGER','inventory','read'),
  ('AUDITOR','corporate','read'),
  ('AUDITOR','finance','read'),
  ('AUDITOR','sales','read'),
  ('AUDITOR','procurement','read'),
  ('AUDITOR','inventory','read'),
  ('AUDITOR','manufacturing','read'),
  ('AUDITOR','projects','read'),
  ('AUDITOR','reports','read'),
  ('AUDITOR','admin','read'),
  ('VIEWER','finance','read'),
  ('VIEWER','sales','read'),
  ('VIEWER','procurement','read'),
  ('VIEWER','inventory','read'),
  ('VIEWER','projects','read'),
  ('VIEWER','reports','read');

CREATE TABLE company_user_access (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    scope TEXT NOT NULL CHECK (scope IN ('group','company')),
    group_id INTEGER REFERENCES corporate_groups(id),
    cocd TEXT REFERENCES companies(cocd),
    include_descendants INTEGER NOT NULL DEFAULT 0 CHECK (include_descendants IN (0,1)),
    role_code TEXT NOT NULL REFERENCES company_roles(role_code),
    valid_from TEXT NOT NULL CHECK (date(valid_from) = valid_from),
    valid_to TEXT CHECK (valid_to IS NULL OR date(valid_to) = valid_to),
    granted_by TEXT NOT NULL,
    granted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    revoked_at TEXT, revoked_by TEXT,
    CHECK ((scope = 'group' AND group_id IS NOT NULL AND cocd IS NULL AND include_descendants = 0)
        OR (scope = 'company' AND cocd IS NOT NULL AND group_id IS NULL)),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE INDEX ix_access_user ON company_user_access(user_id);
-- Exceptions: a parent grant that includes descendants can exclude a company (and everything below it).
CREATE TABLE company_access_exclusions (
    access_id INTEGER NOT NULL REFERENCES company_user_access(id) ON DELETE CASCADE,
    cocd TEXT NOT NULL REFERENCES companies(cocd),
    PRIMARY KEY (access_id, cocd)
);
CREATE TRIGGER trg_access_scope_role BEFORE INSERT ON company_user_access
WHEN NEW.scope = 'group' AND (SELECT scope_level FROM company_roles WHERE role_code = NEW.role_code) <> 'group'
BEGIN SELECT RAISE(ABORT, 'this role is a company-level role and cannot be granted group-wide'); END;
CREATE TRIGGER trg_access_history BEFORE UPDATE ON company_user_access
WHEN NEW.user_id IS NOT OLD.user_id OR NEW.scope IS NOT OLD.scope OR NEW.group_id IS NOT OLD.group_id
  OR NEW.cocd IS NOT OLD.cocd OR NEW.role_code IS NOT OLD.role_code OR NEW.valid_from IS NOT OLD.valid_from
  OR NEW.granted_by IS NOT OLD.granted_by OR (OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS NOT OLD.revoked_at)
BEGIN SELECT RAISE(ABORT, 'access grants cannot be rewritten; revoke and grant again'); END;

-- Existing users keep the access they have today: group-wide, mapped from their current global role.
INSERT INTO company_user_access(user_id, scope, group_id, include_descendants, role_code, valid_from, granted_by)
SELECT u.id, 'group', g.id, 0,
       CASE u.role WHEN 'admin' THEN 'GROUP_ADMIN' WHEN 'accountant' THEN 'GROUP_ACCOUNTANT' ELSE 'AUDITOR' END,
       date('now'), 'migration'
FROM users u JOIN corporate_groups g ON g.code = 'DEFAULT';

-- ===== audit trail: record which company an action belongs to =====
ALTER TABLE audit_log ADD COLUMN cocd TEXT;
CREATE INDEX ix_audit_cocd ON audit_log(cocd);
