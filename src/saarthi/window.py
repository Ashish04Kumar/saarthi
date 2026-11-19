"""The transparent always-on-top window the character lives in."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QWidget

from .skin import Skin
from .states import State
from .wellness_logic import breath_phase

FPS = 30


class BuddyWindow(QWidget):
    clicked = Signal(float)  # where: 0 = top of the window, 1 = bottom
    double_clicked = Signal()
    grabbed = Signal()  # mouse went down on the buddy (stops any walk)
    moved = Signal()
    drag_finished = Signal()
    context_menu = Signal(QPoint)

    def __init__(self, skin: Skin, size: int):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)  # stay visible on macOS
        self.setWindowTitle("Saarthi")
        self.skin = skin
        self.state = State.IDLE
        self.state_started = time.monotonic()
        self.override: State | None = None  # e.g. WALK while the walker moves us
        self.override_started = 0.0
        self.override_speed = 1.0  # animation speed for the override (slow strolls)
        self.mirror = False
        self.t0 = time.monotonic()
        self.set_size(size)
        self._press: QPoint | None = None
        self._offset = QPoint()
        self._dragging = False
        self._timer = QTimer(self, timeout=self.update)
        self._timer.start(1000 // FPS)
        self._squash_at: float | None = None
        self._click_y = 0.5
        # wait to see if a click becomes a double-click before reacting to it
        self._single = QTimer(self, singleShot=True, timeout=lambda: self.clicked.emit(self._click_y))

    def squash(self) -> None:
        self._squash_at = time.monotonic()

    def _body_scale(self, now: float) -> tuple[float, float]:
        sx = sy = 1.0
        if self._squash_at is not None:
            k = now - self._squash_at
            if k > 0.8:
                self._squash_at = None
            else:  # springy squash-and-stretch
                w = math.exp(-6 * k) * math.cos(22 * k)
                sx, sy = 1 + 0.14 * w, 1 - 0.14 * w
        if self.state == State.BREATHE:
            level = breath_phase(now - self.state_started)[2]
            sx *= 1 + 0.035 * level
            sy *= 1 + 0.06 * level
        return sx, sy

    def set_size(self, size: int) -> None:
        self.setFixedSize(int(size * self.skin.aspect), size)

    def set_skin(self, skin: Skin, size: int) -> None:
        self.skin = skin
        self.set_size(size)
        self.update()

    def set_override(self, state: State | None, mirror: bool = False, speed: float = 1.0) -> None:
        if state != self.override:
            self.override_started = time.monotonic()
        self.override, self.mirror, self.override_speed = state, mirror, speed

    def set_state(self, state: State, started: float) -> None:
        if state != self.state:
            self.state = state
            self.state_started = started

    def paintEvent(self, _):
        now = time.monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        sx, sy = self._body_scale(now)
        w, h = self.width(), self.height()
        if self.mirror:
            p.translate(w, 0)
            p.scale(-1, 1)
        inset = 0.94  # leave a little room to squash, stretch and breathe
        p.translate(w / 2, h)  # scale around the feet so the buddy stays planted
        p.scale(sx * inset, sy * inset)
        p.translate(-w / 2, -h)
        if self.override is not None:
            shown, t_state = self.override, (now - self.override_started) * self.override_speed
        else:
            shown, t_state = self.state, now - self.state_started
        self.skin.paint(p, QRectF(self.rect()), shown, now - self.t0, t_state)

    # ---- dragging / clicks ----
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.grabbed.emit()
            self._press = e.globalPosition().toPoint()
            self._offset = self._press - self.frameGeometry().topLeft()
            self._dragging = False
        elif e.button() == Qt.MouseButton.RightButton:
            self.context_menu.emit(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._press is None:
            return
        pos = e.globalPosition().toPoint()
        if not self._dragging and (pos - self._press).manhattanLength() > 5:
            self._dragging = True
        if self._dragging:
            self.move(pos - self._offset)
            self.moved.emit()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._single.stop()
            self._press = None
            self.double_clicked.emit()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        if self._dragging:
            self.drag_finished.emit()
        else:
            self._click_y = e.position().y() / max(1, self.height())
            self._single.start(QApplication.doubleClickInterval())
        self._press = None
        self._dragging = False
