"""FINORA design-system guard rails: approved colours, accessibility, typography, no stray colours."""
import re
from pathlib import Path

import pytest
from finora.client.design import tokens as T

CLIENT = Path(__file__).resolve().parents[1] / "finora" / "client"


def test_approved_brand_palette_is_exact():
    p = T.build_palette("light")
    assert (p.navy, p.primary, p.accent) == ("#102B3A", "#137C78", "#17A398")
    assert (p.bg, p.surface, p.text, p.text2, p.border) == ("#F3F6F8", "#FFFFFF", "#243E4A", "#71848D", "#E0E7EA")
    assert (p.success, p.warning, p.danger, p.info) == ("#16A36A", "#E9A23B", "#D9534F", "#2684C7")


def test_solid_fill_text_tokens_exist_only_where_contrast_allows():
    p = T.build_palette("light")
    assert hasattr(p, "on_success") and hasattr(p, "on_warning")
    assert not hasattr(p, "on_danger") and not hasattr(p, "on_info")   # approved colours cannot carry AA text


def test_light_and_dark_define_the_same_tokens():
    assert vars(T.build_palette("light")).keys() == vars(T.build_palette("dark")).keys()


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_text_meets_wcag_aa(mode):
    p = T.build_palette(mode)
    pairs = [("text/surface", p.text, p.surface), ("text/bg", p.text, p.bg),
             ("text2_strong/surface", p.text2_strong, p.surface), ("text2_strong/bg", p.text2_strong, p.bg),
             ("on_primary/primary", p.on_primary, p.primary), ("on_primary/hover", p.on_primary, p.primary_hover),
             ("sidebar_text/sidebar", p.sidebar_text, p.sidebar_bg), ("sidebar_dim/sidebar", p.sidebar_dim, p.sidebar_bg),
             ("white/sidebar_active", "#FFFFFF", p.sidebar_active), ("link/surface", p.link, p.surface)]
    for k in T.STATUS:
        pairs.append((f"{k}_ink/soft", getattr(p, k + "_ink"), getattr(p, k + "_soft")))
        if hasattr(p, "on_" + k):
            pairs.append((f"on_{k}/{k}", getattr(p, "on_" + k), getattr(p, k)))
    failures = [(n, round(T.contrast(a, b), 2)) for n, a, b in pairs if T.contrast(a, b) < 4.5]
    assert not failures, failures


def test_secondary_text_is_kept_as_approved_but_flagged_for_small_use():
    p = T.build_palette("light")
    assert T.contrast(p.text2, p.surface) < 4.5          # documented: hints/captions only
    assert T.contrast(p.text2_strong, p.bg) >= 4.5       # small meaningful labels use this one


def test_typography_prefers_inter_when_installed_with_segoe_ui_fallback():
    t = T.Typography()
    assert t.families()[:2] == ["Inter", "Segoe UI"]
    assert t.resolve({"Inter", "Segoe UI", "Arial"}, "X") == "Inter"
    assert t.resolve({"Segoe UI", "Arial"}, "X") == "Segoe UI"             # Windows without Inter
    assert t.resolve({"Comic Sans"}, "DefaultFont") == "DefaultFont"        # nothing known: system default
    assert t.css_stack() == '"DefaultFont", sans-serif'


def test_typography_can_be_forced_without_touching_screens():
    t = T.Typography()
    t.override = "Segoe UI"
    assert t.resolve({"Inter", "Segoe UI"}, "X") == "Segoe UI"
    T.set_font_family("Inter"); T.set_font_family(None)


def test_input_outline_meets_non_text_contrast():
    for mode in ("light", "dark"):
        p = T.build_palette(mode)
        assert T.contrast(p.border_strong, p.surface) >= 3.0, mode


def test_screens_use_components_not_raw_qt_buttons_or_message_boxes():
    for name in ("screens.py", "shell.py", "login.py", "app.py"):
        src = (CLIENT / name).read_text(encoding="utf-8")
        assert "QMessageBox" not in src and "QPushButton(" not in src, name


def test_brand_assets(qapp):
    from finora.client.design import brand
    svg = brand.mark_svg()
    assert T.TEAL in svg and "stroke" in svg                      # teal checkmark on a document
    assert brand.mark_svg(on_dark=True) != svg


def test_buttons_have_standard_kinds(qapp):
    import pytest as _p
    from finora.client.components import Button
    for kind in ("primary", "secondary", "danger", "ghost"):
        assert Button("x", kind).property("kind") == kind
    with _p.raises(ValueError):
        Button("x", "fancy")


def test_form_grid_reflows_with_width(qapp):
    from PyQt6.QtWidgets import QLineEdit
    from finora.client.components import ResponsiveFormGrid
    g = ResponsiveFormGrid()
    for i in range(6):
        g.add_field(f"F{i}", QLineEdit())
    for width, cols in ((1000, 3), (700, 2), (400, 1)):
        g.resize(width, 300); g.show(); qapp.processEvents()
        assert g.columns == cols, (width, g.columns)


def test_no_hard_coded_colours_outside_design_package():
    offenders = {}
    for f in CLIENT.rglob("*.py"):
        if "design" in f.relative_to(CLIENT).parts:
            continue
        found = re.findall(r"#[0-9a-fA-F]{6}\b", f.read_text(encoding="utf-8"))
        if found:
            offenders[str(f.relative_to(CLIENT))] = found
    assert not offenders, offenders


def test_no_windows_only_dependencies_in_client():
    bad = [str(f) for f in CLIENT.rglob("*.py")
           if re.search(r"\bwindll\b|\bwinreg\b|\bwin32\w*|\bpywin", f.read_text(encoding="utf-8"))]
    assert not bad, bad


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_stylesheet_parses_cleanly(qapp, mode):
    from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
    from PyQt6.QtWidgets import QWidget
    from finora.client import design
    msgs = []
    qInstallMessageHandler(lambda t, c, m: msgs.append(m))
    try:
        design.apply_theme(qapp, mode)
        w = QWidget(); w.ensurePolished(); w.deleteLater()
    finally:
        qInstallMessageHandler(None)
        design.apply_theme(qapp, "light")
    assert not [m for m in msgs if "parse" in m.lower() or "unknown property" in m.lower()], msgs


def test_components_and_icons_render(qapp):
    from finora.client.components import Card, EmptyState, KpiTile, PageHeader, StatusChip
    from finora.client.design import brand, icons
    assert all(not icons.pixmap(n).isNull() for n in icons.PATHS)
    assert not brand.logo_pixmap(48).isNull() and not brand.logo_pixmap(48, on_dark=True).isNull()
    chip = StatusChip("Posted", "success"); chip.set_status("Out of balance", "danger")
    with pytest.raises(ValueError):
        chip.set_status("x", "purple")
    for w in (Card("t"), EmptyState("a", "b"), KpiTile("Debit", "0.00"), PageHeader("T", "s")):
        w.ensurePolished()
