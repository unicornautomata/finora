"""Screens. Each one is built from the definitions the server publishes at /meta."""
from __future__ import annotations
from datetime import date
from decimal import Decimal

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (QAbstractItemView, QDateEdit, QDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                             QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                             QSplitter, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
                             QComboBox)

from .tasks import run_async
from .widgets import SEP, AmountDelegate, Editor, GLDelegate, RefCache, to_dec

R = Qt.ItemDataRole
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def card(layout=None) -> QFrame:
    f = QFrame(); f.setObjectName("card")
    if layout is not None:
        f.setLayout(layout)
    return f


def fmt(v) -> str:
    d = to_dec(v)
    return "" if d == 0 else f"{d:,.2f}"


class Screen(QWidget):
    """Base class. The shell shows the same fixed toolbar for every screen and only
    enables the buttons a screen supports, like the original CRUD button row."""
    state_changed = pyqtSignal()
    message = pyqtSignal(str, bool)       # text, is_error
    master_changed = pyqtSignal(str)

    def actions(self) -> dict:
        return {}

    def heading(self) -> str:
        return ""

    def is_dirty(self) -> bool:
        return False

    def run(self, name: str):
        fn = getattr(self, "act_" + name, None)
        if fn:
            fn()

    def error(self, msg): self.message.emit(msg, True)
    def info(self, msg): self.message.emit(msg, False)


# ====================================================================== documents
class JournalPicker(QDialog):
    def __init__(self, client, doctype, label, parent=None):
        super().__init__(parent)
        self.client, self.doctype, self.selected_id = client, doctype, None
        self.setWindowTitle(f"Open {label}"); self.resize(860, 480)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.q = QLineEdit(); self.q.setPlaceholderText("Search number, reference or description")
        self.q.returnPressed.connect(self.search)
        go = QPushButton("Search"); go.clicked.connect(self.search)
        row.addWidget(self.q, 1); row.addWidget(go)
        lay.addLayout(row)
        cols = ["Number", "Date", "Reference", "Description", "Total", "Status"]
        self.t = QTableWidget(0, len(cols)); self.t.setHorizontalHeaderLabels(cols)
        self.t.verticalHeader().setVisible(False); self.t.setAlternatingRowColors(True)
        self.t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.t.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.t.doubleClicked.connect(self.accept_row)
        lay.addWidget(self.t, 1)
        self.status = QLabel(""); self.status.setObjectName("muted"); lay.addWidget(self.status)
        self.search()

    def search(self):
        self.status.setText("Loading…")
        run_async(lambda: self.client.journals(doctype=self.doctype, q=self.q.text().strip()),
                  self._fill, lambda m: self.status.setText(m))

    def _fill(self, rows):
        self.rows = rows
        self.t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [r["doc_no"] or f"Draft #{r['id']}", r["posting_date"], r["reference"] or "",
                    r["description"] or "", f"{to_dec(r['total']):,.2f}", r["status"].title()]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 4:
                    it.setTextAlignment(RIGHT)
                self.t.setItem(i, c, it)
        self.status.setText(f"{len(rows)} journal(s)")

    def accept_row(self, *_):
        r = self.t.currentRow()
        if r >= 0:
            self.selected_id = self.rows[r]["id"]
            self.accept()


class DocumentScreen(Screen):
    """Header, line grid and line-item detail panel, laid out like the original journal mock-up."""

    def __init__(self, client, meta, refs: RefCache, doctype: str):
        super().__init__()
        self.client, self.meta, self.refs, self.doctype = client, meta, refs, doctype
        self.doc = meta["document"]
        self.label = next((t["description"] for t in meta["doc_types"] if t["doctype"] == doctype), doctype)
        perms = meta["permissions"]
        self.can_write, self.can_post = "write" in perms, "post" in perms
        self.journal, self.lines = None, []
        self.dirty = self.busy = self._loading = False
        self.cols = self.doc["line_columns"]
        self.col_ix = {c["name"]: i for i, c in enumerate(self.cols)}
        self._lay = QVBoxLayout(self); self._lay.setContentsMargins(16, 14, 16, 14)
        self._lay.addWidget(QLabel("Loading…"))
        refs.load(["companies", "gl_accounts"], self._build, self.error)

    # ---- construction
    def _build(self):
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        lay = self._lay; lay.setSpacing(12)

        # header card (3 columns, like the mock-up)
        self.h: dict[str, Editor] = {}
        g = QGridLayout(); g.setHorizontalSpacing(14); g.setVerticalSpacing(10)
        for r, row in enumerate(self.doc["header_layout"]):
            for c, f in enumerate(row):
                lab = QLabel(f["label"]); lab.setObjectName("muted")
                ed = Editor(f, self.refs); self.h[f["name"]] = ed
                g.addWidget(lab, r, c * 2); g.addWidget(ed.widget, r, c * 2 + 1)
        df = self.doc["description_field"]
        dl = QLabel(df["label"]); dl.setObjectName("muted")
        self.h["description"] = Editor(df, self.refs)
        n = len(self.doc["header_layout"])
        g.addWidget(dl, n, 0); g.addWidget(self.h["description"].widget, n, 1, 1, 5)
        for c in (1, 3, 5):
            g.setColumnStretch(c, 1)
        top = QHBoxLayout()
        self.badge = QLabel("New"); self.badge.setObjectName("badge")
        top.addWidget(self.badge); top.addStretch(1)
        hv = QVBoxLayout(); hv.addLayout(top); hv.addLayout(g)
        lay.addWidget(card(hv))
        for name, ed in self.h.items():
            w = ed.widget
            if hasattr(w, "textEdited"): w.textEdited.connect(self._touch)
            elif hasattr(w, "dateChanged"): w.dateChanged.connect(self._touch)
            elif hasattr(w, "currentTextChanged"): w.currentTextChanged.connect(self._touch)

        # line grid
        self.tbl = QTableWidget(0, len(self.cols) + 1)
        self.tbl.setHorizontalHeaderLabels([c["label"] for c in self.cols] + [""])
        self.tbl.verticalHeader().setVisible(False); self.tbl.verticalHeader().setDefaultSectionSize(36)
        self.tbl.setAlternatingRowColors(True); self.tbl.setMinimumHeight(190)
        self.tbl.setShowGrid(False)
        hdr = self.tbl.horizontalHeader()
        for i, c in enumerate(self.cols):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive); self.tbl.setColumnWidth(i, c.get("width", 120))
        hdr.setSectionResizeMode(self.col_ix["description"], QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(len(self.cols), QHeaderView.ResizeMode.Fixed); self.tbl.setColumnWidth(len(self.cols), 44)
        self.tbl.setItemDelegateForColumn(self.col_ix["glcd"], GLDelegate(self.refs, self.tbl))
        for k in ("debit", "credit"):
            self.tbl.setItemDelegateForColumn(self.col_ix[k], AmountDelegate(self.tbl))
        self.tbl.itemChanged.connect(self._on_item)
        self.tbl.currentCellChanged.connect(lambda *_: self._refresh_detail())

        foot = QHBoxLayout()
        self.btn_add = QPushButton("+ Add line"); self.btn_add.clicked.connect(lambda: self._add_line())
        self.lbl_dr, self.lbl_cr, self.lbl_diff = QLabel(), QLabel(), QLabel()
        self.chip = QLabel(); self.chip.setObjectName("badge")
        foot.addWidget(self.btn_add); foot.addStretch(1)
        for w in (self.lbl_dr, self.lbl_cr, self.lbl_diff, self.chip):
            foot.addWidget(w); foot.addSpacing(16)
        gv = QVBoxLayout(); gv.addWidget(self.tbl, 1); gv.addLayout(foot)
        lay.addWidget(card(gv), 1)

        # line item details
        self.d: dict[str, Editor] = {}
        dg = QGridLayout(); dg.setHorizontalSpacing(14); dg.setVerticalSpacing(10)
        for r, row in enumerate(self.doc["detail_layout"]):
            for c, f in enumerate(row):
                lab = QLabel(f["label"]); lab.setObjectName("muted")
                ed = Editor(f, self.refs); self.d[f["name"]] = ed
                dg.addWidget(lab, r, c * 2); dg.addWidget(ed.widget, r, c * 2 + 1)
                if not f.get("readonly") and hasattr(ed.widget, "textEdited"):
                    ed.widget.textEdited.connect(lambda _=None, n=f["name"]: self._on_detail(n))
        pf = self.doc["detail_description"]
        pl = QLabel(pf["label"]); pl.setObjectName("muted")
        self.d[pf["name"]] = Editor(pf, self.refs)
        self.d[pf["name"]].widget.textEdited.connect(lambda _=None: self._on_detail(pf["name"]))
        nr = len(self.doc["detail_layout"])
        dg.addWidget(pl, nr, 0); dg.addWidget(self.d[pf["name"]].widget, nr, 1, 1, 5)
        for c in (1, 3, 5):
            dg.setColumnStretch(c, 1)
        grp = QVBoxLayout(); t = QLabel("Line Item Details"); t.setStyleSheet("font-weight:600;")
        grp.addWidget(t); grp.addLayout(dg)
        lay.addWidget(card(grp))
        self.new_document()

    # ---- state helpers
    @property
    def status(self):
        return self.journal["status"] if self.journal else "new"

    @property
    def editable(self):
        return self.can_write and self.status in ("new", "draft")

    def heading(self):
        if not self.journal:
            return f"Create {self.label}"
        return f"{self.label} · {self.journal['doc_no'] or 'Draft #' + str(self.journal['id'])}"

    def is_dirty(self):
        return self.dirty

    def actions(self):
        if self.busy or not hasattr(self, "h"):
            return {}
        j, real = self.journal, [l for l in self.lines if l.get("glcd")]
        return dict(new=True, open=True, save=self.editable and self.dirty,
                    post=self.can_post and self.editable and len(real) >= 2,
                    delete=self.can_write and self.status == "draft",
                    reverse=self.can_post and self.status == "posted" and not (j or {}).get("reverses_id"),
                    copy=bool(j or real), refresh=j is not None)

    def _changed(self):
        self._update_badge(); self.state_changed.emit()

    def _touch(self, *_):
        if not self._loading and not self.dirty:
            self.dirty = True; self._changed()

    def _set_busy(self, b):
        self.busy = b; self.setEnabled(not b); self._changed()

    def _update_badge(self):
        st = self.status
        text = {"new": "New", "draft": f"Draft #{self.journal['id']}" if self.journal else "Draft",
                "posted": f"Posted {self.journal['doc_no']}" if self.journal else "",
                "reversed": f"Reversed {self.journal['doc_no']}" if self.journal else ""}[st]
        if self.dirty and st in ("new", "draft"):
            text += "  •  unsaved"
        self.badge.setText(text); self.badge.setProperty("state", st)
        self.badge.style().unpolish(self.badge); self.badge.style().polish(self.badge)

    # ---- loading / blank
    def new_document(self, lines=None, header=None):
        self.journal, self.dirty = None, False
        self._loading = True
        today = date.today().isoformat()
        vals = dict(doc_no="(assigned on posting)", doctype=self.doctype, doc_date=today, posting_date=today,
                    entry_date=today, entered_by=self.client.user["username"], reference=None, department=None,
                    description=None, cocd=None)
        vals.update(header or {})
        companies = self.refs.data.get("companies", [])
        if not vals["cocd"] and len(companies) == 1:
            vals["cocd"] = companies[0]["cocd"]
        for k, ed in self.h.items():
            ed.set_value(vals.get(k))
        self.lines = lines if lines is not None else []
        self._loading = False
        self._apply_readonly(); self._render_lines(); self._changed()
        if not self.lines and self.editable:
            self._add_line(focus=False); self._add_line(focus=False)   # a journal needs at least two lines
            self.dirty = False; self._changed()

    def _load(self, j):
        self.journal, self.dirty = j, False
        self._loading = True
        vals = dict(j); vals["doc_no"] = j["doc_no"] or "(assigned on posting)"
        for k, ed in self.h.items():
            ed.set_value(vals.get(k))
        self.lines = [dict(l) for l in j["lines"]]
        self._loading = False
        self._apply_readonly(); self._render_lines(); self._changed()

    def _apply_readonly(self):
        for k, ed in self.h.items():
            ed.set_readonly(True if ed.field.get("readonly") else not self.editable)
        for k, ed in self.d.items():
            ed.set_readonly(True if ed.field.get("readonly") else not self.editable)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers if self.editable
                                 else QAbstractItemView.EditTrigger.NoEditTriggers)
        self.btn_add.setEnabled(self.editable)

    # ---- grid
    def _render_lines(self):
        self._loading = True
        labels = dict(self.refs.pairs("gl_accounts"))
        self.tbl.setRowCount(len(self.lines))
        for r, l in enumerate(self.lines):
            it = QTableWidgetItem(str(r + 1)); it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter); self.tbl.setItem(r, self.col_ix["item_no"], it)
            gl = QTableWidgetItem(labels.get(l.get("glcd"), l.get("glcd") or ""))
            gl.setData(R.UserRole, l.get("glcd")); self.tbl.setItem(r, self.col_ix["glcd"], gl)
            self.tbl.setItem(r, self.col_ix["description"], QTableWidgetItem(l.get("description") or ""))
            for k in ("debit", "credit"):
                a = QTableWidgetItem(fmt(l.get(k))); a.setTextAlignment(RIGHT); self.tbl.setItem(r, self.col_ix[k], a)
            b = QToolButton(); b.setObjectName("rowmenu"); b.setText("⋯"); b.setEnabled(self.editable)
            b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            m = QMenu(b)
            for text, fn in (("Insert line above", lambda _=0, r=r: self._add_line(at=r)),
                             ("Duplicate line", lambda _=0, r=r: self._dup_line(r)),
                             ("Move up", lambda _=0, r=r: self._move(r, -1)),
                             ("Move down", lambda _=0, r=r: self._move(r, 1)),
                             ("Delete line", lambda _=0, r=r: self._del_line(r))):
                a = QAction(text, m); a.triggered.connect(fn); m.addAction(a)
            b.setMenu(m); self.tbl.setCellWidget(r, len(self.cols), b)
        self._loading = False
        self._update_totals(); self._refresh_detail()

    def _blank(self):
        return dict(glcd=None, description="", debit="0.00", credit="0.00", quantity=None, unit=None,
                    ref_item_no=None, preceding_doc=None, origin_ref=None, product_desc=None, partner_code=None)

    def _totals(self):
        return (sum((to_dec(l.get("debit")) for l in self.lines), Decimal(0)),
                sum((to_dec(l.get("credit")) for l in self.lines), Decimal(0)))

    def _add_line(self, at=None, focus=True):
        l = self._blank()
        td, tc = self._totals()
        if td > tc: l["credit"] = f"{td - tc:.2f}"          # pre-fill the balancing amount
        elif tc > td: l["debit"] = f"{tc - td:.2f}"
        self.lines.insert(len(self.lines) if at is None else at, l)
        self._render_lines(); self._touch(); self._changed()
        r = len(self.lines) - 1 if at is None else at
        if focus:
            self.tbl.setCurrentCell(r, self.col_ix["glcd"]); self.tbl.editItem(self.tbl.item(r, self.col_ix["glcd"]))

    def _dup_line(self, r):
        self.lines.insert(r + 1, dict(self.lines[r])); self._render_lines(); self._touch(); self._changed()

    def _move(self, r, d):
        s = r + d
        if 0 <= s < len(self.lines):
            self.lines[r], self.lines[s] = self.lines[s], self.lines[r]
            self._render_lines(); self.tbl.setCurrentCell(s, 1); self._touch()

    def _del_line(self, r):
        del self.lines[r]; self._render_lines(); self._touch(); self._changed()

    def _on_item(self, item):
        if self._loading or item.row() >= len(self.lines):
            return
        r, name = item.row(), self.cols[item.column()]["name"] if item.column() < len(self.cols) else None
        l = self.lines[r]
        if name == "glcd":
            l["glcd"] = item.data(R.UserRole) or item.text().split(SEP)[0].strip() or None
        elif name == "description":
            l["description"] = item.text()
        elif name in ("debit", "credit"):
            v = to_dec(item.text()); other = "credit" if name == "debit" else "debit"
            l[name] = f"{v:.2f}"
            self._loading = True
            item.setText(fmt(v))
            if v > 0:
                l[other] = "0.00"; self.tbl.item(r, self.col_ix[other]).setText("")
            self._loading = False
        else:
            return
        self._touch(); self._update_totals(); self._refresh_detail(); self._changed()

    def _update_totals(self):
        td, tc = self._totals(); diff = td - tc
        n = len([l for l in self.lines if l.get("glcd")])
        self.lbl_dr.setText(f"Debit  {td:,.2f}"); self.lbl_cr.setText(f"Credit  {tc:,.2f}")
        self.lbl_diff.setText(f"Difference  {diff:,.2f}")
        ok = diff == 0 and td > 0 and n >= 2
        self.chip.setText("Balanced" if ok else ("Out of balance" if td or tc else "Empty"))
        self.chip.setStyleSheet("" if not td and not tc else
                                f"background:{'#2f9e6f' if ok else '#d64545'}; color:#fff;")

    # ---- line detail panel
    def _refresh_detail(self):
        r = self.tbl.currentRow()
        self._loading = True
        valid = 0 <= r < len(self.lines)
        l = self.lines[r] if valid else {}
        hv = lambda k: self.h[k].value()
        self.d["item_no"].set_value(r + 1 if valid else None)
        for k in ("ref_item_no", "preceding_doc", "unit", "origin_ref", "product_desc"):
            self.d[k].set_value(l.get(k))
        self.d["quantity"].set_value(l.get("quantity"))
        amt = to_dec(l.get("debit")) or to_dec(l.get("credit"))
        self.d["amount"].set_value(f"{amt:,.2f}" if valid else None)
        self.d["doc_date"].set_value(hv("doc_date")); self.d["entry_date"].set_value(hv("entry_date"))
        for k, ed in self.d.items():
            if not ed.field.get("readonly"):
                ed.widget.setEnabled(valid and self.editable)
        self._loading = False

    def _on_detail(self, name):
        r = self.tbl.currentRow()
        if self._loading or not (0 <= r < len(self.lines)):
            return
        self.lines[r][name] = self.d[name].value(); self._touch()

    # ---- server round trips
    def _payload(self):
        p = {k: self.h[k].value() for k in ("cocd", "doc_date", "posting_date", "reference", "department", "description")}
        p["lines"] = [{k: v for k, v in l.items() if k != "item_no"}
                      for l in self.lines if l.get("glcd") or to_dec(l.get("debit")) or to_dec(l.get("credit"))]
        return p

    def _call(self, fn, ok, busy=True):
        self._set_busy(True)

        def good(res):
            self._set_busy(False); ok(res)

        def bad(msg):
            self._set_busy(False); self.error(msg)
        run_async(fn, good, bad)

    def _save(self, then=None):
        p = self._payload()
        if self.journal:
            p["version"] = self.journal["version"]; jid = self.journal["id"]
            fn = lambda: self.client.journal_update(jid, p)
        else:
            p["doctype"] = self.doctype
            fn = lambda: self.client.journal_create(p)

        def ok(j):
            self._load(j); self.info(f"Saved as draft #{j['id']}")
            if then: then()
        self._call(fn, ok)

    def act_save(self):
        if self.editable: self._save()

    def act_post(self):
        if not (self.can_post and self.editable): return
        td, tc = self._totals()
        if td != tc:
            return self.error(f"The journal is out of balance by {abs(td - tc):,.2f}. Debits must equal credits before posting.")
        if QMessageBox.question(self, "Post journal", "Post this journal?\n\nPosted journals cannot be edited. "
                                "To correct one you reverse it.") != QMessageBox.StandardButton.Yes:
            return
        def post():
            j = self.journal
            self._call(lambda: self.client.journal_post(j["id"], j["version"]),
                       lambda r: (self._load(r), self.info(f"Posted as {r['doc_no']}")))
        if self.dirty or not self.journal: self._save(then=post)
        else: post()

    def act_new(self):
        if self._confirm_discard(): self.new_document()

    def act_open(self):
        if not self._confirm_discard(): return
        dlg = JournalPicker(self.client, self.doctype, self.label, self)
        if dlg.exec() and dlg.selected_id:
            self._call(lambda: self.client.journal(dlg.selected_id), self._load)

    def act_refresh(self):
        if self.journal and self._confirm_discard():
            jid = self.journal["id"]; self._call(lambda: self.client.journal(jid), self._load)

    def act_delete(self):
        if self.status != "draft": return
        if QMessageBox.question(self, "Delete draft", "Delete this draft journal?") != QMessageBox.StandardButton.Yes: return
        j = self.journal
        self._call(lambda: self.client.journal_delete(j["id"], j["version"]),
                   lambda _: (self.new_document(), self.info("Draft deleted")))

    def act_reverse(self):
        if self.status != "posted": return
        text, ok = QInputDialog.getText(self, "Reverse journal", "Posting date for the reversal (YYYY-MM-DD):",
                                        text=date.today().isoformat())
        if not ok: return
        jid = self.journal["id"]
        self._call(lambda: self.client.journal_reverse(jid, text.strip()),
                   lambda r: (self._load(r), self.info(f"Reversal {r['doc_no']} posted")))

    def act_copy(self):
        if not self._confirm_discard(): return
        lines = [dict(l) for l in self.lines]
        h = {k: self.h[k].value() for k in ("cocd", "reference", "department", "description")}
        self.new_document(lines=lines, header=h); self.dirty = True; self._changed()
        self.info("Copied into a new draft")

    def _confirm_discard(self):
        if not self.dirty: return True
        return QMessageBox.question(self, "Unsaved changes", "Discard unsaved changes?") == QMessageBox.StandardButton.Yes


# ====================================================================== master data
class MasterScreen(Screen):
    def __init__(self, client, meta, refs, entity):
        super().__init__()
        self.client, self.meta, self.refs, self.entity = client, meta, refs, entity
        self.e = meta["entities"][entity]
        self.can_write = "write" in meta["permissions"]
        self.key, self.rows, self.busy = None, [], False
        self._lay = QVBoxLayout(self); self._lay.setContentsMargins(16, 14, 16, 14)
        self._lay.addWidget(QLabel("Loading…"))
        refs.load([f["ref"] for f in self.e["fields"] if f["type"] == "ref"], self._build, self.error)

    def _build(self):
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w: w.deleteLater()
        fields = self.e["fields"]
        self.shown = [f for f in fields if f["type"] not in ("password",)][:5]
        left = QVBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText(f"Search {self.e['plural'].lower()}")
        self.search.returnPressed.connect(self.act_refresh)
        left.addWidget(self.search)
        self.t = QTableWidget(0, len(self.shown)); self.t.setHorizontalHeaderLabels([f["label"] for f in self.shown])
        self.t.verticalHeader().setVisible(False); self.t.setAlternatingRowColors(True); self.t.setShowGrid(False)
        self.t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.t.horizontalHeader().setStretchLastSection(True)
        self.t.itemSelectionChanged.connect(self._select)
        left.addWidget(self.t, 1)
        lw = QWidget(); lw.setLayout(left)

        self.form: dict[str, Editor] = {}
        fl = QFormLayout(); fl.setVerticalSpacing(12); fl.setHorizontalSpacing(16)
        for f in fields:
            ed = Editor(f, self.refs); self.form[f["name"]] = ed
            lab = QLabel(f["label"] + (" *" if f["required"] else "")); lab.setObjectName("muted")
            fl.addRow(lab, ed.widget)
        self.hint = QLabel(""); self.hint.setObjectName("muted"); self.hint.setWordWrap(True)
        title = QLabel(self.e["label"]); title.setObjectName("title")
        rv = QVBoxLayout(); rv.addWidget(title); rv.addLayout(fl); rv.addWidget(self.hint); rv.addStretch(1)
        right = card(rv)
        sp = QSplitter(); sp.addWidget(lw); sp.addWidget(right); sp.setStretchFactor(0, 3); sp.setStretchFactor(1, 2)
        self._lay.addWidget(sp)
        self.act_new(); self.act_refresh()

    def heading(self):
        return f"{self.e['plural']}"

    def actions(self):
        if self.busy or not hasattr(self, "form"): return {}
        return dict(new=self.can_write, save=self.can_write,
                    delete=self.can_write and self.key is not None and self.e.get("deletable", True),
                    refresh=True)

    def _fill_table(self):
        self.t.blockSignals(True)
        self.t.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            for c, f in enumerate(self.shown):
                v = r.get(f["name"]); v = ("Yes" if v else "No") if f["type"] == "bool" else ("" if v is None else str(v))
                self.t.setItem(i, c, QTableWidgetItem(v))
        self.t.blockSignals(False)

    def _select(self):
        r = self.t.currentRow()
        if not (0 <= r < len(self.rows)): return
        row = self.rows[r]; self.key = row[self.e["pk"]]
        for f in self.e["fields"]:
            ed = self.form[f["name"]]; ed.set_value(row.get(f["name"]) if f["type"] != "password" else "")
            if f.get("pk"): ed.set_readonly(True)
        self.hint.setText("Leave the password blank to keep the current one." if self.entity == "users" else "")
        self.state_changed.emit()

    def act_new(self):
        self.key = None; self.t.clearSelection()
        for f in self.e["fields"]:
            ed = self.form[f["name"]]; ed.set_readonly(not self.can_write)
            ed.set_value(f.get("default")) if f.get("default") is not None else ed.set_value(None)
        self.hint.setText("")
        self.state_changed.emit()

    def act_refresh(self):
        q = self.search.text().strip()
        self._call(lambda: self.client.master_list(self.entity, q), lambda rows: (setattr(self, "rows", rows), self._fill_table()))

    def _call(self, fn, ok):
        self.busy = True; self.state_changed.emit()
        def good(r): self.busy = False; ok(r); self.state_changed.emit()
        def bad(m): self.busy = False; self.state_changed.emit(); self.error(m)
        run_async(fn, good, bad)

    def act_save(self):
        if not self.can_write: return
        data = {}
        for f in self.e["fields"]:
            v = self.form[f["name"]].value()
            if f["type"] == "password" and not v: continue
            data[f["name"]] = v
        key, pk = self.key, self.e["pk"]
        if key is None:
            fn = lambda: self.client.master_create(self.entity, data)
        else:
            data.pop(pk, None); fn = lambda: self.client.master_update(self.entity, key, data)

        def ok(saved):
            self.info(f"{self.e['label']} saved"); self.master_changed.emit(self.entity)
            self.key = saved[pk]; self.act_refresh()
        self._call(fn, ok)

    def act_delete(self):
        if self.key is None: return
        if QMessageBox.question(self, "Delete", f"Delete {self.e['label'].lower()} '{self.key}'?") != QMessageBox.StandardButton.Yes: return
        key = self.key
        self._call(lambda: self.client.master_delete(self.entity, key),
                   lambda _: (self.info("Deleted"), self.master_changed.emit(self.entity), self.act_new(), self.act_refresh()))


# ====================================================================== reports
class TrialBalanceScreen(Screen):
    def __init__(self, client, meta, refs):
        super().__init__()
        self.client, self.refs, self.busy = client, refs, False
        self._lay = QVBoxLayout(self); self._lay.setContentsMargins(16, 14, 16, 14)
        self._lay.addWidget(QLabel("Loading…"))
        refs.load(["companies"], self._build, self.error)

    def _build(self):
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w: w.deleteLater()
        bar = QHBoxLayout()
        self.co = Editor(dict(name="cocd", label="Company", type="ref", required=True, ref="companies"), self.refs)
        self.asof = Editor(dict(name="as_of", label="As of", type="date"), self.refs)
        go = QPushButton("Run report"); go.setObjectName("primary"); go.clicked.connect(self.act_refresh)
        for t, w in (("Company", self.co.widget), ("As of", self.asof.widget)):
            l = QLabel(t); l.setObjectName("muted"); bar.addWidget(l); bar.addWidget(w, 1)
        bar.addWidget(go)
        self._lay.addWidget(card(bar))
        cols = ["GL Account", "Description", "Debit", "Credit", "Balance"]
        self.t = QTableWidget(0, 5); self.t.setHorizontalHeaderLabels(cols); self.t.setAlternatingRowColors(True)
        self.t.verticalHeader().setVisible(False); self.t.setShowGrid(False)
        self.t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._lay.addWidget(self.t, 1)
        self.sum = QLabel(""); self.sum.setObjectName("badge"); self._lay.addWidget(self.sum, 0, Qt.AlignmentFlag.AlignRight)
        if self.refs.data.get("companies") and len(self.refs.data["companies"]) == 1:
            self.co.set_value(self.refs.data["companies"][0]["cocd"]); self.act_refresh()

    def heading(self): return "Trial Balance"
    def actions(self): return dict(refresh=True) if hasattr(self, "t") else {}

    def act_refresh(self):
        cocd = self.co.value()
        if not cocd: return self.error("Choose a company first")
        run_async(lambda: self.client.trial_balance(cocd, self.asof.value()), self._fill, self.error)

    def _fill(self, tb):
        self.t.setRowCount(len(tb["rows"]))
        for i, r in enumerate(tb["rows"]):
            for c, v in enumerate([r["glcd"], r["description"] or "", f"{to_dec(r['debit']):,.2f}",
                                   f"{to_dec(r['credit']):,.2f}", f"{to_dec(r['balance']):,.2f}"]):
                it = QTableWidgetItem(v)
                if c >= 2: it.setTextAlignment(RIGHT)
                self.t.setItem(i, c, it)
        ok = tb["balanced"]
        self.sum.setText(f"Total debit {to_dec(tb['total_debit']):,.2f}   Total credit {to_dec(tb['total_credit']):,.2f}   "
                         + ("Balanced" if ok else "OUT OF BALANCE"))
        self.sum.setStyleSheet(f"background:{'#2f9e6f' if ok else '#d64545'}; color:#fff;")
