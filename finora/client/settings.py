"""The one place the app opens its saved settings. Tests redirect `app_settings` to a temporary file so they
never read or write a real user's settings (the registry on Windows)."""
from __future__ import annotations
from PyQt6.QtCore import QSettings


def app_settings() -> QSettings:
    return QSettings("FINORA", "FINORA")
