"""Colours for Saarthi's own pop-ups (panel, cards). Follows the system's dark/light setting
unless the user picked one in Settings."""

from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

MODE = "auto"  # auto / dark / light (set from config)

LIGHT = dict(
    bg="#F8FAFF",
    surface="#FFFFFF",
    text="#1B2440",
    sub="#6B7590",
    border="#C9D3EA",
    soft="#EEF2FB",
    hover="#DCE5FA",
    chip_border="#DCE3F2",
    tab="#E9EDF7",
    tabtext="#3E4A6B",
    accent="#3E6FE0",
    accent_hover="#2F5DCB",
    muted="#8A93AB",
    done="#9AA2B6",
    outline="#1B2440",
    item_hover="#F4F7FF",
    item_sel="#EAF0FF",
    green="#2EAD5B",
    red="#E5484D",
    stripe="#FFD23D",
)
DARK = dict(
    bg="#1A1E2A",
    surface="#232938",
    text="#E8ECF6",
    sub="#9AA4BF",
    border="#3A4259",
    soft="#2B3245",
    hover="#36405A",
    chip_border="#353D54",
    tab="#2B3245",
    tabtext="#C3CAE0",
    accent="#5B8DEF",
    accent_hover="#4A7BE0",
    muted="#8790AA",
    done="#666F88",
    outline="#4A5575",
    item_hover="#2B3245",
    item_sel="#334064",
    green="#2EAD5B",
    red="#E5484D",
    stripe="#FFD23D",
)


def system_is_dark() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def is_dark() -> bool:
    return MODE == "dark" or (MODE == "auto" and system_is_dark())


def colors() -> dict:
    return DARK if is_dark() else LIGHT


def css(template: str) -> str:
    return Template(template).substitute(colors())


def palette() -> QPalette:
    c = colors()
    pal = QPalette()
    for role, key in (
        (QPalette.ColorRole.Window, "bg"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "surface"),
        (QPalette.ColorRole.AlternateBase, "item_hover"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "soft"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.PlaceholderText, "muted"),
        (QPalette.ColorRole.Highlight, "accent"),
        (QPalette.ColorRole.HighlightedText, "surface"),
        (QPalette.ColorRole.ToolTipBase, "text"),
        (QPalette.ColorRole.ToolTipText, "bg"),
    ):
        pal.setColor(role, QColor(c[key]))
    return pal


def q(key: str) -> QColor:
    return QColor(colors()[key])
