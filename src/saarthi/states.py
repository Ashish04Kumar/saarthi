"""Character states and the state machine that picks one from activity.

Pure Python (no Qt) so it is easy to unit-test.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class State(str, Enum):
    IDLE = "idle"
    TYPING_FAST = "typing_fast"
    TYPING_SLOW = "typing_slow"
    SCROLLING = "scrolling"
    WATCHING = "watching"
    AFK = "afk"
    SLEEPING = "sleeping"
    WAKING = "waking"
    HAPPY = "happy"
    STRETCH = "stretch"
    ALERT = "alert"
    POKED = "poked"  # clicked on the head
    GIGGLE = "giggle"  # tickled (clicked on the body)
    BREAK = "break"  # on a break with chai
    BREATHE = "breathe"  # guided breathing
    WALK = "walk"  # walking across the screen (drawn facing right; mirrored for left)
    EAT = "eat"  # lunch
    THINK = "think"  # lost in thought (lunch stroll pauses)


# States that play for a fixed time, then hand back to whatever activity says.
TRANSIENT: dict[State, float] = {
    State.WAKING: 2.5,
    State.HAPPY: 2.5,
    State.STRETCH: 6.0,
    State.ALERT: 8.0,
    State.POKED: 1.6,
    State.GIGGLE: 2.0,
    State.BREAK: 300.0,
    State.BREATHE: 60.0,
}

# If a skin lacks a state, walk this chain until it finds one it has.
FALLBACK: dict[State, State] = {
    State.TYPING_FAST: State.TYPING_SLOW,
    State.TYPING_SLOW: State.IDLE,
    State.SCROLLING: State.IDLE,
    State.WATCHING: State.IDLE,
    State.AFK: State.IDLE,
    State.SLEEPING: State.AFK,
    State.WAKING: State.HAPPY,
    State.STRETCH: State.HAPPY,
    State.ALERT: State.HAPPY,
    State.HAPPY: State.IDLE,
    State.POKED: State.HAPPY,
    State.GIGGLE: State.HAPPY,
    State.BREAK: State.IDLE,
    State.BREATHE: State.STRETCH,
    State.WALK: State.IDLE,
    State.EAT: State.BREAK,
    State.THINK: State.TYPING_SLOW,
}


def resolve(state: State, available: set[State]) -> State:
    seen = set()
    while state not in available and state not in seen and state in FALLBACK:
        seen.add(state)
        state = FALLBACK[state]
    return state if state in available else State.IDLE


@dataclass
class Activity:
    keys_per_sec: float = 0.0
    scrolls_per_sec: float = 0.0
    idle_seconds: float = 0.0
    video_playing: bool = False
    music_playing: bool = False
    media_site: str | None = None  # "youtube", "udemy", ...
    media_tutorial: bool = False
    media_title: str = ""


@dataclass
class Thresholds:
    fast_kps: float = 4.0
    slow_kps: float = 0.3
    scroll_ps: float = 0.8
    afk_after: float = 180.0
    sleep_after: float = 900.0
    video_sleep_after: float = 3600.0  # watching long video with no input is normal
    hold: float = 1.2  # seconds a new state must persist before switching
    video_typing_kps: float = 1.0  # while a video plays, this much typing still counts as typing
    stretch_after_min: float = 10_000.0  # breaks are handled by wellness.py now
    session_reset_idle: float = 300.0


class StateMachine:
    def __init__(self, thresholds: Thresholds | None = None):
        self.th = thresholds or Thresholds()
        self.state = State.IDLE
        self.entered_at = 0.0
        self.preview: State | None = None
        self._candidate: State | None = None
        self._candidate_since = 0.0
        self._transient_until: float | None = None
        self._active_seconds = 0.0
        self._last_update: float | None = None

    @property
    def active_minutes(self) -> float:
        return self._active_seconds / 60.0

    def classify(self, a: Activity) -> State:
        th = self.th
        if a.video_playing:
            if a.idle_seconds >= th.video_sleep_after:
                return State.SLEEPING
            if a.keys_per_sec < th.video_typing_kps:  # real typing beats a video playing in the background
                return State.WATCHING
        if a.idle_seconds >= th.sleep_after:
            return State.SLEEPING
        if a.idle_seconds >= th.afk_after:
            return State.AFK
        if a.keys_per_sec >= th.fast_kps:
            return State.TYPING_FAST
        if a.keys_per_sec >= th.slow_kps:
            return State.TYPING_SLOW
        if a.scrolls_per_sec >= th.scroll_ps:
            return State.SCROLLING
        return State.IDLE

    def trigger(self, state: State, now: float, duration: float | None = None) -> State:
        """Force a transient state (e.g. ALERT when a reminder fires)."""
        self._enter(state, now)
        self._transient_until = now + (duration or TRANSIENT.get(state, 3.0))
        return state

    def update(self, a: Activity, now: float) -> State:
        dt = 0.0 if self._last_update is None else max(0.0, now - self._last_update)
        self._last_update = now
        if a.idle_seconds < 60:
            self._active_seconds += dt
        elif a.idle_seconds >= self.th.session_reset_idle:
            self._active_seconds = 0.0

        if self.preview is not None:
            return self.preview

        target = self.classify(a)
        resting = (State.AFK, State.SLEEPING)

        if self._transient_until is not None:
            if now < self._transient_until:
                return self.state
            self._transient_until = None

        if self.state in resting and target not in resting:
            return self.trigger(State.WAKING, now)

        if self._active_seconds >= self.th.stretch_after_min * 60 and target not in resting:
            self._active_seconds = 0.0
            return self.trigger(State.STRETCH, now)

        if target == self.state:
            self._candidate = None
            return self.state
        if target != self._candidate:
            self._candidate = target
            self._candidate_since = now
        hold = 0.0 if target in resting else self.th.hold
        if now - self._candidate_since >= hold:
            self._enter(target, now)
        return self.state

    @property
    def busy(self) -> bool:
        """In a break or breathing session (don't interrupt with other transients)."""
        return self.state in (State.BREAK, State.BREATHE, State.EAT, State.THINK) and self._transient_until is not None

    def end_transient(self, now: float) -> None:
        self._transient_until = None
        self._enter(State.IDLE, now)

    def extend_transient(self, until: float) -> None:
        """Change when the current session ends (e.g. lunch made longer)."""
        if self._transient_until is not None:
            self._transient_until = until

    def reset_active(self) -> None:
        self._active_seconds = 0.0

    def _enter(self, state: State, now: float) -> None:
        self.state = state
        self.entered_at = now
        self._candidate = None
