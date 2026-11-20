"""Break reminders and guided breathing, done together with the buddy."""

from __future__ import annotations

import random
from datetime import datetime

from PySide6.QtCore import QTimer

from . import clock
from .lines import line_for
from .states import State
from .wellness_logic import CYCLE, TypingStreak, break_due, breath_phase, mmss

NO_INTERRUPT = {State.SLEEPING, State.AFK, State.TYPING_FAST, State.WATCHING}
SKIP_BREAK_AFTER = 45.0  # seconds of typing during a break = something important, cancel it
SKIP_BREATHE_AFTER = 10.0
BREAK_SNOOZE_MIN = 15


class Wellness:
    def __init__(self, buddy):
        self.buddy = buddy
        self.cfg = buddy.cfg
        self.mode: str | None = None  # None / "break" / "breathe" / "lunch"
        self.eat_until = 0.0
        self.lunch_asked = False
        self.started = 0.0
        self.ends = 0.0
        self.offer_open = False
        self.break_snooze: float | None = None
        self.last_nag = 0.0
        self._last_text = ""
        self.streak = TypingStreak()
        self._last_tick = clock.now()
        self.next_breath = clock.now() + self._breath_gap()
        self.timer = QTimer(timeout=self.tick)
        self.timer.start(500)

    # ---------- helpers ----------
    def _line(self, key: str, **kw) -> str:
        text = line_for(key, self.cfg["language"]) or ""
        return text.format(**kw) if kw else text

    def _breath_gap(self) -> float:
        lo, hi = self.cfg["breathing_every"]
        return random.uniform(lo, hi) * 60

    @property
    def active(self) -> bool:
        return self.mode is not None

    def _show(self, text: str):
        if text != self._last_text or not self.buddy.bubble.isVisible():
            self._last_text = text
            self.buddy.say_shared(text, 2500, force=True)

    # ---------- loop ----------
    def tick(self):
        now = clock.now()
        dt, self._last_tick = now - self._last_tick, now
        sm = self.buddy.sm
        if self.mode is not None:
            a = getattr(self.buddy, "activity", None)
            typing = self.streak.update(a.keys_per_sec if a is not None else 0.0, dt)
            if self.mode == "break" and typing >= SKIP_BREAK_AFTER:
                self.skip_break()
                return
            if self.mode == "breathe" and typing >= SKIP_BREATHE_AFTER:
                self.skip_breathe()
                return
            if self.mode == "lunch" and typing >= SKIP_BREAK_AFTER and not self.lunch_asked:
                self.ask_lunch_over()
        if self.mode == "lunch":
            self._lunch_tick(now)
            return
        if self.mode == "break":
            left = self.ends - now
            if left <= 0:
                self.end_break()
                return
            a = getattr(self.buddy, "activity", None)
            if a is not None and a.keys_per_sec > 1.5 and now - self.last_nag > 60:
                self.last_nag = now
                self.buddy.say_shared(self._line("break_nag"), 3000, force=True)
                return
            if now - self.last_nag > 4:
                self._show(f"☕ Break  {mmss(left)}")
            return
        if self.mode == "breathe":
            t = now - self.started
            if now >= self.ends:
                self.end_breathe()
                return
            phase, n, _ = breath_phase(t)
            cycle = int(t // CYCLE) + 1
            total = int(round((self.ends - self.started) / CYCLE))
            self._show(f"{self._line('breathe_' + phase, n=n)}   ({cycle}/{total})")
            return
        if self.offer_open or self.buddy.sm.preview is not None or getattr(self.buddy, "quiet", False):
            return
        if (
            self.cfg["break_enabled"]
            and sm.state not in (State.SLEEPING, State.AFK)
            and break_due(sm.active_minutes, float(self.cfg["work_minutes"]), self.break_snooze, now)
        ):
            self.offer_break()
        elif self.cfg["breathing_enabled"] and now >= self.next_breath:
            if sm.state in NO_INTERRUPT:
                self.next_breath = now + 5 * 60  # try again a bit later
            else:
                self.offer_breathe()

    # ---------- breaks ----------
    def offer_break(self):
        self.offer_open = True
        work, brk = int(self.cfg["work_minutes"]), int(self.cfg["break_minutes"])
        hinglish = self.cfg["language"] == "hinglish"
        text = self._line("break_offer", work=work, brk=brk)
        self.buddy.say_shared(text, 6000, force=True)

        def later():
            self.offer_open = False
            self.break_snooze = clock.now() + 10 * 60

        self.buddy.org._card(
            "☕",
            text,
            "",
            [
                ("Break lo ☕" if hinglish else "Take a break ☕", self._accept_break),
                ("10 min baad" if hinglish else "In 10 min", later),
            ],
            on_dismiss=later,
        )

    def _accept_break(self):
        self.offer_open = False
        self.start_break()

    def start_break(self, minutes: float | None = None):
        self.stop(quiet=True)
        now = clock.now()
        dur = 60 * float(minutes or self.cfg["break_minutes"])
        self.mode, self.started, self.ends = "break", now, now + dur
        self.streak.reset()
        self.buddy.sm.trigger(State.BREAK, now, dur + 1)
        self.buddy.win.set_state(State.BREAK, now)
        self.buddy.say_shared(self._line("break_start", brk=int(round(dur / 60))), 4000, force=True)
        self.last_nag = now  # let the start line stay up for a moment
        self.buddy.walker.start_pacing()

    # ---------- lunch ----------
    @property
    def status(self) -> str:
        """working / break / lunch / breathe"""
        return self.mode or "working"

    def set_status(self, status: str):
        if status == self.status:
            return
        if status == "working":
            self.stop()
        elif status == "break":
            self.start_break()
        elif status == "lunch":
            self.start_lunch()

    def start_lunch(self, minutes: float | None = None):
        self.stop(quiet=True)
        self.buddy.walker.cancel()
        now = clock.now()
        dur = 60 * float(minutes or self.cfg["lunch_minutes"])
        self.mode, self.started, self.ends = "lunch", now, now + dur
        self.eat_until = now + min(dur * 0.6, random.uniform(10, 15) * 60)  # eat first, then stroll
        self.streak.reset()
        self.lunch_asked = False
        self.buddy.sm.trigger(State.EAT, now, dur + 1)
        self.buddy.win.set_state(State.EAT, now)
        self.buddy.say_shared(self._line("lunch_start"), 4000, force=True)
        self.last_nag = now

    def _lunch_tick(self, now: float):
        left = self.ends - now
        if left <= 0:
            self.end_lunch()
            return
        if self.buddy.sm.state == State.EAT and now >= self.eat_until:
            self._lunch_stroll(now)
            return
        if now - self.last_nag > 4:
            self._show(f"🍱 Lunch  {mmss(left)}")

    def _lunch_stroll(self, now: float):
        """Done eating: slow walks with little thinking stops in between."""
        self.buddy.sm.trigger(State.THINK, now, self.ends - now + 1)
        self.buddy.win.set_state(State.THINK, now)
        self.buddy.say_shared(self._line("lunch_walk"), 4000, force=True)
        self.last_nag = now
        self.buddy.walker.start_pacing(factor=0.55, pause=(15, 30), on_pause=self._think_out_loud)

    def _think_out_loud(self):
        if self.mode != "lunch":
            return
        now = clock.now()
        self.buddy.win.set_state(State.THINK, now)
        self.buddy.say_shared(self._line("think"), 4500, force=True)
        self.last_nag = now  # keep the thought up before the countdown returns

    def set_remaining(self, minutes: float):
        """Change how long the running break/lunch has left."""
        if self.mode not in ("break", "lunch"):
            return
        now = clock.now()
        self.ends = now + 60 * float(minutes)
        if self.mode == "lunch":
            self.eat_until = min(self.eat_until, self.ends)
        self.buddy.sm.extend_transient(self.ends + 1)
        self._last_text = ""

    def ask_lunch_over(self):
        self.lunch_asked = True
        hinglish = self.cfg["language"] == "hinglish"

        def not_yet():
            self.streak.reset()
            QTimer.singleShot(10 * 60_000, lambda: setattr(self, "lunch_asked", False))

        self.buddy.org._card(
            "🍱",
            self._line("lunch_back"),
            "",
            [
                ("Haan, kaam pe 💻" if hinglish else "Yes, back to work 💻", self.end_lunch),
                ("Abhi nahi" if hinglish else "Not yet", not_yet),
            ],
            on_dismiss=not_yet,
        )

    def end_lunch(self):
        if self.mode != "lunch":
            return
        self.mode = None
        self.buddy.walker.stop_pacing()
        now = clock.now()
        self.buddy.sm.end_transient(now)
        self.buddy.sm.reset_active()  # lunch counts as a real break
        self.break_snooze = None
        self.buddy.org.store.meta["last_lunch"] = datetime.now().date().isoformat()
        self.buddy.sm.trigger(State.HAPPY, now)
        self.buddy.win.set_state(State.HAPPY, now)
        self.buddy.say_shared(self._line("lunch_end"), 5000, force=True)

    def skip_break(self):
        """You kept typing through the break: it's important, so cancel and ask again later."""
        self.mode = None
        self.streak.reset()
        self.buddy.walker.stop_pacing()
        now = clock.now()
        self.buddy.sm.end_transient(now)
        self.break_snooze = now + BREAK_SNOOZE_MIN * 60  # active time is NOT reset
        self.buddy.say_shared(self._line("break_skip", snooze=BREAK_SNOOZE_MIN), 6000, force=True)

    def skip_breathe(self):
        self.mode = None
        self.streak.reset()
        now = clock.now()
        self.buddy.sm.end_transient(now)
        self.next_breath = now + 30 * 60
        self.buddy.say_shared(self._line("breathe_skip"), 4000, force=True)

    def end_break(self):
        self.mode = None
        self.buddy.walker.stop_pacing()
        now = clock.now()
        self.buddy.sm.end_transient(now)
        self.buddy.sm.reset_active()
        self.break_snooze = None
        self.buddy.sm.trigger(State.HAPPY, now)
        self.buddy.win.set_state(State.HAPPY, now)
        self.buddy.say_shared(self._line("break_end"), 5000, force=True)

    # ---------- breathing ----------
    def offer_breathe(self):
        self.offer_open = True
        hinglish = self.cfg["language"] == "hinglish"
        text = self._line("breathe_offer")
        self.buddy.say_shared(text, 6000, force=True)

        def later():
            self.offer_open = False
            self.next_breath = clock.now() + 30 * 60

        self.buddy.org._card(
            "🧘",
            text,
            "~1 min · 4s andar, 2s roko, 6s bahar" if hinglish else "~1 min · in 4s, hold 2s, out 6s",
            [
                ("Chalo 🧘" if hinglish else "Let's go 🧘", self._accept_breathe),
                ("Baad me" if hinglish else "Later", later),
            ],
            on_dismiss=later,
        )

    def _accept_breathe(self):
        self.offer_open = False
        self.start_breathe()

    def start_breathe(self):
        self.stop(quiet=True)
        self.buddy.walker.cancel()  # stand still to breathe
        now = clock.now()
        dur = CYCLE * int(self.cfg["breathing_cycles"])
        self.mode, self.started, self.ends = "breathe", now, now + dur
        self.streak.reset()
        self.buddy.sm.trigger(State.BREATHE, now, dur + 1)
        self.buddy.win.set_state(State.BREATHE, now)

    def end_breathe(self):
        self.mode = None
        now = clock.now()
        self.next_breath = now + self._breath_gap()
        self.buddy.sm.end_transient(now)
        self.buddy.sm.trigger(State.HAPPY, now)
        self.buddy.win.set_state(State.HAPPY, now)
        self.buddy.say_shared(self._line("breathe_end"), 5000, force=True)

    def stop(self, quiet: bool = False):
        """End whatever session is running (menu: End break / breathing)."""
        if self.mode is None:
            return
        if quiet:
            if self.mode in ("break", "lunch"):
                self.buddy.walker.stop_pacing()
            self.mode = None
            self.buddy.sm.end_transient(clock.now())
        elif self.mode == "break":
            self.end_break()
        elif self.mode == "lunch":
            self.end_lunch()
        else:
            self.end_breathe()
