"""Screens. Each one is built from the definitions the server publishes at /meta."""
from __future__ import annotations
from datetime import date
from decimal import Decimal

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (QAbstractItemView, QDateEdit, QDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                             QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu,
                             QSplitter, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
                             QComboBox)

from . import design
from .components import (Button, Card, EmptyStateStack, ReportHeader, ResponsiveFormGrid, StatusChip,
                         configure_table, dialogs, page_margins, scroll_page)
from .tasks import run_async
from .widgets import SEP, AmountDelegate, Editor, GLDelegate, RefCache, to_dec

R = Qt.ItemDataRole
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def card(layout=None):
    return Card.from_layout(layout) if layout is not None else Card()


def fmt(v) -> str:
    d = to_dec(v)
    return "" if d == 0 else f"{d:,.2f}"


class Screen(QWidget):
    """Base class. The shell shows the same fixed toolbar for every screen and only
    enables the buttons a screen supports, like the original CRUD button row."""
    state_changed = pyqtSignal()
    message = pyqtSignal(str, str)        # text, kind: success | info | warning | error
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

    def error(self, msg): self.message.emit(msg, "error")
    def info(self, msg): self.message.emit(msg, "success")      # an operation succeeded
    def note(self, msg): self.message.emit(msg, "info")        # neutral information


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
        go = Button("Search", "primary"); go.clicked.connect(self.search)
        row.addWidget(self.q, 1); row.addWidget(go)
        lay.addLayout(row)
        cols = ["Number", "Date", "Reference", "Description", "Total", "Status"]
        self.t = QTableWidget(0, len(cols)); self.t.setHorizontalHeaderLabels(cols)
        configure_table(self.t, stretch_col=3)
        self.t.doubleClicked.connect(self.accept_row)
        self.stack = EmptyStateStack(self.t, "No journals found", "Try a different search, or create a new journal.", "search")
        lay.addWidget(self.stack, 1)
        self.status = QLabel(""); self.status.setObjectName("muted"); lay.addWidget(self.status)
        self.search()

    def search(self):
        self.status.setText("Loading…")
        run_async(lambda: self.client.journals(doctype=self.doctype, q=self.q.text().strip()),
                  self._fill, lambda m: self.status.setText(m))

    def _fill(self, rows):
        self.rows = rows
        self.stack.show_rows(bool(rows))
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
        self._lay = QVBoxLayout(self); self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.addWidget(QLabel("Loading…"), 0, Qt.AlignmentFlag.AlignCenter)
        refs.load(["companies", "gl_accounts"], self._build, self.error)

    # ---- construction
    def _build(self):
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        content = QWidget(); lay = page_margins(QVBoxLayout(content))
        self._lay.addWidget(scroll_page(content))

        # header card: 3 columns on wide windows, 2 or 1 as the window narrows
        self.h: dict[str, Editor] = {}
        hg = ResponsiveFormGrid()
        for row in self.doc["header_layout"]:
            for f in row:
                ed = Editor(f, self.refs); self.h[f["name"]] = ed
                hg.add_field(f["label"], ed.widget)
        df = self.doc["description_field"]
        self.h["description"] = Editor(df, self.refs)
        hg.add_field(df["label"], self.h["description"].widget, full=True)
        self.badge = StatusChip("New", "info")
        top = QHBoxLayout(); top.addWidget(self.badge); top.addStretch(1)
        hc = Card(); hc.body.addLayout(top); hc.body.addWidget(hg)
        lay.addWidget(hc)
        for name, ed in self.h.items():
            w = ed.widget
            if hasattr(w, "textEdited"): w.textEdited.connect(self._touch)
            elif hasattr(w, "dateChanged"): w.dateChanged.connect(self._touch)
            elif hasattr(w, "currentTextChanged"): w.currentTextChanged.connect(self._touch)

        # line grid
        self.tbl = QTableWidget(0, len(self.cols) + 1)
        self.tbl.setHorizontalHeaderLabels([c["label"] for c in self.cols] + [""])
        configure_table(self.tbl, stretch_col=self.col_ix["description"], select_rows=False, editable=True)
        self.tbl.setMinimumHeight(200)
        hdr = self.tbl.horizontalHeader()
        for i, c in enumerate(self.cols):
            if i != self.col_ix["description"]:
                hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive); self.tbl.setColumnWidth(i, c.get("width", 120))
        hdr.setSectionResizeMode(len(self.cols), QHeaderView.ResizeMode.Fixed); self.tbl.setColumnWidth(len(self.cols), 44)
        self.tbl.setItemDelegateForColumn(self.col_ix["glcd"], GLDelegate(self.refs, self.tbl))
        for k in ("debit", "credit"):
            self.tbl.setItemDelegateForColumn(self.col_ix[k], AmountDelegate(self.tbl))
        self.tbl.itemChanged.connect(self._on_item)
        self.tbl.currentCellChanged.connect(lambda *_: self._refresh_detail())

        foot = QHBoxLayout(); foot.setSpacing(design.SPACE.lg)
        self.btn_add = Button("Add line", "secondary", "plus", size="sm"); self.btn_add.clicked.connect(lambda: self._add_line())
        self.lbl_dr, self.lbl_cr, self.lbl_diff = QLabel(), QLabel(), QLabel()
        self.chip = StatusChip("Empty", "neutral")
        foot.addWidget(self.btn_add); foot.addStretch(1)
        for w in (self.lbl_dr, self.lbl_cr, self.lbl_diff, self.chip):
            foot.addWidget(w)
        lc = Card(); lc.body.addWidget(self.tbl, 1); lc.body.addLayout(foot)
        lay.addWidget(lc, 1)

        # line item details
        self.d: dict[str, Editor] = {}
        dg = ResponsiveFormGrid()
        for row in self.doc["detail_layout"]:
            for f in row:
                ed = Editor(f, self.refs); self.d[f["name"]] = ed
                dg.add_field(f["label"], ed.widget)
                if not f.get("readonly") and hasattr(ed.widget, "textEdited"):
                    ed.widget.textEdited.connect(lambda _=None, n=f["name"]: self._on_detail(n))
        pf = self.doc["detail_description"]
        self.d[pf["name"]] = Editor(pf, self.refs)
        self.d[pf["name"]].widget.textEdited.connect(lambda _=None: self._on_detail(pf["name"]))
        dg.add_field(pf["label"], self.d[pf["name"]].widget, full=True)
        dc = Card("Line Item Details"); dc.body.addWidget(dg)
        lay.addWidget(dc)
        self.refs.changed.connect(self._refs_changed)
        self.new_document()

    def _refs_changed(self, names):
        if not hasattr(self, "h"):
            return
        for ed in [*self.h.values(), *self.d.values()]:
            if ed.type == "ref" and ed.field["ref"] in names:
                ed.reload_options(self.refs)
        if "gl_accounts" in names:
            self._render_lines()

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
        self.badge.set_status(text, {"new": "info", "draft": "warning", "posted": "success", "reversed": "neutral"}[st])

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
        self.chip.set_status("Balanced" if ok else ("Out of balance" if td or tc else "Empty"),
                             "success" if ok else ("danger" if td or tc else "neutral"))

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
            self._load(j); self.info(f"Transaction Number {j['id']} {self.doctype} was saved as a draft!")
            if then: then()
        self._call(fn, ok)

    def act_save(self):
        if self.editable: self._save()

    def act_post(self):
        if not (self.can_post and self.editable): return
        td, tc = self._totals()
        if td != tc:
            return self.error(f"The journal is out of balance by {abs(td - tc):,.2f}. Debits must equal credits before posting.")
        if not dialogs.confirm(self, "Post this journal?", "Post journal", confirm_text="Post journal",
                               detail="Posted journals cannot be edited. To correct one, reverse it."):
            return
        def post():
            j = self.journal
            self._call(lambda: self.client.journal_post(j["id"], j["version"]),
                       lambda r: (self._load(r), self.info(f"Transaction Number {r['doc_no']} {self.doctype} was posted!")))
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
        if not dialogs.confirm(self, "Delete this draft journal?", "Delete draft", confirm_text="Delete", danger=True): return
        j = self.journal
        self._call(lambda: self.client.journal_delete(j["id"], j["version"]),
                   lambda _: (self.new_document(), self.info(f"Draft transaction {j['id']} {self.doctype} was deleted!")))

    def act_reverse(self):
        if self.status != "posted": return
        text, ok = QInputDialog.getText(self, "Reverse journal", "Posting date for the reversal (YYYY-MM-DD):",
                                        text=date.today().isoformat())
        if not ok: return
        jid, orig_no = self.journal["id"], self.journal["doc_no"]
        self._call(lambda: self.client.journal_reverse(jid, text.strip()),
                   lambda r: (self._load(r), self.info(f"Transaction Number {r['doc_no']} {self.doctype} was posted as a reversal of {orig_no}!")))

    def act_copy(self):
        if not self._confirm_discard(): return
        lines = [dict(l) for l in self.lines]
        h = {k: self.h[k].value() for k in ("cocd", "reference", "department", "description")}
        self.new_document(lines=lines, header=h); self.dirty = True; self._changed()
        self.note("Copied into a new draft. Review it, then save.")

    def _confirm_discard(self):
        if not self.dirty: return True
        return dialogs.confirm(self, "Discard unsaved changes?", "Unsaved changes", confirm_text="Discard changes",
                               cancel_text="Keep editing", danger=True)


# ====================================================================== master data
class MasterScreen(Screen):
    def __init__(self, client, meta, refs, entity):
        super().__init__()
        self.client, self.meta, self.refs, self.entity = client, meta, refs, entity
        self.e = meta["entities"][entity]
        self.can_write = "write" in meta["permissions"]
        self.key, self.rows, self.busy = None, [], False
        self._lay = page_margins(QVBoxLayout(self))
        self._lay.addWidget(QLabel("Loading…"), 0, Qt.AlignmentFlag.AlignCenter)
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
        configure_table(self.t)
        self.t.horizontalHeader().setStretchLastSection(True)
        self.t.itemSelectionChanged.connect(self._select)
        self.stack = EmptyStateStack(self.t, f"No {self.e['plural'].lower()} yet",
                                     f"Use New to add the first {self.e['label'].lower()}.", "inbox")
        left.addWidget(self.stack, 1)
        lw = QWidget(); lw.setLayout(left)

        self.form: dict[str, Editor] = {}
        fl = QFormLayout(); fl.setVerticalSpacing(design.SPACE.md); fl.setHorizontalSpacing(design.SPACE.lg)
        fl.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        fl.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for f in fields:
            ed = Editor(f, self.refs); self.form[f["name"]] = ed
            lab = QLabel(f["label"] + (" *" if f["required"] else "")); lab.setObjectName("fieldLabel")
            fl.addRow(lab, ed.widget)
        self.hint = QLabel(""); self.hint.setObjectName("muted"); self.hint.setWordWrap(True)
        title = QLabel(self.e["label"]); title.setObjectName("h2")
        rv = QVBoxLayout(); rv.addWidget(title); rv.addLayout(fl); rv.addWidget(self.hint); rv.addStretch(1)
        right = card(rv); right.setMinimumWidth(300)
        sp = QSplitter(); sp.setChildrenCollapsible(False); sp.addWidget(lw); sp.addWidget(scroll_page(right))
        sp.setStretchFactor(0, 3); sp.setStretchFactor(1, 2)
        self._lay.addWidget(sp)
        self.refs.changed.connect(self._refs_changed)
        self.act_new(); self.act_refresh()

    def _refs_changed(self, names):
        if hasattr(self, "form"):
            for ed in self.form.values():
                if ed.type == "ref" and ed.field["ref"] in names:
                    ed.reload_options(self.refs)

    def heading(self):
        return f"{self.e['plural']}"

    def actions(self):
        if self.busy or not hasattr(self, "form"): return {}
        return dict(new=self.can_write, save=self.can_write,
                    delete=self.can_write and self.key is not None and self.e.get("deletable", True),
                    refresh=True)

    def _fill_table(self):
        searching = bool(self.search.text().strip())
        self.stack.show_rows(bool(self.rows),
                             "No matches" if searching else f"No {self.e['plural'].lower()} yet",
                             "Try a different search term." if searching else f"Use New to add the first {self.e['label'].lower()}.")
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
        verb = "created" if key is None else "updated"
        if key is None:
            fn = lambda: self.client.master_create(self.entity, data)
        else:
            data.pop(pk, None); fn = lambda: self.client.master_update(self.entity, key, data)

        def ok(saved):
            self.info(f"{self.e['label']} '{saved[pk]}' was {verb}!"); self.master_changed.emit(self.entity)
            self.key = saved[pk]; self.act_refresh()
        self._call(fn, ok)

    def act_delete(self):
        if self.key is None: return
        if not dialogs.confirm(self, f"Delete {self.e['label'].lower()} '{self.key}'?", "Delete", confirm_text="Delete", danger=True): return
        key = self.key
        self._call(lambda: self.client.master_delete(self.entity, key),
                   lambda _: (self.info(f"{self.e['label']} '{key}' was deleted!"), self.master_changed.emit(self.entity), self.act_new(), self.act_refresh()))


# ====================================================================== reports
class TrialBalanceScreen(Screen):
    def __init__(self, client, meta, refs):
        super().__init__()
        self.client, self.refs, self.busy = client, refs, False
        self._lay = page_margins(QVBoxLayout(self))
        self._lay.addWidget(QLabel("Loading…"), 0, Qt.AlignmentFlag.AlignCenter)
        refs.load(["companies"], self._build, self.error)

    def _build(self):
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w: w.deleteLater()
        bar = QHBoxLayout()
        self.co = Editor(dict(name="cocd", label="Company", type="ref", required=True, ref="companies"), self.refs)
        self.asof = Editor(dict(name="as_of", label="As of", type="date"), self.refs)
        go = Button("Run report", "primary", "bar-chart"); go.clicked.connect(self.act_refresh)
        for t, w in (("Company", self.co.widget), ("As of", self.asof.widget)):
            l = QLabel(t); l.setObjectName("fieldLabel"); bar.addWidget(l); bar.addWidget(w, 1)
        bar.addWidget(go)
        self.report = ReportHeader("Trial Balance"); self._lay.addWidget(self.report)
        self.report.set_report("Choose a company and date, then run the report", None)
        self._lay.addWidget(card(bar))
        cols = ["GL Account", "Description", "Debit", "Credit", "Balance"]
        self.t = QTableWidget(0, 5); self.t.setHorizontalHeaderLabels(cols)
        configure_table(self.t, stretch_col=1)
        self.stack = EmptyStateStack(self.t, "Run the report", "Choose a company and date, then press Run report.", "bar-chart")
        self.stack.show_rows(False)
        self._lay.addWidget(self.stack, 1)
        self.sum = StatusChip("", "neutral"); self._lay.addWidget(self.sum, 0, Qt.AlignmentFlag.AlignRight)
        self.refs.changed.connect(lambda names: self.co.reload_options(self.refs) if "companies" in names else None)
        if self.refs.data.get("companies") and len(self.refs.data["companies"]) == 1:
            self.co.set_value(self.refs.data["companies"][0]["cocd"]); self.act_refresh()

    def heading(self): return "Trial Balance"
    def actions(self): return dict(refresh=True) if hasattr(self, "t") else {}

    def act_refresh(self):
        cocd = self.co.value()
        if not cocd: return self.error("Choose a company first")
        run_async(lambda: self.client.trial_balance(cocd, self.asof.value()), self._fill, self.error)

    def _fill(self, tb):
        self.stack.show_rows(bool(tb["rows"]), "No posted journals", "Nothing has been posted for this company up to that date.")
        self.t.setRowCount(len(tb["rows"]))
        for i, r in enumerate(tb["rows"]):
            for c, v in enumerate([r["glcd"], r["description"] or "", f"{to_dec(r['debit']):,.2f}",
                                   f"{to_dec(r['credit']):,.2f}", f"{to_dec(r['balance']):,.2f}"]):
                it = QTableWidgetItem(v)
                if c >= 2: it.setTextAlignment(RIGHT)
                self.t.setItem(i, c, it)
        label = dict(self.refs.pairs("companies")).get(tb["cocd"], tb["cocd"])
        self.report.set_report(f"{label}  ·  As of {tb['as_of']}", (self.client.user or {}).get("username"))
        ok = tb["balanced"]
        self.sum.set_status(f"Total debit {to_dec(tb['total_debit']):,.2f}   Total credit {to_dec(tb['total_credit']):,.2f}   "
                            + ("Balanced" if ok else "OUT OF BALANCE"), "success" if ok else "danger")
