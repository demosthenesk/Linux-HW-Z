"""Light/dark palettes (Fusion) and the compact CPU-Z-like style sheet."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

LIGHT = {
    "window": "#eef0f3", "base": "#ffffff", "alt": "#f5f6f8", "text": "#1b1f26", "muted": "#5d6573",
    "field": "#ffffff", "field_border": "#b9c0cb", "group": "#c9ced6", "accent": "#2f6fcf",
    "accent_text": "#ffffff", "graph": "#d8452f", "graph_fill": "#f4c7bd", "tab": "#e2e5ea",
    "button": "#e6e9ee", "warn_bg": "#fff4d6", "warn_text": "#6b4e00", "bar": "#3d7be0", "bar2": "#9aa4b2",
}
DARK = {
    "window": "#1c1f24", "base": "#14161a", "alt": "#20242a", "text": "#e3e6eb", "muted": "#9aa3b0",
    "field": "#111317", "field_border": "#3b414b", "group": "#363c45", "accent": "#5b9bf0",
    "accent_text": "#0b0d10", "graph": "#ff6b55", "graph_fill": "#4a2620", "tab": "#262a31",
    "button": "#2b3038", "warn_bg": "#3b3215", "warn_text": "#f1d38a", "bar": "#5b9bf0", "bar2": "#5a6270",
}

current = dict(LIGHT)


def system_is_dark() -> bool:
    try:
        hints = QGuiApplication.styleHints()
        return hints.colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def apply(app, mode: str = "system") -> dict:
    global current
    dark = system_is_dark() if mode == "system" else mode == "dark"
    c = DARK if dark else LIGHT
    current = dict(c, dark=dark)
    app.setStyle("Fusion")
    pal = QPalette()
    role = QPalette.ColorRole
    pal.setColor(role.Window, QColor(c["window"]))
    pal.setColor(role.WindowText, QColor(c["text"]))
    pal.setColor(role.Base, QColor(c["base"]))
    pal.setColor(role.AlternateBase, QColor(c["alt"]))
    pal.setColor(role.Text, QColor(c["text"]))
    pal.setColor(role.Button, QColor(c["button"]))
    pal.setColor(role.ButtonText, QColor(c["text"]))
    pal.setColor(role.Highlight, QColor(c["accent"]))
    pal.setColor(role.HighlightedText, QColor(c["accent_text"]))
    pal.setColor(role.ToolTipBase, QColor(c["base"]))
    pal.setColor(role.ToolTipText, QColor(c["text"]))
    pal.setColor(role.PlaceholderText, QColor(c["muted"]))
    pal.setColor(role.Link, QColor(c["accent"]))
    for grp in (QPalette.ColorGroup.Disabled,):
        pal.setColor(grp, role.Text, QColor(c["muted"]))
        pal.setColor(grp, role.ButtonText, QColor(c["muted"]))
        pal.setColor(grp, role.WindowText, QColor(c["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(c))
    return current


def stylesheet(c: dict) -> str:
    return f"""
    QGroupBox {{ border: 1px solid {c['group']}; border-radius: 4px; margin-top: 9px; padding: 6px 6px 5px 6px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {c['muted']}; }}
    QLineEdit[field="true"] {{ background: {c['field']}; border: 1px solid {c['field_border']}; border-radius: 2px;
        padding: 1px 4px; color: {c['text']}; selection-background-color: {c['accent']}; }}
    QLabel[field="true"] {{ background: {c['field']}; border: 1px solid {c['field_border']}; border-radius: 2px;
        padding: 2px 4px; color: {c['text']}; }}
    QLabel[role="key"] {{ color: {c['muted']}; }}
    QLabel[role="muted"] {{ color: {c['muted']}; }}
    QLabel[role="brand"] {{ color: {c['muted']}; font-weight: 600; }}
    QFrame[role="banner"] {{ background: {c['warn_bg']}; border-radius: 4px; }}
    QFrame[role="banner"] QLabel {{ color: {c['warn_text']}; }}
    QTabWidget::pane {{ border: 1px solid {c['group']}; border-radius: 3px; top: -1px; background: {c['window']}; }}
    QTabBar::tab {{ background: {c['tab']}; border: 1px solid {c['group']}; border-bottom: none; padding: 4px 10px;
        margin-right: 1px; border-top-left-radius: 3px; border-top-right-radius: 3px; color: {c['muted']}; }}
    QTabBar::tab:selected {{ background: {c['window']}; color: {c['text']}; }}
    QTabBar::tab:hover {{ color: {c['text']}; }}
    QTreeWidget, QTableWidget {{ background: {c['base']}; alternate-background-color: {c['alt']};
        border: 1px solid {c['group']}; }}
    QHeaderView::section {{ background: {c['tab']}; color: {c['muted']}; border: none;
        border-right: 1px solid {c['group']}; border-bottom: 1px solid {c['group']}; padding: 3px 6px; }}
    QProgressBar {{ border: 1px solid {c['field_border']}; border-radius: 2px; background: {c['field']};
        text-align: right; padding-right: 4px; color: {c['text']}; }}
    QProgressBar::chunk {{ background: {c['bar']}; }}
    QProgressBar[ref="true"]::chunk {{ background: {c['bar2']}; }}
    QCheckBox:disabled {{ color: {c['text']}; }}
    """
