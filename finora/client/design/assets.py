"""Small SVG files the stylesheet needs (QSS can only reference images by file path)."""
from __future__ import annotations
import tempfile
from pathlib import Path

_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="{w}" '
        'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def _write(name: str, color: str, body: str, width: float = 2.4) -> str:
    d = Path(tempfile.gettempdir()) / "finora-ui-assets"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}-{color.lstrip('#')}.svg"
    text = _SVG.format(c=color, w=width, body=body)
    if not f.exists() or f.read_text(encoding="utf-8") != text:
        f.write_text(text, encoding="utf-8")
    return f.as_posix()                       # forward slashes work in QSS on Windows too


def chevron_down(color: str) -> str:
    return _write("chevron-down", color, '<path d="M6 9l6 6 6-6"/>')


def chevron_up(color: str) -> str:
    return _write("chevron-up", color, '<path d="M6 15l6-6 6 6"/>')


def check(color: str) -> str:
    return _write("check", color, '<path d="M5 12.5l4.5 4.5L19 7.5"/>', 3)
