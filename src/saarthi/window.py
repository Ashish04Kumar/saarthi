"""The transparent always-on-top window the character lives in."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBitmap, QImage, QPainter, QRegion
from PySide6.QtWidgets import QApplication, QWidget

from .skin import Skin
from .states import State
from .wellness_logic import breath_phase

FPS = 30
CREDIT_STRIP = 28  # px under the character for the developer credit
MIN_CREDIT_WIDTH = 170
MASK_EVERY = 0.12  # s between click-through mask refreshes
MASK_GROW = 4  # px of slack around the drawn pixels so moving limbs aren't clipped
HIT_SLACK = 3  # px: a click this close to the character still counts


class BuddyWindow(QWidget):
    clicked = Signal(str)  # which part: head / body / jeans / boots
    double_clicked = Signal()
    grabbed = Signal()  # mouse went down on the buddy (stops any walk)
    moved = Signal()
    drag_finished = Signal()
    context_menu = Signal(QPoint)

    def __init__(self, skin: Skin, size: int, credit: str | None = None):
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
        # alternative takes per state, e.g. WATCHING -> "notes", IDLE -> "tired": (name, started)
        self.takes: dict[State, tuple[str, float]] = {}
        self.badge: str | None = None  # small battery icon: "low" / "critical" / "charging" / "full"
        self.battery = 0.0  # % shown in the badge
        self._badge_rect = QRect()
        self.presence = False  # green dot: someone has your Couple mode link open right now
        self._frame: QImage | None = None  # last drawn frame, for pixel-exact clicks
        self._mask_at = 0.0
        self._body = QRect()  # where the character's pixels are (widget coords)
        self.mirror = False
        self.t0 = time.monotonic()
        self.credit = credit  # developer credit shown under the character (None = hidden)
        self.set_size(size)
        self._press: QPoint | None = None
        self._offset = QPoint()
        self._dragging = False
        self._timer = QTimer(self, timeout=self.update)
        self._timer.start(1000 // FPS)
        self._squash_at: float | None = None
        self._click_part = "body"
        # wait to see if a click becomes a double-click before reacting to it
        self._single = QTimer(self, singleShot=True, timeout=lambda: self.clicked.emit(self._click_part))

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

    def credit_height(self) -> int:
        return CREDIT_STRIP if self.credit else 0

    def set_size(self, size: int) -> None:
        self.setFixedSize(
            max(int(size * self.skin.aspect), MIN_CREDIT_WIDTH if self.credit else 0), size + self.credit_height()
        )

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

    def set_variant(self, state: State, variant: str | None) -> None:
        """Use the `variant` take whenever `state` is shown (None = the plain animation)."""
        if variant is None:
            self.takes.pop(state, None)
        elif self.variant(state) != variant:
            self.takes[state] = (variant, time.monotonic())

    def variant(self, state: State) -> str | None:
        take = self.takes.get(state)
        return take[0] if take else None

    def set_badge(self, badge: str | None, battery: float = 0.0) -> None:
        self.badge, self.battery = badge, battery

    def body_rect(self) -> QRect:
        """The character's drawn pixels in global coordinates (falls back to the whole window)."""
        r = self._body if not self._body.isEmpty() else self.rect().adjusted(0, 0, 0, -self.credit_height())
        return r.translated(self.frameGeometry().topLeft())

    def paintEvent(self, _):
        now = time.monotonic()
        dpr = self.devicePixelRatioF()
        img = QImage(round(self.width() * dpr), round(self.height() * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.credit:
            self._paint_credit(p)
        sx, sy = self._body_scale(now)
        w, h = self.width(), self.height() - self.credit_height()
        if self.mirror:
            p.translate(w, 0)
            p.scale(-1, 1)
        inset = 0.94  # leave a little room to squash, stretch and breathe
        p.translate(w / 2, h)  # scale around the feet so the buddy stays planted
        p.scale(sx * inset, sy * inset)
        p.translate(-w / 2, -h)
        variant = None
        if self.override is not None:
            shown, t_state = self.override, (now - self.override_started) * self.override_speed
        else:
            shown, t_state = self.state, now - self.state_started
            take = self.takes.get(shown)
            if take and take[0] in self.skin.variants(shown):
                variant, t_state = take[0], now - take[1]
        self.skin.paint(p, QRectF(0, 0, w, h), shown, now - self.t0, t_state, variant)
        p.resetTransform()
        if self.badge:
            self._paint_badge(p, now)
        if self.presence:
            self._paint_presence(p, now)
        p.end()
        self._frame = img
        out = QPainter(self)
        out.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        out.drawImage(0, 0, img)
        out.end()
        if now - self._mask_at > MASK_EVERY and self._press is None:
            self._mask_at = now
            self._update_mask(img)

    def _update_mask(self, img: QImage) -> None:
        """Let clicks on the empty space around the character fall through to the window behind."""
        if img.devicePixelRatio() != 1:
            img = img.scaled(self.width(), self.height())
        # every pixel with any alpha at all is "inside"
        alpha = img.convertToFormat(QImage.Format.Format_Alpha8)
        gray = QImage(
            alpha.constBits(), alpha.width(), alpha.height(), alpha.bytesPerLine(), QImage.Format.Format_Grayscale8
        ).copy()
        bits = QBitmap.fromImage(gray.createMaskFromColor(0xFF000000, Qt.MaskMode.MaskInColor))
        drawn = QRegion(bits)
        body = drawn.intersected(QRegion(0, 0, self.width(), self.height() - self.credit_height()))
        if self.badge or self.presence:
            body = body.subtracted(QRegion(self._badge_rect))  # the badge sits on the body, isn't part of it
        self._body = body.boundingRect()
        grown = drawn
        for dx, dy in ((MASK_GROW, 0), (-MASK_GROW, 0)):
            grown = grown.united(drawn.translated(dx, dy))
        wide = grown
        for dx, dy in ((0, MASK_GROW), (0, -MASK_GROW)):
            grown = grown.united(wide.translated(dx, dy))
        if not grown.isEmpty() and (handle := self.windowHandle()) is not None:
            handle.setMask(grown)

    def _hits_character(self, pos: QPoint) -> bool:
        """True if `pos` (widget coords) is on the character or the credit, not on empty space."""
        img = self._frame
        if img is None:
            return True
        dpr = img.devicePixelRatio()
        cx, cy, r = int(pos.x() * dpr), int(pos.y() * dpr), int(HIT_SLACK * dpr)
        for y in range(max(0, cy - r), min(img.height(), cy + r + 1)):
            for x in range(max(0, cx - r), min(img.width(), cx + r + 1)):
                if img.pixelColor(x, y).alpha() > 24:
                    return True
        return False

    def set_presence(self, on: bool) -> None:
        self.presence = on
        self.update()

    def _paint_presence(self, p: QPainter, now: float) -> None:
        """A small green 'online' dot left of the head, gently pulsing."""
        from PySide6.QtGui import QColor, QPen

        body = self._body if not self._body.isEmpty() else self.rect()
        r = 5.0
        x = max(r + 3, body.center().x() - body.width() // 5)
        y = max(r + 3, body.top() + 8)
        glow = 0.5 + 0.5 * math.sin(now * 3)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(58, 210, 122, int(60 + 60 * glow)))
        p.drawEllipse(QRectF(x - r - 3, y - r - 3, 2 * r + 6, 2 * r + 6))
        p.setPen(QPen(QColor(255, 255, 255, 230), 1.4))
        p.setBrush(QColor(58, 210, 122))
        p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
        p.restore()
        self._badge_rect = self._badge_rect.united(
            QRect(int(x - r - 4), int(y - r - 4), int(2 * r + 8), int(2 * r + 8))
        )

    def _paint_badge(self, p: QPainter, now: float) -> None:
        """A phone-style battery icon next to the head."""
        from PySide6.QtGui import QColor, QPainterPath, QPen

        if self.badge == "critical" and int(now * 2) % 2:
            return  # blink
        body = self._body if not self._body.isEmpty() else self.rect()
        bw, bh = 24, 12
        x = min(self.width() - bw - 6, body.center().x() + body.width() // 6)  # just right of the head
        y = max(2, body.top() + 2)
        self._badge_rect = QRect(int(x) - 2, int(y) - 2, bw + 8, bh + 4)
        color = {"low": "#FF4D4F", "critical": "#FF1F1F", "charging": "#38D172", "full": "#38D172"}[self.badge]
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 235), 1.6))
        p.setBrush(QColor(20, 24, 40, 200))
        p.drawRoundedRect(QRectF(x, y, bw, bh), 3, 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRoundedRect(QRectF(x + bw + 0.5, y + 3.5, 2.5, bh - 7), 1, 1)  # the nub
        level = 1.0 if self.badge == "full" else max(0.12, min(1.0, self.battery / 100))
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(x + 2, y + 2, (bw - 4) * level, bh - 4), 1.5, 1.5)
        if self.badge == "charging":  # lightning bolt
            bolt = QPainterPath()
            cx, cy = x + bw / 2, y + bh / 2
            for i, (dx, dy) in enumerate(((1.5, -5), (-3, 0.8), (0, 0.8), (-1.5, 5), (3, -0.8), (0, -0.8))):
                (bolt.moveTo if i == 0 else bolt.lineTo)(cx + dx, cy + dy)
            bolt.closeSubpath()
            p.setBrush(QColor(255, 255, 255))
            p.drawPath(bolt)
        p.restore()

    def _paint_credit(self, p: QPainter) -> None:
        """Small developer credit under the character."""
        from PySide6.QtGui import QColor, QFont, QFontMetrics

        w, strip = self.width(), self.credit_height()
        top = self.height() - strip
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 24, 40, 170))
        p.drawRoundedRect(QRectF(2, top + 1, w - 4, strip - 2), 7, 7)
        f = QFont()
        f.setPixelSize(10 if w >= 200 else 8)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 235))
        fm = QFontMetrics(f)
        name, _, email = self.credit.partition(" (")
        lines = [name, "(" + email] if email else [name]
        for i, line in enumerate(lines):
            text = fm.elidedText(line, Qt.TextElideMode.ElideRight, w - 10)
            p.drawText(
                QRectF(4, top + 2 + i * (strip - 4) / 2, w - 8, (strip - 4) / 2), Qt.AlignmentFlag.AlignCenter, text
            )
        p.restore()

    def part_at(self, pos: QPoint) -> str:
        """Which part of the character is under `pos`: head / body / jeans / boots.
        Jeans and boots are told apart by colour (dark blue / brown) low on the body."""
        body = self._body if not self._body.isEmpty() else self.rect().adjusted(0, 0, 0, -self.credit_height())
        down = (pos.y() - body.top()) / max(1, body.height())  # 0 = top of the head, 1 = feet
        img = self._frame
        if img is not None and down > 0.62:  # legs only (the laptop lid is dark blue too)
            dpr = img.devicePixelRatio()
            jeans = boots = 0
            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    x, y = int((pos.x() + dx) * dpr), int((pos.y() + dy) * dpr)
                    if not (0 <= x < img.width() and 0 <= y < img.height()):
                        continue
                    c = img.pixelColor(x, y)
                    if c.alpha() < 120:
                        continue
                    r, g, b = c.red(), c.green(), c.blue()
                    bright = (r + g + b) / 3
                    if b > r + 12 and bright < 95:
                        jeans += 1
                    elif r > b + 25 and bright < 110 and r < 150 and down > 0.78:
                        boots += 1
            if max(jeans, boots) >= 6:
                return "boots" if boots > jeans else "jeans"
        return "head" if down < 0.4 else "body"

    # ---- dragging / clicks ----
    def mousePressEvent(self, e):
        if not self._hits_character(e.position().toPoint()):
            e.ignore()
            return
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
        if e.button() == Qt.MouseButton.LeftButton and self._hits_character(e.position().toPoint()):
            self._single.stop()
            self._press = None
            self.double_clicked.emit()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        if self._dragging:
            self.drag_finished.emit()
        else:
            self._click_part = self.part_at(e.position().toPoint())
            self._single.start(QApplication.doubleClickInterval())
        self._press = None
        self._dragging = False
