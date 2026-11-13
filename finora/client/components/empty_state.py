from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .. import design
from ..design import icons


class EmptyState(QWidget):
    """Friendly 'nothing here' panel: icon, title, hint and an optional action."""

    def __init__(self, title: str, message: str = "", icon: str = "inbox", action_text: str | None = None,
                 on_action=None, parent=None):
        super().__init__(parent)
        self._icon_name = icon
        lay = QVBoxLayout(self); lay.setAlignment(Qt.AlignmentFlag.AlignCenter); lay.setSpacing(design.SPACE.sm)
        self.icon = QLabel(); self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel(title); self.title.setObjectName("emptyTitle"); self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message = QLabel(message); self.message.setObjectName("muted"); self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for w in (self.icon, self.title, self.message):
            lay.addWidget(w)
        self.button = None
        if action_text:
            self.button = QPushButton(action_text); self.button.setObjectName("primary")
            if on_action: self.button.clicked.connect(on_action)
            lay.addWidget(self.button, 0, Qt.AlignmentFlag.AlignCenter)
        design.bus.changed.connect(self._retint)
        self._retint()

    def _retint(self, *_):
        self.icon.setPixmap(icons.pixmap(self._icon_name, 40, design.palette().text2))

    def set_text(self, title: str, message: str = ""):
        self.title.setText(title); self.message.setText(message)


class EmptyStateStack(QStackedWidget):
    """Shows a table when it has rows and an EmptyState when it does not."""

    def __init__(self, table: QWidget, title: str, message: str = "", icon: str = "inbox", parent=None):
        super().__init__(parent)
        self.table = table
        self.empty = EmptyState(title, message, icon)
        self.addWidget(table); self.addWidget(self.empty)

    def show_rows(self, has_rows: bool, title: str | None = None, message: str | None = None):
        if title is not None:
            self.empty.set_text(title, message or "")
        self.setCurrentWidget(self.table if has_rows else self.empty)
