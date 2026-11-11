-- Money is stored as integer minor units (cents). Quantities as integer thousandths.
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name TEXT,
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('viewer','accountant','admin')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT
);
CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE coa (coa TEXT PRIMARY KEY, description TEXT);
CREATE TABLE gl_types (
    gltype TEXT PRIMARY KEY, description TEXT,
    coa TEXT NOT NULL REFERENCES coa(coa),
    normal_side TEXT NOT NULL DEFAULT 'D' CHECK (normal_side IN ('D','C'))
);
CREATE TABLE gl_accounts (
    glcd TEXT PRIMARY KEY, description TEXT,
    gltype TEXT NOT NULL REFERENCES gl_types(gltype),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);
CREATE TABLE companies (
    cocd TEXT PRIMARY KEY, name TEXT NOT NULL, currency TEXT NOT NULL,
    coa TEXT NOT NULL REFERENCES coa(coa), tax_id TEXT
);
CREATE TABLE partners (
    code TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('customer','vendor')),
    name TEXT NOT NULL,
    glcd TEXT REFERENCES gl_accounts(glcd),
    cocd TEXT REFERENCES companies(cocd)
);
CREATE TABLE doc_types (doctype TEXT PRIMARY KEY, description TEXT, prefix TEXT NOT NULL);
CREATE TABLE number_ranges (
    cocd TEXT NOT NULL REFERENCES companies(cocd),
    doctype TEXT NOT NULL REFERENCES doc_types(doctype),
    next_no INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (cocd, doctype)
);

CREATE TABLE journal_headers (
    id INTEGER PRIMARY KEY,
    cocd TEXT NOT NULL REFERENCES companies(cocd),
    doctype TEXT NOT NULL REFERENCES doc_types(doctype),
    doc_no TEXT,                       -- assigned at posting, so numbers are gapless
    doc_date TEXT NOT NULL,
    posting_date TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    reference TEXT, department TEXT, description TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','posted','reversed')),
    entered_by TEXT NOT NULL,
    posted_by TEXT, posted_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    reverses_id INTEGER REFERENCES journal_headers(id),
    reversed_by_id INTEGER REFERENCES journal_headers(id),
    UNIQUE (cocd, doctype, doc_no)
);
CREATE TABLE journal_lines (
    id INTEGER PRIMARY KEY,
    header_id INTEGER NOT NULL REFERENCES journal_headers(id) ON DELETE CASCADE,
    item_no INTEGER NOT NULL,
    glcd TEXT NOT NULL REFERENCES gl_accounts(glcd),
    description TEXT,
    debit_minor INTEGER NOT NULL DEFAULT 0 CHECK (debit_minor >= 0),
    credit_minor INTEGER NOT NULL DEFAULT 0 CHECK (credit_minor >= 0),
    partner_code TEXT REFERENCES partners(code),
    qty_milli INTEGER, unit TEXT,
    ref_item_no TEXT, preceding_doc TEXT, origin_ref TEXT, product_desc TEXT,
    UNIQUE (header_id, item_no),
    CHECK (NOT (debit_minor > 0 AND credit_minor > 0))
);
CREATE INDEX ix_lines_gl ON journal_lines(glcd);
CREATE INDEX ix_hdr_lookup ON journal_headers(cocd, doctype, status);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, username TEXT,
    action TEXT NOT NULL, entity TEXT, entity_id TEXT, detail TEXT
);

-- Integrity enforced in the database itself, not only in application code.
CREATE TRIGGER trg_post_balanced BEFORE UPDATE OF status ON journal_headers
WHEN OLD.status = 'draft' AND NEW.status = 'posted'
BEGIN
    SELECT RAISE(ABORT, 'journal is not balanced or has fewer than two lines')
    WHERE (SELECT COALESCE(SUM(debit_minor),0) FROM journal_lines WHERE header_id = NEW.id)
       != (SELECT COALESCE(SUM(credit_minor),0) FROM journal_lines WHERE header_id = NEW.id)
       OR (SELECT COUNT(*) FROM journal_lines WHERE header_id = NEW.id) < 2;
END;
CREATE TRIGGER trg_hdr_immutable BEFORE UPDATE ON journal_headers
WHEN OLD.status != 'draft' AND NOT (OLD.status = 'posted' AND NEW.status = 'reversed')
BEGIN SELECT RAISE(ABORT, 'posted journals are immutable; reverse them instead'); END;
CREATE TRIGGER trg_hdr_nodelete BEFORE DELETE ON journal_headers
WHEN OLD.status != 'draft'
BEGIN SELECT RAISE(ABORT, 'posted journals cannot be deleted'); END;
CREATE TRIGGER trg_line_ins BEFORE INSERT ON journal_lines
WHEN (SELECT status FROM journal_headers WHERE id = NEW.header_id) != 'draft'
BEGIN SELECT RAISE(ABORT, 'posted journals are immutable'); END;
CREATE TRIGGER trg_line_upd BEFORE UPDATE ON journal_lines
WHEN (SELECT status FROM journal_headers WHERE id = OLD.header_id) != 'draft'
BEGIN SELECT RAISE(ABORT, 'posted journals are immutable'); END;
CREATE TRIGGER trg_line_del BEFORE DELETE ON journal_lines
WHEN (SELECT status FROM journal_headers WHERE id = OLD.header_id) != 'draft'
BEGIN SELECT RAISE(ABORT, 'posted journals are immutable'); END;
