"""Corporate groups, legal ownership and operational reporting lines (ERP Phase 1 foundation).

The database enforces the hard rules (no cycles, <=100% per company per date, history is never rewritten,
owner and owned in the same group). This module adds friendly validation, the hierarchy queries and
effective-dated change operations. All functions take an open connection, like the rest of the service layer.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from .services import Principal, ServiceError, _integrity, audit, check_date

COMPANY_STATUSES = ("active", "inactive", "dissolved", "acquired")
RELATIONSHIPS = ("subsidiary", "associate", "joint_venture", "investment")


# ------------------------------------------------------------------ helpers
def pct_to_bp(v, label: str = "Percentage") -> int:
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        raise ServiceError(f"{label} must be a number between 0 and 100")
    if d != d.quantize(Decimal("0.01")):
        raise ServiceError(f"{label} allows at most 2 decimal places")
    if not (Decimal(0) <= d <= Decimal(100)):
        raise ServiceError(f"{label} must be between 0 and 100")
    return int(d * 100)


def bp_to_pct(bp: int) -> str:
    return f"{Decimal(bp) / 100:.2f}"


def _today() -> str:
    return date.today().isoformat()


def _company(c, cocd: str):
    r = c.execute("SELECT * FROM companies WHERE cocd=?", (cocd,)).fetchone()
    if r is None:
        raise ServiceError(f"Company '{cocd}' does not exist", 404)
    return r


def _row(r) -> dict:
    d = dict(r)
    for k in ("ownership_bp", "voting_bp"):
        if k in d:
            d[k.replace("_bp", "_pct")] = bp_to_pct(d[k])
    return d


# ------------------------------------------------------------------ groups and company profile
@_integrity
def create_group(c, p: Principal, code: str, name: str, description: str | None = None) -> dict:
    if not (code or "").strip() or not (name or "").strip():
        raise ServiceError("A group needs a code and a name")
    cur = c.execute("INSERT INTO corporate_groups(code,name,description) VALUES (?,?,?)",
                    (code.strip(), name.strip(), description))
    audit(c, p.username, "create", "corporate_group", cur.lastrowid, code.strip())
    return dict(c.execute("SELECT * FROM corporate_groups WHERE id=?", (cur.lastrowid,)).fetchone())


def list_groups(c) -> list[dict]:
    return [dict(r) for r in c.execute(
        """SELECT g.*, (SELECT COUNT(*) FROM companies WHERE group_id=g.id) AS company_count
           FROM corporate_groups g ORDER BY g.code""")]


@_integrity
def move_company_to_group(c, p: Principal, cocd: str, group_id: int) -> dict:
    co = _company(c, cocd)
    if c.execute("SELECT 1 FROM corporate_groups WHERE id=?", (group_id,)).fetchone() is None:
        raise ServiceError("Corporate group does not exist", 404)
    cross = c.execute(
        """SELECT 1 FROM company_ownership o JOIN companies x ON x.cocd = CASE WHEN o.parent_company=? THEN o.child_company ELSE o.parent_company END
           WHERE (o.parent_company=? OR o.child_company=?) AND o.voided_at IS NULL AND x.group_id IS NOT ?
           UNION ALL
           SELECT 1 FROM company_reporting_lines r JOIN companies x ON x.cocd = CASE WHEN r.company=? THEN r.reports_to ELSE r.company END
           WHERE (r.company=? OR r.reports_to=?) AND r.voided_at IS NULL AND x.group_id IS NOT ?""",
        (cocd, cocd, cocd, group_id, cocd, cocd, cocd, group_id)).fetchone()
    if cross:
        raise ServiceError("This company still has ownership or reporting records with companies of its current group. "
                           "Void or close them first; ownership must stay inside one corporate group.", 409)
    c.execute("UPDATE companies SET group_id=? WHERE cocd=?", (group_id, cocd))
    audit(c, p.username, "move_group", "company", cocd, f"{co['group_id']} -> {group_id}", cocd=cocd)
    return dict(_company(c, cocd))


@_integrity
def set_company_profile(c, p: Principal, cocd: str, *, legal_name=None, status=None, incorporated_on=None,
                        dissolved_on=None) -> dict:
    _company(c, cocd)
    vals = {}
    if legal_name is not None: vals["legal_name"] = legal_name.strip() or None
    if status is not None:
        if status not in COMPANY_STATUSES:
            raise ServiceError(f"Status must be one of {', '.join(COMPANY_STATUSES)}")
        vals["status"] = status
    if incorporated_on is not None: vals["incorporated_on"] = check_date(incorporated_on, "Incorporation date")
    if dissolved_on is not None: vals["dissolved_on"] = check_date(dissolved_on, "Dissolution date")
    if vals:
        c.execute(f"UPDATE companies SET {','.join(k + '=?' for k in vals)} WHERE cocd=?", [*vals.values(), cocd])
        audit(c, p.username, "update_profile", "company", cocd, ",".join(vals), cocd=cocd)
    return dict(_company(c, cocd))


# ------------------------------------------------------------------ legal ownership
@_integrity
def record_ownership(c, p: Principal, parent: str, child: str, ownership_pct, voting_pct=None,
                     relationship: str = "subsidiary", effective_from: str | None = None,
                     effective_to: str | None = None, acquisition_date: str | None = None,
                     note: str | None = None) -> dict:
    _company(c, parent); _company(c, child)
    if parent == child:
        raise ServiceError("A company cannot own itself")
    if relationship not in RELATIONSHIPS:
        raise ServiceError(f"Relationship must be one of {', '.join(RELATIONSHIPS)}")
    own = pct_to_bp(ownership_pct, "Ownership percentage")
    vote = own if voting_pct is None else pct_to_bp(voting_pct, "Voting percentage")
    frm = check_date(effective_from or _today(), "Effective from")
    to = check_date(effective_to, "Effective to") if effective_to else None
    acq = check_date(acquisition_date, "Acquisition date") if acquisition_date else None
    cur = c.execute("""INSERT INTO company_ownership(parent_company,child_company,ownership_bp,voting_bp,relationship,
                       effective_from,effective_to,acquisition_date,note,recorded_by) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (parent, child, own, vote, relationship, frm, to, acq, note, p.username))
    audit(c, p.username, "ownership_record", "company_ownership", cur.lastrowid,
          f"{parent} -> {child} {bp_to_pct(own)}% from {frm}", cocd=child)
    return _row(c.execute("SELECT * FROM company_ownership WHERE id=?", (cur.lastrowid,)).fetchone())


def _own(c, oid: int):
    r = c.execute("SELECT * FROM company_ownership WHERE id=?", (oid,)).fetchone()
    if r is None:
        raise ServiceError("Ownership record not found", 404)
    return r


@_integrity
def close_ownership(c, p: Principal, ownership_id: int, effective_to: str) -> dict:
    r = _own(c, ownership_id)
    to = check_date(effective_to, "Effective to")
    if r["voided_at"]:
        raise ServiceError("This ownership record was voided", 409)
    c.execute("UPDATE company_ownership SET effective_to=? WHERE id=?", (to, ownership_id))
    audit(c, p.username, "ownership_close", "company_ownership", ownership_id, to, cocd=r["child_company"])
    return _row(_own(c, ownership_id))


@_integrity
def void_ownership(c, p: Principal, ownership_id: int, reason: str) -> dict:
    r = _own(c, ownership_id)
    if not (reason or "").strip():
        raise ServiceError("Give a reason for voiding the record")
    if r["voided_at"]:
        raise ServiceError("This ownership record is already voided", 409)
    c.execute("UPDATE company_ownership SET voided_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), voided_by=?, void_reason=? WHERE id=?",
              (p.username, reason.strip(), ownership_id))
    audit(c, p.username, "ownership_void", "company_ownership", ownership_id, reason.strip(), cocd=r["child_company"])
    return _row(_own(c, ownership_id))


@_integrity
def change_ownership(c, p: Principal, parent: str, child: str, ownership_pct, voting_pct=None, *,
                     effective_from: str, note: str | None = None) -> dict:
    """Change the percentage from a date, keeping history: the record in force is closed at that date and a new one starts."""
    frm = check_date(effective_from, "Effective from")
    cur = c.execute("""SELECT * FROM company_ownership WHERE parent_company=? AND child_company=? AND voided_at IS NULL
                       AND effective_from <= ? AND COALESCE(effective_to,'9999-12-31') > ?""", (parent, child, frm, frm)).fetchone()
    if cur is None:
        raise ServiceError(f"{parent} has no ownership record in force over {child} on {frm}")
    if cur["effective_from"] == frm:
        raise ServiceError("A record already starts on that date. Void it and record the correct one, or choose a later date.")
    old_to = cur["effective_to"]
    c.execute("UPDATE company_ownership SET effective_to=? WHERE id=?", (frm, cur["id"]))
    return record_ownership(c, p, parent, child, ownership_pct, voting_pct, cur["relationship"], frm, old_to,
                            cur["acquisition_date"], note)


def ownership_history(c, company: str | None = None, parent: str | None = None, include_voided: bool = True) -> list[dict]:
    where, args = [], []
    if company: where.append("child_company=?"); args.append(company)
    if parent: where.append("parent_company=?"); args.append(parent)
    if not include_voided: where.append("voided_at IS NULL")
    sql = "SELECT * FROM company_ownership" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY child_company, parent_company, effective_from, id"
    return [_row(r) for r in c.execute(sql, args)]


# ------------------------------------------------------------------ hierarchy queries (as of a date)
_ACTIVE = "o.voided_at IS NULL AND o.effective_from <= :d AND COALESCE(o.effective_to,'9999-12-31') > :d"


def children(c, parent: str, as_of: str | None = None) -> list[dict]:
    d = as_of or _today()
    return [_row(r) for r in c.execute(
        f"SELECT o.* FROM company_ownership o WHERE o.parent_company=:p AND {_ACTIVE} ORDER BY o.child_company", dict(p=parent, d=d))]


def parents(c, child: str, as_of: str | None = None) -> list[dict]:
    d = as_of or _today()
    return [_row(r) for r in c.execute(
        f"SELECT o.* FROM company_ownership o WHERE o.child_company=:c AND {_ACTIVE} ORDER BY o.parent_company", dict(c=child, d=d))]


def descendants(c, root: str, as_of: str | None = None) -> dict[str, int]:
    """Every company below `root` (any depth) -> its shallowest depth. Root itself is not included."""
    d = as_of or _today()
    rows = c.execute(f"""WITH RECURSIVE t(c, depth) AS (
            SELECT :r, 0
            UNION
            SELECT o.child_company, t.depth + 1 FROM t JOIN company_ownership o ON o.parent_company = t.c WHERE {_ACTIVE})
        SELECT c, MIN(depth) FROM t WHERE c <> :r GROUP BY c""", dict(r=root, d=d)).fetchall()
    return {r[0]: r[1] for r in rows}


def ancestors(c, company: str, as_of: str | None = None) -> dict[str, int]:
    d = as_of or _today()
    rows = c.execute(f"""WITH RECURSIVE t(c, depth) AS (
            SELECT :r, 0
            UNION
            SELECT o.parent_company, t.depth + 1 FROM t JOIN company_ownership o ON o.child_company = t.c WHERE {_ACTIVE})
        SELECT c, MIN(depth) FROM t WHERE c <> :r GROUP BY c""", dict(r=company, d=d)).fetchall()
    return {r[0]: r[1] for r in rows}


def ultimate_parents(c, company: str, as_of: str | None = None) -> list[str]:
    """Top of every ownership path above the company (the company itself if nothing owns it)."""
    d = as_of or _today()
    up = ancestors(c, company, d)
    if not up:
        return [company]
    return sorted(a for a in up if not parents(c, a, d))


def effective_ownership_bp(c, owner: str, owned: str, as_of: str | None = None) -> int:
    """Indirect plus direct ownership, summed over every ownership path (basis points, rounded half up)."""
    d = as_of or _today()
    total = Fraction(0)

    def walk(node: str, share: Fraction, seen: frozenset):
        nonlocal total
        for e in children(c, node, d):
            nxt = e["child_company"]
            if nxt in seen:
                continue
            s = share * Fraction(e["ownership_bp"], 10000)
            if nxt == owned:
                total += s
            else:
                walk(nxt, s, seen | {nxt})
    walk(owner, Fraction(1), frozenset({owner}))
    return int(total * 10000 + Fraction(1, 2))


def hierarchy(c, group_id: int, as_of: str | None = None) -> list[dict]:
    """Nested structure for tree views: roots are group companies nothing in the group owns on that date."""
    d = as_of or _today()
    cos = {r["cocd"]: dict(r) for r in c.execute("SELECT * FROM companies WHERE group_id=?", (group_id,))}
    kids: dict[str, list[dict]] = {}
    owned = set()
    for r in c.execute(f"""SELECT o.* FROM company_ownership o JOIN companies p ON p.cocd=o.parent_company
                           WHERE p.group_id=:g AND {_ACTIVE} ORDER BY o.child_company""", dict(g=group_id, d=d)):
        kids.setdefault(r["parent_company"], []).append(dict(r)); owned.add(r["child_company"])

    def node(code: str, edge: dict | None, depth: int) -> dict:
        co = cos[code]
        n = dict(cocd=code, name=co["name"], legal_name=co["legal_name"], status=co["status"], depth=depth,
                 ownership_pct=bp_to_pct(edge["ownership_bp"]) if edge else None,
                 voting_pct=bp_to_pct(edge["voting_bp"]) if edge else None,
                 relationship=edge["relationship"] if edge else None, children=[])
        n["children"] = [node(e["child_company"], e, depth + 1) for e in kids.get(code, [])]
        n["subsidiary_count"] = sum(1 + k["subsidiary_count"] for k in n["children"])
        return n
    return [node(code, None, 0) for code in sorted(cos) if code not in owned]


def group_stats(c, group_id: int, as_of: str | None = None) -> dict:
    tree = hierarchy(c, group_id, as_of)

    def depth(n): return max([n["depth"]] + [depth(k) for k in n["children"]])
    cos = c.execute("SELECT status, COUNT(*) FROM companies WHERE group_id=? GROUP BY status", (group_id,)).fetchall()
    by = {r[0]: r[1] for r in cos}
    return dict(companies=sum(by.values()), by_status=by, roots=[n["cocd"] for n in tree],
                max_depth=max((depth(n) for n in tree), default=0))


# ------------------------------------------------------------------ operational reporting lines
@_integrity
def record_reporting_line(c, p: Principal, company: str, reports_to: str, effective_from: str | None = None,
                          effective_to: str | None = None, note: str | None = None) -> dict:
    _company(c, company); _company(c, reports_to)
    if company == reports_to:
        raise ServiceError("A company cannot report to itself")
    frm = check_date(effective_from or _today(), "Effective from")
    to = check_date(effective_to, "Effective to") if effective_to else None
    cur = c.execute("""INSERT INTO company_reporting_lines(company,reports_to,effective_from,effective_to,note,recorded_by)
                       VALUES (?,?,?,?,?,?)""", (company, reports_to, frm, to, note, p.username))
    audit(c, p.username, "reporting_record", "company_reporting_line", cur.lastrowid, f"{company} -> {reports_to} from {frm}", cocd=company)
    return dict(c.execute("SELECT * FROM company_reporting_lines WHERE id=?", (cur.lastrowid,)).fetchone())


@_integrity
def close_reporting_line(c, p: Principal, line_id: int, effective_to: str) -> dict:
    r = c.execute("SELECT * FROM company_reporting_lines WHERE id=?", (line_id,)).fetchone()
    if r is None:
        raise ServiceError("Reporting line not found", 404)
    c.execute("UPDATE company_reporting_lines SET effective_to=? WHERE id=?", (check_date(effective_to, "Effective to"), line_id))
    audit(c, p.username, "reporting_close", "company_reporting_line", line_id, effective_to, cocd=r["company"])
    return dict(c.execute("SELECT * FROM company_reporting_lines WHERE id=?", (line_id,)).fetchone())


def reporting_children(c, parent: str, as_of: str | None = None) -> list[str]:
    d = as_of or _today()
    return [r[0] for r in c.execute("""SELECT company FROM company_reporting_lines WHERE reports_to=? AND voided_at IS NULL
                                       AND effective_from <= ? AND COALESCE(effective_to,'9999-12-31') > ? ORDER BY company""", (parent, d, d))]
