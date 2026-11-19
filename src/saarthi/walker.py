"""Walking: random strolls across the bottom of the screen, and pacing during breaks."""

from __future__ import annotations

import random
import time

from PySide6.QtCore import QTimer

from .states import State

STEP_MS = 33
STROLL_STATES = {State.IDLE, State.HAPPY}


class Walker:
    def __init__(self, buddy):
        self.buddy = buddy
        self.win = buddy.win
        self.cfg = buddy.cfg
        self.target: float | None = None
        self.x = 0.0
        self._last = 0.0
        self._arrive = None
        self.home: tuple[int, int] | None = None
        self.pacing = False
        self.factor = 1.0  # walking speed multiplier (lunch strolls are slow)
        self.pace_factor = 1.0
        self.pause_range = (6.0, 12.0)
        self.on_pause = None  # called each time a pacing walk stops (e.g. to think out loud)
        self.step_timer = QTimer(timeout=self._step)
        self.pause_timer = QTimer(singleShot=True, timeout=self._pace_next)
        self.stroll_timer = QTimer(timeout=self._maybe_stroll)
        self.stroll_timer.start(15_000)
        self.win.grabbed.connect(self.cancel)

    @property
    def walking(self) -> bool:
        return self.target is not None

    def speed(self) -> float:
        return self.win.height() * 0.38 * self.factor  # px per second, scales with buddy size

    def _bounds(self) -> tuple[int, int]:
        g = self.buddy.screen_rect()
        return g.left() + 10, g.right() - self.win.width() - 10

    # ---------- moving ----------
    def walk_to(self, x: float, on_arrive=None, factor: float = 1.0) -> None:
        lo, hi = self._bounds()
        x = max(lo, min(hi, x))
        self.x = float(self.win.x())
        if abs(x - self.x) < 4:
            if on_arrive:
                on_arrive()
            return
        self.target, self._arrive, self.factor = x, on_arrive, factor
        self._last = time.monotonic()
        self.win.set_override(State.WALK, mirror=x < self.x, speed=factor)
        self.step_timer.start(STEP_MS)

    def walk_random(self, on_arrive=None, factor: float = 1.0) -> None:
        lo, hi = self._bounds()
        cur = self.win.x()
        for _ in range(10):
            x = random.uniform(lo, hi)
            if abs(x - cur) > self.win.width() * 1.2:
                break
        self.walk_to(x, on_arrive, factor)

    def _step(self) -> None:
        now = time.monotonic()
        dt, self._last = now - self._last, now
        if self.target is None:
            return
        d = self.target - self.x
        move = self.speed() * dt
        if abs(d) <= move:
            self.x = self.target
        else:
            self.x += move if d > 0 else -move
        self.win.move(int(self.x), self.win.y())
        self.win.moved.emit()
        if self.x == self.target:
            self._stop_moving()
            cb, self._arrive = self._arrive, None
            if cb:
                cb()

    def _stop_moving(self) -> None:
        self.step_timer.stop()
        self.target = None
        self.win.set_override(None)

    def cancel(self) -> None:
        """User grabbed the buddy: stop walking right away."""
        if self.walking:
            self._stop_moving()
            self._arrive = None
        self.pause_timer.stop()
        if self.pacing:
            self.pacing = False
            self.home = None  # they placed it somewhere on purpose

    # ---------- random strolls ----------
    def _maybe_stroll(self) -> None:
        if not self.cfg["walk_enabled"] or self.walking or self.pacing or getattr(self.buddy, "quiet", False):
            return
        sm = self.buddy.sm
        if sm.busy or sm.preview is not None or sm.state not in STROLL_STATES:
            return
        org = self.buddy.org
        if self.buddy.wellness.active or org.cards or (org.panel is not None and org.panel.isVisible()):
            return  # don't wander off while something is open next to the buddy
        if not self.win.isVisible():
            return
        if random.random() < 0.18:  # roughly every couple of minutes while you're idle
            self.walk_random(on_arrive=self.buddy.save_position)

    # ---------- breaks ----------
    def start_pacing(self, factor: float = 1.0, pause: tuple[float, float] = (6.0, 12.0), on_pause=None) -> None:
        if not self.pacing:
            self.home = (self.win.x(), self.win.y())
        self.pacing = True
        self.pace_factor, self.pause_range, self.on_pause = factor, pause, on_pause
        self._pace_next()

    def _pace_next(self) -> None:
        if not self.pacing:
            return
        self.walk_random(on_arrive=self._paused, factor=self.pace_factor)

    def _paused(self) -> None:
        if not self.pacing:
            return
        if self.on_pause:
            self.on_pause()
        self.pause_timer.start(int(random.uniform(*self.pause_range) * 1000))

    def stop_pacing(self) -> None:
        self.pacing = False
        self.on_pause = None
        self.pause_timer.stop()
        if self.home is not None:
            hx, _ = self.home
            self.home = None
            self.walk_to(hx, on_arrive=self.buddy.save_position)
        elif self.walking:
            self._stop_moving()
