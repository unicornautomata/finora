"""Branded message dialogs. Screens call these instead of QMessageBox so every dialog carries the
FINORA title, icon set and button styling. (Tests patch these functions, not Qt statics.)"""
from __future__ import annotations
from PyQt6.QtWidgets import QMessageBox

from .. import design
from ..design import icons
from ..design.brand import app_icon


def _box(parent, text: str, title: str | None, icon_name: str, color_key: str, detail: str | None):
    box = QMessageBox(parent)
    box.setWindowTitle(title or design.PRODUCT_NAME)
    box.setWindowIcon(app_icon())
    box.setText(text)
    if detail:
        box.setInformativeText(detail)
    box.setIconPixmap(icons.pixmap(icon_name, 36, getattr(design.palette(), color_key)))
    return box


def _button(box, text, role, kind):
    b = box.addButton(text, role)
    b.setProperty("kind", kind)
    b.style().unpolish(b); b.style().polish(b)      # dynamic property: re-apply the stylesheet
    return b


def confirm(parent, text: str, title: str | None = None, *, confirm_text: str = "Confirm",
            cancel_text: str = "Cancel", danger: bool = False, detail: str | None = None) -> bool:
    box = _box(parent, text, title, "help-circle" if not danger else "alert-triangle",
               "primary" if not danger else "danger_ink", detail)
    cancel = _button(box, cancel_text, QMessageBox.ButtonRole.RejectRole, "secondary")
    ok = _button(box, confirm_text, QMessageBox.ButtonRole.AcceptRole, "danger" if danger else "primary")
    box.setDefaultButton(cancel if danger else ok)
    box.exec()
    return box.clickedButton() is ok


def error(parent, text: str, title: str | None = None, detail: str | None = None) -> None:
    box = _box(parent, text, title, "alert-circle", "danger_ink", detail)
    box.setDefaultButton(_button(box, "OK", QMessageBox.ButtonRole.AcceptRole, "primary"))
    box.exec()


def warning(parent, text: str, title: str | None = None, detail: str | None = None) -> None:
    box = _box(parent, text, title, "alert-triangle", "warning_ink", detail)
    box.setDefaultButton(_button(box, "OK", QMessageBox.ButtonRole.AcceptRole, "primary"))
    box.exec()


def info(parent, text: str, title: str | None = None, detail: str | None = None) -> None:
    box = _box(parent, text, title, "info", "info_ink", detail)
    box.setDefaultButton(_button(box, "OK", QMessageBox.ButtonRole.AcceptRole, "primary"))
    box.exec()
