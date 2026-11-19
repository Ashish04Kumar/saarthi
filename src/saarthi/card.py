"""Pop-up card next to the buddy for reminders and events, with action buttons."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme

STYLE = """
QLabel { color: $text; }
QLabel#title { font-size: 14px; font-weight: bold; color: $text; }
QLabel#sub { color: $sub; }
QPushButton { background: $soft; border: 1px solid $border; border-radius: 8px; padding: 5px 8px; color: $text; }
QPushButton:hover { background: $hover; }
QPushButton#primary { background: $accent; color: white; border-color: $accent; }
QPushButton#primary:hover { background: $accent_hover; }
"""


class Card(QWidget):
    def __init__(
        self,
        icon: str,
        title: str,
        subtitle: str,
        actions: list[tuple[str, Callable[[], None]]],
        on_close: Callable[[Card], None],
        on_dismiss: Callable[[], None] | None = None,
    ):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)  # stay visible on macOS
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        from .quick_panel import light_palette

        self.setPalette(light_palette())  # readable on dark system themes
        self.setStyleSheet(theme.css(STYLE))
        self._on_close = on_close
        self._on_dismiss = on_dismiss
        self._acted = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        top = QHBoxLayout()
        ic = QLabel(icon)
        ic.setStyleSheet("font-size: 22px;")
        top.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        t = QLabel(title, objectName="title")
        t.setWordWrap(True)
        texts.addWidget(t)
        if subtitle:
            st = QLabel(subtitle, objectName="sub")
            st.setWordWrap(True)
            texts.addWidget(st)
        top.addLayout(texts, 1)
        lay.addLayout(top)
        row = QHBoxLayout()
        row.addStretch(1)
        for i, (label, cb) in enumerate(actions):
            b = QPushButton(label)
            if i == 0:
                b.setObjectName("primary")
            b.clicked.connect(lambda _=False, c=cb: self._act(c))
            row.addWidget(b)
        lay.addLayout(row)
        self.setFixedWidth(350)
        self.adjustSize()

    def _act(self, cb):
        self._acted = True
        cb()
        self.close()

    def mouseDoubleClickEvent(self, e):  # double-click the card background to dismiss
        self.close()

    def closeEvent(self, e):
        if not self._acted and self._on_dismiss is not None:
            self._on_dismiss()  # outcome stays "pending": tick it later in the panel
        self._on_close(self)
        super().closeEvent(e)

    def place(self, anchor: QRect, screen: QRect, stack_index: int):
        h = self.sizeHint().height()
        x = anchor.left() - self.width() - 8
        if x < screen.left():
            x = anchor.right() + 8
        y = anchor.bottom() - h - stack_index * (h + 8)
        y = max(screen.top() + 4, min(y, screen.bottom() - h - 4))
        self.move(x, y)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(theme.q("outline"), 2))
        p.setBrush(theme.q("surface"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFD23D"))
        p.drawRoundedRect(QRectF(1, 1, 6, self.height() - 2), 3, 3)
