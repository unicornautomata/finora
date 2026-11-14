"""When the server rejects the session, the main window asks for the password in place and keeps unsaved work."""
import pytest
from PyQt6.QtTest import QTest
from finora.client import shell as shell_mod
from finora.client.api_client import ApiClient
from finora.client.components import dialogs
from finora.client.shell import Shell
from conftest import wait_until


class _Env:
    pass


@pytest.fixture
def env(qapp, live_server, monkeypatch):
    e = _Env()
    e.errors, e.logouts = [], []
    monkeypatch.setattr(dialogs, "error", lambda parent, text, *a, **k: e.errors.append(text))
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: True)
    e.srv = live_server
    e.client = ApiClient(live_server.url); e.client.login("admin", "test-admin-pass")
    e.win = Shell(e.client, e.client.meta(), on_logout=lambda: e.logouts.append(1)); e.win.show()
    e.screen = e.win.tabs.currentWidget()
    assert wait_until(lambda: hasattr(e.screen, "tbl"))
    e.screen._touch()                                              # unsaved work
    assert e.screen.dirty
    yield e
    e.win.close()


def expire(env):
    with env.srv.db.tx() as c:
        c.execute("DELETE FROM sessions")


def test_expired_session_reauthenticates_in_place(env, monkeypatch):
    calls = []

    class FakeReauth:
        def __init__(self, client, parent=None): self.client = client
        def exec(self):
            calls.append(1); self.client.login("admin", "test-admin-pass"); return True
    monkeypatch.setattr(shell_mod, "ReauthDialog", FakeReauth)
    old = env.client.token
    expire(env)
    # a real user action that fails with 401: its error callback reaches the window like any other error
    env.screen._call(lambda: env.client.journal(1), env.screen._load)
    assert wait_until(lambda: calls)
    assert wait_until(lambda: not env.client.session_expired)
    assert env.client.token != old
    assert env.screen.dirty, "unsaved edits must survive re-authentication"
    assert env.win.isVisible() and not env.logouts
    QTest.qWait(300)                                               # let the failed request's error callback arrive
    assert not env.errors, f"no pop-up errors while the session is being renewed: {env.errors}"
    assert env.client.master_list("companies") == []               # requests work again


def test_cancelling_reauth_signs_out(env, monkeypatch):
    class Cancel:
        def __init__(self, client, parent=None): pass
        def exec(self): return False
    monkeypatch.setattr(shell_mod, "ReauthDialog", Cancel)
    expire(env)
    env.win.refs.invalidate("companies")
    assert wait_until(lambda: env.logouts)
    assert env.client.token is None and not env.win.isVisible()


def test_login_requests_do_not_trigger_the_expiry_hook(qapp, live_server):
    c = ApiClient(live_server.url); fired = []
    c.on_unauthorized = lambda: fired.append(1)
    with pytest.raises(Exception):
        c.login("admin", "wrong")                                  # a 401 from /auth/login is a bad password, not an expiry
    assert not fired and not c.session_expired
