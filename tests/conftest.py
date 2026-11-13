import os, sys, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from finora.server.db import Database
from finora.server import services as S


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "t.db")
    S.seed_defaults(d)
    with d.tx() as c:
        c.execute("INSERT INTO coa VALUES ('C1','Main')")
        c.execute("INSERT INTO gl_types VALUES ('AST','Assets','C1','D'),('REV','Revenue','C1','C')")
        c.executemany("INSERT INTO gl_accounts(glcd,description,gltype) VALUES (?,?,?)",
                      [("1000", "Cash", "AST"), ("4000", "Sales", "REV"), ("1200", "Receivables", "AST")])
        c.execute("INSERT INTO companies VALUES ('1000','Acme','USD','C1',NULL)")
    return d


@pytest.fixture
def me(db):
    with db.read() as c:
        r = c.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    return S.Principal(r["id"], "admin", "admin")


def entry(a="100.00", b="100.00", **kw):
    d = dict(cocd="1000", doctype="GJ", doc_date="2026-11-09", posting_date="2026-11-09", description="t",
             lines=[dict(glcd="1000", debit=a, credit="0"), dict(glcd="4000", debit="0", credit=b)])
    d.update(kw)
    return d


# ---- Qt fixtures (offscreen so tests run on CI and Windows without a display)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from finora.client import design
    design.apply_theme(app, "light")
    return app
