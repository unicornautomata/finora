"""Regression for audit finding 7.1: invalidating a lookup must not empty pickers that are already open."""
import time
from PyQt6.QtTest import QTest
from finora.client.widgets import Editor, RefCache
from finora.server.definitions import ENTITIES


class FakeClient:
    def __init__(self):
        self.accounts = [dict(glcd="1000", description="Cash", gltype="AST", active=1)]
        self.calls = 0

    def master_list(self, entity, q="", limit=1000):
        self.calls += 1
        return list(self.accounts) if entity == "gl_accounts" else []


def wait(cond, secs=5):
    end = time.time() + secs
    while time.time() < end:
        QTest.qWait(20)
        if cond():
            return True
    return False


def test_invalidate_keeps_serving_old_values_then_refreshes(qapp):
    client = FakeClient(); refs = RefCache(client, ENTITIES)
    ok = []; refs.load(["gl_accounts"], lambda: ok.append(1))
    assert wait(lambda: ok)
    seen = []; refs.changed.connect(seen.append)
    client.accounts.append(dict(glcd="5000", description="Rent", gltype="AST", active=1))
    refs.invalidate("gl_accounts")
    assert [k for k, _ in refs.pairs("gl_accounts")] == ["1000"]            # never empty while reloading
    assert wait(lambda: len(refs.pairs("gl_accounts")) == 2)
    assert seen and "gl_accounts" in seen[-1] and "gl_accounts" not in refs.stale


def test_ref_editor_keeps_selection_when_options_reload(qapp):
    client = FakeClient(); refs = RefCache(client, ENTITIES)
    done = []; refs.load(["gl_accounts"], lambda: done.append(1)); assert wait(lambda: done)
    field = dict(name="glcd", label="GL", type="ref", required=True, ref="gl_accounts")
    ed = Editor(field, refs); ed.set_value("1000")
    client.accounts.append(dict(glcd="5000", description="Rent", gltype="AST", active=1))
    refs.invalidate("gl_accounts"); assert wait(lambda: len(refs.pairs("gl_accounts")) == 2)
    ed.reload_options(refs)
    assert ed.value() == "1000" and ed.widget.count() == 2
