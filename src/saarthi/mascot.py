"""Bit: the built-in placeholder mascot, drawn entirely with QPainter.

Everything is drawn on a 200x200 design canvas and scaled to the target rect,
so it stays crisp at any size and needs no image files.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

from .skin import Skin
from .states import State
from .wellness_logic import breath_phase

S = State
BODY_TOP = QColor("#6FA0FF")
BODY_BOTTOM = QColor("#3E6FE0")
BELLY = QColor(255, 255, 255, 45)
INK = QColor("#1B2440")
CHEEK = QColor(255, 120, 150, 110)
LAPTOP = QColor("#D5DAE3")
LAPTOP_EDGE = QColor("#9CA4B3")
ANTENNA_GLOW = {
    S.TYPING_FAST: QColor("#FF6B3D"),
    S.ALERT: QColor("#FF3D5A"),
    S.SLEEPING: QColor("#7A86FF"),
    S.AFK: QColor("#9AA3C7"),
    S.WATCHING: QColor("#FFD23D"),
    S.HAPPY: QColor("#FF8FD0"),
    S.WAKING: QColor("#FF8FD0"),
}
DEFAULT_GLOW = QColor("#5CF29B")

LAPTOP_STATES = {S.TYPING_FAST, S.TYPING_SLOW, S.SCROLLING, S.WATCHING}


class BitSkin(Skin):
    id = "builtin:bit"
    name = "Bit"
    author = "Saarthi"
    aspect = 1.0

    def states(self) -> set[State]:
        return set(State)

    def variants(self, state: State) -> set[str]:
        return {"popcorn"} if state == S.WATCHING else set()

    def paint(
        self, p: QPainter, rect: QRectF, state: State, t: float, t_state: float, variant: str | None = None
    ) -> None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = min(rect.width(), rect.height()) / 200.0
        p.translate(rect.x() + (rect.width() - 200 * s) / 2, rect.y() + (rect.height() - 200 * s) / 2)
        p.scale(s, s)
        _Bit(p, state, t, t_state, self.accessory, variant).draw()
        p.restore()


class _Bit:
    def __init__(
        self, p: QPainter, state: State, t: float, ts: float, accessory: str | None = None, variant: str | None = None
    ):
        self.variant = variant
        self.p, self.state, self.t, self.ts = p, state, t, ts
        self.accessory = accessory
        speed = {S.TYPING_FAST: 10.0, S.SLEEPING: 0.9, S.AFK: 1.3}.get(state, 2.4)
        amp = {S.TYPING_FAST: 2.0, S.SLEEPING: 3.5}.get(state, 3.0)
        self.bob = math.sin(t * speed) * amp
        if state in (S.HAPPY, S.WAKING):
            self.bob = -abs(math.sin(ts * 7)) * 14 * max(0.0, 1 - ts / 2.5)
        self.stretch = (math.sin(ts * 2.2 - math.pi / 2) + 1) / 2 if state == S.STRETCH else 0.0
        self.breath = breath_phase(ts)[2] if state == S.BREATHE else 0.0
        self.exhaling = state == S.BREATHE and breath_phase(ts)[0] == "out"
        if state == S.POKED:
            self.bob = 6 * math.exp(-4 * ts) * math.cos(14 * ts)
        if state == S.WALK:
            self.bob = -abs(math.sin(ts * 9.4)) * 5
        self.body_h = 108 + self.stretch * 16 + self.breath * 8
        self.bottom = 178 + min(self.bob, 0) * 0 + self.bob
        self.top = self.bottom - self.body_h
        self.cx = 100.0

    # ---------- helpers ----------
    def pen(self, color=INK, width=3.0):
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def text(self, x, y, txt, size=16, color=INK, alpha=255, bold=True):
        f = QFont()
        f.setPointSizeF(size)
        f.setBold(bold)
        self.p.setFont(f)
        c = QColor(color)
        c.setAlpha(int(max(0, min(255, alpha))))
        self.p.setPen(c)
        self.p.drawText(QPointF(x, y), txt)

    # ---------- main ----------
    def draw(self):
        p = self.p
        p.save()
        if self.state == S.GIGGLE:  # shake with laughter
            p.translate(math.sin(self.ts * 32) * 3, 0)
        elif self.state == S.WALK:  # lean into the walk
            p.translate(100, 185)
            p.rotate(5 + math.sin(self.ts * 9.4) * 2)
            p.translate(-100, -185)
        elif self.state == S.POKED:  # wobble from the poke
            p.translate(100, 185)
            p.rotate(10 * math.exp(-3.5 * self.ts) * math.sin(12 * self.ts))
            p.translate(-100, -185)
        self._draw()
        p.restore()

    def _draw(self):
        self.shadow()
        if self.state == S.WALK:
            self.feet()
        if self.accessory == "umbrella":
            self.umbrella()
        else:
            self.antenna()
        self.arms_back()
        self.body()
        self.face()
        acc = self.accessory
        if acc == "shades" and self.state not in (S.SLEEPING, S.WATCHING):
            self.shades()
        if acc == "scarf":
            self.scarf()
            self.beanie()
        if self.state in LAPTOP_STATES:
            self.laptop()
        self.arms_front()
        self.props()
        if acc == "umbrella":
            self.rain()

    # ---------- weather outfits ----------
    def shades(self):
        p = self.p
        ey = self.top + 46
        p.setPen(self.pen(INK, 3))
        p.setBrush(QColor(20, 24, 40, 235))
        for x in (self.cx - 21, self.cx + 21):
            path = QPainterPath()
            path.moveTo(x - 16, ey - 10)
            path.lineTo(x + 16, ey - 10)
            path.quadTo(x + 15, ey + 12, x, ey + 12)
            path.quadTo(x - 15, ey + 12, x - 16, ey - 10)
            p.drawPath(path)
        p.drawLine(QPointF(self.cx - 5, ey - 8), QPointF(self.cx + 5, ey - 8))
        p.setPen(self.pen(QColor(255, 255, 255, 150), 2))
        for x in (self.cx - 27, self.cx + 15):
            p.drawLine(QPointF(x, ey - 5), QPointF(x + 5, ey - 5))

    def beanie(self):
        p = self.p
        top = self.top
        hat = QPainterPath()
        hat.moveTo(self.cx - 44, top + 20)
        hat.cubicTo(self.cx - 44, top - 14, self.cx + 44, top - 14, self.cx + 44, top + 20)
        hat.closeSubpath()
        p.setPen(self.pen(INK, 3))
        p.setBrush(QColor("#E94B5A"))
        p.drawPath(hat)
        p.setBrush(QColor("#F7F2E8"))
        p.drawRoundedRect(QRectF(self.cx - 48, top + 14, 96, 14), 7, 7)
        p.drawEllipse(QPointF(self.cx, top - 9), 9, 9)

    def scarf(self):
        p = self.p
        y = self.top + 90
        p.setPen(self.pen(INK, 3))
        p.setBrush(QColor("#E94B5A"))
        p.drawRoundedRect(QRectF(self.cx - 50, y, 100, 15), 7, 7)
        sway = math.sin(self.t * 2) * 3
        tail = QPainterPath()
        tail.moveTo(self.cx + 22, y + 10)
        tail.lineTo(self.cx + 38 + sway, y + 40)
        tail.lineTo(self.cx + 24 + sway, y + 42)
        tail.lineTo(self.cx + 12, y + 12)
        tail.closeSubpath()
        p.drawPath(tail)
        p.setPen(self.pen(QColor("#F7F2E8"), 2.5))
        for i in range(3):
            p.drawLine(QPointF(self.cx - 40 + i * 30, y + 3), QPointF(self.cx - 34 + i * 30, y + 12))

    def rain(self):
        p = self.p
        for i in range(8):
            k = ((self.t * 1.4) + i * 0.37) % 1.0
            x = (10 + i * 26) % 200
            if 25 < x < 175:
                continue
            c = QColor("#6EC8FF")
            c.setAlpha(int(220 * (1 - k)))
            p.setPen(QPen(c, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            y = 10 + k * 170
            p.drawLine(QPointF(x, y), QPointF(x - 3, y + 9))

    def umbrella(self):
        """Drawn behind the body: canopy over the head, shaft hidden behind Bit."""
        p = self.p
        p.save()
        p.translate(self.cx, self.top - 20)
        p.rotate(-6 + math.sin(self.t * 1.5) * 2)
        p.setPen(self.pen(INK, 3.5))
        p.drawLine(QPointF(0, -12), QPointF(0, 90))
        top = -12
        canopy = QPainterPath()
        canopy.moveTo(-70, top + 22)
        canopy.cubicTo(-64, top - 34, 64, top - 34, 70, top + 22)
        for i in range(4):
            x0 = 70 - i * 35
            canopy.quadTo(x0 - 17.5, top + 10, x0 - 35, top + 22)
        canopy.closeSubpath()
        g = QLinearGradient(QPointF(-70, 0), QPointF(70, 0))
        g.setColorAt(0, QColor("#FF6B8A"))
        g.setColorAt(0.5, QColor("#FFB23D"))
        g.setColorAt(1, QColor("#FF6B8A"))
        p.setPen(self.pen(INK, 3))
        p.setBrush(QBrush(g))
        p.drawPath(canopy)
        p.setBrush(INK)
        p.drawEllipse(QPointF(0, top - 20), 3, 3)
        p.restore()

    def shadow(self):
        p = self.p
        lift = max(0.0, -self.bob)
        rx = 52 - lift * 1.2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, max(20, 60 - int(lift * 2))))
        p.drawEllipse(QPointF(100, 188), rx, 7)

    def antenna(self):
        p = self.p
        wiggle = math.sin(self.t * (9 if self.state == S.TYPING_FAST else 3)) * (
            14 if self.state == S.TYPING_FAST else 8
        )
        if self.state == S.SLEEPING:
            wiggle = 35  # droops
        a = math.radians(wiggle)
        base = QPointF(self.cx, self.top + 4)
        tip = QPointF(self.cx + math.sin(a) * 26, self.top + 4 - math.cos(a) * 26)
        p.setPen(self.pen(INK, 3))
        p.drawLine(base, tip)
        glow = ANTENNA_GLOW.get(self.state, DEFAULT_GLOW)
        pulse = 0.6 + 0.4 * math.sin(self.t * (8 if self.state == S.ALERT else 3))
        g = QRadialGradient(tip, 14)
        c = QColor(glow)
        c.setAlpha(int(120 * pulse))
        g.setColorAt(0, c)
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(tip, 14, 14)
        p.setPen(self.pen(INK, 2.5))
        p.setBrush(glow)
        p.drawEllipse(tip, 6, 6)

    def body(self):
        p = self.p
        r = QRectF(self.cx - 52, self.top, 104, self.body_h)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, BODY_TOP)
        g.setColorAt(1, BODY_BOTTOM)
        p.setPen(self.pen(INK, 3.5))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 46, 46)
        # belly + shine
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BELLY)
        p.drawEllipse(QPointF(self.cx, self.bottom - 28), 32, 22)
        p.setBrush(QColor(255, 255, 255, 90))
        p.drawEllipse(QPointF(self.cx - 28, self.top + 22), 9, 5)

    # ---------- face ----------
    def look(self):
        t, st = self.t, self.state
        if st == S.TYPING_FAST:
            return 0, 6
        if st == S.TYPING_SLOW:
            return (4, -5) if math.sin(t * 0.8) > -0.3 else (0, 6)
        if st == S.THINK:
            return 5, -6
        if st == S.EAT:
            return 0, 5
        if st == S.SCROLLING:
            return 0, math.sin(t * 3.5) * 6
        if st == S.WATCHING:
            return math.sin(t * 0.4) * 1.5, 4
        if st in (S.HAPPY, S.WAKING, S.ALERT):
            return 0, 0
        return math.sin(t * 0.7) * 5, math.cos(t * 0.45) * 2.5

    def face(self):
        p, st = self.p, self.state
        ey = self.top + 46
        ex = (self.cx - 21, self.cx + 21)
        closed = st in (S.SLEEPING, S.BREATHE) or (st == S.STRETCH and self.stretch > 0.6)
        blink = (self.t % 4.3) < 0.13 and st not in (S.ALERT, S.WAKING)
        happy_eyes = st in (S.HAPPY, S.GIGGLE)

        # cheeks
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(CHEEK)
        for x in (self.cx - 36, self.cx + 36):
            p.drawEllipse(QPointF(x, ey + 18), 8, 5)

        for i, x in enumerate(ex):
            if st == S.POKED:  # squeezed shut: > <
                p.setPen(self.pen(INK, 3.5))
                d = 1 if i == 0 else -1
                p.drawLine(QPointF(x - 8 * d, ey - 7), QPointF(x + 6 * d, ey))
                p.drawLine(QPointF(x + 6 * d, ey), QPointF(x - 8 * d, ey + 7))
                continue
            if closed or blink:
                p.setPen(self.pen(INK, 3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(QRectF(x - 10, ey - 4, 20, 12), 200 * 16, 140 * 16)
                continue
            if happy_eyes:
                p.setPen(self.pen(INK, 3.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(QRectF(x - 10, ey - 4, 20, 16), 20 * 16, 140 * 16)
                continue
            ry = 16 if st != S.WAKING else 18
            p.setPen(self.pen(INK, 3))
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(x, ey), 13, ry)
            lx, ly = self.look()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(INK)
            pr = 6.5 if st != S.WAKING else 4.5
            p.drawEllipse(QPointF(x + lx, ey + ly), pr, pr + 0.5)
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(x + lx + 2.5, ey + ly - 3), 2.2, 2.2)
            if st in (S.AFK, S.BREAK):  # heavy, relaxed eyelids
                p.setBrush(BODY_TOP)
                p.setPen(self.pen(INK, 3))
                lid = QPainterPath()
                lid.moveTo(x - 14, ey - 1)
                lid.arcTo(QRectF(x - 14, ey - 17, 28, 32), 180, -180)
                lid.closeSubpath()
                p.drawPath(lid)

        self.brows(ex, ey)
        if st == S.WATCHING:
            self.glasses(ex, ey)
        self.mouth(ey + 30)

    def brows(self, ex, ey):
        p, st = self.p, self.state
        p.setPen(self.pen(INK, 3))
        y = ey - 24
        if st == S.TYPING_FAST:  # determined
            p.drawLine(QPointF(ex[0] - 10, y - 2), QPointF(ex[0] + 8, y + 4))
            p.drawLine(QPointF(ex[1] + 10, y - 2), QPointF(ex[1] - 8, y + 4))
        elif st in (S.TYPING_SLOW, S.THINK):  # one raised
            p.drawLine(QPointF(ex[0] - 9, y + 2), QPointF(ex[0] + 9, y + 2))
            p.drawLine(QPointF(ex[1] - 9, y - 3), QPointF(ex[1] + 9, y - 7))
        elif st in (S.ALERT, S.WAKING):
            for x in ex:
                p.drawArc(QRectF(x - 10, y - 8, 20, 10), 30 * 16, 120 * 16)

    def glasses(self, ex, ey):
        p = self.p
        p.setPen(self.pen(INK, 3))
        p.setBrush(QColor(80, 200, 255, 50))
        for x in ex:
            p.drawRoundedRect(QRectF(x - 16, ey - 13, 32, 26), 8, 8)
        p.drawLine(QPointF(ex[0] + 16, ey - 3), QPointF(ex[1] - 16, ey - 3))

    def mouth(self, my):
        p, st, cx = self.p, self.state, self.cx
        p.setPen(self.pen(INK, 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if st in (S.HAPPY, S.WAKING, S.STRETCH, S.GIGGLE):
            open_h = 14 if st != S.STRETCH else 8 + 10 * self.stretch
            path = QPainterPath()
            path.moveTo(cx - 13, my - 3)
            path.quadTo(cx, my - 3 - 2, cx + 13, my - 3)
            path.quadTo(cx + 12, my + open_h, cx, my + open_h)
            path.quadTo(cx - 12, my + open_h, cx - 13, my - 3)
            p.setBrush(QColor("#7A1F3D"))
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#FF7A9A"))
            p.drawEllipse(QPointF(cx, my + open_h - 4), 6, 3.5)
        elif st == S.SLEEPING:
            r = 3 + math.sin(self.t * 0.9) * 1.2
            p.drawEllipse(QPointF(cx, my + 2), r, r)
        elif st in (S.TYPING_SLOW, S.THINK):
            p.drawEllipse(QPointF(cx + 6, my + 2), 3.5, 3.5)
        elif st == S.EAT:  # chewing
            if math.sin(self.t * 9) > 0:
                p.setBrush(QColor("#7A1F3D"))
                p.drawEllipse(QPointF(cx, my + 3), 5, 4)
            else:
                p.drawArc(QRectF(cx - 8, my - 3, 16, 10), 200 * 16, 140 * 16)
        elif st == S.TYPING_FAST:
            # focused grin with tongue out at the side
            p.drawLine(QPointF(cx - 10, my + 2), QPointF(cx + 10, my + 2))
            p.setPen(self.pen(INK, 2))
            p.setBrush(QColor("#FF7A9A"))
            p.drawChord(QRectF(cx + 2, my - 3, 10, 12), 180 * 16, 180 * 16)
        elif st in (S.SCROLLING, S.AFK):
            p.drawLine(QPointF(cx - 8, my + 3), QPointF(cx + 8, my + 3))
        elif st in (S.ALERT, S.POKED):
            p.setBrush(QColor("#7A1F3D"))
            p.drawEllipse(QPointF(cx, my + 4), 6, 8)
        elif st == S.BREATHE:
            if self.exhaling:  # blowing out
                p.drawEllipse(QPointF(cx, my + 3), 3.5, 4.5)
            else:
                p.drawLine(QPointF(cx - 6, my + 3), QPointF(cx + 6, my + 3))
        else:
            p.drawArc(QRectF(cx - 12, my - 8, 24, 16), 200 * 16, 140 * 16)

    # ---------- laptop & arms ----------
    def laptop(self):
        p = self.p
        lid = QRectF(56, 124, 88, 50)
        glow_alpha = 70 if self.state == S.WATCHING else 40
        flicker = 0.75 + 0.25 * math.sin(self.t * 5) if self.state == S.WATCHING else 1
        g = QRadialGradient(QPointF(100, 124), 80)
        g.setColorAt(0, QColor(140, 210, 255, int(glow_alpha * flicker)))
        g.setColorAt(1, QColor(140, 210, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(100, 110), 70, 50)
        p.setPen(self.pen(INK, 3))
        p.setBrush(LAPTOP)
        p.drawRoundedRect(lid, 6, 6)
        p.setBrush(LAPTOP_EDGE)
        p.drawRoundedRect(QRectF(46, 172, 108, 8), 4, 4)
        # logo: tiny heart
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FF6B8A"))
        heart = QPainterPath()
        heart.moveTo(100, 156)
        heart.cubicTo(88, 147, 92, 138, 100, 144)
        heart.cubicTo(108, 138, 112, 147, 100, 156)
        p.drawPath(heart)

    def arms_back(self):
        pass

    def hand(self, x, y, r=9):
        self.p.setPen(self.pen(INK, 3))
        self.p.setBrush(BODY_BOTTOM)
        self.p.drawEllipse(QPointF(x, y), r, r)

    def arms_front(self):
        st, t, ts = self.state, self.t, self.ts
        if st in LAPTOP_STATES:
            if st == S.TYPING_FAST:
                ly = 124 + math.sin(t * 28) * 4
                ry = 124 + math.sin(t * 28 + math.pi) * 4
            elif st == S.TYPING_SLOW:
                tap = math.sin(t * 5)
                ly = 124 - (4 if tap > 0.75 else 0)
                ry = 124 - (4 if tap < -0.75 else 0)
            elif st == S.SCROLLING:
                ly, ry = 126, 124 + math.sin(t * 7) * 3
            else:  # watching: relaxed, right hand dips into popcorn
                ly, ry = 126, 126
            self.hand(56, ly)
            if st == S.WATCHING and self.variant == "popcorn":
                self.popcorn()
                dip = max(0.0, math.sin(t * 1.3)) ** 6
                self.hand(146 + dip * 12, 126 + dip * 8)
            else:
                self.hand(144, ry)
            return

        base_y = self.bottom - 40
        if st in (S.HAPPY, S.WAKING):
            wave = math.sin(ts * 14) * 6
            self.hand(40, base_y - 30 + wave)
            self.hand(160, base_y - 30 - wave)
        elif st == S.STRETCH:
            lift = self.stretch
            self.hand(46 + 20 * lift, base_y - 30 - 70 * lift)
            self.hand(154 - 20 * lift, base_y - 30 - 70 * lift)
        elif st == S.ALERT:
            self.sign()
        elif st == S.EAT:
            bite = max(0.0, math.sin(t * 1.4)) ** 3  # spoon goes up to the mouth
            self.bowl(self.cx, base_y + 28)
            sx, sy = 132 - bite * 22, base_y + 12 - bite * 16
            self.spoon(sx, sy)
            self.hand(sx + 8, sy + 6)
            self.hand(70, base_y + 18)
        elif st == S.THINK:  # hand on the chin
            self.hand(self.cx + 26, self.top + 92)
            self.hand(54, base_y + 8)
        elif st == S.BREAK:
            sip = max(0.0, math.sin(t * 0.9)) ** 4  # now and then, a sip
            cx, cy = 152 - sip * 34, base_y + 6 - sip * 6
            self.hand(46, base_y + 12)
            self.cup(cx, cy)
            self.hand(cx - 14, cy + 4)
        elif st == S.GIGGLE:  # holding the belly
            j = math.sin(ts * 30) * 2
            self.hand(70, base_y + 4 + j)
            self.hand(130, base_y + 4 - j)
        elif st == S.BREATHE:
            b = self.breath
            self.hand(44 + 6 * b, base_y + 6 - 46 * b)
            self.hand(156 - 6 * b, base_y + 6 - 46 * b)
        elif st == S.WALK:  # swing the arms
            k = math.sin(ts * 9.4) * 10
            self.hand(46 + k, base_y + 6)
            self.hand(154 - k, base_y + 6)
        elif st == S.POKED:  # rubbing the head
            rub = math.sin(ts * 18) * 4
            self.hand(46, base_y + 6)
            self.hand(140 + rub, self.top + 10)
        elif st in (S.SLEEPING, S.AFK):
            self.hand(46, base_y + 12)
            self.hand(154, base_y + 12)
        else:  # idle: occasional little wave
            phase = t % 9
            wave = math.sin(phase * 12) * 8 if phase < 1.2 else 0
            self.hand(46, base_y + 6)
            self.hand(156 + (4 if wave else 0), base_y + 4 - (24 if wave else 0) + wave)

    def feet(self):
        p = self.p
        for i in (0, 1):
            k = math.sin(self.ts * 9.4 + i * math.pi)
            x = 100 + (-18 if i == 0 else 18) + k * 12
            y = 186 - max(0.0, k) * 6
            p.setPen(self.pen(INK, 3))
            p.setBrush(BODY_BOTTOM)
            p.drawEllipse(QPointF(x, y), 13, 7)

    def bowl(self, x, y):
        p = self.p
        p.setPen(self.pen(INK, 2.5))
        p.setBrush(QColor("#FFF6D6"))  # rice
        p.drawEllipse(QPointF(x, y - 8), 24, 7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#E8A33D"))  # dal
        p.drawEllipse(QPointF(x + 8, y - 9), 10, 4)
        body = QPainterPath()
        body.moveTo(x - 26, y - 8)
        body.quadTo(x - 24, y + 14, x, y + 14)
        body.quadTo(x + 24, y + 14, x + 26, y - 8)
        body.closeSubpath()
        p.setPen(self.pen(INK, 2.5))
        p.setBrush(QColor("#D9DEE8"))
        p.drawPath(body)

    def spoon(self, x, y):
        p = self.p
        p.setPen(self.pen(QColor("#8C95A6"), 3.5))
        p.drawLine(QPointF(x + 8, y + 10), QPointF(x - 4, y - 6))
        p.setPen(self.pen(INK, 2))
        p.setBrush(QColor("#D9DEE8"))
        p.drawEllipse(QPointF(x - 6, y - 9), 6, 4)

    def cup(self, x, y):
        p = self.p
        p.setPen(self.pen(INK, 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(x + 9, y - 10, 12, 14), -90 * 16, 180 * 16)  # handle
        body = QPainterPath()
        body.moveTo(x - 13, y - 14)
        body.lineTo(x + 13, y - 14)
        body.lineTo(x + 10, y + 8)
        body.quadTo(x, y + 12, x - 10, y + 8)
        body.closeSubpath()
        p.setBrush(QColor("#FFFFFF"))
        p.drawPath(body)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#B5713A"))
        p.drawEllipse(QPointF(x, y - 13), 11, 3)
        for i in range(3):  # steam
            k = ((self.t * 0.7) + i / 3) % 1.0
            c = QColor(150, 160, 190)
            c.setAlpha(int(170 * (1 - k)))
            p.setPen(QPen(c, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            sx = x - 6 + i * 6
            sy = y - 20 - k * 28
            path = QPainterPath()
            path.moveTo(sx, sy)
            path.quadTo(sx + 5 * math.sin(k * 6 + i), sy - 6, sx, sy - 12)
            p.drawPath(path)

    def popcorn(self):
        p = self.p
        bucket = QPainterPath()
        bucket.moveTo(150, 140)
        bucket.lineTo(176, 140)
        bucket.lineTo(172, 176)
        bucket.lineTo(154, 176)
        bucket.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFF6D6"))
        for _i, (x, y) in enumerate([(154, 138), (160, 134), (167, 136), (173, 139), (163, 140)]):
            p.drawEllipse(QPointF(x, y), 5, 5)
        p.setPen(self.pen(INK, 2.5))
        p.setBrush(QColor("white"))
        p.drawPath(bucket)
        p.setPen(QPen(QColor("#FF3D5A"), 4))
        p.drawLine(QPointF(158, 142), QPointF(157, 174))
        p.drawLine(QPointF(167, 142), QPointF(168, 174))

    def sign(self):
        p = self.p
        sway = math.sin(self.ts * 4) * 3
        r = QRectF(52 + sway, self.top - 58, 96, 44)
        p.setPen(self.pen(INK, 3))
        p.drawLine(QPointF(70 + sway, r.bottom()), QPointF(60, self.top + 40))
        p.drawLine(QPointF(130 + sway, r.bottom()), QPointF(140, self.top + 40))
        p.setBrush(QColor("#FFE066"))
        p.drawRoundedRect(r, 8, 8)
        f = QFont()
        f.setPointSizeF(22)
        f.setBold(True)
        p.setFont(f)
        p.setPen(INK)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "!")
        self.hand(60, self.top + 40)
        self.hand(140, self.top + 40)

    # ---------- floating props ----------
    def props(self):
        st, t, ts = self.state, self.t, self.ts
        if st == S.SLEEPING:
            for i in range(3):
                k = ((t * 0.5) + i / 3) % 1.0
                self.text(
                    130 + k * 30 + i * 4,
                    self.top + 10 - k * 50,
                    "z" if i < 2 else "Z",
                    10 + i * 4 + k * 4,
                    QColor("#5866D9"),
                    255 * (1 - k),
                )
        elif st == S.AFK:
            k = (t * 0.4) % 1.0
            self.text(140 + k * 10, self.top + 15 - k * 25, "z", 12, QColor("#8890B8"), 220 * (1 - k))
        elif st == S.TYPING_FAST:
            for i in range(2):
                k = ((t * 1.2) + i * 0.5) % 1.0
                x = 150 + i * 8
                y = self.top + 20 + k * 30
                self.drop(x, y, 255 * (1 - k))
            p = self.p
            p.setPen(self.pen(QColor(27, 36, 64, 120), 2))
            for i, dy in enumerate((0, 8, 16)):
                p.drawLine(QPointF(24, 118 + dy), QPointF(36 - i * 3, 118 + dy))
                p.drawLine(QPointF(176, 118 + dy), QPointF(164 + i * 3, 118 + dy))
        elif st in (S.TYPING_SLOW, S.THINK):
            n = int(t * 1.5) % 4
            p = self.p
            p.setPen(self.pen(INK, 2))
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(150, self.top + 4), 4, 4)
            p.drawEllipse(QPointF(160, self.top - 8), 6, 6)
            p.drawRoundedRect(QRectF(150, self.top - 42, 42, 26), 13, 13)
            for i in range(n):
                p.setBrush(INK)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(161 + i * 10, self.top - 29), 2.6, 2.6)
        elif st == S.SCROLLING:
            k = (t * 1.5) % 1.0
            up = int(t * 0.75) % 2 == 0
            self.text(172, 100 + (-k if up else k) * 20, "▲" if up else "▼", 12, INK, 255 * (1 - k))
        elif st == S.WAKING:
            self.text(126, self.top - 4 - min(ts, 0.4) * 20, "!", 26, QColor("#FF3D5A"))
        elif st == S.GIGGLE:
            k = (ts * 1.2) % 1.0
            self.text(132, self.top + 6 - k * 16, "hehe", 11, QColor("#FF5C8A"), 255 * (1 - k * 0.6))
        elif st == S.POKED:
            for i in range(3):
                a = ts * 5 + i * 2.1
                self.text(
                    self.cx - 6 + math.cos(a) * 34,
                    self.top - 6 + math.sin(a) * 8,
                    "✦",
                    11,
                    QColor("#FFB800"),
                    255 * max(0.0, 1 - ts / 1.6),
                )
        elif st == S.BREATHE:
            c = QColor(120, 200, 255)
            c.setAlpha(int(40 + 60 * self.breath))
            self.p.setPen(QPen(c, 3))
            self.p.setBrush(Qt.BrushStyle.NoBrush)
            r = 60 + 22 * self.breath
            self.p.drawEllipse(QPointF(self.cx, self.bottom - self.body_h / 2), r, r * 0.9)
        elif st == S.BREAK:
            self.text(140, self.top + 2, "☕", 14, INK, 200)
        elif st in (S.HAPPY, S.STRETCH):
            for i in range(3):
                k = ((ts * 0.8) + i / 3) % 1.0
                x = 40 + i * 60 + math.sin(k * 6 + i) * 6
                self.text(
                    x,
                    self.top + 10 - k * 40,
                    "♥" if st == S.HAPPY else "✦",
                    12,
                    QColor("#FF5C8A") if st == S.HAPPY else QColor("#FFB800"),
                    255 * (1 - k),
                )

    def drop(self, x, y, alpha):
        p = self.p
        c = QColor("#6EC8FF")
        c.setAlpha(int(alpha))
        path = QPainterPath()
        path.moveTo(x, y - 7)
        path.quadTo(x + 5, y, x, y + 4)
        path.quadTo(x - 5, y, x, y - 7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawPath(path)
