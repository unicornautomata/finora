"""Sign-in and re-sign-in dialogs. Authentication happens inside the dialog (off the UI thread), and every
problem is shown inline, so the user never gets a pop-up for a mistyped password."""
from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QLayout, QLineEdit, QSpinBox, QVBoxLayout, QWidget)

from . import design
from . import settings as _settings
from .api_client import ApiClient, ApiError
from .auth_flow import describe_login_error, is_encrypted_url, is_local_url, looks_like_caps_lock, normalize_server_url
from .components import Banner, Button
from .design import icons
from .design.brand import BrandHeader, app_icon, logo_pixmap
from .tasks import run_async

S = design.SPACE


def _labelled(text: str, widget: QWidget) -> QWidget:
    box = QWidget(); v = QVBoxLayout(box); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(S.xs)
    lab = QLabel(text); lab.setObjectName("fieldLabel"); v.addWidget(lab); v.addWidget(widget)
    return box


class _PasswordField(QLineEdit):
    """Password input with a show/hide toggle and a caps-lock hint."""

    def __init__(self, caps_label: QLabel, parent=None):
        super().__init__(parent)
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.caps_label = caps_label
        self._toggle = QAction(icons.icon("eye", 16, design.palette().text2_strong), "Show password", self)
        self._toggle.setCheckable(True)
        self._toggle.toggled.connect(self._show)
        self.addAction(self._toggle, QLineEdit.ActionPosition.TrailingPosition)

    def _show(self, on: bool):
        self.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password)
        self._toggle.setIcon(icons.icon("eye-off" if on else "eye", 16, design.palette().text2_strong))
        self._toggle.setText("Hide password" if on else "Show password")

    def keyPressEvent(self, e):
        caps = looks_like_caps_lock(e.text(), bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier))
        if caps is not None:
            self.caps_label.setVisible(caps)
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        self.caps_label.setVisible(False)
        super().focusOutEvent(e)


class LoginDialog(QDialog):
    """Connect to a FINORA server, or host one on this computer. On success `client`, `meta` and `server` are set."""

    def __init__(self, host_default: bool = False, server=None, parent=None):
        super().__init__(parent)
        self.s = _settings.app_settings()
        self.server, self.client, self.meta = server, None, None
        self._busy = self._cancelled = False
        self.setWindowTitle(f"Sign in to {design.PRODUCT_NAME}"); self.setWindowIcon(app_icon())

        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)      # the dialog grows to fit banners and host fields
        # ---- brand panel
        panel = QFrame(); panel.setObjectName("brandPanel"); panel.setFixedWidth(280)
        pv = QVBoxLayout(panel); pv.setContentsMargins(S.xl + 4, S.xxl, S.xl + 4, S.xl)
        pv.addWidget(BrandHeader(on_dark=True, size=52)); pv.addStretch(1)
        hero = QLabel(design.TAGLINE); hero.setObjectName("brandHero"); hero.setWordWrap(True); pv.addWidget(hero)
        root.addWidget(panel)

        # ---- form
        side = QVBoxLayout(); side.setContentsMargins(S.xxl, S.xxl, S.xxl, S.xl); side.setSpacing(S.md)
        title = QLabel("Sign in"); title.setObjectName("title"); side.addWidget(title)
        sub = QLabel("Enter your details to continue."); sub.setObjectName("muted"); side.addWidget(sub)

        self.mode_row = QWidget(); mr = QHBoxLayout(self.mode_row); mr.setContentsMargins(0, 0, 0, 0); mr.setSpacing(S.sm)
        self.btn_connect = Button("Connect to a server", "segment"); self.btn_host = Button("Host on this computer", "segment")
        grp = QButtonGroup(self); grp.setExclusive(True); grp.addButton(self.btn_connect); grp.addButton(self.btn_host)
        mr.addWidget(self.btn_connect); mr.addWidget(self.btn_host)
        side.addWidget(self.mode_row)

        self.url = QLineEdit(self.s.value("url", "http://127.0.0.1:8000")); self.url.setPlaceholderText("http://192.168.1.10:8000")
        self.test_btn = Button("Test connection", "ghost", size="sm"); self.test_btn.clicked.connect(self._test)
        url_row = QWidget(); ur = QHBoxLayout(url_row); ur.setContentsMargins(0, 0, 0, 0); ur.setSpacing(S.sm)
        ur.addWidget(self.url, 1); ur.addWidget(self.test_btn)
        self.g_url = _labelled("Server address", url_row)

        self.db = QLineEdit(self.s.value("db", "finora.db"))
        browse = Button("Browse…", "secondary", size="sm"); browse.clicked.connect(self._browse)
        db_row = QWidget(); dr = QHBoxLayout(db_row); dr.setContentsMargins(0, 0, 0, 0); dr.setSpacing(S.sm)
        dr.addWidget(self.db, 1); dr.addWidget(browse)
        self.g_db = _labelled("Database file (created if it does not exist)", db_row)
        self.port = QSpinBox(); self.port.setRange(1024, 65535); self.port.setValue(int(self.s.value("port", 8000)))
        self.g_port = _labelled("Port", self.port)
        self.lan = QCheckBox("Allow other computers on the network to connect")
        self.lan.setChecked(self.s.value("lan", False, bool))
        self.lan_note = QLabel("Traffic is not encrypted (HTTP). Use this only on a trusted network or VPN.")
        self.lan_note.setObjectName("caption"); self.lan_note.setWordWrap(True)
        self.g_lan = QWidget(); lv = QVBoxLayout(self.g_lan); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(S.xs)
        lv.addWidget(self.lan); lv.addWidget(self.lan_note)
        for g in (self.g_url, self.g_db, self.g_port, self.g_lan):
            side.addWidget(g)

        self.user = QLineEdit(self.s.value("user", "")); self.user.setPlaceholderText("Username")
        side.addWidget(_labelled("Username", self.user))
        self.caps = QLabel("Caps Lock appears to be on"); self.caps.setObjectName("warnText"); self.caps.setVisible(False)
        self.pw = _PasswordField(self.caps); self.pw.setPlaceholderText("Password")
        side.addWidget(_labelled("Password", self.pw)); side.addWidget(self.caps)
        self.remember = QCheckBox("Remember my username"); self.remember.setChecked(self.s.value("remember", True, bool))
        side.addWidget(self.remember)

        self.banner = Banner(); side.addWidget(self.banner)
        self.copy_btn = Button("Copy password", "secondary", "copy", size="sm"); self.copy_btn.setVisible(False)
        self.copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.pw.text()))
        side.addWidget(self.copy_btn, 0, Qt.AlignmentFlag.AlignLeft)
        side.addStretch(1)

        row = QHBoxLayout(); row.addStretch(1)
        self.cancel_btn = Button("Cancel"); self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn = Button("Sign in", "primary"); self.ok_btn.setDefault(True); self.ok_btn.clicked.connect(self._ok)
        row.addWidget(self.cancel_btn); row.addWidget(self.ok_btn); side.addLayout(row)
        host = QWidget(); host.setLayout(side); root.addWidget(host, 1)
        self.setMinimumWidth(780)

        self.btn_host.clicked.connect(lambda: self._set_mode(True)); self.btn_connect.clicked.connect(lambda: self._set_mode(False))
        self.lan.toggled.connect(lambda _: self._url_notes())
        self.url.textChanged.connect(lambda _: self._url_notes())
        self._set_mode(host_default or self.s.value("host", False, bool))
        (self.pw if self.user.text() else self.user).setFocus()

    # ---- mode and notes
    @property
    def hosting(self) -> bool:
        return self.btn_host.isChecked()

    def _set_mode(self, hosting: bool):
        (self.btn_host if hosting else self.btn_connect).setChecked(True)
        locked = self.server is not None
        self.mode_row.setVisible(not locked)
        self.g_url.setVisible(not hosting)
        for g in (self.g_db, self.g_port, self.g_lan):
            g.setVisible(hosting and not locked)
        if locked:
            self.banner.show_message(f"This computer is hosting the server on port {self.server.port}.", "info")
        self._url_notes()

    def _url_notes(self):
        self.lan_note.setVisible(self.lan.isChecked())
        if self._busy or self.server is not None and self.hosting:
            return
        if not self.hosting:
            try:
                url = normalize_server_url(self.url.text())
            except ValueError:
                return
            if not is_local_url(url) and not is_encrypted_url(url):
                self.banner.show_message("This connection is not encrypted. Passwords are sent as plain text, "
                                         "so use it only on a trusted network or VPN.", "warning")
                return
        if self.banner.kind in ("warning",) and self.banner.isVisible() and "not encrypted" in self.banner.text():
            self.banner.clear()

    def _browse(self):
        p, _ = QFileDialog.getSaveFileName(self, "Database file", self.db.text(), "SQLite (*.db)",
                                           options=QFileDialog.Option.DontConfirmOverwrite)
        if p:
            self.db.setText(p)

    # ---- busy state
    def _set_busy(self, busy: bool, label: str = "Signing in…"):
        self._busy = busy
        for w in (self.url, self.db, self.port, self.lan, self.user, self.pw, self.remember, self.test_btn,
                  self.btn_connect, self.btn_host, self.ok_btn):
            w.setEnabled(not busy)
        self.ok_btn.setText(label if busy else "Sign in")
        self.setCursor(Qt.CursorShape.BusyCursor if busy else Qt.CursorShape.ArrowCursor)

    def _flag_credentials(self, invalid: bool):
        for f in (self.user, self.pw):
            f.setProperty("invalid", invalid); f.style().unpolish(f); f.style().polish(f)

    # ---- actions
    def _params(self):
        user, pw = self.user.text().strip(), self.pw.text()
        if not user or not pw:
            raise ValueError("Enter your username and password.")
        if self.hosting:
            if not self.db.text().strip():
                raise ValueError("Choose a database file for the server.")
            return dict(hosting=True, db=self.db.text().strip(), port=self.port.value(), lan=self.lan.isChecked(),
                        user=user, pw=pw, url="")
        return dict(hosting=False, url=normalize_server_url(self.url.text()), user=user, pw=pw)

    def _ok(self):
        if self._busy:
            return
        self._flag_credentials(False); self.banner.clear(); self.copy_btn.setVisible(False)
        try:
            params = self._params()
        except ValueError as ex:
            self.banner.show_message(str(ex), "danger")
            return
        self._set_busy(True, "Starting server…" if params["hosting"] and self.server is None else "Signing in…")
        run_async(lambda: self._attempt(params), self._on_ok, lambda ex: self._on_fail(ex, params), raw_errors=True)

    def _attempt(self, p):                                 # runs in a worker thread
        server = self.server
        if p["hosting"] and server is None:
            from ..server.host import ServerThread
            server = ServerThread(p["db"], "0.0.0.0" if p["lan"] else "127.0.0.1", p["port"])
            server.start()
            if not server.wait_ready():
                raise ApiError(f"The server could not start. Is port {p['port']} already in use?")
            if server.initial_admin_password:
                return dict(server=server, first_run=server.initial_admin_password)
        url = f"http://127.0.0.1:{server.port}" if p["hosting"] else p["url"]
        client = ApiClient(url)
        client.login(p["user"], p["pw"])
        return dict(server=server, client=client, meta=client.meta())

    def _on_ok(self, res):
        if res.get("server") is not None:
            self.server = res["server"]                  # keep it even if the dialog was cancelled, so the app can stop it
        if self._cancelled:
            return
        self._set_busy(False)
        if "first_run" in res:
            self.user.setText("admin"); self.pw.setText(res["first_run"])
            self.pw._show(True)
            self.copy_btn.setVisible(True)
            self.banner.show_message("A new database was created. Your administrator password is filled in below. "
                                     "Write it down now: it is shown only once. Press Sign in to continue, then change it "
                                     "under Administration.", "success")
            self.ok_btn.setFocus()
            return
        self.client, self.meta = res["client"], res["meta"]
        self.s.setValue("host", self.hosting); self.s.setValue("url", self.url.text().strip())
        self.s.setValue("db", self.db.text()); self.s.setValue("port", self.port.value())
        self.s.setValue("lan", self.lan.isChecked()); self.s.setValue("remember", self.remember.isChecked())
        self.s.setValue("user", self.user.text().strip() if self.remember.isChecked() else "")
        self.accept()

    def _on_fail(self, ex, params):
        if self._cancelled:
            return
        self._set_busy(False)
        text, kind = describe_login_error(ex, params.get("url", ""))
        self.banner.show_message(text, kind)
        if isinstance(ex, ApiError) and ex.status in (401, 429):
            self._flag_credentials(ex.status == 401)
            self.pw.selectAll(); self.pw.setFocus()

    def _test(self):
        try:
            url = normalize_server_url(self.url.text())
        except ValueError as ex:
            self.banner.show_message(str(ex), "danger"); return
        self.banner.show_message(f"Checking {url} …", "info"); self.test_btn.setEnabled(False)

        def done(_):
            self.test_btn.setEnabled(True)
            self.banner.show_message(f"Server reachable at {url}.", "success")

        def failed(ex):
            self.test_btn.setEnabled(True)
            self.banner.show_message(describe_login_error(ex, url)[0], "danger")
        run_async(lambda: ApiClient(url).health(), done, failed, raw_errors=True)

    def reject(self):
        self._cancelled = True
        super().reject()


class ReauthDialog(QDialog):
    """Shown when the server says the session has expired. Keeps the window and any unsaved work intact."""

    def __init__(self, client: ApiClient, parent=None):
        super().__init__(parent)
        self.client = client
        self.username = (client.user or {}).get("username", "")
        self.setWindowTitle(design.PRODUCT_NAME); self.setWindowIcon(app_icon()); self.setMinimumWidth(420)
        lay = QVBoxLayout(self); lay.setContentsMargins(S.xl, S.xl, S.xl, S.lg); lay.setSpacing(S.md)
        lay.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        head = QHBoxLayout(); mark = QLabel(); mark.setPixmap(logo_pixmap(40)); mark.setFixedSize(40, 40)
        t = QLabel("Your session has expired"); t.setObjectName("h2")
        head.addWidget(mark); head.addWidget(t, 1); lay.addLayout(head)
        msg = QLabel(f"Sign in again as {self.username} to continue. Your unsaved changes are kept. "
                     "Choosing Sign out discards them."); msg.setWordWrap(True); msg.setObjectName("muted"); lay.addWidget(msg)
        self.caps = QLabel("Caps Lock appears to be on"); self.caps.setObjectName("warnText"); self.caps.setVisible(False)
        self.pw = _PasswordField(self.caps); self.pw.setPlaceholderText("Password")
        lay.addWidget(_labelled("Password", self.pw)); lay.addWidget(self.caps)
        self.banner = Banner(); lay.addWidget(self.banner)
        row = QHBoxLayout(); row.addStretch(1)
        self.out_btn = Button("Sign out", "danger"); self.out_btn.clicked.connect(self.reject)
        self.ok_btn = Button("Sign in", "primary"); self.ok_btn.setDefault(True); self.ok_btn.clicked.connect(self._ok)
        row.addWidget(self.out_btn); row.addWidget(self.ok_btn); lay.addLayout(row)
        self.pw.setFocus()

    def _ok(self):
        if not self.pw.text():
            self.banner.show_message("Enter your password.", "danger"); return
        self.banner.clear(); self.ok_btn.setEnabled(False); self.ok_btn.setText("Signing in…")
        run_async(lambda: self.client.login(self.username, self.pw.text()), self._done, self._failed, raw_errors=True)

    def _done(self, _):
        self.accept()

    def _failed(self, ex):
        self.ok_btn.setEnabled(True); self.ok_btn.setText("Sign in")
        text, kind = describe_login_error(ex, self.client.base_url)
        self.banner.show_message(text, kind); self.pw.selectAll(); self.pw.setFocus()
