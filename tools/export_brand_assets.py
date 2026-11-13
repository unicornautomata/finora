"""Writes the FINORA logo files to docs/brand/.   python tools/export_brand_assets.py"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication
from finora.client.design import brand, tokens as T

out = Path(__file__).resolve().parent.parent / "docs" / "brand"
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])


def horizontal(on_dark: bool) -> str:
    inner = brand.mark_svg(on_dark).replace('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">', "").replace("</svg>", "")
    word, sub = (T.WHITE, T.mix(T.NAVY, T.WHITE, 0.7)) if on_dark else (T.NAVY, T.TEXT2)
    bg = f'<rect width="320" height="80" fill="{T.NAVY}"/>' if on_dark else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 80">{bg}<g transform="translate(8 8) scale(1)">{inner}</g>'
            f'<text x="84" y="40" font-family="Inter, \'Segoe UI\', Arial, sans-serif" font-size="30" font-weight="700" '
            f'letter-spacing="4" fill="{word}">FINORA</text>'
            f'<text x="85" y="60" font-family="Inter, \'Segoe UI\', Arial, sans-serif" font-size="12" fill="{sub}">'
            f'{T.PRODUCT_DESCRIPTOR}</text></svg>')


files = {"finora-mark.svg": brand.mark_svg(False), "finora-mark-on-dark.svg": brand.mark_svg(True),
         "finora-mark-no-tile.svg": brand.mark_svg(False, tile=False),
         "finora-logo-horizontal.svg": horizontal(False), "finora-logo-horizontal-on-dark.svg": horizontal(True)}
for name, svg in files.items():
    (out / name).write_text(svg, encoding="utf-8")


def png(svg: str, w: int, h: int, name: str):
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied); img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img); QSvgRenderer(QByteArray(svg.encode())).render(p); p.end()
    return img.save(str(out / name))


for s in (64, 256, 512):
    png(brand.mark_svg(False), s, s, f"finora-mark-{s}.png")
png(horizontal(False), 960, 240, "finora-logo-horizontal.png")
ico_ok = png(brand.mark_svg(False), 256, 256, "finora.ico")     # Windows icon (needs Qt's ico plugin)
print("wrote", sorted(p.name for p in out.iterdir()), "| ico:", ico_ok)
