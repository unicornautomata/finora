"""The sign-in dialog against a real server: every outcome is shown inline, never as a pop-up."""
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog

from conftest import free_port, wait_until
from finora.client import settings
from finora.client.login import LoginDialog, ReauthDialog


def fill(dlg, url=None, user="admin", pw="test-admin-pass"):
    if url:
        dlg.url.setText(url)
    dlg.user.setText(user); dlg.pw.setText(pw)


def settle(dlg):
    return wait_until(lambda: not dlg._busy)


def test_successful_sign_in(qapp, live_server):
    dlg = LoginDialog(); fill(dlg, live_server.url)
    dlg._ok()
    assert wait_until(lambda: dlg.client is not None)
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.client.token and dlg.client.user["role"] == "admin"
    assert dlg.meta["menu"] and "permissions" in dlg.meta


def test_wrong_password_is_inline_and_flags_fields(qapp, live_server):
    dlg = LoginDialog(); dlg.show(); fill(dlg, live_server.url, pw="nope")
    dlg._ok(); assert settle(dlg)
    assert dlg.client is None and dlg.result() != QDialog.DialogCode.Accepted
    assert dlg.banner.isVisible() and "Incorrect username or password" in dlg.banner.text() and dlg.banner.kind == "danger"
    assert dlg.pw.property("invalid") is True
    assert dlg.ok_btn.isEnabled() and dlg.ok_btn.text() == "Sign in"
    fill(dlg, pw="test-admin-pass"); dlg._ok()                      # a retry works and clears the flags
    assert wait_until(lambda: dlg.client is not None)


def test_lockout_message_after_repeated_failures(qapp, live_server):
    dlg = LoginDialog(); dlg.show(); fill(dlg, live_server.url, pw="bad")
    for _ in range(5):
        dlg._ok(); assert settle(dlg)
    fill(dlg, pw="test-admin-pass"); dlg._ok(); assert settle(dlg)      # correct password, but the account is locked
    assert dlg.client is None and "locked" in dlg.banner.text() and dlg.banner.kind == "warning"


def test_unreachable_server_is_explained(qapp):
    dlg = LoginDialog(); dlg.show(); fill(dlg, "http://127.0.0.1:1")
    dlg._ok(); assert settle(dlg)
    assert "Can't reach the server at http://127.0.0.1:1" in dlg.banner.text()
    assert dlg.pw.property("invalid") is not True                # a network problem is not a credentials problem


def test_bad_address_and_missing_fields_are_caught_before_any_request(qapp):
    dlg = LoginDialog(); dlg.show()
    fill(dlg, "http://", user="", pw=""); dlg._ok()
    assert "username and password" in dlg.banner.text() and not dlg._busy
    fill(dlg, "ftp://nope", user="a", pw="b"); dlg._ok()
    assert "must look like http://" in dlg.banner.text() and not dlg._busy


def test_password_visibility_toggle(qapp):
    from PyQt6.QtWidgets import QLineEdit
    dlg = LoginDialog(); dlg.show()
    assert dlg.pw.echoMode() == QLineEdit.EchoMode.Password
    dlg.pw._toggle.trigger(); assert dlg.pw.echoMode() == QLineEdit.EchoMode.Normal
    dlg.pw._toggle.trigger(); assert dlg.pw.echoMode() == QLineEdit.EchoMode.Password


def test_caps_lock_hint(qapp):
    dlg = LoginDialog(); dlg.show(); dlg.pw.setFocus()
    QTest.keyClick(dlg.pw, "A"); assert dlg.caps.isVisible()
    QTest.keyClick(dlg.pw, "b"); assert not dlg.caps.isVisible()


def test_unencrypted_remote_connection_is_flagged(qapp):
    dlg = LoginDialog(); dlg.show()
    dlg.url.setText("http://192.168.1.50:8000")
    assert dlg.banner.isVisible() and "not encrypted" in dlg.banner.text() and dlg.banner.kind == "warning"
    dlg.url.setText("https://acct.example.com"); assert not dlg.banner.isVisible()
    dlg.url.setText("http://127.0.0.1:8000"); assert not dlg.banner.isVisible()


def test_test_connection_button(qapp, live_server):
    dlg = LoginDialog(); dlg.show(); dlg.url.setText(live_server.url)
    dlg._test(); assert wait_until(lambda: "reachable" in dlg.banner.text()) and dlg.banner.kind == "success"
    dlg.url.setText("http://127.0.0.1:1"); dlg._test()
    assert wait_until(lambda: "Can't reach" in dlg.banner.text())


def test_remember_username_choice(qapp, live_server):
    dlg = LoginDialog(); fill(dlg, live_server.url); dlg.remember.setChecked(False); dlg._ok()
    assert wait_until(lambda: dlg.client is not None)
    assert settings.app_settings().value("user", "") == ""
    assert settings.app_settings().value("pw", None) is None          # passwords are never stored
    dlg2 = LoginDialog(); fill(dlg2, live_server.url); dlg2.remember.setChecked(True); dlg2._ok()
    assert wait_until(lambda: dlg2.client is not None)
    assert settings.app_settings().value("user") == "admin"


def test_host_mode_first_run_then_sign_in(qapp, tmp_path, monkeypatch):
    monkeypatch.delenv("FINORA_ADMIN_PASSWORD", raising=False)
    dlg = LoginDialog(host_default=True); dlg.show()
    assert dlg.hosting and dlg.g_db.isVisible() and not dlg.g_url.isVisible()
    dlg.db.setText(str(tmp_path / "hosted.db")); dlg.port.setValue(free_port()); fill(dlg, user="x", pw="x")
    dlg._ok()
    try:
        assert wait_until(lambda: dlg.copy_btn.isVisible())
        assert dlg.server is not None and dlg.user.text() == "admin" and len(dlg.pw.text()) >= 8
        assert dlg.banner.kind == "success" and "shown only once" in dlg.banner.text()
        dlg._ok()                                                              # sign in with the generated password
        assert wait_until(lambda: dlg.client is not None)
        assert dlg.client.user["username"] == "admin"
    finally:
        if dlg.server:
            dlg.server.stop()


def test_reauth_dialog_checks_password_and_keeps_session_object(qapp, live_server):
    from finora.client.api_client import ApiClient
    client = ApiClient(live_server.url); client.login("admin", "test-admin-pass"); old = client.token
    dlg = ReauthDialog(client); dlg.show()
    dlg.pw.setText("wrong"); dlg._ok()
    assert wait_until(lambda: dlg.banner.isVisible()) and "Incorrect" in dlg.banner.text()
    assert dlg.ok_btn.isEnabled()
    dlg.pw.setText("test-admin-pass"); dlg._ok()
    assert wait_until(lambda: dlg.result() == QDialog.DialogCode.Accepted)
    assert client.token and client.token != old and not client.session_expired


def test_tests_never_touch_real_settings(qapp):
    s = settings.app_settings()
    assert s.fileName().endswith("settings.ini") and "/.config/FINORA" not in s.fileName().replace("\\", "/")
    dlg = LoginDialog()
    assert not dlg.hosting          # a fresh profile starts in "connect" mode
