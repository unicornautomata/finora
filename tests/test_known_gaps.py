"""KNOWN GAPS found by the ERP Phase 1 audit. Each test states the behaviour the finished platform must have.
They are strict xfails: they fail today on purpose, and the day a phase fixes the gap the test will report
XPASS(strict) and force this file to be updated, so a fixed gap cannot be forgotten and a regression cannot hide."""
import pytest
from fastapi.testclient import TestClient
from finora.server import services as S
from finora.server.api import build_app
from finora.server.db import Database

ADMIN = S.Principal(1, "admin", "admin")


@pytest.fixture
def two_charts(tmp_path):
    d = Database(tmp_path / "gap.db"); S.seed_defaults(d)
    with d.tx() as c:
        for coa, t, gl in (("A", "TA", "A100"), ("B", "TB", "B100")):
            S.master_create(c, ADMIN, "coa", dict(coa=coa, description=f"chart {coa}"))
            S.master_create(c, ADMIN, "gl_types", dict(gltype=t, coa=coa, normal_side="D"))
            S.master_create(c, ADMIN, "gl_accounts", dict(glcd=gl, description=f"{coa} only", gltype=t))
        S.master_create(c, ADMIN, "companies", dict(cocd="CA", name="Co A", currency="USD", coa="A"))
        S.master_create(c, ADMIN, "companies", dict(cocd="CB", name="Co B", currency="USD", coa="B"))
    return d


@pytest.mark.xfail(strict=True, reason="F1: a journal can use an account from another company's chart. Fix: ERP Phase 3 (company-specific CoA).")
def test_company_cannot_post_to_an_account_of_another_charts(two_charts):
    with pytest.raises(S.ServiceError):
        with two_charts.tx() as c:
            S.journal_create(c, ADMIN, dict(cocd="CA", doctype="GJ", doc_date="2026-11-01", posting_date="2026-11-01",
                                            lines=[dict(glcd="B100", debit="10.00"), dict(glcd="A100", credit="10.00")]))


@pytest.mark.xfail(strict=True, reason="F2: HTTP endpoints do not check company access. Fix: ERP Phase 2 (company context + scoping).")
def test_user_without_access_cannot_read_another_companys_journal(two_charts):
    with two_charts.tx() as c:
        j = S.journal_create(c, ADMIN, dict(cocd="CB", doctype="GJ", doc_date="2026-11-01", posting_date="2026-11-01",
                                            lines=[dict(glcd="B100", debit="10.00"), dict(glcd="B100", credit="10.00")]))
        S.master_create(c, ADMIN, "users", dict(username="eve", role="accountant", password="pw-123456"))
    client = TestClient(build_app(two_charts))
    tok = client.post("/auth/login", json=dict(username="eve", password="pw-123456")).json()["token"]
    r = client.get(f"/journals/{j['id']}", headers={"Authorization": "Bearer " + tok})
    assert r.status_code == 403            # today: 200, because eve was never granted any company


@pytest.mark.xfail(strict=True, reason="F2: company-filtered lists are not enforced server-side. Fix: ERP Phase 2.")
def test_journal_list_only_shows_companies_the_user_may_access(two_charts):
    with two_charts.tx() as c:
        S.journal_create(c, ADMIN, dict(cocd="CB", doctype="GJ", doc_date="2026-11-01", posting_date="2026-11-01",
                                        lines=[dict(glcd="B100", debit="10.00"), dict(glcd="B100", credit="10.00")]))
        S.master_create(c, ADMIN, "users", dict(username="eve", role="accountant", password="pw-123456"))
    client = TestClient(build_app(two_charts))
    tok = client.post("/auth/login", json=dict(username="eve", password="pw-123456")).json()["token"]
    assert client.get("/journals", headers={"Authorization": "Bearer " + tok}).json() == []
