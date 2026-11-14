"""Company-scoped access rules (model and resolution). Nothing is inherited implicitly."""
import sqlite3
import pytest
from finora.server import access as A, corporate as K, services as S
from finora.server.db import Database
from test_corporate_hierarchy import ABC, ADMIN, mk, own

TODAY = "2026-11-14"


@pytest.fixture
def world(tmp_path):
    d = Database(tmp_path / "acc.db"); S.seed_defaults(d)
    with d.tx() as c:
        c.execute("INSERT INTO coa(coa,description) VALUES ('C','chart')")
    mk(d, "ABC", *{c for _, c in ABC})
    for p, ch in ABC:
        own(d, p, ch, "100", effective_from="2020-01-01")
    with d.tx() as c:
        users = {n: S.master_create(c, ADMIN, "users", dict(username=n, role="accountant", password="pw-123456"))["username"] for n in ("ann", "bob", "cy")}
    with d.read() as c:
        ids = {r["username"]: r["id"] for r in c.execute("SELECT id, username FROM users")}
        gid = c.execute("SELECT group_id FROM companies WHERE cocd='ABC'").fetchone()[0]
    d.ids, d.gid = ids, gid
    return d


def grant(db, who, role, **kw):
    with db.tx() as c:
        return A.grant_access(c, ADMIN, db.ids[who], role, **kw)


def seen(db, who, d=TODAY):
    with db.read() as c:
        return set(A.accessible_companies(c, db.ids[who], d))


def test_access_to_a_parent_does_not_silently_include_its_subsidiaries(world):
    grant(world, "ann", "ACCOUNTANT", cocd="ABC-MFG")
    assert seen(world, "ann") == {"ABC-MFG"}


def test_descendants_are_included_only_when_explicitly_requested(world):
    grant(world, "ann", "ACCOUNTANT", cocd="ABC-MFG", include_descendants=True)
    assert seen(world, "ann") == {"ABC-MFG", "ABC-COMP", "ABC-IND", "ABC-PLA", "ABC-PKG"}


def test_an_exception_removes_a_company_and_everything_below_it(world):
    grant(world, "ann", "ACCOUNTANT", cocd="ABC-MFG", include_descendants=True, exclude=["ABC-COMP"])
    assert seen(world, "ann") == {"ABC-MFG", "ABC-IND"}


def test_group_wide_grant_covers_every_company_and_exceptions_still_apply(world):
    grant(world, "bob", "GROUP_ACCOUNTANT", group_id=world.gid)
    assert len(seen(world, "bob")) == 12
    grant(world, "cy", "AUDITOR", group_id=world.gid, exclude=["ABC-TRD"])
    assert seen(world, "cy") == set(seen(world, "bob")) - {"ABC-TRD", "ABC-DIS", "ABC-RET"}


def test_users_without_grants_see_nothing_and_inactive_users_lose_everything(world):
    assert seen(world, "ann") == set()
    grant(world, "ann", "ACCOUNTANT", cocd="ABC-TRD")
    with world.tx() as c:
        c.execute("UPDATE users SET active=0 WHERE username='ann'")
    assert seen(world, "ann") == set()


def test_access_can_expire_start_later_and_be_revoked(world):
    grant(world, "ann", "ACCOUNTANT", cocd="ABC-TRD", valid_from="2026-01-01", valid_to="2026-06-30")
    grant(world, "ann", "ACCOUNTANT", cocd="ABC-LOG", valid_from="2027-01-01")
    g3 = grant(world, "ann", "ACCOUNTANT", cocd="ABC-MFG", valid_from="2020-01-01")
    assert seen(world, "ann", "2026-03-01") == {"ABC-TRD", "ABC-MFG"}
    assert seen(world, "ann", "2026-07-01") == {"ABC-MFG"}                    # expired
    assert seen(world, "ann", "2027-02-01") == {"ABC-MFG", "ABC-LOG"}          # started later
    with world.tx() as c:
        A.revoke_access(c, ADMIN, g3["id"])
    assert seen(world, "ann", "2027-02-01") == {"ABC-LOG"}
    with pytest.raises(S.ServiceError, match="already revoked"):
        with world.tx() as c:
            A.revoke_access(c, ADMIN, g3["id"])


def test_access_follows_ownership_changes_over_time(world):
    """ABC-RET is sold on 2025-01-01: a descendants grant must stop covering it from that date."""
    rec = next(h for h in K.ownership_history(world.connect(), "ABC-RET"))
    with world.tx() as c:
        K.close_ownership(c, ADMIN, rec["id"], "2025-01-01")
    grant(world, "ann", "ACCOUNTANT", cocd="ABC-TRD", include_descendants=True, valid_from="2020-01-01")
    assert "ABC-RET" in seen(world, "ann", "2024-06-01") and "ABC-RET" not in seen(world, "ann", "2025-06-01")


def test_role_permissions_decide_what_a_user_may_do_in_each_company(world):
    grant(world, "ann", "ACCOUNTANT", cocd="ABC-TRD")
    grant(world, "ann", "WAREHOUSE_MANAGER", cocd="ABC-LOG")
    with world.read() as c:
        uid = world.ids["ann"]
        assert A.can(c, uid, "ABC-TRD", "finance", "post") and not A.can(c, uid, "ABC-TRD", "inventory", "read")
        assert A.can(c, uid, "ABC-LOG", "inventory", "write") and not A.can(c, uid, "ABC-LOG", "finance", "read")
        assert not A.can(c, uid, "ABC-MFG", "finance", "read")                 # no access to a company she was never given
        with pytest.raises(S.ServiceError) as e:
            A.require(c, S.Principal(uid, "ann", "accountant"), "ABC-MFG", "finance", "read")
        assert e.value.status == 403 and "ABC-MFG" in e.value.message
        A.require(c, S.Principal(uid, "ann", "accountant"), "ABC-TRD", "finance", "post")


def test_platform_admin_has_no_silent_bypass_into_company_data(world):
    with world.read() as c:
        assert not A.can(c, 1, "ABC-MFG", "finance", "read")                   # admin user, but never granted this company
    grant(world, "ann", "GROUP_ADMIN", group_id=world.gid)
    with world.read() as c:
        assert A.can(c, world.ids["ann"], "ABC-PLA", "admin", "admin")


def test_roles_overlap_by_union(world):
    grant(world, "ann", "ACCOUNTANT", cocd="ABC-TRD")
    grant(world, "ann", "SALES_MANAGER", cocd="ABC-TRD")
    with world.read() as c:
        assert A.accessible_companies(c, world.ids["ann"], TODAY)["ABC-TRD"] == {"ACCOUNTANT", "SALES_MANAGER"}
        assert A.can(c, world.ids["ann"], "ABC-TRD", "finance", "post") and A.can(c, world.ids["ann"], "ABC-TRD", "sales", "approve")


def test_grants_are_validated_and_only_admins_may_grant(world):
    with pytest.raises(S.ServiceError, match="company-level role"):
        grant(world, "ann", "ACCOUNTANT", group_id=world.gid)                    # a company role cannot be group-wide
    for kw, msg in ((dict(), "either"), (dict(cocd="ABC", group_id=1), "either"), (dict(group_id=world.gid, include_descendants=True), "already covers")):
        with pytest.raises(S.ServiceError, match=msg):
            grant(world, "ann", "AUDITOR", **kw)
    with pytest.raises(S.ServiceError, match="Unknown role"):
        grant(world, "ann", "OVERLORD", cocd="ABC")
    with pytest.raises(S.ServiceError, match="does not exist"):
        grant(world, "ann", "AUDITOR", cocd="NOPE")
    with pytest.raises(S.ServiceError) as e:
        with world.tx() as c:
            A.grant_access(c, S.Principal(world.ids["bob"], "bob", "accountant"), world.ids["ann"], "AUDITOR", cocd="ABC")
    assert e.value.status == 403


def test_grants_cannot_be_rewritten_only_revoked(world):
    g = grant(world, "ann", "ACCOUNTANT", cocd="ABC-TRD")
    for sql in ("UPDATE company_user_access SET role_code='GROUP_ADMIN'", "UPDATE company_user_access SET cocd='ABC'"):
        with pytest.raises(sqlite3.IntegrityError, match="cannot be rewritten"):
            with world.tx() as c:
                c.execute(sql)


def test_read_only_roles_can_only_read_and_every_role_has_permissions(world):
    with world.read() as c:
        for r in c.execute("SELECT role_code, is_read_only FROM company_roles"):
            acts = {a[0] for a in c.execute("SELECT DISTINCT action FROM company_role_permissions WHERE role_code=?", (r["role_code"],))}
            assert acts, r["role_code"]
            if r["is_read_only"]:
                assert acts == {"read"}, r["role_code"]
        assert {r[0] for r in c.execute("SELECT role_code FROM company_roles")} == {
            "GROUP_ADMIN", "GROUP_FINANCE_DIRECTOR", "GROUP_ACCOUNTANT", "COMPANY_ADMIN", "COMPANY_FINANCE_MANAGER", "ACCOUNTANT",
            "PROCUREMENT_MANAGER", "WAREHOUSE_MANAGER", "PRODUCTION_MANAGER", "SALES_MANAGER", "PROJECT_MANAGER", "AUDITOR", "VIEWER"}


def test_access_changes_are_audited_per_company(world):
    g = grant(world, "ann", "ACCOUNTANT", cocd="ABC-TRD")
    with world.tx() as c:
        A.revoke_access(c, ADMIN, g["id"])
    with world.read() as c:
        rows = [tuple(r) for r in c.execute("SELECT action, cocd FROM audit_log WHERE entity='company_user_access' ORDER BY id")]
    assert rows == [("access_grant", "ABC-TRD"), ("access_revoke", "ABC-TRD")]
