"""Pure helpers for signing in (no Qt, so they are easy to test): URL checks, friendly error wording,
and a caps-lock heuristic."""
from __future__ import annotations
from urllib.parse import urlparse

from .api_client import ApiError

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def normalize_server_url(text: str) -> str:
    """'192.168.1.5:8000' -> 'http://192.168.1.5:8000'. Raises ValueError with a message fit to show the user."""
    t = (text or "").strip()
    if not t:
        raise ValueError("Enter the server address, for example http://192.168.1.10:8000")
    if "://" not in t:
        t = "http://" + t
    u = urlparse(t)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("The server address must look like http://192.168.1.10:8000")
    try:
        u.port
    except ValueError:
        raise ValueError("The port in the server address is not a valid number")
    return t.rstrip("/")


def is_local_url(url: str) -> bool:
    return (urlparse(url).hostname or "").lower() in LOCAL_HOSTS


def is_encrypted_url(url: str) -> bool:
    return urlparse(url).scheme == "https"


def describe_login_error(ex: Exception, url: str = "") -> tuple[str, str]:
    """Returns (message, kind) where kind is a Banner kind: 'danger' or 'warning'."""
    if isinstance(ex, ApiError):
        if ex.network:
            where = f" at {url}" if url else ""
            return (f"Can't reach the server{where}. Check the address, that the server is running, "
                    "and your network connection.", "danger")
        if ex.status == 401:
            return "Incorrect username or password.", "danger"
        if ex.status == 429:
            return ("Too many failed attempts. This account is locked for a few minutes. "
                    "Try again later, or ask an administrator.", "warning")
        if ex.status == 403:
            return "This account is not allowed to sign in.", "danger"
        if ex.status >= 500:
            return f"The server had a problem ({ex.status}). Try again, or contact your administrator.", "danger"
    return str(ex) or "Sign-in failed.", "danger"


def looks_like_caps_lock(text: str, shift: bool):
    """True if a typed letter suggests Caps Lock is on, False if it suggests off, None if it tells us nothing."""
    if len(text) != 1 or not text.isalpha() or text.upper() == text.lower():
        return None
    return text.isupper() != shift
