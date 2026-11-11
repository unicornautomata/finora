"""One place for colours and styling (replaces the colors2 lists copied into every old file).
Brand blue is kept from the original app; light and dark palettes are generated from tokens."""
from __future__ import annotations

LIGHT = dict(bg="#f3f5f8", surface="#ffffff", sidebar="#ffffff", border="#dde2e8", text="#1f2933",
             muted="#6b7785", primary="#51a5e1", primary_hover="#3f93d1", primary_text="#ffffff",
             primary_soft="#e9f4fc", row_alt="#f8fafc", danger="#d64545", ok="#2f9e6f", warn="#c98a1b",
             readonly="#eef1f5")
DARK = dict(bg="#15191e", surface="#1e242b", sidebar="#1a1f25", border="#303843", text="#e6eaee",
            muted="#93a0ad", primary="#51a5e1", primary_hover="#6bb5ea", primary_text="#0b1620",
            primary_soft="#203241", row_alt="#222930", danger="#ef6a6a", ok="#4cc592", warn="#e0a93a",
            readonly="#262d35")


def qss(t: dict) -> str:
    return f"""
* {{ font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif; font-size: 13px; }}
QMainWindow, QDialog, QWidget#canvas {{ background: {t['bg']}; color: {t['text']}; }}
QWidget {{ color: {t['text']}; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 20px; font-weight: 600; }}
QLabel#muted, QLabel.muted {{ color: {t['muted']}; }}
QLabel#badge {{ padding: 3px 10px; border-radius: 10px; font-weight: 600; background: {t['primary_soft']}; color: {t['primary']}; }}
QLabel#badge[state="posted"] {{ background: {t['ok']}; color: #fff; }}
QLabel#badge[state="reversed"] {{ background: {t['warn']}; color: #fff; }}
QFrame#card, QGroupBox {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 10px; }}
QGroupBox {{ margin-top: 14px; padding: 12px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {t['muted']}; }}
QFrame#sidebar {{ background: {t['sidebar']}; border-right: 1px solid {t['border']}; }}
QFrame#topbar {{ background: {t['surface']}; border-bottom: 1px solid {t['border']}; }}
QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox {{
    background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {t['primary']}; selection-color: {t['primary_text']}; min-height: 20px; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{ border: 1px solid {t['primary']}; }}
QLineEdit[readOnly="true"], QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled {{
    background: {t['readonly']}; color: {t['muted']}; }}
QLineEdit[invalid="true"] {{ border: 1px solid {t['danger']}; }}
QComboBox QAbstractItemView {{ background: {t['surface']}; selection-background-color: {t['primary_soft']};
    selection-color: {t['text']}; border: 1px solid {t['border']}; }}
QPushButton, QToolButton {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 6px;
    padding: 6px 12px; }}
QPushButton:hover, QToolButton:hover {{ border-color: {t['primary']}; background: {t['primary_soft']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t['muted']}; background: {t['readonly']}; border-color: {t['border']}; }}
QPushButton#primary {{ background: {t['primary']}; color: {t['primary_text']}; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: {t['primary_hover']}; }}
QPushButton#primary:disabled {{ background: {t['border']}; color: {t['muted']}; }}
QPushButton#danger {{ color: {t['danger']}; }}
QToolButton#rowmenu {{ padding: 0px 6px; border: none; background: transparent; font-weight: 700; }}
QToolButton#rowmenu::menu-indicator {{ image: none; }}
QTableWidget, QTreeWidget, QListWidget {{ background: {t['surface']}; alternate-background-color: {t['row_alt']};
    border: 1px solid {t['border']}; border-radius: 8px; gridline-color: {t['border']};
    selection-background-color: {t['primary_soft']}; selection-color: {t['text']}; outline: 0; }}
QHeaderView::section {{ background: {t['bg']}; color: {t['muted']}; border: none; border-bottom: 1px solid {t['border']};
    padding: 7px 8px; font-weight: 600; }}
QTreeWidget#nav {{ border: none; background: transparent; }}
QTreeWidget#nav::item {{ padding: 6px 4px; border-radius: 6px; }}
QTreeWidget#nav::item:selected {{ background: {t['primary']}; color: {t['primary_text']}; }}
QTreeWidget#nav::item:hover:!selected {{ background: {t['primary_soft']}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::close-button {{ subcontrol-position: right; border-radius: 4px; background: transparent; }}
QTabBar::close-button:hover {{ background: {t['primary_soft']}; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; border-bottom: 2px solid transparent; color: {t['muted']}; }}
QTabBar::tab:selected {{ color: {t['text']}; border-bottom: 2px solid {t['primary']}; font-weight: 600; }}
QToolBar {{ background: {t['surface']}; border: none; border-bottom: 1px solid {t['border']}; spacing: 4px; padding: 6px 10px; }}
QToolBar QToolButton {{ border: 1px solid transparent; background: transparent; }}
QToolBar QToolButton:disabled {{ background: transparent; border-color: transparent; color: {t['muted']}; }}
QToolBar QToolButton:hover {{ border-color: {t['border']}; background: {t['primary_soft']}; }}
QStatusBar {{ background: {t['surface']}; color: {t['muted']}; border-top: 1px solid {t['border']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t['primary_soft']}; color: {t['text']}; }}
"""
