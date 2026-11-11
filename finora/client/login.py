from __future__ import annotations
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
                             QVBoxLayout, QFileDialog)


class LoginDialog(QDialog):
    """Connect to a server, or host one on this machine (host mode)."""

    def __init__(self, host_default=False, username="", password="", parent=None):
        super().__init__(parent)
        self.s = QSettings("Finora", "Finora")
        self.setWindowTitle("Sign in to Finora"); self.setMinimumWidth(420)
        lay = QVBoxLayout(self); lay.setSpacing(12)
        t = QLabel("Finora"); t.setObjectName("title"); lay.addWidget(t)
        form = QFormLayout()
        self.host_cb = QCheckBox("Host the server on this computer")
        self.host_cb.setChecked(host_default or self.s.value("host", False, bool))
        self.url = QLineEdit(self.s.value("url", "http://127.0.0.1:8000"))
        self.db = QLineEdit(self.s.value("db", "ledger.db")); browse = QPushButton("…"); browse.setFixedWidth(34)
        browse.clicked.connect(self._browse)
        dbrow = QHBoxLayout(); dbrow.addWidget(self.db, 1); dbrow.addWidget(browse)
        self.port = QSpinBox(); self.port.setRange(1024, 65535); self.port.setValue(int(self.s.value("port", 8000)))
        self.lan = QCheckBox("Allow other computers on the network to connect")
        self.lan.setChecked(self.s.value("lan", False, bool))
        self.user = QLineEdit(username or self.s.value("user", "")); self.pw = QLineEdit(password)
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(self.host_cb)
        form.addRow("Server address", self.url)
        form.addRow("Database file", dbrow)
        form.addRow("Port", self.port)
        form.addRow("", self.lan)
        form.addRow("Username", self.user); form.addRow("Password", self.pw)
        self.dbrow = dbrow
        self.form = form
        lay.addLayout(form)
        self.err = QLabel(""); self.err.setStyleSheet("color:#d64545"); self.err.setWordWrap(True); lay.addWidget(self.err)
        row = QHBoxLayout(); row.addStretch(1)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        ok = QPushButton("Sign in"); ok.setObjectName("primary"); ok.setDefault(True); ok.clicked.connect(self._ok)
        row.addWidget(cancel); row.addWidget(ok); lay.addLayout(row)
        self.host_cb.toggled.connect(self._toggle); self._toggle(self.host_cb.isChecked())
        (self.pw if self.user.text() else self.user).setFocus()

    def _toggle(self, hosting):
        self.form.setRowVisible(self.url, not hosting)
        for w in (self.dbrow, self.port, self.lan):
            self.form.setRowVisible(w, hosting)

    def _browse(self):
        p, _ = QFileDialog.getSaveFileName(self, "Database file", self.db.text(), "SQLite (*.db)", options=QFileDialog.Option.DontConfirmOverwrite)
        if p: self.db.setText(p)

    def _ok(self):
        if not self.user.text().strip() or not self.pw.text():
            self.err.setText("Enter your username and password."); return
        self.s.setValue("host", self.host_cb.isChecked()); self.s.setValue("url", self.url.text())
        self.s.setValue("db", self.db.text()); self.s.setValue("port", self.port.value())
        self.s.setValue("lan", self.lan.isChecked()); self.s.setValue("user", self.user.text())
        self.accept()

    @property
    def hosting(self): return self.host_cb.isChecked()
