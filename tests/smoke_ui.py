"""Drives the real PyQt6 UI against a real server thread (offscreen). Run: QT_QPA_PLATFORM=offscreen python tests/smoke_ui.py"""
import os, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LEDGER_ADMIN_PASSWORD"] = "smoke-pass-1"

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from ledger.server.host import ServerThread
from ledger.client import theme
from ledger.client.api_client import ApiClient
from ledger.client.shell import Shell
from ledger.client.login import LoginDialog

out = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
srv = ServerThread(os.path.join(tempfile.mkdtemp(), "s.db"), port=8765); srv.start(); assert srv.wait_ready()
cl = ApiClient("http://127.0.0.1:8765"); cl.login("admin", "smoke-pass-1")
cl.master_create("coa", dict(coa="C1", description="Main"))
cl.master_create("gl_types", dict(gltype="AST", description="Assets", coa="C1", normal_side="D"))
cl.master_create("gl_types", dict(gltype="REV", description="Revenue", coa="C1", normal_side="C"))
for g, d, t in (("1000", "Cash", "AST"), ("1200", "Receivables", "AST"), ("4000", "Sales", "REV")):
    cl.master_create("gl_accounts", dict(glcd=g, description=d, gltype=t))
cl.master_create("companies", dict(cocd="1000", name="Acme Corp", currency="USD", coa="C1"))

app = QApplication([]); app.setStyleSheet(theme.qss(theme.LIGHT))
warnings = []
QMessageBox.warning = staticmethod(lambda *a, **k: warnings.append(a[2]))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)

def wait(cond, secs=6):
    end = time.time() + secs
    while time.time() < end:
        QTest.qWait(30)
        if cond(): return True
    return False

meta = cl.meta()
win = Shell(cl, meta, "smoke test"); win.show()
scr = win.tabs.currentWidget()
assert wait(lambda: hasattr(scr, "tbl")), "document screen did not build"
print("heading:", win.mode.text(), "| enabled:", [k for k, a in win.acts.items() if a.isEnabled()])

# fill header + two lines through the real widgets
scr.h["reference"].set_value("INV-77"); scr.h["description"].set_value("Cash sale"); scr._touch()
assert len(scr.lines) == 2, "new journals start with two lines"
scr.lines[0].update(glcd="1000", debit="250.00", credit="0.00", description="Cash in")
del scr.lines[1]; scr._render_lines()
scr._add_line(focus=False)                          # should pre-fill the balancing credit
assert scr.lines[1]["credit"] == "250.00", scr.lines[1]
scr.lines[1].update(glcd="4000", description="Sales"); scr._render_lines(); scr._touch()
print("totals:", scr.lbl_dr.text(), "|", scr.lbl_cr.text(), "|", scr.chip.text())
scr._changed(); QTest.qWait(100); scr.grab().save(os.path.join(out, "1_draft_light.png"))
print("enabled before post:", [k for k, a in win.acts.items() if a.isEnabled()], "| dirty:", scr.dirty, "| editable:", scr.editable)
win.acts["post"].trigger()
assert wait(lambda: scr.status == "posted"), warnings
print("posted:", scr.journal["doc_no"], "| badge:", scr.badge.text(), "| enabled:", [k for k, a in win.acts.items() if a.isEnabled()])
win.grab().save(os.path.join(out, "2_posted_window.png"))

# unbalanced journal must be refused by the UI before it reaches the server
scr.act_new(); scr.lines[0].update(glcd="1000", debit="10.00"); scr._render_lines(); scr._touch()
scr.lines[1].update(glcd="4000", credit="9.00"); scr._render_lines(); scr._touch()
n = len(warnings); scr.act_post(); assert len(warnings) == n + 1 and "out of balance" in warnings[-1].lower(), warnings
print("unbalanced blocked:", warnings[-1])

# reverse the posted one via the toolbar path
scr.act_open  # picker is modal; use API to load instead
j = cl.journals(doctype="PJ", status="posted")[0]; scr._load(cl.journal(j["id"]))
import ledger.client.screens as sc
sc.QInputDialog.getText = staticmethod(lambda *a, **k: ("2026-11-10", True))
win.acts["reverse"].trigger(); assert wait(lambda: scr.journal and scr.journal.get("reverses_id")), warnings
print("reversal:", scr.journal["doc_no"], scr.journal["status"])

# master data + report + admin screens
for key in ("master:gl_accounts", "master:customers", "report:trial_balance", "master:users"):
    win.open_screen(key); QTest.qWait(400)
tb = win.tabs.currentWidget() if False else None
win.open_screen("report:trial_balance"); t = win.tabs.currentWidget(); wait(lambda: t.t.rowCount() > 0)
print("trial balance rows:", t.t.rowCount(), "|", t.sum.text())
win.open_screen("master:customers"); m = win.tabs.currentWidget(); wait(lambda: hasattr(m, "form"))
m.form["code"].set_value("CUST1"); m.form["name"].set_value("First Customer"); m.act_save()
assert wait(lambda: any(r["code"] == "CUST1" for r in m.rows)), warnings
print("customer created via master screen")
win.open_screen("doc:SJ"); QTest.qWait(300)
win._toggle_theme(); QTest.qWait(150)
d = win.tabs.currentWidget(); wait(lambda: hasattr(d, "tbl"))
win.grab().save(os.path.join(out, "3_dark_window.png"))
win._toggle_theme(); win.open_screen("doc:PJ"); QTest.qWait(200)
g = win.tabs.currentWidget(); g._load(cl.journal(cl.journals(doctype="PJ", status="posted")[0]["id"])); QTest.qWait(100)
win.grab().save(os.path.join(out, "4_posted_light.png"))
print("warnings during run:", warnings)
srv.stop(); print("UI SMOKE TEST PASSED")
