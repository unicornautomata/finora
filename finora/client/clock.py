"""Status-bar clock text. Weekday and month names are fixed English so they never depend on the PC's language."""
from __future__ import annotations
from datetime import datetime

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def format_clock(dt: datetime) -> str:
    """'Friday, November 13, 2026  2:05:09 PM'"""
    hour12 = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return (f"{WEEKDAYS[dt.weekday()]}, {MONTHS[dt.month - 1]} {dt.day}, {dt.year}  "
            f"{hour12}:{dt.minute:02d}:{dt.second:02d} {ampm}")
