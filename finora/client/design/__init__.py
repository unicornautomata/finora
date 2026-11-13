"""FINORA design system entry point.

    from finora.client import design
    design.apply_theme(app, "light")      # builds tokens + stylesheet + application font
    design.palette().primary              # read a token (never hard-code colours elsewhere)
"""
from __future__ import annotations
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase

from . import tokens
from .tokens import (PRODUCT_DESCRIPTOR, PRODUCT_FULL, PRODUCT_NAME, RADIUS, SPACE, TAGLINE, TYPE, set_font_family,
                     typography)


class _Bus(QObject):
    changed = pyqtSignal(str)          # emitted with the new mode after the theme changes


bus = _Bus()
_state = {"mode": "light"}
_palettes: dict = {}


def mode() -> str:
    return _state["mode"]


def palette(m: str | None = None):
    m = m or _state["mode"]
    if m not in _palettes:
        _palettes[m] = tokens.build_palette(m)
    return _palettes[m]


def apply_theme(app, m: str | None = None) -> None:
    from . import icons, qss
    if m:
        _state["mode"] = m
    icons.clear_cache()
    typography.resolve(set(QFontDatabase.families()), default=app.font().family())
    f = QFont(typography.family); f.setPixelSize(TYPE.body)
    app.setFont(f)
    app.setStyleSheet(qss.build(palette()))
    bus.changed.emit(_state["mode"])


__all__ = ["apply_theme", "palette", "mode", "bus", "tokens", "set_font_family", "typography",
           "PRODUCT_NAME", "PRODUCT_DESCRIPTOR", "PRODUCT_FULL", "TAGLINE", "SPACE", "RADIUS", "TYPE"]
