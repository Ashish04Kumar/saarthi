"""Speech bubble shown next to the character."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

PAD = 12
TAIL = 12
MAX_TEXT_W = 240


class Bubble(QWidget):
    closed = Signal()  # hidden by its timer or a click

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)  # stay visible on macOS
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.text = ""
        self.tail_down = True
        self.tail_x = 0.0
        self.font_ = QFont()
        self.font_.setPointSize(11)
        self._hide = QTimer(self, singleShot=True, timeout=self.hide)

    def say(self, text: str, anchor: QRect, screen: QRect, ms: int | None = None) -> None:
        self.text = text
        fm = QFontMetrics(self.font_)
        br = fm.boundingRect(QRect(0, 0, MAX_TEXT_W, 1000), Qt.TextFlag.TextWordWrap, text)
        w = br.width() + PAD * 2 + 4
        h = br.height() + PAD * 2 + TAIL
        x = anchor.center().x() - w // 2
        x = max(screen.left() + 4, min(x, screen.right() - w - 4))
        y = anchor.top() - h + 2  # tail tip just touches the head
        self.tail_down = y >= screen.top()
        if not self.tail_down:
            y = anchor.bottom() - 2
        self.tail_x = min(max(anchor.center().x() - x, 20), w - 20)
        self.setGeometry(x, y, w, h)
        self.show()
        self.raise_()
        self.update()
        self._hide.start(ms or max(3500, 60 * len(text)))

    def follow(self, anchor: QRect, screen: QRect) -> None:
        if self.isVisible():
            remaining = self._hide.remainingTime()
            self.say(self.text, anchor, screen, max(remaining, 500))

    def mousePressEvent(self, e):
        self.hide()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.closed.emit()

    def remaining_ms(self) -> int:
        return self._hide.remainingTime() if self.isVisible() else 0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        body = QRectF(2, 2 if self.tail_down else TAIL, w - 4, h - TAIL - 4)
        path = QPainterPath()
        path.addRoundedRect(body, 14, 14)
        tail = QPainterPath()
        tx = self.tail_x
        if self.tail_down:
            tail.moveTo(tx - 9, body.bottom() - 1)
            tail.lineTo(tx, h - 2)
            tail.lineTo(tx + 9, body.bottom() - 1)
        else:
            tail.moveTo(tx - 9, body.top() + 1)
            tail.lineTo(tx, 2)
            tail.lineTo(tx + 9, body.top() + 1)
        tail.closeSubpath()
        path = path.united(tail)
        p.setPen(QPen(QColor("#1B2440"), 2))
        p.setBrush(QColor(255, 255, 255, 245))
        p.drawPath(path)
        p.setFont(self.font_)
        p.setPen(QColor("#1B2440"))
        p.drawText(body.adjusted(PAD, PAD - 2, -PAD, -PAD + 2), Qt.TextFlag.TextWordWrap, self.text)
