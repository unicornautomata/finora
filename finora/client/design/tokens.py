"""FINORA design tokens: the single source of truth for colour, type, spacing and radius.

Nothing outside this package should contain a hex colour. Palettes are built from the approved
brand colours; anything derived (tints, hover states, readable "ink" for status colours) is
computed here and checked by tests/test_design.py so it keeps meeting WCAG AA (4.5:1) for text.
"""
from __future__ import annotations
import os
from types import SimpleNamespace

PRODUCT_NAME = "FINORA"
PRODUCT_DESCRIPTOR = "Financial Management System"
PRODUCT_FULL = "FINORA Financial Management System"
TAGLINE = "Clarity in every transaction"

# ---- approved brand palette (docs/DECISIONS.md, decision 3)
NAVY, TEAL, MINT = "#102B3A", "#137C78", "#17A398"
BACKGROUND, CARD = "#F3F6F8", "#FFFFFF"
TEXT, TEXT2, BORDER = "#243E4A", "#71848D", "#E0E7EA"
STATUS = {"success": "#16A36A", "warning": "#E9A23B", "danger": "#D9534F", "info": "#2684C7"}
WHITE = "#FFFFFF"


# ---- colour maths
def _rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(r, g, b) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(v))) for v in (r, g, b)))


def mix(a: str, b: str, t: float) -> str:
    """Blend colour a toward colour b by fraction t (0 = a, 1 = b)."""
    (ar, ag, ab), (br, bg, bb) = _rgb(a), _rgb(b)
    return _hex(ar + (br - ar) * t, ag + (bg - ag) * t, ab + (bb - ab) * t)


def luminance(h: str) -> float:
    def f(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def ensure_contrast(fg: str, bg: str, toward: str, minimum: float = 4.5) -> str:
    """Shift fg toward `toward` just far enough to reach the contrast minimum against bg."""
    for i in range(0, 51):
        c = mix(fg, toward, i / 50)
        if contrast(c, bg) >= minimum:
            return c
    return toward


def _status_tokens(p: dict, dark: bool) -> None:
    pull = WHITE if dark else NAVY
    for k, base in STATUS.items():
        soft = mix(p["surface"], base, 0.20 if dark else 0.12)
        p[k] = base
        p[k + "_soft"] = soft
        p[k + "_ink"] = ensure_contrast(base, soft, pull)                  # readable text on the soft tint
        best = NAVY if contrast(NAVY, base) >= contrast(WHITE, base) else WHITE
        if contrast(best, base) >= 4.5:        # text on a solid fill exists only where AA is reachable
            p["on_" + k] = best                # (success/warning). danger and info: use soft chips or edges.


def build_palette(mode: str) -> SimpleNamespace:
    if mode == "dark":
        p = dict(bg="#0B1B24", surface="#122B38", border="#264452", text="#E7EFF3", text2="#9DB1BA",
                 primary=TEAL, primary_hover=mix(TEAL, NAVY, 0.18), primary_pressed=mix(TEAL, NAVY, 0.35),
                 on_primary=WHITE, accent=MINT, link=MINT, navy=NAVY,
                 sidebar_bg="#0A1820", sidebar_text="#DCE7EC", sidebar_hover=mix("#0A1820", WHITE, 0.08),
                 sidebar_active=mix("#0A1820", TEAL, 0.55))
    else:
        p = dict(bg=BACKGROUND, surface=CARD, border=BORDER, text=TEXT, text2=TEXT2,
                 primary=TEAL, primary_hover=mix(TEAL, NAVY, 0.18), primary_pressed=mix(TEAL, NAVY, 0.35),
                 on_primary=WHITE, accent=MINT, link=TEAL, navy=NAVY,
                 sidebar_bg=NAVY, sidebar_text="#DCE7EC", sidebar_hover=mix(NAVY, WHITE, 0.08),
                 sidebar_active=mix(NAVY, TEAL, 0.50))
    dark = mode == "dark"
    pull = WHITE if dark else NAVY
    worst_bg = min((p["bg"], p["surface"]), key=lambda c: contrast(p["text2"], c))
    # text2 is kept exactly as approved for hints/captions; text2_strong is the same hue, darkened
    # (or lightened) only as far as needed to read at small sizes.
    p["text2_strong"] = ensure_contrast(p["text2"], worst_bg, pull)
    p["border_strong"] = ensure_contrast(p["border"], p["surface"], p["text2"], 3.0)   # input outlines
    p["hover"] = mix(p["surface"], TEAL, 0.14 if dark else 0.08)
    p["selection"] = mix(p["surface"], TEAL, 0.28 if dark else 0.14)
    p["row_alt"] = mix(p["surface"], p["bg"], 0.55)
    p["readonly"] = mix(p["bg"], p["border"], 0.5) if not dark else mix(p["surface"], p["bg"], 0.5)
    p["sidebar_dim"] = ensure_contrast(mix(p["sidebar_bg"], WHITE, 0.6), p["sidebar_bg"], WHITE)
    p["sidebar_disabled"] = mix(p["sidebar_bg"], WHITE, 0.38)
    p["accent_on_sidebar"] = MINT
    _status_tokens(p, dark)
    return SimpleNamespace(mode=mode, **p)


# ---- scales
SPACE = SimpleNamespace(xs=4, sm=8, md=12, lg=16, xl=24, xxl=32)
RADIUS = SimpleNamespace(sm=6, md=10, pill=10)
TYPE = SimpleNamespace(caption=11, small=12, body=13, h3=15, h2=18, h1=22)   # pixels


class Typography:
    """Inter where it is installed, Segoe UI as the fallback (the Windows default). Inter is NOT bundled.
    Force a family with design.set_font_family("Segoe UI") or the FINORA_FONT environment variable."""
    PREFERRED = ("Inter", "Segoe UI")
    FALLBACKS = ("Helvetica Neue", "Arial", "Noto Sans", "DejaVu Sans")

    def __init__(self):
        self.override = os.environ.get("FINORA_FONT") or None
        self.active = None                       # resolved against installed fonts by apply_theme()

    def families(self):
        head = [self.override] if self.override else []
        return head + [f for f in (*self.PREFERRED, *self.FALLBACKS) if f not in head]

    def resolve(self, installed, default: str) -> str:
        self.active = next((f for f in self.families() if f in installed), default)
        return self.active

    @property
    def family(self) -> str:
        return self.active or self.families()[0]

    def css_stack(self) -> str:
        return f'"{self.family}", sans-serif'


typography = Typography()


def set_font_family(name: str | None) -> None:
    typography.override = name
    typography.active = None
