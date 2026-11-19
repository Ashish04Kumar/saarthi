"""Pure timing logic for breaks and guided breathing (no Qt, easy to test)."""

from __future__ import annotations

import math

# one breath: in 4 s, hold 2 s, out 6 s
INHALE, HOLD, EXHALE = 4.0, 2.0, 6.0
CYCLE = INHALE + HOLD + EXHALE


def breath_phase(t: float) -> tuple[str, int, float]:
    """(phase, whole seconds left in this phase, lung level 0..1) at t seconds into the session."""
    k = t % CYCLE
    if k < INHALE:
        x = k / INHALE
        return "in", math.ceil(INHALE - k), x * x * (3 - 2 * x)
    if k < INHALE + HOLD:
        return "hold", math.ceil(INHALE + HOLD - k), 1.0
    x = (k - INHALE - HOLD) / EXHALE
    return "out", math.ceil(CYCLE - k), 1 - x * x * (3 - 2 * x)


def break_due(active_min: float, work_min: float, snoozed_until: float | None, now: float) -> bool:
    if snoozed_until is not None and now < snoozed_until:
        return False
    return active_min >= work_min


class TypingStreak:
    """How long you've been typing more or less non-stop (short pauses are allowed)."""

    def __init__(self, active_kps: float = 0.8, pause_allowed: float = 8.0):
        self.active_kps, self.pause_allowed = active_kps, pause_allowed
        self.seconds = 0.0
        self.quiet = 0.0

    def update(self, kps: float, dt: float) -> float:
        if kps >= self.active_kps:
            self.seconds += dt
            self.quiet = 0.0
        else:
            self.quiet += dt
            if self.quiet > self.pause_allowed:
                self.seconds = 0.0
        return self.seconds

    def reset(self) -> None:
        self.seconds = self.quiet = 0.0


def mmss(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    return f"{s // 60}:{s % 60:02d}"
