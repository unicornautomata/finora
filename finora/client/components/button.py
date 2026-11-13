from __future__ import annotations
from PyQt6.QtWidgets import QPushButton

from .. import design
from ..design import icons

KINDS = ("secondary", "primary", "danger", "ghost")


class Button(QPushButton):
    """The one way to make a button. kind: primary | secondary | danger | ghost. size: md | sm.
    The icon takes the right colour for the kind and follows theme changes."""

    def __init__(self, text: str = "", kind: str = "secondary", icon: str | None = None, size: str = "md",
                 tooltip: str | None = None, parent=None):
        super().__init__(text, parent)
        self._icon_name = icon
        self.set_kind(kind)
        self.setProperty("size", size)
        if tooltip:
            self.setToolTip(tooltip)
        design.bus.changed.connect(self._retint)

    def _icon_color(self) -> str:
        p = design.palette()
        return {"primary": p.on_primary, "danger": p.danger_ink, "ghost": p.link}.get(self.property("kind"), p.text)

    def _retint(self, *_):
        if self._icon_name:
            self.setIcon(icons.icon(self._icon_name, 16, self._icon_color()))

    def set_kind(self, kind: str):
        if kind not in KINDS:
            raise ValueError(f"unknown button kind: {kind}")
        self.setProperty("kind", kind)
        self.style().unpolish(self); self.style().polish(self)
        self._retint()
