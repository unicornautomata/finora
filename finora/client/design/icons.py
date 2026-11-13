"""Consistent line-icon set (24x24, 2px stroke), drawn from SVG so it is identical on every OS and
recoloured for light/dark. No icon fonts and no platform style icons."""
from __future__ import annotations
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

PATHS = {
    "file-plus": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 12v6M9 15h6"/>',
    "folder-open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "save": '<path d="M5 3h11l4 4v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M7 3v6h8V3"/><path d="M7 21v-7h10v7"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
    "trash": '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v6M14 11v6"/>',
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
    "printer": '<path d="M7 9V3h10v6"/><rect x="4" y="9" width="16" height="9" rx="2"/><path d="M7 14h10v7H7z"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.5-4"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.5 4"/><path d="M20 20v-4h-4"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/>',
    "moon": '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
    "log-out": '<path d="M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3"/><path d="M16 8l4 4-4 4M20 12H9"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "alert-triangle": '<path d="M12 3L2 20h20z"/><path d="M12 10v4"/><path d="M12 17.2v.3"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8v.3"/>',
    "help-circle": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 1-1 1.7"/><path d="M12 17v.3"/>',
    "alert-circle": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5"/><path d="M12 16v.3"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    "inbox": '<path d="M3 13l3-8h12l3 8"/><path d="M3 13v6a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-6h-5l-1 3h-6l-1-3z"/>',
    "book": '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M8 17h11"/>',
    "bar-chart": '<path d="M5 20V10M12 20V4M19 20v-7"/>',
    "database": '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/><path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
}

_cache: dict = {}


def clear_cache() -> None:
    _cache.clear()


def _svg(name: str, color: str) -> bytes:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>').encode()


def pixmap(name: str, size: int = 18, color: str | None = None) -> QPixmap:
    from . import palette                      # late import: palette depends on the active mode
    color = color or palette().text
    scr = QGuiApplication.primaryScreen()
    dpr = scr.devicePixelRatio() if scr else 1.0
    key = (name, color, size, dpr)
    if key not in _cache:
        img = QImage(int(size * dpr), int(size * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        QSvgRenderer(QByteArray(_svg(name, color))).render(p)
        p.end()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        _cache[key] = pm
    return _cache[key]


def icon(name: str, size: int = 18, color: str | None = None, disabled_color: str | None = None) -> QIcon:
    from . import palette
    ic = QIcon()
    ic.addPixmap(pixmap(name, size, color), QIcon.Mode.Normal)
    ic.addPixmap(pixmap(name, size, disabled_color or palette().text2), QIcon.Mode.Disabled)
    return ic
