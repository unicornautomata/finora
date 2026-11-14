"""Company-scoped access resolution (ERP Phase 1: the model and its rules).

Who can see which company is decided here, from the grants stored in company_user_access:
  * a GROUP grant covers every company of that corporate group;
  * a COMPANY grant covers that company, and its subsidiaries only if include_descendants was set explicitly;
  * exclusions remove a company and everything below it from a grant;
  * grants can expire (valid_to) and be revoked; nothing is inherited implicitly.
Access to a parent company never silently grants access to its subsidiaries.

STATUS: these functions are complete and tested, but NOT yet called by the HTTP endpoints. Wiring company
scoping into every endpoint is ERP Phase 2 (it needs the company-context selector at the same time).
"""
from __future__ import annotations
from datetime import date

from . import corporate
from .services import Principal, ServiceError, _integrity, audit, check_date


def _today() -> str:
    return date.today().isoformat()


@_integrity
def grant_access(c, p: Principal, user_id: int, role_code: str, *, group_id: int | None = None, cocd: str | None = None,
                 include_descendants: bool = False, valid_from: str | None = None, valid_to: str | None = None,
                 exclude=()) -> dict:
    if not p.can("admin"):
        raise ServiceError("Only an administrator can grant company access", 403)
    if (group_id is None) == (cocd is None):
        raise ServiceError("Grant access to either a corporate group or a single company")
    if c.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone() is None:
        raise ServiceError("User does not exist", 404)
    if c.execute("SELECT 1 FROM company_roles WHERE role_code=?", (role_code,)).fetchone() is None:
        raise ServiceError(f"Unknown role '{role_code}'", 404)
    if group_id is not None:
        if c.execute("SELECT 1 FROM corporate_groups WHERE id=?", (group_id,)).fetchone() is None:
            raise ServiceError("Corporate group does not exist", 404)
        if include_descendants:
            raise ServiceError("A group grant already covers every company of the group")
    else:
        corporate._company(c, cocd)
    frm = check_date(valid_from or _today(), "Valid from")
    to = check_date(valid_to, "Valid to") if valid_to else None
    cur = c.execute("""INSERT INTO company_user_access(user_id,scope,group_id,cocd,include_descendants,role_code,valid_from,
                       valid_to,granted_by) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (user_id, "group" if group_id is not None else "company", group_id, cocd,
                     1 if include_descendants else 0, role_code, frm, to, p.username))
    for x in exclude:
        corporate._company(c, x)
        c.execute("INSERT INTO company_access_exclusions(access_id,cocd) VALUES (?,?)", (cur.lastrowid, x))
    audit(c, p.username, "access_grant", "company_user_access", cur.lastrowid,
          f"user {user_id} {role_code} {'group ' + str(group_id) if group_id is not None else cocd}", cocd=cocd)
    return dict(c.execute("SELECT * FROM company_user_access WHERE id=?", (cur.lastrowid,)).fetchone())


def revoke_access(c, p: Principal, access_id: int) -> None:
    if not p.can("admin"):
        raise ServiceError("Only an administrator can revoke company access", 403)
    r = c.execute("SELECT * FROM company_user_access WHERE id=?", (access_id,)).fetchone()
    if r is None:
        raise ServiceError("Access grant not found", 404)
    if r["revoked_at"]:
        raise ServiceError("This grant is already revoked", 409)
    c.execute("UPDATE company_user_access SET revoked_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), revoked_by=? WHERE id=?",
              (p.username, access_id))
    audit(c, p.username, "access_revoke", "company_user_access", access_id, cocd=r["cocd"])


def list_access(c, user_id: int) -> list[dict]:
    return [dict(r) for r in c.execute("SELECT * FROM company_user_access WHERE user_id=? ORDER BY id", (user_id,))]


def accessible_companies(c, user_id: int, as_of: str | None = None) -> dict[str, set[str]]:
    """company code -> the set of role codes through which this user may act on it, on the given date."""
    d = as_of or _today()
    u = c.execute("SELECT active FROM users WHERE id=?", (user_id,)).fetchone()
    if u is None or not u["active"]:
        return {}
    out: dict[str, set[str]] = {}
    grants = c.execute("""SELECT * FROM company_user_access WHERE user_id=? AND revoked_at IS NULL AND valid_from <= ?
                          AND (valid_to IS NULL OR valid_to > ?)""", (user_id, d, d)).fetchall()
    for g in grants:
        if g["scope"] == "group":
            covered = {r[0] for r in c.execute("SELECT cocd FROM companies WHERE group_id=?", (g["group_id"],))}
        else:
            covered = {g["cocd"]}
            if g["include_descendants"]:
                covered |= set(corporate.descendants(c, g["cocd"], d))
        for (x,) in c.execute("SELECT cocd FROM company_access_exclusions WHERE access_id=?", (g["id"],)):
            covered -= {x} | set(corporate.descendants(c, x, d))
        for co in covered:
            out.setdefault(co, set()).add(g["role_code"])
    return out


def permissions_for(c, user_id: int, cocd: str, as_of: str | None = None) -> set[tuple[str, str]]:
    roles = accessible_companies(c, user_id, as_of).get(cocd, set())
    if not roles:
        return set()
    q = ",".join("?" * len(roles))
    return {(r[0], r[1]) for r in c.execute(
        f"SELECT module, action FROM company_role_permissions WHERE role_code IN ({q})", sorted(roles))}


def can(c, user_id: int, cocd: str, module: str, action: str, as_of: str | None = None) -> bool:
    return (module, action) in permissions_for(c, user_id, cocd, as_of)


def require(c, p: Principal, cocd: str, module: str, action: str, as_of: str | None = None) -> None:
    """Raises 403 unless the user may perform `action` in `module` for company `cocd`. There is no silent
    global-admin bypass: platform administrators need an explicit grant to work inside a company."""
    if not can(c, p.user_id, cocd, module, action, as_of):
        raise ServiceError(f"You do not have {action} access to {module} for company {cocd}", 403)
