"""Reusable, definition-driven building blocks."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import QDate, QRegularExpression, Qt
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QDateEdit, QLineEdit, QStyledItemDelegate)

from .tasks import run_async

SEP = " – "


class RefCache:
    """Lookup lists (GL accounts, companies, ...) fetched once and shared by all screens."""

    def __init__(self, client, entities: dict):
        self.client, self.entities, self.data = client, entities, {}

    def invalidate(self, *names):
        for n in (names or list(self.data)):
            self.data.pop(n, None)

    def load(self, names, done, fail=None):
        missing = [n for n in set(names) if n not in self.data and n in self.entities]
        if not missing:
            return done()

        def fetch():
            return {n: self.client.master_list(n, limit=5000) for n in missing}

        def ok(res):
            self.data.update(res)
            done()
        run_async(fetch, ok, fail)

    def pairs(self, name):
        e = self.entities.get(name)
        if not e:
            return []
        pk = e["pk"]
        label = next((f["name"] for f in e["fields"] if f["type"] == "text" and f["name"] != pk), None)
        return [(r[pk], f"{r[pk]}{SEP}{r.get(label) or ''}".rstrip(SEP + " ") if label else r[pk])
                for r in self.data.get(name, [])]


def to_dec(text) -> Decimal:
    try:
        return Decimal(str(text).replace(",", "").strip() or "0")
    except InvalidOperation:
        return Decimal(0)


class Editor:
    """Uniform wrapper so forms can read/write any field type the same way."""

    def __init__(self, field: dict, refs: RefCache | None = None):
        self.field, t = field, field["type"]
        self.type = t
        if t == "date":
            w = QDateEdit(); w.setCalendarPopup(True); w.setDisplayFormat("yyyy-MM-dd")
            w.setDate(QDate.currentDate())
        elif t == "bool":
            w = QCheckBox()
        elif t == "select":
            w = QComboBox(); w.addItems(field["options"])
        elif t == "ref":
            w = QComboBox(); w.setEditable(True); w.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            if not field.get("required"):
                w.addItem("", None)
            for key, label in (refs.pairs(field["ref"]) if refs else []):
                w.addItem(label, key)
            w.completer().setFilterMode(Qt.MatchFlag.MatchContains)
            w.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            w.setCurrentIndex(0 if not field.get("required") else -1)
        else:
            w = QLineEdit()
            if t == "password":
                w.setEchoMode(QLineEdit.EchoMode.Password)
            if t in ("amount", "qty"):
                dec = 2 if t == "amount" else 3
                w.setValidator(QRegularExpressionValidator(QRegularExpression(rf"^\d{{0,13}}(\.\d{{0,{dec}}})?$")))
                w.setAlignment(Qt.AlignmentFlag.AlignRight)
            if field.get("maxlen"):
                w.setMaxLength(field["maxlen"])
        self.widget = w
        if field.get("readonly"):
            self.set_readonly(True)

    def value(self):
        w, t = self.widget, self.type
        if t == "date":
            return w.date().toString("yyyy-MM-dd")
        if t == "bool":
            return 1 if w.isChecked() else 0
        if t == "select":
            return w.currentText()
        if t == "ref":
            text = w.currentText().strip()
            i = w.findText(text)
            if i >= 0:
                return w.itemData(i)
            return text.split(SEP)[0].strip() or None
        return w.text().strip() or None

    def set_value(self, v):
        w, t = self.widget, self.type
        if t == "date":
            d = QDate.fromString(str(v or ""), "yyyy-MM-dd")
            w.setDate(d if d.isValid() else QDate.currentDate())
        elif t == "bool":
            w.setChecked(bool(v))
        elif t == "select":
            i = w.findText(str(v)); w.setCurrentIndex(max(i, 0))
        elif t == "ref":
            i = w.findData(v)
            if i >= 0:
                w.setCurrentIndex(i)
            else:
                w.setCurrentIndex(-1); w.setEditText("" if v is None else str(v))
        else:
            w.setText("" if v is None else str(v))

    def set_readonly(self, ro: bool):
        w = self.widget
        if isinstance(w, QLineEdit):
            w.setReadOnly(ro)
            w.style().unpolish(w); w.style().polish(w)
        else:
            w.setEnabled(not ro)


class GLDelegate(QStyledItemDelegate):
    """Searchable GL-account picker inside the line grid."""

    def __init__(self, refs: RefCache, parent=None):
        super().__init__(parent)
        self.refs = refs

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.setEditable(True); cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for key, label in self.refs.pairs("gl_accounts"):
            cb.addItem(label, key)
        cb.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        cb.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        cb.setCurrentIndex(-1)
        return cb

    def setEditorData(self, ed, index):
        i = ed.findData(index.data(Qt.ItemDataRole.UserRole))
        if i >= 0:
            ed.setCurrentIndex(i)

    def setModelData(self, ed, model, index):
        text = ed.currentText().strip()
        i = ed.findText(text)
        key, label = (ed.itemData(i), ed.itemText(i)) if i >= 0 else (text.split(SEP)[0].strip(), text)
        model.setData(index, key, Qt.ItemDataRole.UserRole)
        model.setData(index, label, Qt.ItemDataRole.DisplayRole)


class AmountDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        e = QLineEdit(parent)
        e.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\d{0,13}(\.\d{0,2})?$")))
        e.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return e
