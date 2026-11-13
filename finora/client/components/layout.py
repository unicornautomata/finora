"""Spacing helpers so every screen uses the same margins and gaps (tokens, not magic numbers)."""
from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QGridLayout, QHeaderView, QLabel, QScrollArea, QTableWidget,
                             QWidget)

from .. import design

S = design.SPACE


def page_margins(layout):
    layout.setContentsMargins(S.xl, S.lg, S.xl, S.xl)
    layout.setSpacing(S.lg)
    return layout


def scroll_page(content: QWidget) -> QScrollArea:
    """Wrap a screen's content so it scrolls instead of squashing on small windows."""
    sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(content)
    return sa


def configure_table(t: QTableWidget, row_height: int = 36, stretch_col: int | None = None,
                    select_rows: bool = True, editable: bool = False) -> QTableWidget:
    """One consistent look for every data table."""
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(row_height)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setWordWrap(False)
    t.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    t.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    if select_rows:
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    if not editable:
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.horizontalHeader().setHighlightSections(False)
    t.horizontalHeader().setMinimumSectionSize(48)
    if stretch_col is not None:
        t.horizontalHeader().setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
    return t


class ResponsiveFormGrid(QWidget):
    """Label/field pairs that flow into 3, 2 or 1 columns depending on the available width."""
    BREAKPOINTS = ((880, 3), (560, 2))          # (min width, columns); below the last: 1 column

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(S.lg); self._grid.setVerticalSpacing(S.md)
        self._fields: list[tuple[QLabel, QWidget, bool]] = []
        self.columns = 0

    def add_field(self, label: str, widget: QWidget, full: bool = False) -> QLabel:
        lab = QLabel(label); lab.setObjectName("fieldLabel")
        self._fields.append((lab, widget, full))
        self._relayout(self._columns_for(max(self.width(), 900)))
        return lab

    def _columns_for(self, width: int) -> int:
        return next((c for w, c in self.BREAKPOINTS if width >= w), 1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cols = self._columns_for(self.width())
        if cols != self.columns:
            self._relayout(cols)

    def _relayout(self, cols: int):
        g = self._grid
        while g.count():
            g.takeAt(0)
        for c in range(0, 8):
            g.setColumnStretch(c, 0)
        r = c = 0
        for lab, w, full in self._fields:
            if full:
                if c: r, c = r + 1, 0
                g.addWidget(lab, r, 0); g.addWidget(w, r, 1, 1, cols * 2 - 1)
                r, c = r + 1, 0
                continue
            if cols == 1:                       # stacked: label above field
                g.addWidget(lab, r, 0); g.addWidget(w, r + 1, 0)
                r += 2
                continue
            g.addWidget(lab, r, c * 2, Qt.AlignmentFlag.AlignVCenter); g.addWidget(w, r, c * 2 + 1)
            c += 1
            if c == cols:
                r, c = r + 1, 0
        for k in range(cols):
            g.setColumnStretch(k * 2 + 1, 1)
        if cols == 1:
            g.setColumnStretch(0, 1)
        self.columns = cols
