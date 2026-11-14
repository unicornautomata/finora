"""Main window: collapsible sidebar, fixed action toolbar, closable tabs."""
from __future__ import annotations
from datetime import datetime

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QTabBar, QTabWidget,
                             QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import design
from .design import icons
from .clock import format_clock
from .components import Button, StatusMessage, dialogs
from .design.brand import BrandHeader, app_icon
from .api_client import SESSION_EXPIRED_MESSAGE
from .login import ReauthDialog
from .screens import DocumentScreen, MasterScreen, Screen, TrialBalanceScreen
from .widgets import RefCache

# Same button row as the original app, in the same order: (key, label, icon name)
TOOLBAR = [("new", "New", "file-plus", "Start a new document"),
           ("open", "Open", "folder-open", "Open an existing document"),
           ("save", "Save", "save", "Save as a draft"),
           ("post", "Post", "check-circle", "Post to the ledger. Posted journals cannot be edited, only reversed"),
           ("delete", "Delete", "trash", "Delete this draft"),
           ("reverse", "Reverse", "undo", "Reverse this posted journal with a linked entry"),
           ("copy", "Copy", "copy", "Copy into a new draft"),
           ("print", "Print", "printer", "Print (coming soon)"),
           ("refresh", "Refresh", "refresh", "Reload from the server")]
NARROW = 1100            # below this window width the sidebar hides and the toolbar shows icons only
GROUP_ICONS = {"Journals": "book", "Operations": "layers", "Finance": "bar-chart",
               "Master Data": "database", "Administration": "shield"}


class Shell(QMainWindow):
    session_lost = pyqtSignal()          # emitted (possibly from a worker thread) when the server rejects our token

    def __init__(self, client, meta, host_info: str | None = None, on_logout=None):
        super().__init__()
        self.client, self.meta, self.on_logout = client, meta, on_logout
        self.refs = RefCache(client, meta["entities"])
        self._reauth_open = False
        self.session_lost.connect(self._on_session_lost)
        client.on_unauthorized = self.session_lost.emit
        self.setWindowTitle(design.PRODUCT_NAME); self.setWindowIcon(app_icon())
        self.setMinimumSize(900, 600); self.resize(1360, 860); self._narrow = False

        root = QWidget(); root.setObjectName("canvas"); self.setCentralWidget(root)
        outer = QHBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # ---- sidebar (navy; navigation comes from the server menu)
        self.sidebar = QFrame(); self.sidebar.setObjectName("sidebar"); self.sidebar.setFixedWidth(236)
        sv = QVBoxLayout(self.sidebar); sv.setContentsMargins(12, 16, 12, 10); sv.setSpacing(12)
        sv.addWidget(BrandHeader(on_dark=True, size=38))
        self.nav = QTreeWidget(); self.nav.setObjectName("nav"); self.nav.setHeaderHidden(True)
        self.nav.setIndentation(10); self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav.setIconSize(QSize(16, 16))
        self._build_nav(meta["menu"])
        self.nav.itemClicked.connect(self._nav_clicked)
        sv.addWidget(self.nav, 1)
        foot = QLabel(design.TAGLINE); foot.setObjectName("brandTag"); foot.setProperty("onDark", True); foot.setWordWrap(True)
        sv.addWidget(foot)
        outer.addWidget(self.sidebar)

        # ---- right side
        right = QVBoxLayout(); right.setSpacing(0)
        top = QFrame(); top.setObjectName("topbar")
        th = QHBoxLayout(top); th.setContentsMargins(12, 8, 16, 8)
        self.btn_menu = QToolButton(); self.btn_menu.setObjectName("iconbtn"); self.btn_menu.setToolTip("Show or hide the menu")
        self.btn_menu.clicked.connect(self._toggle_sidebar)
        self.mode = QLabel("Welcome"); self.mode.setObjectName("title")
        user = client.user or {}
        self.who = QLabel(f"{user.get('username', '')} · {user.get('role', '')}"); self.who.setObjectName("muted")
        self.btn_theme = QToolButton(); self.btn_theme.setObjectName("iconbtn"); self.btn_theme.clicked.connect(self._toggle_theme)
        self.btn_out = Button("Sign out", "secondary", "log-out", size="sm"); self.btn_out.clicked.connect(self._logout)
        for w in (self.btn_menu, self.mode):
            th.addWidget(w)
        th.addStretch(1)
        for w in (self.who, self.btn_theme, self.btn_out):
            th.addWidget(w)
        right.addWidget(top)

        self.toolbar = QToolBar(); self.toolbar.setMovable(False); self.toolbar.setIconSize(QSize(18, 18))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.acts: dict[str, QAction] = {}
        for key, text, _icon, tip in TOOLBAR:
            a = QAction(text, self); a.setToolTip(tip); a.setStatusTip(tip)
            a.triggered.connect(lambda _=False, k=key: self._do(k)); a.setEnabled(False)
            self.toolbar.addAction(a); self.acts[key] = a
            if key in ("post", "copy"):
                self.toolbar.addSeparator()
        right.addWidget(self.toolbar)

        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True); self.tabs.setTabsClosable(False)   # close buttons are our own themed icons
        self.tabs.tabBar().setUsesScrollButtons(True); self.tabs.tabBar().setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.currentChanged.connect(self._tab_changed)
        right.addWidget(self.tabs, 1)
        rw = QWidget(); rw.setLayout(right); outer.addWidget(rw, 1)

        design.bus.changed.connect(self._refresh_icons)
        self._refresh_icons()
        # status bar: operation messages on the left, weekday / date / time on the right
        self.status_msg = StatusMessage(); self.statusBar().addWidget(self.status_msg, 1)
        self.clock = QLabel(); self.clock.setObjectName("statusClock"); self.statusBar().addPermanentWidget(self.clock)
        self._tick(); self._clock_timer = QTimer(self); self._clock_timer.timeout.connect(self._tick); self._clock_timer.start(1000)
        self.set_status(host_info or f"{design.PRODUCT_NAME} · connected to {client.base_url}", "info")
        self.open_screen("doc:" + (meta["menu"][0]["items"][0]["key"].split(":")[1]))

    # ---- status bar
    def _tick(self):
        self.clock.setText(format_clock(datetime.now()))

    def set_status(self, text: str, kind: str = "info"):
        """Show an operation message at the left of the status bar (stays until the next one)."""
        self.status_msg.set_message(text, "danger" if kind == "error" else kind)

    # ---- responsive behaviour
    def resizeEvent(self, e):
        super().resizeEvent(e)
        narrow = self.width() < NARROW
        if narrow != self._narrow:
            self._narrow = narrow
            self.sidebar.setVisible(not narrow)
            self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if narrow
                                            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

    # ---- icons follow the theme
    def _refresh_icons(self, *_):
        for key, _t, name, _tip in TOOLBAR:
            self.acts[key].setIcon(icons.icon(name))
        self.btn_menu.setIcon(icons.icon("menu", 20))
        self.btn_theme.setIcon(icons.icon("sun" if design.mode() == "dark" else "moon", 20))
        self.btn_theme.setToolTip("Switch to light theme" if design.mode() == "dark" else "Switch to dark theme")
        for i in range(self.tabs.count()):
            b = self.tabs.tabBar().tabButton(i, QTabBar.ButtonPosition.RightSide)
            if b: b.setIcon(icons.icon("x", 12))
        side = design.palette().sidebar_text
        for i in range(self.nav.topLevelItemCount()):
            g = self.nav.topLevelItem(i)
            name = GROUP_ICONS.get(g.text(0))
            if name:
                g.setIcon(0, icons.icon(name, 16, side, side))

    # ---- navigation
    def _build_nav(self, menu):
        self.nav.clear()
        for g in menu:
            gi = QTreeWidgetItem([g["group"]]); f = gi.font(0); f.setBold(True); gi.setFont(0, f)
            gi.setFlags(Qt.ItemFlag.ItemIsEnabled); self.nav.addTopLevelItem(gi)
            for it in g["items"]:
                c = QTreeWidgetItem([it["label"]]); c.setData(0, Qt.ItemDataRole.UserRole, it["key"]); gi.addChild(c)
            for name in g["planned"]:
                c = QTreeWidgetItem([name]); c.setFlags(Qt.ItemFlag.NoItemFlags); c.setToolTip(0, "Planned")
                gi.addChild(c)
            gi.setExpanded(g["group"] in ("Journals", "Master Data", "Finance"))

    def _nav_clicked(self, item, _col=0):
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self.open_screen(key)
        else:
            item.setExpanded(not item.isExpanded())

    def _toggle_sidebar(self):
        self.sidebar.setVisible(not self.sidebar.isVisible())

    def _toggle_theme(self):
        from PyQt6.QtWidgets import QApplication
        design.apply_theme(QApplication.instance(), "light" if design.mode() == "dark" else "dark")

    # ---- screens
    def _make(self, key: str) -> Screen:
        kind, _, arg = key.partition(":")
        if kind == "doc":
            return DocumentScreen(self.client, self.meta, self.refs, arg)
        if kind == "master":
            return MasterScreen(self.client, self.meta, self.refs, arg)
        if kind == "report":
            return TrialBalanceScreen(self.client, self.meta, self.refs)
        raise ValueError(key)

    def open_screen(self, key: str):
        for i in range(self.tabs.count()):
            if self.tabs.widget(i).property("key") == key:
                self.tabs.setCurrentIndex(i); return
        s = self._make(key); s.setProperty("key", key)
        s.state_changed.connect(lambda s=s: self._sync(s)); s.message.connect(self._message)
        s.master_changed.connect(lambda name: self.refs.invalidate(name))
        label = next((i["label"] for g in self.meta["menu"] for i in g["items"] if i["key"] == key), key)
        i = self.tabs.addTab(s, label)
        close = QToolButton(); close.setObjectName("iconbtn"); close.setIcon(icons.icon("x", 12)); close.setToolTip("Close tab")
        close.setAutoRaise(True); close.clicked.connect(lambda _=False, s=s: self._close_tab(self.tabs.indexOf(s)))
        self.tabs.tabBar().setTabButton(i, QTabBar.ButtonPosition.RightSide, close)
        self.tabs.setCurrentIndex(i)

    def _close_tab(self, i):
        if i < 0: return
        s = self.tabs.widget(i)
        if s.is_dirty() and not dialogs.confirm(self, "Close this tab and discard unsaved changes?", "Unsaved changes",
                                                confirm_text="Discard changes", cancel_text="Keep editing", danger=True):
            return
        self.tabs.removeTab(i); s.deleteLater()

    def _tab_changed(self, _i):
        self._sync(self.tabs.currentWidget())

    def _sync(self, screen):
        if screen is not self.tabs.currentWidget():
            return
        caps = screen.actions() if screen else {}
        for k, a in self.acts.items():
            a.setEnabled(bool(caps.get(k)))
        heading = screen.heading() if screen else "Welcome"
        self.mode.setText(heading)
        self.setWindowTitle(f"{heading} — {design.PRODUCT_NAME}" if heading else design.PRODUCT_NAME)

    def _do(self, key):
        s = self.tabs.currentWidget()
        if s: s.run(key)

    def _on_session_lost(self):
        """Token rejected: ask for the password again in place, so open screens and unsaved edits survive."""
        if self._reauth_open:
            return
        self._reauth_open = True
        try:
            ok = ReauthDialog(self.client, self).exec()
        finally:
            self._reauth_open = False
        if ok:
            self.client.session_expired = False
            self.set_status("Signed in again. Please repeat your last action.", "info")
            self.refs.invalidate()                         # lookups may have failed while signed out
        else:
            self.client.token = None
            self.close()
            if self.on_logout:
                self.on_logout()

    def _message(self, text, kind):
        if kind == "error":
            if text == SESSION_EXPIRED_MESSAGE or self.client.session_expired or self._reauth_open:
                self.set_status("Your session expired. Sign in again, then repeat the action.", "warning")
                return
            self.set_status(text, "danger")
            dialogs.error(self, text)
        else:
            self.set_status(text, kind)

    def _logout(self):
        dirty = [self.tabs.widget(i) for i in range(self.tabs.count()) if self.tabs.widget(i).is_dirty()]
        if dirty and not dialogs.confirm(self, "You have unsaved changes. Sign out anyway?", "Sign out",
                                         confirm_text="Sign out", cancel_text="Stay signed in", danger=True):
            return
        self.client.logout()
        self.close()
        if self.on_logout:
            self.on_logout()
