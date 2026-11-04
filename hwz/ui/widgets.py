"""Small building blocks: read-only fields, label/field grids, vendor badge, sparkline."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSizePolicy, QWidget)

from . import theme


class Field(QLineEdit):
    def __init__(self, text: str = "", centered: bool = False, width: int | None = None):
        super().__init__()
        self.setReadOnly(True)
        self.setProperty("field", True)
        if centered:
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        if width:
            self.setFixedWidth(width)
        self.setMinimumHeight(21)
        self.set(text)

    def set(self, text) -> None:
        t = "" if text is None else str(text)
        if t != self.text():
            self.setText(t)
            self.setCursorPosition(0)
            self.setToolTip(t if len(t) > 30 else "")


def key(text: str, align=Qt.AlignmentFlag.AlignRight) -> QLabel:
    lb = QLabel(text)
    lb.setProperty("role", "key")
    lb.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    return lb


class Grid(QGroupBox):
    """Group box with a grid of 'Label [field]' cells, added row by row.

    row(("Name", 7), ("Rev", 1)): each cell is a key label (one column) followed
    by a field spanning the given number of columns.  A label may carry a
    '~suffix' to make the field name unique while showing the same text.
    """

    def __init__(self, title: str = "", cols: int = 10):
        super().__init__(title)
        self.cols = cols
        self.g = QGridLayout(self)
        self.g.setContentsMargins(6, 8, 6, 6)
        self.g.setHorizontalSpacing(5)
        self.g.setVerticalSpacing(4)
        self.r = 0
        self.f: dict[str, QWidget] = {}
        self.labels: dict[str, QLabel] = {}

    def show_field(self, name: str, visible: bool):
        """Show or hide one field together with its key label."""
        for w in (self.f.get(name), self.labels.get(name)):
            if w is not None:
                w.setVisible(visible)

    def row(self, *cells, start: int = 0, centered: bool = False):
        col = start
        for cell in cells:
            name, span = (cell, self.cols - 1 - col) if isinstance(cell, str) else cell
            label = name.split("~", 1)[0]
            if label:
                lb = key(label)
                self.labels[name] = lb
                self.g.addWidget(lb, self.r, col)
                col += 1
            fld = Field(centered=centered)
            self.g.addWidget(fld, self.r, col, 1, span)
            self.f[name] = fld
            col += span
        self.r += 1
        return self

    def multi(self, name: str, lines: int = 2):
        self.g.addWidget(key(name, Qt.AlignmentFlag.AlignRight), self.r, 0, Qt.AlignmentFlag.AlignTop)
        lb = MultiField(lines)
        self.g.addWidget(lb, self.r, 1, 1, self.cols - 1)
        self.f[name] = lb
        self.r += 1
        return lb

    def place(self, w, r, c, rs=1, cs=1, align=None):
        if align is None:
            self.g.addWidget(w, r, c, rs, cs)
        else:
            self.g.addWidget(w, r, c, rs, cs, align)
        return w

    def add_row_widget(self, w):
        self.g.addWidget(w, self.r, 0, 1, self.cols)
        self.r += 1
        return w

    def set(self, name: str, value):
        w = self.f.get(name)
        if w is not None:
            w.set(value)

    def even(self, first: int = 0):
        for c in range(self.cols):
            self.g.setColumnStretch(c, 0 if c == first and False else 1)


class MultiField(QLabel):
    def __init__(self, lines: int = 2):
        super().__init__()
        self.setProperty("field", True)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setMinimumHeight(8 + lines * self.fontMetrics().lineSpacing())

    def set(self, text):
        self.setText("" if text is None else str(text))


class Flag(QCheckBox):
    """Read-only check box used for API support flags."""

    def __init__(self, text: str):
        super().__init__(text)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)


VENDOR_COLORS = {
    "Intel": ("#0b6fc6", "#0a4f93"), "AMD": ("#3a3f47", "#16181c"), "NVIDIA": ("#5aa31a", "#3c7310"),
    "Hygon": ("#7a3d9a", "#4b2361"),
}


class Badge(QWidget):
    """A painted chip 'badge' with the vendor name (no trademarked logos)."""

    def __init__(self, size=QSize(92, 86)):
        super().__init__()
        self.vendor = ""
        self.sub = ""
        self.setFixedSize(size)

    def set(self, vendor: str, sub: str = ""):
        self.vendor, self.sub = vendor, sub
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(8, 6, -8, -6)
        c1, c2 = VENDOR_COLORS.get(self.vendor, ("#6b7686", "#454d59"))
        # pins
        pen = QPen(QColor(theme.current.get("muted", "#888")), 2)
        p.setPen(pen)
        for i in range(5):
            x = r.left() + 10 + i * (r.width() - 20) / 4
            p.drawLine(QPointF(x, r.top() - 5), QPointF(x, r.top()))
            p.drawLine(QPointF(x, r.bottom()), QPointF(x, r.bottom() + 5))
            y = r.top() + 10 + i * (r.height() - 20) / 4
            p.drawLine(QPointF(r.left() - 5, y), QPointF(r.left(), y))
            p.drawLine(QPointF(r.right(), y), QPointF(r.right() + 5, y))
        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0, QColor(c1))
        grad.setColorAt(1, QColor(c2))
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        p.fillPath(path, grad)
        p.setPen(QColor("#ffffff"))
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(max(9.0, f.pointSizeF() * (1.25 if len(self.vendor) <= 5 else 1.0)))
        p.setFont(f)
        top = QRectF(r.left(), r.top() + 6, r.width(), r.height() * 0.55)
        p.drawText(top, Qt.AlignmentFlag.AlignCenter, self.vendor or "?")
        if self.sub:
            from PySide6.QtGui import QFontMetrics
            bot = QRectF(r.left() + 3, r.top() + r.height() * 0.55, r.width() - 6, r.height() * 0.4)
            f2 = QFont(self.font())
            size = max(6.0, f2.pointSizeF() * 0.85)
            f2.setPointSizeF(size)
            while size > 5.5 and QFontMetrics(f2).horizontalAdvance(self.sub) > bot.width():
                size -= 0.5
                f2.setPointSizeF(size)
            p.setFont(f2)
            p.setPen(QColor(255, 255, 255, 215))
            p.drawText(bot, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       QFontMetrics(f2).elidedText(self.sub, Qt.TextElideMode.ElideRight, int(bot.width())))
        p.end()


class Sparkline(QWidget):
    """GPU-Z style history graph (newest sample on the right)."""

    def __init__(self, n=150):
        super().__init__()
        self.values: deque[float] = deque(maxlen=n)
        self.setMinimumSize(120, 20)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(20)
        self.vmin = 0.0
        self.vmax = None

    def push(self, v: float):
        self.values.append(v)
        self.update()

    def clear(self):
        self.values.clear()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        c = theme.current
        r = self.rect().adjusted(0, 0, -1, -1)
        p.fillRect(r, QColor(c["field"]))
        p.setPen(QColor(c["field_border"]))
        p.drawRect(r)
        if len(self.values) >= 1:
            vals = list(self.values)
            hi = self.vmax if self.vmax is not None else max(max(vals), 1e-9)
            lo = min(self.vmin, min(vals))
            span = (hi - lo) or 1.0
            n = self.values.maxlen or len(vals)
            step = (r.width() - 2) / max(1, n - 1)
            x0 = r.right() - 1 - (len(vals) - 1) * step
            path = QPainterPath()
            path.moveTo(x0, r.bottom())
            for i, v in enumerate(vals):
                y = r.bottom() - 1 - (v - lo) / span * (r.height() - 3)
                path.lineTo(x0 + i * step, y)
            path.lineTo(x0 + (len(vals) - 1) * step, r.bottom())
            path.closeSubpath()
            p.fillPath(path, QColor(c["graph_fill"]))
            p.setPen(QPen(QColor(c["graph"]), 1.2))
            line = QPainterPath()
            for i, v in enumerate(vals):
                y = r.bottom() - 1 - (v - lo) / span * (r.height() - 3)
                (line.moveTo if i == 0 else line.lineTo)(x0 + i * step, y)
            p.drawPath(line)
        p.end()


class Banner(QFrame):
    clicked = Signal()

    def __init__(self, text: str, button: str = ""):
        super().__init__()
        self.setProperty("role", "banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 6, 5)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        lay.addWidget(self.label, 1)
        if button:
            self.btn = QPushButton(button)
            self.btn.clicked.connect(self.clicked)
            lay.addWidget(self.btn)
