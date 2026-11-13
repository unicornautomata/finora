from __future__ import annotations
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import design


class Card(QFrame):
    """White surface with a border and radius. Use `body` for contents, or `Card.from_layout(layout)`."""

    def __init__(self, title: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._outer = QVBoxLayout(self)
        m = design.SPACE.lg
        self._outer.setContentsMargins(m, m, m, m); self._outer.setSpacing(design.SPACE.md)
        if title:
            t = QLabel(title); t.setObjectName("h3"); self._outer.addWidget(t)
        self.body = QVBoxLayout(); self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(design.SPACE.sm)
        self._outer.addLayout(self.body)

    @classmethod
    def from_layout(cls, layout) -> "Card":
        c = cls()
        c.body.addLayout(layout)
        return c


class PageHeader(QWidget):
    """Title, optional subtitle and a right-hand slot for actions."""

    def __init__(self, title: str, subtitle: str | None = None, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self); row.setContentsMargins(0, 0, 0, 0)
        col = QVBoxLayout(); col.setSpacing(2)
        self.title = QLabel(title); self.title.setObjectName("title"); col.addWidget(self.title)
        self.subtitle = QLabel(subtitle or ""); self.subtitle.setObjectName("muted"); self.subtitle.setVisible(bool(subtitle))
        col.addWidget(self.subtitle)
        row.addLayout(col, 1)
        self.actions = QHBoxLayout(); row.addLayout(self.actions)

    def set_title(self, text: str, subtitle: str | None = None):
        self.title.setText(text)
        if subtitle is not None:
            self.subtitle.setText(subtitle); self.subtitle.setVisible(bool(subtitle))
