from __future__ import annotations
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from .. import design


class KpiTile(QFrame):
    """Label, big value and a caption, with a coloured left edge. Values must come from real API data."""

    def __init__(self, label: str, value: str = "—", caption: str = "", kind: str = "info", parent=None):
        super().__init__(parent)
        self.setObjectName("kpi"); self.setProperty("kind", kind)
        lay = QVBoxLayout(self)
        m = design.SPACE.lg
        lay.setContentsMargins(m, design.SPACE.md, m, design.SPACE.md); lay.setSpacing(2)
        self._label = QLabel(label); self._label.setObjectName("kpiLabel")
        self._value = QLabel(value); self._value.setObjectName("kpiValue")
        self._caption = QLabel(caption); self._caption.setObjectName("caption")
        for w in (self._label, self._value, self._caption):
            lay.addWidget(w)
        self._caption.setVisible(bool(caption))

    def set_value(self, value: str, caption: str | None = None):
        self._value.setText(value)
        if caption is not None:
            self._caption.setText(caption); self._caption.setVisible(bool(caption))

    def set_kind(self, kind: str):
        self.setProperty("kind", kind); self.style().unpolish(self); self.style().polish(self)
