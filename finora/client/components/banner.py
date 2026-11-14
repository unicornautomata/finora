from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel

from .. import design
from ..design import icons

_ICON = {"success": "check-circle", "info": "info", "warning": "alert-triangle", "danger": "alert-circle"}


class _WrapLabel(QLabel):
    """A word-wrapped label that always claims the height its text needs at its current width.
    (Plain wrapped QLabels inside nested layouts often get laid out one line too short and clip.)"""

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.wordWrap() and self.width() > 0:
            h = self.heightForWidth(self.width())
            if h > 0 and self.minimumHeight() != h:
                self.setMinimumHeight(h)
                self.updateGeometry()


class Banner(QFrame):
    """Inline message with an icon, used instead of pop-up dialogs for problems the user can fix in place."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("banner")
        row = QHBoxLayout(self)
        row.setContentsMargins(design.SPACE.md, design.SPACE.sm, design.SPACE.md, design.SPACE.sm)
        row.setSpacing(design.SPACE.sm)
        self._icon = QLabel(); self._icon.setFixedWidth(20); self._icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._text = _WrapLabel(); self._text.setObjectName("bannerText"); self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self._icon); row.addWidget(self._text, 1)
        self.kind = "info"
        self.setVisible(False)

    def show_message(self, text: str, kind: str = "info"):
        if kind not in _ICON:
            raise ValueError(f"unknown banner kind: {kind}")
        self.kind = kind
        self.setProperty("kind", kind)
        self.style().unpolish(self); self.style().polish(self)
        self._text.setMinimumHeight(0)
        self._text.setText(text)
        self._icon.setPixmap(icons.pixmap(_ICON[kind], 18, getattr(design.palette(), kind + "_ink")))
        self.setVisible(True)

    def text(self) -> str:
        return self._text.text()

    def clear(self):
        self._text.setText(""); self.setVisible(False)
