"""Builds the application stylesheet from tokens. Components pick a look through object names and
dynamic properties (kind, size, onDark); they never carry colours themselves."""
from __future__ import annotations
from . import assets
from .tokens import RADIUS, STATUS, TYPE, typography


def build(p) -> str:
    chev = assets.chevron_down(p.text2_strong)
    chev_up = assets.chevron_up(p.text2_strong)
    tick = assets.check(p.on_primary)
    chips = "\n".join(f"""
QLabel#chip[kind="{k}"] {{ background: {getattr(p, k + '_soft')}; color: {getattr(p, k + '_ink')}; }}
QFrame#kpi[kind="{k}"] {{ border-left: 4px solid {getattr(p, k)}; }}""" for k in STATUS)
    banners = "\n".join(f"""
QFrame#banner[kind="{k}"] {{ background: {getattr(p, k + '_soft')}; border: 1px solid {getattr(p, k)}; }}
QFrame#banner[kind="{k}"] QLabel#bannerText {{ color: {getattr(p, k + '_ink')}; }}""" for k in STATUS)
    return f"""
/* ===== base & typography ===== */
* {{ font-family: {typography.css_stack()}; font-size: {TYPE.body}px; }}
QMainWindow, QDialog, QWidget#canvas {{ background: {p.bg}; color: {p.text}; }}
QWidget {{ color: {p.text}; }}
QLabel {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QToolTip {{ background: {p.navy}; color: #FFFFFF; border: 1px solid {p.sidebar_active}; border-radius: 4px;
    padding: 5px 9px; font-size: {TYPE.small}px; }}

QLabel#title {{ font-size: {TYPE.h1}px; font-weight: 700; }}
QLabel#h2 {{ font-size: {TYPE.h2}px; font-weight: 600; }}
QLabel#h3 {{ font-size: {TYPE.h3}px; font-weight: 600; }}
QLabel#fieldLabel {{ color: {p.text2_strong}; font-size: {TYPE.small}px; font-weight: 500; }}
QLabel#muted {{ color: {p.text2}; }}
QLabel#caption {{ color: {p.text2}; font-size: {TYPE.caption}px; }}
QLabel#errorText {{ color: {p.danger_ink}; }}
QLabel#brandName {{ font-size: {TYPE.h2}px; font-weight: 700; color: {p.navy}; letter-spacing: 2px; }}
QLabel#brandTag {{ font-size: {TYPE.caption}px; color: {p.text2_strong}; }}
QLabel#brandName[onDark="true"] {{ color: #FFFFFF; }}
QLabel#brandTag[onDark="true"] {{ color: {p.sidebar_dim}; }}
QLabel#kpiLabel {{ color: {p.text2_strong}; font-size: {TYPE.small}px; font-weight: 500; }}
QLabel#kpiValue {{ font-size: 24px; font-weight: 700; }}
QLabel#emptyTitle {{ font-size: {TYPE.h3}px; font-weight: 600; }}
QLabel#reportTitle {{ font-size: {TYPE.h2}px; font-weight: 700; }}

/* ===== status badges ===== */
QLabel#chip {{ padding: 3px 10px; border-radius: {RADIUS.pill}px; font-weight: 600; font-size: {TYPE.small}px; }}
QLabel#chip[kind="neutral"] {{ background: {p.readonly}; color: {p.text2_strong}; }}
{chips}

/* ===== banners (inline messages) ===== */
QFrame#banner {{ border-radius: {RADIUS.sm}px; }}
QLabel#bannerText {{ font-size: {TYPE.small}px; }}
{banners}
QLabel#warnText {{ color: {p.warning_ink}; font-size: {TYPE.small}px; font-weight: 600; }}
QLabel#brandHero {{ color: #FFFFFF; font-size: 20px; font-weight: 600; }}
QFrame#brandPanel {{ background: {p.sidebar_bg}; border: none; }}
QFrame#brandPanel QLabel {{ color: {p.sidebar_text}; }}

/* ===== cards & panels ===== */
QFrame#card, QGroupBox {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: {RADIUS.md}px; }}
QFrame#kpi {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: {RADIUS.md}px; }}
QFrame#reportHeader {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: {RADIUS.md}px;
    border-top: 3px solid {p.accent}; }}
QGroupBox {{ margin-top: 14px; padding: 12px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {p.text2_strong}; }}
QFrame#sidebar {{ background: {p.sidebar_bg}; border: none; }}
QFrame#sidebar QLabel {{ color: {p.sidebar_text}; }}
QFrame#topbar {{ background: {p.surface}; border-bottom: 1px solid {p.border}; }}
QFrame#divider {{ background: {p.border}; max-height: 1px; border: none; }}

/* ===== inputs: 1px outline, 2px focus ring (padding compensates so nothing shifts) ===== */
QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox {{
    background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: {RADIUS.sm}px; padding: 5px 9px;
    selection-background-color: {p.primary}; selection-color: {p.on_primary}; min-height: 20px; }}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QSpinBox:hover {{ border-color: {p.text2}; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QTextEdit:focus {{
    border: 2px solid {p.primary}; padding: 4px 8px; }}
QLineEdit[invalid="true"] {{ border: 2px solid {p.danger}; padding: 4px 8px; }}
QLineEdit[readOnly="true"], QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled, QSpinBox:disabled {{
    background: {p.readonly}; color: {p.text2_strong}; border-color: {p.border}; }}
QLineEdit::placeholder {{ color: {p.text2}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right;
    width: 26px; border: none; background: transparent; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{chev}"); width: 12px; height: 12px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; border: none; background: transparent; }}
QSpinBox::up-arrow {{ image: url("{chev_up}"); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url("{chev}"); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{ background: {p.surface}; selection-background-color: {p.selection};
    selection-color: {p.text}; border: 1px solid {p.border_strong}; outline: 0; padding: 4px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {p.border_strong}; border-radius: 4px; background: {p.surface}; }}
QCheckBox::indicator:hover {{ border-color: {p.primary}; }}
QCheckBox::indicator:checked {{ background: {p.primary}; border-color: {p.primary}; image: url("{tick}"); }}
QCheckBox::indicator:disabled {{ background: {p.readonly}; }}

/* ===== buttons: secondary (default), primary, danger, ghost; size sm ===== */
QPushButton, QToolButton {{ background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: {RADIUS.sm}px;
    padding: 6px 14px; font-weight: 500; }}
QPushButton:hover, QToolButton:hover {{ border-color: {p.primary}; background: {p.hover}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {p.selection}; }}
QPushButton:focus {{ border: 2px solid {p.primary}; padding: 5px 13px; }}
QPushButton:disabled, QToolButton:disabled {{ color: {p.text2}; background: {p.readonly}; border-color: {p.border}; }}
QPushButton[kind="primary"] {{ background: {p.primary}; color: {p.on_primary}; border: 1px solid {p.primary}; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {p.primary_hover}; border-color: {p.primary_hover}; }}
QPushButton[kind="primary"]:pressed {{ background: {p.primary_pressed}; border-color: {p.primary_pressed}; }}
QPushButton[kind="primary"]:disabled {{ background: {p.border}; color: {p.text2}; border-color: {p.border}; }}
QPushButton[kind="primary"]:focus {{ border: 2px solid {p.accent}; padding: 5px 13px; }}
QPushButton[kind="danger"] {{ color: {p.danger_ink}; border-color: {p.danger}; background: {p.surface}; }}
QPushButton[kind="danger"]:hover {{ background: {p.danger_soft}; border-color: {p.danger}; }}
QPushButton[kind="ghost"] {{ border: 1px solid transparent; background: transparent; color: {p.link}; }}
QPushButton[kind="ghost"]:hover {{ background: {p.hover}; border-color: transparent; }}
QPushButton[kind="segment"] {{ background: {p.surface}; border: 1px solid {p.border_strong}; font-weight: 500; }}
QPushButton[kind="segment"]:checked {{ background: {p.selection}; border: 1px solid {p.primary}; font-weight: 600; }}
QPushButton[size="sm"] {{ padding: 3px 10px; font-size: {TYPE.small}px; }}
QToolButton#rowmenu {{ padding: 0px 6px; border: none; background: transparent; font-weight: 700; }}
QToolButton#rowmenu::menu-indicator {{ image: none; }}
QToolButton#iconbtn {{ border: none; background: transparent; padding: 6px; }}
QToolButton#iconbtn:hover {{ background: {p.hover}; }}

/* ===== tables ===== */
QTableWidget, QTreeWidget, QListWidget {{ background: {p.surface}; alternate-background-color: {p.row_alt};
    border: 1px solid {p.border}; border-radius: {RADIUS.md}px; gridline-color: {p.border};
    selection-background-color: {p.selection}; selection-color: {p.text}; outline: 0; }}
QTableWidget::item {{ padding: 4px 8px; border: none; }}
QTableWidget::item:hover {{ background: {p.hover}; }}
QTableWidget::item:selected {{ background: {p.selection}; color: {p.text}; }}
QHeaderView {{ background: {p.bg}; }}
QHeaderView::section {{ background: {p.bg}; color: {p.text2_strong}; border: none; border-bottom: 1px solid {p.border};
    padding: 9px 8px; font-weight: 600; font-size: {TYPE.small}px; }}
QTableCornerButton::section {{ background: {p.bg}; border: none; }}

/* ===== navigation ===== */
QTreeWidget#nav {{ border: none; background: transparent; color: {p.sidebar_text}; }}
QTreeWidget#nav::item {{ padding: 7px 6px; border-radius: {RADIUS.sm}px; border-left: 3px solid transparent; color: {p.sidebar_text}; }}
QTreeWidget#nav::item:hover:!selected {{ background: {p.sidebar_hover}; }}
QTreeWidget#nav::item:selected {{ background: {p.sidebar_active}; border-left: 3px solid {p.accent_on_sidebar}; color: #FFFFFF; }}
QTreeWidget#nav::item:disabled {{ color: {p.sidebar_disabled}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 9px 14px; border-bottom: 2px solid transparent; color: {p.text2_strong}; }}
QTabBar::tab:hover {{ color: {p.text}; }}
QTabBar::tab:selected {{ color: {p.text}; border-bottom: 2px solid {p.primary}; font-weight: 600; }}
QTabBar QToolButton {{ border: none; background: transparent; padding: 2px; }}
QToolBar {{ background: {p.surface}; border: none; border-bottom: 1px solid {p.border}; spacing: 4px; padding: 6px 10px; }}
QToolBar QToolButton {{ border: 1px solid transparent; background: transparent; padding: 6px 10px; }}
QToolBar QToolButton:disabled {{ background: transparent; border-color: transparent; color: {p.text2}; }}
QToolBar QToolButton:hover {{ border-color: {p.border}; background: {p.hover}; }}
QToolBar::separator {{ background: {p.border}; width: 1px; margin: 4px 6px; }}
QStatusBar {{ background: {p.surface}; color: {p.text2_strong}; border-top: 1px solid {p.border}; }}
QStatusBar::item {{ border: none; }}
QLabel#statusText {{ color: {p.text2_strong}; font-size: {TYPE.small}px; }}
QLabel#statusText[kind="success"] {{ color: {p.success_ink}; font-weight: 600; }}
QLabel#statusText[kind="info"] {{ color: {p.info_ink}; font-weight: 600; }}
QLabel#statusText[kind="warning"] {{ color: {p.warning_ink}; font-weight: 600; }}
QLabel#statusText[kind="danger"] {{ color: {p.danger_ink}; font-weight: 600; }}
QLabel#statusClock {{ color: {p.text2_strong}; font-size: {TYPE.small}px; padding: 0 12px; }}

/* ===== dialogs & menus ===== */
QMessageBox, QInputDialog {{ background: {p.surface}; }}
QMessageBox QLabel {{ color: {p.text}; }}
QDialogButtonBox QPushButton, QMessageBox QPushButton {{ min-width: 88px; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: {RADIUS.sm}px; padding: 4px; }}
QMenu::item {{ padding: 7px 20px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p.selection}; color: {p.text}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 6px; }}

/* ===== scrollbars & splitters ===== */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border_strong}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.text2}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border_strong}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QSplitter::handle {{ background: transparent; }}
"""
