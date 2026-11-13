from __future__ import annotations
from datetime import datetime
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from .. import design
from ..design.brand import logo_pixmap


class ReportHeader(QFrame):
    """Branded header placed at the top of every report: mark, report title, entity, period, who and when."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("reportHeader")
        row = QHBoxLayout(self)
        m = design.SPACE.lg
        row.setContentsMargins(m, design.SPACE.md, m, design.SPACE.md); row.setSpacing(design.SPACE.md)
        mark = QLabel(); mark.setPixmap(logo_pixmap(40)); mark.setFixedSize(40, 40)
        col = QVBoxLayout(); col.setSpacing(2)
        self.title = QLabel(title); self.title.setObjectName("reportTitle")
        self.line = QLabel(""); self.line.setObjectName("muted")
        col.addWidget(self.title); col.addWidget(self.line)
        brand = QLabel(design.PRODUCT_NAME); brand.setObjectName("brandName")
        row.addWidget(mark); row.addLayout(col, 1); row.addWidget(brand)

    def set_report(self, subtitle: str, generated_by: str | None = None):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        tail = f"  ·  Generated {stamp}" + (f" by {generated_by}" if generated_by else "")
        self.line.setText(subtitle + tail)
