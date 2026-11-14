"""ERP Phase 1: corporate groups, nested ownership, effective-dated history, database-enforced integrity."""
import sqlite3, threading
import pytest
from finora.server import corporate as K, services as S
from finora.server.db import Database

ADMIN = S.Principal(1, "admin", "admin")


@pytest.fixture
def cdb(tmp_path):
    d = Database(tmp_path / "corp.db"); S.seed_defaults(d)
    with d.tx() as c:
        c.execute("INSERT INTO coa(coa,description) VALUES ('C','chart')")
    return d


def mk(db, *codes, group_id=None):
    with db.tx() as c:
        for code in codes:
            c.execute("INSERT INTO companies(cocd,name,currency,coa,group_id) VALUES (?,?,?,?,?)",
                      (code, f"{code} Corp", "PHP", "C", group_id))


def own(db, parent, child, pct="100", voting_pct=None, **kw):
    with db.tx() as c:
        return K.record_ownership(c, ADMIN, parent, child, pct, voting_pct, **kw)


ABC = [("ABC", "ABC-MFG"), ("ABC", "ABC-TRD"), ("ABC", "ABC-LOG"), ("ABC-MFG", "ABC-COMP"), ("ABC-MFG", "ABC-IND"),
       ("ABC-COMP", "ABC-PLA"), ("ABC-COMP", "ABC-PKG"), ("ABC-TRD", "ABC-DIS"), ("ABC-TRD", "ABC-RET"),
       ("ABC-LOG", "ABC-WHS"), ("ABC-LOG", "ABC-TRN")]


@pytest.fixture
def abc(cdb):
    mk(cdb, "ABC", *{c for _, c in ABC})
    for p, ch in ABC:
        own(cdb, p, ch, "100", effective_from="2020-01-01")
    return cdb


def test_holding_with_nested_subsidiaries_matches_the_brief(abc):
    with abc.read() as c:
        gid = c.execute("SELECT group_id FROM companies WHERE cocd='ABC'").fetchone()[0]
        tree = K.hierarchy(c, gid, "2026-01-01")
        assert [n["cocd"] for n in tree] == ["ABC"]
        root = tree[0]
        assert root["subsidiary_count"] == 11 and K.group_stats(c, gid)["max_depth"] == 3
        mfg = next(n for n in root["children"] if n["cocd"] == "ABC-MFG")
        assert mfg["subsidiary_count"] == 4 and mfg["ownership_pct"] == "100.00"
        assert K.descendants(c, "ABC", "2026-01-01")["ABC-PLA"] == 3
        assert K.ancestors(c, "ABC-PLA", "2026-01-01") == {"ABC-COMP": 1, "ABC-MFG": 2, "ABC": 3}
        assert K.ultimate_parents(c, "ABC-PLA", "2026-01-01") == ["ABC"]
        assert K.ultimate_parents(c, "ABC", "2026-01-01") == ["ABC"]


def test_companies_created_through_the_existing_api_land_in_the_default_group(cdb):
    with cdb.tx() as c:
        S.master_create(c, ADMIN, "companies", dict(cocd="X1", name="Legacy API Co", currency="USD", coa="C"))
    with cdb.read() as c:
        r = c.execute("SELECT g.code, co.legal_name, co.status FROM companies co JOIN corporate_groups g ON g.id=co.group_id WHERE cocd='X1'").fetchone()
    assert tuple(r) == ("DEFAULT", "Legacy API Co", "active")


def test_nesting_depth_is_unlimited_and_long_cycles_are_still_caught(cdb):
    n = 150
    codes = [f"N{i:03d}" for i in range(n)]
    mk(cdb, *codes)
    with cdb.tx() as c:
        for a, b in zip(codes, codes[1:]):
            K.record_ownership(c, ADMIN, a, b, "100", effective_from="2020-01-01")
    with cdb.read() as c:
        assert K.descendants(c, codes[0], "2026-01-01")[codes[-1]] == n - 1
        assert K.ultimate_parents(c, codes[-1], "2026-01-01") == [codes[0]]
    with pytest.raises(S.ServiceError, match="circular"):
        own(cdb, codes[-1], codes[0], "100", effective_from="2020-01-01")       # closes a 149-link loop


@pytest.mark.parametrize("edges,bad", [([], ("A", "A")), ([("A", "B")], ("B", "A")),
                                       ([("A", "B"), ("B", "C"), ("C", "D")], ("D", "A")),
                                       ([("A", "B"), ("B", "C")], ("C", "A"))])
def test_circular_and_self_ownership_are_rejected(cdb, edges, bad):
    mk(cdb, "A", "B", "C", "D")
    for p, ch in edges:
        own(cdb, p, ch, "50", effective_from="2020-01-01")
    with pytest.raises(S.ServiceError, match="circular|cannot own itself"):
        own(cdb, *bad, "10", effective_from="2020-01-01")


def test_database_itself_rejects_a_cycle_even_if_the_service_layer_is_bypassed(cdb):
    mk(cdb, "A", "B")
    own(cdb, "A", "B", "50", effective_from="2020-01-01")
    with pytest.raises(sqlite3.IntegrityError, match="circular"):
        with cdb.tx() as c:
            c.execute("INSERT INTO company_ownership(parent_company,child_company,ownership_bp,voting_bp,effective_from,recorded_by)"
                      " VALUES ('B','A',100,100,'2021-01-01','raw sql')")


def test_a_historical_ownership_in_the_opposite_direction_is_not_a_cycle(cdb):
    """A sold B in 2022, and B bought A in 2023: no date has both directions, so it is legitimate history."""
    mk(cdb, "A", "B")
    own(cdb, "A", "B", "100", effective_from="2020-01-01", effective_to="2022-01-01")
    own(cdb, "B", "A", "100", effective_from="2023-01-01")
    with cdb.read() as c:
        assert K.ultimate_parents(c, "A", "2021-06-01") == ["A"] and K.ultimate_parents(c, "B", "2021-06-01") == ["A"]
        assert K.ultimate_parents(c, "A", "2024-01-01") == ["B"]
    with pytest.raises(S.ServiceError, match="circular"):
        own(cdb, "B", "A", "5", effective_from="2020-06-01", effective_to="2021-06-01")  # overlaps A->B


def test_ownership_change_keeps_history_and_answers_as_of_any_date(cdb):
    mk(cdb, "P", "S")
    first = own(cdb, "P", "S", "100", effective_from="2020-01-01", acquisition_date="2020-01-01")
    with cdb.tx() as c:
        new = K.change_ownership(c, ADMIN, "P", "S", "60", "55", effective_from="2024-01-01", note="sold 40% to investors")
    with cdb.read() as c:
        hist = K.ownership_history(c, "S")
        assert [(h["ownership_pct"], h["effective_from"], h["effective_to"]) for h in hist] == [
            ("100.00", "2020-01-01", "2024-01-01"), ("60.00", "2024-01-01", None)]
        assert hist[1]["voting_pct"] == "55.00" and hist[1]["note"] == "sold 40% to investors"
        assert K.children(c, "P", "2023-06-01")[0]["ownership_pct"] == "100.00"
        assert K.children(c, "P", "2024-06-01")[0]["ownership_pct"] == "60.00"
        assert K.children(c, "P", "2019-06-01") == []
        assert K.effective_ownership_bp(c, "P", "S", "2024-06-01") == 6000
    assert first["id"] != new["id"]


def test_ownership_history_cannot_be_rewritten_or_deleted(cdb):
    mk(cdb, "P", "S"); rec = own(cdb, "P", "S", "80", effective_from="2020-01-01")
    for sql in ("UPDATE company_ownership SET ownership_bp=1", "UPDATE company_ownership SET effective_from='2019-01-01'",
                "UPDATE company_ownership SET parent_company='S', child_company='P'", "DELETE FROM company_ownership"):
        with pytest.raises(sqlite3.IntegrityError, match="history"):
            with cdb.tx() as c:
                c.execute(sql)
    with cdb.tx() as c:
        K.close_ownership(c, ADMIN, rec["id"], "2025-01-01")                       # closing earlier is allowed
    with pytest.raises(sqlite3.IntegrityError):
        with cdb.tx() as c:
            c.execute("UPDATE company_ownership SET effective_to='2030-01-01'")    # extending is not


def test_voiding_a_mistake_keeps_the_record_and_frees_the_slot(cdb):
    mk(cdb, "P", "S"); wrong = own(cdb, "P", "S", "30", effective_from="2020-01-01")
    with cdb.tx() as c:
        K.void_ownership(c, ADMIN, wrong["id"], "typed 30 instead of 60")
    own(cdb, "P", "S", "60", effective_from="2020-01-01")                         # same key is free again
    with cdb.read() as c:
        assert len(K.ownership_history(c, "S")) == 2 and len(K.ownership_history(c, "S", include_voided=False)) == 1
        assert K.ownership_history(c, "S")[0]["void_reason"] == "typed 30 instead of 60"
    with pytest.raises(S.ServiceError, match="reason"):
        with cdb.tx() as c:
            K.void_ownership(c, ADMIN, wrong["id"], " ")


def test_total_ownership_and_voting_cannot_exceed_100_percent(cdb):
    mk(cdb, "A", "B", "C", "J")
    own(cdb, "A", "J", "50", effective_from="2020-01-01"); own(cdb, "B", "J", "50", effective_from="2020-01-01")  # 50/50 joint venture
    with pytest.raises(S.ServiceError, match="exceed 100%"):
        own(cdb, "C", "J", "1", effective_from="2020-01-01")
    with pytest.raises(S.ServiceError, match="exceed 100%"):
        own(cdb, "C", "J", "1", effective_from="2030-01-01")                      # still over in the future
    mk(cdb, "V")
    own(cdb, "A", "V", "10", "70", effective_from="2020-01-01")
    with pytest.raises(S.ServiceError, match="voting control"):
        own(cdb, "B", "V", "10", "31", effective_from="2020-01-01")
    own(cdb, "B", "V", "10", "30", effective_from="2020-01-01")                   # exactly 100% of votes is fine


def test_an_overlap_in_the_future_is_detected_but_sequential_periods_are_fine(cdb):
    mk(cdb, "A", "B", "S")
    first = own(cdb, "A", "S", "60", effective_from="2020-01-01")
    with pytest.raises(S.ServiceError, match="exceed 100%"):
        own(cdb, "B", "S", "50", effective_from="2025-01-01")
    with cdb.tx() as c:
        K.close_ownership(c, ADMIN, first["id"], "2025-01-01")
    own(cdb, "B", "S", "50", effective_from="2025-01-01")                         # A left, B arrives: no overlap


def test_indirect_ownership_sums_every_path(cdb):
    mk(cdb, "A", "B", "C")
    own(cdb, "A", "B", "60", effective_from="2020-01-01"); own(cdb, "B", "C", "50", effective_from="2020-01-01")
    own(cdb, "A", "C", "30", effective_from="2020-01-01")
    with cdb.read() as c:
        assert K.effective_ownership_bp(c, "A", "C", "2026-01-01") == 6000        # 60% x 50% + 30%
        assert K.effective_ownership_bp(c, "A", "B", "2026-01-01") == 6000
        assert K.effective_ownership_bp(c, "C", "A", "2026-01-01") == 0
        assert K.ultimate_parents(c, "C", "2026-01-01") == ["A"]


def test_percentages_are_validated(cdb):
    mk(cdb, "A", "B")
    for bad in ("100.01", "-1", "abc", "10.005"):
        with pytest.raises(S.ServiceError):
            own(cdb, "A", "B", bad)
    with pytest.raises(S.ServiceError, match="does not exist"):
        own(cdb, "A", "NOPE", "10")
    with pytest.raises(S.ServiceError, match="Relationship"):
        own(cdb, "A", "B", "10", relationship="friend")
    j = own(cdb, "A", "B", "33.33", relationship="joint_venture", effective_from="2020-01-01")
    assert j["ownership_bp"] == 3333 and j["voting_pct"] == "33.33"


def test_ownership_must_stay_inside_one_corporate_group(cdb):
    with cdb.tx() as c:
        g2 = K.create_group(c, ADMIN, "G2", "Second group")["id"]
    mk(cdb, "A1", "A2"); mk(cdb, "B1", group_id=g2)
    own(cdb, "A1", "A2", "100", effective_from="2020-01-01")
    with pytest.raises(S.ServiceError, match="same corporate group"):
        own(cdb, "A1", "B1", "100", effective_from="2020-01-01")
    with pytest.raises(S.ServiceError, match="still has ownership"):
        with cdb.tx() as c:
            K.move_company_to_group(c, ADMIN, "A2", g2)                            # would split an existing ownership link
    with cdb.read() as c:
        default_id = c.execute("SELECT id FROM corporate_groups WHERE code='DEFAULT'").fetchone()[0]
    with cdb.tx() as c:
        K.move_company_to_group(c, ADMIN, "B1", default_id)                        # B1 has no links: may move
    with cdb.read() as c:
        assert {g["code"]: g["company_count"] for g in K.list_groups(c)} == {"DEFAULT": 3, "G2": 0}


def test_reporting_lines_are_separate_from_legal_ownership(cdb):
    mk(cdb, "H", "M", "S")
    own(cdb, "M", "S", "100", effective_from="2020-01-01")                         # legally owned by M ...
    with cdb.tx() as c:
        K.record_reporting_line(c, ADMIN, "S", "H", "2020-01-01")                  # ... but operationally reports to H
    with cdb.read() as c:
        assert K.reporting_children(c, "H", "2026-01-01") == ["S"]
        assert [e["parent_company"] for e in K.parents(c, "S", "2026-01-01")] == ["M"]
    with pytest.raises(S.ServiceError, match="only one company at a time"):
        with cdb.tx() as c:
            K.record_reporting_line(c, ADMIN, "S", "M", "2021-01-01")
    with pytest.raises(S.ServiceError, match="circular"):
        with cdb.tx() as c:
            K.record_reporting_line(c, ADMIN, "H", "S", "2020-01-01")
    with cdb.tx() as c:
        K.close_reporting_line(c, ADMIN, 1, "2023-01-01")
        K.record_reporting_line(c, ADMIN, "S", "M", "2023-01-01")                   # re-assigned from 2023
    with cdb.read() as c:
        assert K.reporting_children(c, "M", "2024-01-01") == ["S"] and K.reporting_children(c, "H", "2024-01-01") == []


def test_company_status_and_dates_are_validated(cdb):
    mk(cdb, "A")
    with cdb.tx() as c:
        K.set_company_profile(c, ADMIN, "A", legal_name="A Holdings Inc.", status="dissolved", incorporated_on="2000-01-01", dissolved_on="2020-12-31")
    with pytest.raises(S.ServiceError, match="Status"):
        with cdb.tx() as c:
            K.set_company_profile(c, ADMIN, "A", status="bankrupt")
    with pytest.raises(sqlite3.IntegrityError, match="invalid company status"):
        with cdb.tx() as c:
            c.execute("UPDATE companies SET status='zombie' WHERE cocd='A'")
    with pytest.raises(sqlite3.IntegrityError, match="invalid company dates"):
        with cdb.tx() as c:
            c.execute("UPDATE companies SET dissolved_on='1999-01-01' WHERE cocd='A'")
    with cdb.read() as c:
        gid = c.execute("SELECT group_id FROM companies WHERE cocd='A'").fetchone()[0]
        assert K.group_stats(c, gid)["by_status"] == {"dissolved": 1}


def test_audit_log_records_the_company(cdb):
    mk(cdb, "P", "S"); own(cdb, "P", "S", "100", effective_from="2020-01-01")
    with cdb.read() as c:
        rows = c.execute("SELECT action, cocd FROM audit_log WHERE entity='company_ownership'").fetchall()
    assert [tuple(r) for r in rows] == [("ownership_record", "S")]


def test_two_users_cannot_create_a_cycle_by_acting_at_the_same_time(cdb):
    mk(cdb, "A", "B")
    results, barrier = [], threading.Barrier(2)

    def worker(p, ch):
        barrier.wait()
        try:
            with cdb.tx() as c:
                K.record_ownership(c, ADMIN, p, ch, "50", effective_from="2020-01-01")
            results.append("ok")
        except S.ServiceError as e:
            results.append(str(e))
    ts = [threading.Thread(target=worker, args=("A", "B")), threading.Thread(target=worker, args=("B", "A"))]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count("ok") == 1 and any("circular" in r for r in results)
