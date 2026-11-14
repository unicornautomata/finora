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
        c.execute("INSERT INTO companies(cocd,name,currency,coa,tax_id) VALUES ('1000','Acme','USD','C1',NULL)")
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


# ---- helpers shared by the UI tests
import socket
import time


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until(cond, secs: float = 8.0) -> bool:
    from PyQt6.QtTest import QTest
    end = time.time() + secs
    while time.time() < end:
        QTest.qWait(25)
        if cond():
            return True
    return False


@pytest.fixture(autouse=True)
def isolated_qsettings(tmp_path, monkeypatch):
    """Never touch real user settings (the registry on Windows) from tests."""
    from PyQt6.QtCore import QSettings
    from finora.client import settings
    path = str(tmp_path / "settings.ini")
    monkeypatch.setattr(settings, "app_settings", lambda: QSettings(path, QSettings.Format.IniFormat))


@pytest.fixture
def live_server(tmp_path, monkeypatch):
    """A real FINORA server on a free port with a known admin password."""
    monkeypatch.setenv("FINORA_ADMIN_PASSWORD", "test-admin-pass")
    from finora.server.host import ServerThread
    port = free_port()
    srv = ServerThread(str(tmp_path / "live.db"), port=port)
    srv.start()
    assert srv.wait_ready()
    srv.url = f"http://127.0.0.1:{port}"
    yield srv
    srv.stop()
