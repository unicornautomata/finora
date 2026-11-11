"""Main window: collapsible sidebar, fixed action toolbar, closable tabs."""
from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                             QStyle, QTabWidget, QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                             QWidget)

from . import theme
from .screens import DocumentScreen, MasterScreen, Screen, TrialBalanceScreen
from .widgets import RefCache

# Same button row as the original app, in the same order.
TOOLBAR = [("new", "New", QStyle.StandardPixmap.SP_FileIcon), ("open", "Open", QStyle.StandardPixmap.SP_DirOpenIcon),
           ("save", "Save", QStyle.StandardPixmap.SP_DialogSaveButton),
           ("post", "Post", QStyle.StandardPixmap.SP_DialogApplyButton),
           ("delete", "Delete", QStyle.StandardPixmap.SP_TrashIcon),
           ("reverse", "Reverse", QStyle.StandardPixmap.SP_ArrowBack),
           ("copy", "Copy", QStyle.StandardPixmap.SP_FileDialogContentsView),
           ("print", "Print", QStyle.StandardPixmap.SP_DialogHelpButton),
           ("refresh", "Refresh", QStyle.StandardPixmap.SP_BrowserReload)]


class Shell(QMainWindow):
    def __init__(self, client, meta, host_info: str | None = None, on_logout=None):
        super().__init__()
        self.client, self.meta, self.on_logout = client, meta, on_logout
        self.refs = RefCache(client, meta["entities"])
        self.dark = False
        self.setWindowTitle("Ledger"); self.resize(1360, 860)

        root = QWidget(); root.setObjectName("canvas"); self.setCentralWidget(root)
        outer = QHBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # ---- sidebar (navigation comes from the server menu)
        self.sidebar = QFrame(); self.sidebar.setObjectName("sidebar"); self.sidebar.setFixedWidth(230)
        sv = QVBoxLayout(self.sidebar); sv.setContentsMargins(10, 12, 10, 10)
        brand = QLabel("Ledger"); brand.setObjectName("title"); sv.addWidget(brand)
        self.nav = QTreeWidget(); self.nav.setObjectName("nav"); self.nav.setHeaderHidden(True)
        self.nav.setIndentation(12); self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._build_nav(meta["menu"])
        self.nav.itemClicked.connect(self._nav_clicked)
        sv.addWidget(self.nav, 1)
        outer.addWidget(self.sidebar)

        # ---- right side
        right = QVBoxLayout(); right.setSpacing(0)
        top = QFrame(); top.setObjectName("topbar")
        th = QHBoxLayout(top); th.setContentsMargins(12, 8, 16, 8)
        self.btn_menu = QToolButton(); self.btn_menu.setText("☰"); self.btn_menu.clicked.connect(self._toggle_sidebar)
        self.mode = QLabel("Welcome"); self.mode.setObjectName("title")
        user = client.user or {}
        self.who = QLabel(f"{user.get('username', '')} · {user.get('role', '')}"); self.who.setObjectName("muted")
        self.btn_theme = QPushButton("Dark"); self.btn_theme.clicked.connect(self._toggle_theme)
        self.btn_out = QPushButton("Sign out"); self.btn_out.clicked.connect(self._logout)
        for w in (self.btn_menu, self.mode):
            th.addWidget(w)
        th.addStretch(1)
        for w in (self.who, self.btn_theme, self.btn_out):
            th.addWidget(w)
        right.addWidget(top)

        self.toolbar = QToolBar(); self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.acts: dict[str, QAction] = {}
        for key, text, icon in TOOLBAR:
            a = QAction(self.style().standardIcon(icon), text, self)
            a.triggered.connect(lambda _=False, k=key: self._do(k)); a.setEnabled(False)
            self.toolbar.addAction(a); self.acts[key] = a
            if key in ("post", "copy"):
                self.toolbar.addSeparator()
        right.addWidget(self.toolbar)

        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True); self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab); self.tabs.currentChanged.connect(self._tab_changed)
        right.addWidget(self.tabs, 1)
        rw = QWidget(); rw.setLayout(right); outer.addWidget(rw, 1)

        self.statusBar().showMessage(host_info or f"Connected to {client.base_url}")
        self.open_screen("doc:" + (meta["menu"][0]["items"][0]["key"].split(":")[1]))

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
                c.setForeground(0, Qt.GlobalColor.gray); gi.addChild(c)
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
        self.dark = not self.dark
        QApplication.instance().setStyleSheet(theme.qss(theme.DARK if self.dark else theme.LIGHT))
        self.btn_theme.setText("Light" if self.dark else "Dark")

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
        self.tabs.setCurrentIndex(self.tabs.addTab(s, label))

    def _close_tab(self, i):
        s = self.tabs.widget(i)
        if s.is_dirty() and QMessageBox.question(self, "Unsaved changes", "Close and discard unsaved changes?") \
                != QMessageBox.StandardButton.Yes:
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
        self.mode.setText(screen.heading() if screen else "Welcome")

    def _do(self, key):
        s = self.tabs.currentWidget()
        if s: s.run(key)

    def _message(self, text, is_error):
        if is_error:
            QMessageBox.warning(self, "Ledger", text)
        else:
            self.statusBar().showMessage(text, 6000)

    def _logout(self):
        dirty = [self.tabs.widget(i) for i in range(self.tabs.count()) if self.tabs.widget(i).is_dirty()]
        if dirty and QMessageBox.question(self, "Sign out", "You have unsaved changes. Sign out anyway?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.client.logout()
        self.close()
        if self.on_logout:
            self.on_logout()
