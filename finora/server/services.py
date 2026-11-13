"""Business logic. Every function takes an open connection, so the API layer, the PyQt6
host and the tests all share exactly the same rules."""
from __future__ import annotations
import hashlib, hmac, os, secrets, sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from .db import Database
from .definitions import DEFAULT_DOC_TYPES, ENTITIES, MENU

ROLE_PERMS = {"viewer": {"read"}, "accountant": {"read", "write", "post"},
              "admin": {"read", "write", "post", "admin"}}
SESSION_HOURS = 12
MAX_FAILED, LOCK_MINUTES = 5, 5


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


@dataclass(frozen=True)
class Principal:
    user_id: int
    username: str
    role: str

    def can(self, perm: str) -> bool:
        return perm in ROLE_PERMS.get(self.role, set())


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def audit(c, user, action, entity=None, entity_id=None, detail=None):
    c.execute("INSERT INTO audit_log(ts,username,action,entity,entity_id,detail) VALUES (?,?,?,?,?,?)",
              (now(), user, action, entity, None if entity_id is None else str(entity_id), detail))


# ---------------------------------------------------------------- money / quantities
def to_minor(v) -> int:
    try:
        d = Decimal(str(v if v not in (None, "") else 0))
    except InvalidOperation:
        raise ServiceError(f"Invalid amount: {v!r}")
    if d != d.quantize(Decimal("0.01")):
        raise ServiceError("Amounts allow at most 2 decimal places")
    return int(d * 100)


def from_minor(n: int) -> str:
    return f"{Decimal(n) / 100:.2f}"


def to_milli(v):
    if v in (None, ""):
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        raise ServiceError(f"Invalid quantity: {v!r}")
    if d != d.quantize(Decimal("0.001")):
        raise ServiceError("Quantities allow at most 3 decimal places")
    return int(d * 1000)


def from_milli(n):
    return None if n is None else f"{Decimal(n) / 1000:.3f}"


def check_date(v, label):
    try:
        return date.fromisoformat(str(v)).isoformat()
    except ValueError:
        raise ServiceError(f"{label} must be a date in YYYY-MM-DD format")


# ---------------------------------------------------------------- auth
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1)
        return hmac.compare_digest(calc.hex(), h)
    except Exception:
        return False


def _tok_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def seed_defaults(db: Database) -> str | None:
    """Idempotent. Returns a generated admin password only when the admin is created now."""
    created = None
    with db.tx() as c:
        for t in DEFAULT_DOC_TYPES:
            c.execute("INSERT OR IGNORE INTO doc_types(doctype,description,prefix) VALUES (?,?,?)", t)
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            created = os.environ.get("FINORA_ADMIN_PASSWORD") or secrets.token_urlsafe(9)
            c.execute("INSERT INTO users(username,full_name,pw_hash,role) VALUES ('admin','Administrator',?,'admin')",
                      (hash_password(created),))
            audit(c, "system", "bootstrap_admin")
    return created


def login(db: Database, username: str, password: str):
    with db.tx() as c:
        u = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if u is None or not u["active"]:
            hash_password(password)  # equalise timing
            raise ServiceError("Invalid username or password", 401)
        if u["locked_until"] and u["locked_until"] > now():
            raise ServiceError("Account temporarily locked. Try again later.", 429)
        if not verify_password(password, u["pw_hash"]):
            fails = u["failed_attempts"] + 1
            lock = (datetime.now(timezone.utc) + timedelta(minutes=LOCK_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ") \
                if fails >= MAX_FAILED else None
            c.execute("UPDATE users SET failed_attempts=?, locked_until=? WHERE id=?",
                      (0 if lock else fails, lock, u["id"]))
            audit(c, username, "login_failed")
            c.execute("COMMIT")  # keep the failure count even though we raise
            raise ServiceError("Invalid username or password", 401)
        c.execute("UPDATE users SET failed_attempts=0, locked_until=NULL WHERE id=?", (u["id"],))
        token = secrets.token_urlsafe(32)
        exp = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c.execute("INSERT INTO sessions(token_hash,user_id,created_at,expires_at) VALUES (?,?,?,?)",
                  (_tok_hash(token), u["id"], now(), exp))
        audit(c, username, "login")
    return token, dict(username=u["username"], full_name=u["full_name"], role=u["role"])


def principal_for(db: Database, token: str) -> Principal:
    with db.read() as c:
        r = c.execute("""SELECT u.id,u.username,u.role,u.active,s.expires_at FROM sessions s
                         JOIN users u ON u.id=s.user_id WHERE s.token_hash=?""", (_tok_hash(token),)).fetchone()
    if r is None or not r["active"] or r["expires_at"] < now():
        raise ServiceError("Session expired or invalid", 401)
    return Principal(r["id"], r["username"], r["role"])


def logout(db: Database, token: str):
    with db.tx() as c:
        c.execute("DELETE FROM sessions WHERE token_hash=?", (_tok_hash(token),))


# ---------------------------------------------------------------- generic master data
def _entity(name: str) -> dict:
    e = ENTITIES.get(name)
    if e is None:
        raise ServiceError("Unknown entity", 404)
    return e


def _cols(e):
    return [f["name"] for f in e["fields"] if not f.get("virtual")]


def master_list(c, entity: str, q: str = "", limit: int = 500, offset: int = 0):
    e = _entity(entity)
    cols = _cols(e)
    where, args = [], []
    for k, v in e.get("fixed", {}).items():
        where.append(f"{k}=?"); args.append(v)
    if q:
        texts = [f["name"] for f in e["fields"] if f["type"] in ("text", "ref") and not f.get("virtual")]
        where.append("(" + " OR ".join(f"{t} LIKE ?" for t in texts) + ")")
        args += [f"%{q}%"] * len(texts)
    sql = f"SELECT {','.join(cols)} FROM {e['table']}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {e['pk']} LIMIT ? OFFSET ?"
    return [dict(r) for r in c.execute(sql, args + [min(limit, 5000), offset])]


def master_get(c, entity: str, key: str):
    e = _entity(entity)
    where = [f"{e['pk']}=?"] + [f"{k}=?" for k in e.get("fixed", {})]
    r = c.execute(f"SELECT {','.join(_cols(e))} FROM {e['table']} WHERE {' AND '.join(where)}",
                  [key, *e.get("fixed", {}).values()]).fetchone()
    if r is None:
        raise ServiceError(f"{e['label']} '{key}' not found", 404)
    return dict(r)


def _clean(e, data: dict, creating: bool) -> dict:
    out = {}
    for f in e["fields"]:
        n = f["name"]
        if n not in data:
            if creating and f.get("default") is not None:
                out[n] = f["default"]
            elif creating and f["required"] and f["type"] != "password" and not f.get("virtual"):
                raise ServiceError(f"{f['label']} is required")
            continue
        v = data[n]
        if f["type"] == "bool":
            v = 1 if v in (True, 1, "1", "true", "True") else 0
        elif isinstance(v, str):
            v = v.strip()
        if f["required"] and v in (None, "") and f["type"] != "password":
            raise ServiceError(f"{f['label']} is required")
        if f["type"] == "select" and v not in f["options"]:
            raise ServiceError(f"{f['label']} must be one of {', '.join(f['options'])}")
        if f.get("maxlen") and v and len(str(v)) > f["maxlen"]:
            raise ServiceError(f"{f['label']} is longer than {f['maxlen']} characters")
        out[n] = None if v == "" else v
    return out


def _integrity(fn):
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except sqlite3.IntegrityError as ex:
            m = str(ex)
            if "UNIQUE" in m:
                raise ServiceError("A record with this key already exists", 409)
            if "FOREIGN KEY" in m:
                raise ServiceError("Referenced record does not exist, or the record is still in use", 409)
            raise ServiceError(f"Data rule violated: {m}", 409)
    return wrapper


@_integrity
def master_create(c, p: Principal, entity: str, data: dict):
    e = _entity(entity)
    vals = {**_clean(e, data, True), **e.get("fixed", {})}
    if entity == "users":
        if not data.get("password"):
            raise ServiceError("Password is required for a new user")
        vals.pop("password", None)
        vals["pw_hash"] = hash_password(data["password"])
    vals.pop("password", None)
    c.execute(f"INSERT INTO {e['table']}({','.join(vals)}) VALUES ({','.join('?' * len(vals))})", list(vals.values()))
    audit(c, p.username, "create", entity, vals[e["pk"]])
    return master_get(c, entity, vals[e["pk"]])


@_integrity
def master_update(c, p: Principal, entity: str, key: str, data: dict):
    e = _entity(entity)
    master_get(c, entity, key)
    vals = _clean(e, {k: v for k, v in data.items() if k != e["pk"]}, False)
    vals.pop("password", None)
    if entity == "users" and data.get("password"):
        vals["pw_hash"] = hash_password(data["password"])
    if entity == "users" and key == p.username and vals.get("active") == 0:
        raise ServiceError("You cannot deactivate your own account")
    if vals:
        c.execute(f"UPDATE {e['table']} SET {','.join(k + '=?' for k in vals)} WHERE {e['pk']}=?",
                  [*vals.values(), key])
        audit(c, p.username, "update", entity, key, ",".join(vals))
    return master_get(c, entity, key)


@_integrity
def master_delete(c, p: Principal, entity: str, key: str):
    e = _entity(entity)
    if e.get("deletable") is False:
        raise ServiceError("This record type cannot be deleted; deactivate it instead", 409)
    master_get(c, entity, key)
    c.execute(f"DELETE FROM {e['table']} WHERE {e['pk']}=?", (key,))
    audit(c, p.username, "delete", entity, key)


def menu_for(p: Principal):
    out = []
    for g in MENU:
        if g.get("admin") and not p.can("admin"):
            continue
        out.append(dict(group=g["group"], items=g.get("items", []), planned=g.get("planned", [])))
    return out


# ---------------------------------------------------------------- journals
def _line_rows(c, header_id):
    out = []
    for r in c.execute("SELECT * FROM journal_lines WHERE header_id=? ORDER BY item_no", (header_id,)):
        out.append(dict(item_no=r["item_no"], glcd=r["glcd"], description=r["description"],
                        debit=from_minor(r["debit_minor"]), credit=from_minor(r["credit_minor"]),
                        partner_code=r["partner_code"], quantity=from_milli(r["qty_milli"]), unit=r["unit"],
                        ref_item_no=r["ref_item_no"], preceding_doc=r["preceding_doc"],
                        origin_ref=r["origin_ref"], product_desc=r["product_desc"]))
    return out


def journal_get(c, jid: int) -> dict:
    h = c.execute("SELECT * FROM journal_headers WHERE id=?", (jid,)).fetchone()
    if h is None:
        raise ServiceError("Journal not found", 404)
    lines = _line_rows(c, jid)
    td = sum(to_minor(l["debit"]) for l in lines)
    tc = sum(to_minor(l["credit"]) for l in lines)
    d = {k: h[k] for k in h.keys()}
    d.update(lines=lines, total_debit=from_minor(td), total_credit=from_minor(tc),
             balanced=(td == tc and len(lines) >= 2))
    return d


def journal_list(c, cocd=None, doctype=None, status=None, q="", limit=200, offset=0):
    where, args = [], []
    for col, v in (("cocd", cocd), ("doctype", doctype), ("status", status)):
        if v:
            where.append(f"h.{col}=?"); args.append(v)
    if q:
        where.append("(h.doc_no LIKE ? OR h.reference LIKE ? OR h.description LIKE ?)")
        args += [f"%{q}%"] * 3
    sql = """SELECT h.id,h.cocd,h.doctype,h.doc_no,h.doc_date,h.posting_date,h.reference,h.description,h.status,
                    COALESCE((SELECT SUM(debit_minor) FROM journal_lines WHERE header_id=h.id),0) AS td
             FROM journal_headers h"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY h.id DESC LIMIT ? OFFSET ?"
    rows = [dict(r) for r in c.execute(sql, args + [min(limit, 1000), offset])]
    for r in rows:
        r["total"] = from_minor(r.pop("td"))
    return rows


def _validate_and_store_lines(c, header_id: int, cocd: str, lines: list[dict]):
    c.execute("DELETE FROM journal_lines WHERE header_id=?", (header_id,))
    for n, l in enumerate(lines, 1):
        gl = c.execute("SELECT active FROM gl_accounts WHERE glcd=?", (l.get("glcd"),)).fetchone()
        if gl is None:
            raise ServiceError(f"Line {n}: GL account '{l.get('glcd')}' does not exist")
        if not gl["active"]:
            raise ServiceError(f"Line {n}: GL account '{l.get('glcd')}' is inactive")
        dr, cr = to_minor(l.get("debit")), to_minor(l.get("credit"))
        if dr < 0 or cr < 0:
            raise ServiceError(f"Line {n}: amounts cannot be negative")
        if dr and cr:
            raise ServiceError(f"Line {n}: enter either a debit or a credit, not both")
        if not dr and not cr:
            raise ServiceError(f"Line {n}: amount is zero")
        pc = l.get("partner_code") or None
        if pc and c.execute("SELECT 1 FROM partners WHERE code=?", (pc,)).fetchone() is None:
            raise ServiceError(f"Line {n}: partner '{pc}' does not exist")
        c.execute("""INSERT INTO journal_lines(header_id,item_no,glcd,description,debit_minor,credit_minor,
                     partner_code,qty_milli,unit,ref_item_no,preceding_doc,origin_ref,product_desc)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (header_id, n, l["glcd"], l.get("description"), dr, cr, pc, to_milli(l.get("quantity")),
                   l.get("unit"), l.get("ref_item_no"), l.get("preceding_doc"), l.get("origin_ref"),
                   l.get("product_desc")))


def _check_header(c, data: dict):
    if c.execute("SELECT 1 FROM companies WHERE cocd=?", (data.get("cocd"),)).fetchone() is None:
        raise ServiceError(f"Company '{data.get('cocd')}' does not exist")
    return check_date(data.get("doc_date"), "Document date"), check_date(data.get("posting_date"), "Posting date")


@_integrity
def journal_create(c, p: Principal, data: dict) -> dict:
    if c.execute("SELECT 1 FROM doc_types WHERE doctype=?", (data.get("doctype"),)).fetchone() is None:
        raise ServiceError(f"Document type '{data.get('doctype')}' does not exist")
    dd, pd_ = _check_header(c, data)
    cur = c.execute("""INSERT INTO journal_headers(cocd,doctype,doc_date,posting_date,entry_date,reference,
                       department,description,entered_by) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (data["cocd"], data["doctype"], dd, pd_, date.today().isoformat(), data.get("reference"),
                     data.get("department"), data.get("description"), p.username))
    jid = cur.lastrowid
    _validate_and_store_lines(c, jid, data["cocd"], data.get("lines", []))
    audit(c, p.username, "create", "journal", jid)
    return journal_get(c, jid)


def _draft_for_update(c, jid: int, expected_version):
    h = c.execute("SELECT * FROM journal_headers WHERE id=?", (jid,)).fetchone()
    if h is None:
        raise ServiceError("Journal not found", 404)
    if h["status"] != "draft":
        raise ServiceError("Only draft journals can be changed. Reverse a posted journal instead.", 409)
    if expected_version is not None and h["version"] != expected_version:
        raise ServiceError("This journal was changed by someone else. Reload it and try again.", 409)
    return h


@_integrity
def journal_update(c, p: Principal, jid: int, data: dict) -> dict:
    h = _draft_for_update(c, jid, data.get("version"))
    merged = {**dict(h), **{k: v for k, v in data.items() if k in
                            ("cocd", "doc_date", "posting_date", "reference", "department", "description")}}
    dd, pd_ = _check_header(c, merged)
    c.execute("""UPDATE journal_headers SET cocd=?,doc_date=?,posting_date=?,reference=?,department=?,
                 description=?,version=version+1 WHERE id=?""",
              (merged["cocd"], dd, pd_, merged["reference"], merged["department"], merged["description"], jid))
    if "lines" in data:
        _validate_and_store_lines(c, jid, merged["cocd"], data["lines"])
    audit(c, p.username, "update", "journal", jid)
    return journal_get(c, jid)


def journal_delete(c, p: Principal, jid: int, version=None):
    _draft_for_update(c, jid, version)
    c.execute("DELETE FROM journal_headers WHERE id=?", (jid,))
    audit(c, p.username, "delete", "journal", jid)


def _next_number(c, cocd, doctype) -> str:
    c.execute("INSERT OR IGNORE INTO number_ranges(cocd,doctype,next_no) VALUES (?,?,1)", (cocd, doctype))
    n = c.execute("UPDATE number_ranges SET next_no=next_no+1 WHERE cocd=? AND doctype=? RETURNING next_no-1",
                  (cocd, doctype)).fetchone()[0]
    prefix = c.execute("SELECT prefix FROM doc_types WHERE doctype=?", (doctype,)).fetchone()[0]
    return f"{prefix}{n:06d}"


def _post_in_tx(c, p: Principal, jid: int, expected_version=None) -> dict:
    h = _draft_for_update(c, jid, expected_version)
    td, tc = c.execute("SELECT COALESCE(SUM(debit_minor),0), COALESCE(SUM(credit_minor),0) "
                       "FROM journal_lines WHERE header_id=?", (jid,)).fetchone()
    count = c.execute("SELECT COUNT(*) FROM journal_lines WHERE header_id=?", (jid,)).fetchone()[0]
    if count < 2:
        raise ServiceError("A journal needs at least two lines")
    if td != tc:
        raise ServiceError(f"Journal is out of balance: debits {from_minor(td)} vs credits {from_minor(tc)} "
                           f"(difference {from_minor(abs(td - tc))})")
    no = _next_number(c, h["cocd"], h["doctype"])
    c.execute("""UPDATE journal_headers SET status='posted', doc_no=?, posted_by=?, posted_at=?,
                 version=version+1 WHERE id=?""", (no, p.username, now(), jid))
    audit(c, p.username, "post", "journal", jid, no)
    return journal_get(c, jid)


@_integrity
def journal_post(c, p: Principal, jid: int, expected_version=None) -> dict:
    return _post_in_tx(c, p, jid, expected_version)


@_integrity
def journal_reverse(c, p: Principal, jid: int, posting_date: str | None = None) -> dict:
    h = c.execute("SELECT * FROM journal_headers WHERE id=?", (jid,)).fetchone()
    if h is None:
        raise ServiceError("Journal not found", 404)
    if h["status"] != "posted":
        raise ServiceError("Only posted journals that are not yet reversed can be reversed", 409)
    if h["reverses_id"]:
        raise ServiceError("A reversal entry cannot itself be reversed; post a new journal", 409)
    pd_ = check_date(posting_date or date.today().isoformat(), "Posting date")
    cur = c.execute("""INSERT INTO journal_headers(cocd,doctype,doc_date,posting_date,entry_date,reference,department,
                       description,entered_by,reverses_id) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (h["cocd"], h["doctype"], pd_, pd_, date.today().isoformat(), f"REV {h['doc_no']}",
                     h["department"], f"Reversal of {h['doc_no']}", p.username, jid))
    rid = cur.lastrowid
    c.execute("""INSERT INTO journal_lines(header_id,item_no,glcd,description,debit_minor,credit_minor,partner_code,
                 qty_milli,unit,ref_item_no,preceding_doc,origin_ref,product_desc)
                 SELECT ?,item_no,glcd,description,credit_minor,debit_minor,partner_code,qty_milli,unit,
                        ref_item_no,preceding_doc,origin_ref,product_desc FROM journal_lines WHERE header_id=?""",
              (rid, jid))
    _post_in_tx(c, p, rid)
    c.execute("UPDATE journal_headers SET status='reversed', reversed_by_id=? WHERE id=?", (rid, jid))
    audit(c, p.username, "reverse", "journal", jid, str(rid))
    return journal_get(c, rid)


# ---------------------------------------------------------------- reports
def trial_balance(c, cocd: str, as_of: str | None = None) -> dict:
    as_of = check_date(as_of or date.today().isoformat(), "As-of date")
    rows = c.execute("""SELECT l.glcd, a.description, SUM(l.debit_minor) dr, SUM(l.credit_minor) cr
        FROM journal_lines l JOIN journal_headers h ON h.id=l.header_id
        JOIN gl_accounts a ON a.glcd=l.glcd
        WHERE h.cocd=? AND h.status IN ('posted','reversed') AND h.posting_date<=?
        GROUP BY l.glcd ORDER BY l.glcd""", (cocd, as_of)).fetchall()
    out, tdr, tcr = [], 0, 0
    for r in rows:
        bal = r["dr"] - r["cr"]
        out.append(dict(glcd=r["glcd"], description=r["description"], debit=from_minor(r["dr"]),
                        credit=from_minor(r["cr"]), balance=from_minor(bal)))
        tdr += r["dr"]; tcr += r["cr"]
    return dict(cocd=cocd, as_of=as_of, rows=out, total_debit=from_minor(tdr),
                total_credit=from_minor(tcr), balanced=tdr == tcr)
