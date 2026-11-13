"""FINORA identity: a ledger page with a teal checkmark on a navy tile."""
from __future__ import annotations
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .tokens import NAVY, PRODUCT_DESCRIPTOR, PRODUCT_NAME, TEAL, WHITE, mix


def mark_svg(on_dark: bool = False, tile: bool = True) -> str:
    """The FINORA mark. on_dark lightens the tile so it stays visible on the navy sidebar."""
    tile_fill = mix(NAVY, WHITE, 0.14) if on_dark else NAVY
    fold = mix(WHITE, NAVY, 0.18)
    rule = mix(NAVY, WHITE, 0.78)
    bg = f'<rect width="64" height="64" rx="15" fill="{tile_fill}"/>' if tile else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{bg}'
            f'<path d="M19 10H36L47 21V50a4 4 0 0 1-4 4H19a4 4 0 0 1-4-4V14a4 4 0 0 1 4-4Z" fill="{WHITE}"/>'
            f'<path d="M36 10V18a3 3 0 0 0 3 3H47Z" fill="{fold}"/>'
            f'<rect x="20" y="25" width="15" height="3" rx="1.5" fill="{rule}"/>'
            f'<rect x="20" y="31" width="22" height="3" rx="1.5" fill="{rule}"/>'
            f'<path d="M22.5 43L29 49.5L41 37" fill="none" stroke="{TEAL}" stroke-width="5.2" '
            f'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def logo_pixmap(size: int = 40, on_dark: bool = False) -> QPixmap:
    scr = QGuiApplication.primaryScreen()
    dpr = scr.devicePixelRatio() if scr else 1.0
    img = QImage(int(size * dpr), int(size * dpr), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    QSvgRenderer(QByteArray(mark_svg(on_dark).encode())).render(p)
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(logo_pixmap(s))
    return ic


class BrandHeader(QWidget):
    """Mark + FINORA wordmark + descriptor line. `on_dark` is for the navy sidebar."""

    def __init__(self, on_dark: bool = False, size: int = 40, descriptor: str | None = PRODUCT_DESCRIPTOR, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(10)
        mark = QLabel(); mark.setPixmap(logo_pixmap(size, on_dark)); mark.setFixedSize(size, size)
        col = QVBoxLayout(); col.setSpacing(0); col.setContentsMargins(0, 0, 0, 0)
        name = QLabel(PRODUCT_NAME); name.setObjectName("brandName"); name.setProperty("onDark", on_dark)
        col.addWidget(name)
        if descriptor:
            tag = QLabel(descriptor); tag.setObjectName("brandTag"); tag.setProperty("onDark", on_dark)
            col.addWidget(tag)
        row.addWidget(mark); row.addLayout(col); row.addStretch(1)
