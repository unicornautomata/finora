from __future__ import annotations
from PyQt6.QtWidgets import QLabel

KINDS = ("success", "warning", "danger", "info", "neutral")


class StatusChip(QLabel):
    """Small pill. Colours come from the stylesheet (soft tint + readable ink), never from code."""

    def __init__(self, text: str = "", kind: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setObjectName("chip")
        self.set_status(text, kind)

    def set_status(self, text: str, kind: str = "neutral"):
        if kind not in KINDS:
            raise ValueError(f"unknown chip kind: {kind}")
        self.setText(text)
        self.setProperty("kind", kind)
        self.style().unpolish(self); self.style().polish(self)
        self.setVisible(bool(text))
