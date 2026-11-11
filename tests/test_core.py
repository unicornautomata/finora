import sqlite3, threading
import pytest
from fastapi.testclient import TestClient
from ledger.server import services as S
from ledger.server.api import build_app
from conftest import entry


def make(db, me, **kw):
    with db.tx() as c:
        return S.journal_create(c, me, entry(**kw))


def test_post_assigns_gapless_numbers(db, me):
    nums = []
    for _ in range(3):
        j = make(db, me)
        with db.tx() as c:
            nums.append(S.journal_post(c, me, j["id"])["doc_no"])
    assert nums == ["GJ-000001", "GJ-000002", "GJ-000003"]


def test_unbalanced_cannot_post(db, me):
    j = make(db, me, b="90.00")
    with pytest.raises(S.ServiceError, match="out of balance.*difference 10.00"):
        with db.tx() as c:
            S.journal_post(c, me, j["id"])
    with db.read() as c:
        assert S.journal_get(c, j["id"])["status"] == "draft"


def test_database_blocks_unbalanced_post_even_if_service_bypassed(db, me):
    j = make(db, me, b="90.00")
    with pytest.raises(sqlite3.IntegrityError, match="not balanced"):
        with db.tx() as c:
            c.execute("UPDATE journal_headers SET status='posted' WHERE id=?", (j["id"],))


def test_posted_is_immutable_in_database(db, me):
    j = make(db, me)
    with db.tx() as c:
        S.journal_post(c, me, j["id"])
    for sql in ("UPDATE journal_lines SET debit_minor=5 WHERE header_id=?",
                "DELETE FROM journal_lines WHERE header_id=?",
                "UPDATE journal_headers SET description='x' WHERE id=?",
                "DELETE FROM journal_headers WHERE id=?"):
        with pytest.raises(sqlite3.IntegrityError, match="immutable|cannot be deleted"):
            with db.tx() as c:
                c.execute(sql, (j["id"],))


def test_reverse_nets_to_zero_and_links(db, me):
    j = make(db, me)
    with db.tx() as c:
        S.journal_post(c, me, j["id"])
        rev = S.journal_reverse(c, me, j["id"])
    with db.read() as c:
        orig = S.journal_get(c, j["id"])
        tb = S.trial_balance(c, "1000")
    assert orig["status"] == "reversed" and orig["reversed_by_id"] == rev["id"]
    assert rev["status"] == "posted" and rev["reverses_id"] == j["id"]
    assert all(r["balance"] == "0.00" for r in tb["rows"]) and tb["balanced"]
    with pytest.raises(S.ServiceError):
        with db.tx() as c:
            S.journal_reverse(c, me, j["id"])


def test_line_rules(db, me):
    with pytest.raises(S.ServiceError, match="not both"):
        make(db, me, lines=[dict(glcd="1000", debit="1", credit="1"), dict(glcd="4000", credit="1")])
    with pytest.raises(S.ServiceError, match="does not exist"):
        make(db, me, lines=[dict(glcd="9999", debit="1"), dict(glcd="4000", credit="1")])
    with pytest.raises(S.ServiceError, match="2 decimal"):
        make(db, me, a="1.005")


def test_optimistic_locking(db, me):
    j = make(db, me)
    with db.tx() as c:
        S.journal_update(c, me, j["id"], dict(description="by A", version=j["version"]))
    with pytest.raises(S.ServiceError, match="changed by someone else"):
        with db.tx() as c:
            S.journal_update(c, me, j["id"], dict(description="by B", version=j["version"]))


def test_concurrent_posting_never_duplicates_numbers(db, me):
    ids = [make(db, me)["id"] for _ in range(20)]
    results, errors = [], []

    def worker(chunk):
        for i in chunk:
            try:
                with db.tx() as c:
                    results.append(S.journal_post(c, me, i)["doc_no"])
            except Exception as ex:
                errors.append(ex)

    ts = [threading.Thread(target=worker, args=(ids[k::4],)) for k in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errors
    assert sorted(results) == [f"GJ-{n:06d}" for n in range(1, 21)]


def test_login_lockout_and_roles(db):
    with db.tx() as c:
        S.master_create(c, S.Principal(1, "admin", "admin"), "users",
                        dict(username="vic", role="viewer", password="pw-123456"))
    for _ in range(S.MAX_FAILED):
        with pytest.raises(S.ServiceError):
            S.login(db, "vic", "wrong")
    with pytest.raises(S.ServiceError, match="locked"):
        S.login(db, "vic", "pw-123456")


def test_api_end_to_end_and_permissions(db, monkeypatch):
    app = build_app(db)
    cl = TestClient(app)
    with db.tx() as c:
        S.master_create(c, S.Principal(1, "admin", "admin"), "users",
                        dict(username="vic", role="viewer", password="pw-123456"))
        S.master_create(c, S.Principal(1, "admin", "admin"), "users",
                        dict(username="amy", role="accountant", password="pw-123456"))
    assert cl.get("/journals").status_code == 401
    tok = lambda u: {"Authorization": "Bearer " + cl.post("/auth/login", json=dict(username=u, password="pw-123456")).json()["token"]}
    amy, vic = tok("amy"), tok("vic")
    r = cl.post("/journals", json=entry(), headers=amy)
    assert r.status_code == 201
    jid = r.json()["id"]
    assert cl.post("/journals", json=entry(), headers=vic).status_code == 403
    assert cl.get(f"/journals/{jid}", headers=vic).status_code == 200
    assert cl.post(f"/journals/{jid}/post", headers=amy).json()["doc_no"] == "GJ-000001"
    assert cl.put(f"/journals/{jid}", json=dict(description="x"), headers=amy).status_code == 409
    assert cl.get("/master/users", headers=amy).status_code == 403
    assert cl.get("/reports/trial-balance?cocd=1000", headers=vic).json()["balanced"] is True
    meta = cl.get("/meta", headers=vic).json()
    assert "users" not in meta["entities"] and "document" in meta
    assert cl.get("/master/gl_accounts;DROP", headers=vic).status_code == 404  # unknown entity, no SQL built
