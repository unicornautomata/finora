"""Status bar: operation messages on the left, weekday / date / time on the right."""
from datetime import datetime, timedelta

import pytest
from PyQt6.QtTest import QTest

import finora.client.screens as screens_mod
from conftest import wait_until
from finora.client.api_client import ApiClient
from finora.client.clock import WEEKDAYS, format_clock
from finora.client.components import dialogs
from finora.client.shell import Shell


def test_clock_text_names_the_weekday_for_every_day():
    monday = datetime(2026, 11, 9, 8, 0, 0)
    for i, name in enumerate(WEEKDAYS):
        assert format_clock(monday + timedelta(days=i)).startswith(name + ",")


def test_clock_text_format_and_12_hour_edges():
    assert format_clock(datetime(2026, 11, 13, 14, 5, 9)) == "Friday, November 13, 2026  2:05:09 PM"
    assert format_clock(datetime(2026, 1, 1, 0, 0, 0)) == "Thursday, January 1, 2026  12:00:00 AM"
    assert format_clock(datetime(2026, 12, 31, 12, 0, 0)).endswith("12:00:00 PM")


@pytest.fixture
def app_env(qapp, live_server, monkeypatch):
    class E: pass
    e = E(); e.errors = []
    monkeypatch.setattr(dialogs, "error", lambda parent, text, *a, **k: e.errors.append(text))
    monkeypatch.setattr(dialogs, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(screens_mod.QInputDialog, "getText", staticmethod(lambda *a, **k: ("2026-11-14", True)))
    c = ApiClient(live_server.url); c.login("admin", "test-admin-pass")
    c.master_create("coa", dict(coa="C1", description="Main"))
    c.master_create("gl_types", dict(gltype="AST", description="Assets", coa="C1", normal_side="D"))
    for g, d in (("1000", "Cash"), ("4000", "Sales")):
        c.master_create("gl_accounts", dict(glcd=g, description=d, gltype="AST"))
    c.master_create("companies", dict(cocd="1000", name="Acme", currency="USD", coa="C1"))
    e.client = c
    e.win = Shell(c, c.meta()); e.win.show()
    yield e
    e.win.close()


def new_cdj(env):
    env.win.open_screen("doc:CDJ")
    s = env.win.tabs.currentWidget()
    assert wait_until(lambda: hasattr(s, "tbl"))
    s.lines[0].update(glcd="1000", debit="100.00", credit="0.00")
    s.lines[1].update(glcd="4000", debit="0.00", credit="100.00")
    s._render_lines(); s._touch(); s._changed()
    return s


def test_status_bar_shows_weekday_date_and_time(app_env):
    text = app_env.win.clock.text()
    assert text.startswith(WEEKDAYS[datetime.now().weekday()] + ",") and (" AM" in text or " PM" in text)
    app_env.win.clock.setText("stale"); app_env.win._tick()
    assert app_env.win.clock.text() != "stale"


def test_save_post_reverse_delete_messages(app_env):
    win = app_env.win
    s = new_cdj(app_env)
    s.act_save()
    assert wait_until(lambda: "saved as a draft" in win.status_msg.text())
    jid = s.journal["id"]
    assert win.status_msg.text() == f"Transaction Number {jid} CDJ was saved as a draft!"
    assert win.status_msg.kind == "success"

    s.act_post()
    assert wait_until(lambda: s.status == "posted")
    assert win.status_msg.text() == "Transaction Number CD-000001 CDJ was posted!"

    s.act_reverse()
    assert wait_until(lambda: "reversal" in win.status_msg.text())
    assert win.status_msg.text() == "Transaction Number CD-000002 CDJ was posted as a reversal of CD-000001!"

    s.act_new(); s.lines[0].update(glcd="1000", debit="5.00"); s.lines[1].update(glcd="4000", credit="5.00")
    s._render_lines(); s._touch(); s.act_save()
    assert wait_until(lambda: s.status == "draft")
    did = s.journal["id"]
    s.act_delete()
    assert wait_until(lambda: "deleted" in win.status_msg.text())
    assert win.status_msg.text() == f"Draft transaction {did} CDJ was deleted!"
    assert not app_env.errors


def test_errors_show_in_status_bar_and_dialog(app_env):
    win = app_env.win
    s = new_cdj(app_env)
    s.lines[1].update(credit="90.00"); s._render_lines(); s._touch()
    s.act_post()                                                  # unbalanced: refused before any request
    assert any("out of balance" in e for e in app_env.errors)
    assert win.status_msg.kind == "danger" and "out of balance" in win.status_msg.text()


def test_master_data_messages(app_env):
    win = app_env.win
    win.open_screen("master:customers"); m = win.tabs.currentWidget()
    assert wait_until(lambda: hasattr(m, "form"))
    m.form["code"].set_value("C001"); m.form["name"].set_value("First Customer"); m.act_save()
    assert wait_until(lambda: "created" in win.status_msg.text())
    assert win.status_msg.text() == "Customer 'C001' was created!"
    m.form["name"].set_value("Renamed"); m.act_save()
    assert wait_until(lambda: "updated" in win.status_msg.text())
    assert win.status_msg.text() == "Customer 'C001' was updated!"
