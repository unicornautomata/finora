from __future__ import annotations
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .. import design
from ..design import icons

_ICON = {"success": "check-circle", "info": "info", "warning": "alert-triangle", "danger": "alert-circle"}


class StatusMessage(QWidget):
    """The operation message shown at the left of the status bar (icon + text, coloured by kind)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self); row.setContentsMargins(design.SPACE.sm, 0, 0, 0); row.setSpacing(design.SPACE.sm)
        self._icon = QLabel(); self._icon.setFixedSize(16, 16)
        self.label = QLabel(); self.label.setObjectName("statusText")
        row.addWidget(self._icon); row.addWidget(self.label, 1)
        self.kind = "info"
        design.bus.changed.connect(lambda *_: self._paint_icon())
        self._icon.setVisible(False)

    def set_message(self, text: str, kind: str = "info"):
        if kind not in _ICON:
            raise ValueError(f"unknown status kind: {kind}")
        self.kind = kind
        self.label.setText(text); self.label.setToolTip(text)
        self.label.setProperty("kind", kind)
        self.label.style().unpolish(self.label); self.label.style().polish(self.label)
        self._icon.setVisible(bool(text)); self._paint_icon()

    def _paint_icon(self):
        self._icon.setPixmap(icons.pixmap(_ICON[self.kind], 16, getattr(design.palette(), self.kind + "_ink")))

    def text(self) -> str:
        return self.label.text()
