"""Reminders, events, quotes and the daily brief, glued to the buddy."""

from __future__ import annotations

import threading
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QInputDialog, QSystemTrayIcon

from .card import Card
from .config import config_dir
from .ical_sync import sync_all
from .scheduler import Scheduler, complete, snooze
from .states import State
from .store import Note, Reminder, Store, dt_to_str, str_to_dt

SYNC_EVERY_MS = 15 * 60_000
QUIET_STATES = {State.SLEEPING, State.AFK, State.TYPING_FAST, State.BREAK, State.BREATHE}


class _SyncSignal(QObject):
    done = Signal(object, object)


class Organizer:
    def __init__(self, buddy):
        self.buddy = buddy
        self.store = Store(config_dir() / "data.json")
        self.scheduler = Scheduler(self.store)
        self.cards: list[Card] = []
        self.manager = None
        self.panel = None
        self._syncing = False
        self._sync_sig = _SyncSignal()
        self._sync_sig.done.connect(self._sync_finished)
        self.store.on_change(self._changed)

        self.timer = QTimer(timeout=self.check)
        self.timer.start(5000)
        self.sync_timer = QTimer(timeout=self.sync_now)
        self.sync_timer.start(SYNC_EVERY_MS)
        QTimer.singleShot(3000, self.sync_now)

    # ---------- periodic ----------
    def check(self):
        now = datetime.now()
        state = self.buddy.sm.state
        for due in self.scheduler.check(now, quiet=state in QUIET_STATES):
            if due.kind == "reminder":
                self.show_reminder(due.obj)
            elif due.kind == "event":
                self.show_event(due.obj)
            elif due.kind == "quote":
                self.buddy.say(due.title)
        self.maybe_brief(now, state)

    def maybe_brief(self, now: datetime, state: State):
        today = now.date().isoformat()
        if self.store.meta.get("last_brief") == today or now.hour < 5 or state in (State.SLEEPING, State.AFK):
            return
        outdoor = getattr(self.buddy, "outdoor", None)
        if outdoor is not None and outdoor.waiting_for_first_weather():
            return
        self.store.meta["last_brief"] = today
        self.store.save(notify=False)
        self.brief_now(now, delay_ms=2500)

    def brief_now(self, now: datetime | None = None, delay_ms: int = 0):
        now = now or datetime.now()
        outdoor = getattr(self.buddy, "outdoor", None)
        items = [(d, t) for d, t in self.scheduler.upcoming(now, 24 - now.hour) if d.date() == now.date()]
        hinglish = self.buddy.cfg["language"] == "hinglish"
        if not items:
            msg = (
                "Good morning! Aaj calendar khaali hai, full focus 💪"
                if hinglish
                else "Good morning! Nothing scheduled today 💪"
            )
            if now.hour >= 12:
                msg = "Aaj ka schedule khaali hai 😎" if hinglish else "Nothing else scheduled today 😎"
        else:
            head = f"Aaj {len(items)} cheez hai:" if hinglish else f"{len(items)} thing(s) today:"
            lines = [f"• {d.strftime('%H:%M') if (d.hour or d.minute) else 'All day'} {t}" for d, t in items[:5]]
            msg = "\n".join([head, *lines])
        weather = outdoor.weather_line() if outdoor is not None else None
        if weather:
            msg = f"{msg}\n{weather}"
        QTimer.singleShot(delay_ms, lambda: self.buddy.say(msg, 11000))

    # ---------- cards ----------
    def _card(self, icon, title, subtitle, actions, on_dismiss=None):
        card = Card(icon, title, subtitle, actions, self._card_closed, on_dismiss)
        self.cards.append(card)
        self._place_cards()
        if getattr(self.buddy, "quiet", False):
            return  # screen sharing: keep it hidden until quiet mode ends
        card.show()
        self.buddy.alert()
        if self.buddy.tray:
            self.buddy.tray.showMessage(
                f"Saarthi: {title}", subtitle or title, QSystemTrayIcon.MessageIcon.Information, 10_000
            )

    def _card_closed(self, card):
        if card in self.cards:
            self.cards.remove(card)
            self._place_cards()

    def _place_cards(self):
        anchor, screen = self.buddy.win.frameGeometry(), self.buddy.screen_rect()
        for i, c in enumerate(self.cards):
            c.place(anchor, screen, i)

    def show_reminder(self, r: Reminder, demo: bool = False):
        when = str_to_dt(r.snooze_until) or str_to_dt(r.next_at)
        sub = f"Due {when.strftime('%H:%M')}" if when else ""
        hinglish = self.buddy.cfg["language"] == "hinglish"
        entry = {"id": None} if demo else self.store.log_fired(r, r.next_at)
        if not demo:
            self.store.save(notify=False)

        def finish(outcome):
            if not demo:
                complete(r, datetime.now())
                self.store.set_outcome(entry["id"], outcome)
                self._resolved(r)
            if outcome == "done":
                self.buddy.say("Shabash! 🎉" if hinglish else "Nice! 🎉")

        def later(minutes):
            if not demo:
                snooze(r, datetime.now(), minutes)
                self._resolved(r)

        self._card(
            "⏰",
            r.title,
            sub,
            [
                ("✓ Ho gaya" if hinglish else "✓ Done", lambda: finish("done")),
                ("✗ Nahi kiya" if hinglish else "✗ Skipped", lambda: finish("missed")),
                ("10m", lambda: later(10)),
                ("1h", lambda: later(60)),
            ],
            on_dismiss=None if demo else (lambda: (complete(r, datetime.now()), self._resolved(r))),
        )
        self.buddy.say(("Yaad hai na? " if hinglish else "Reminder: ") + r.title, priority=2)

    def _resolved(self, r: Reminder):
        self.scheduler.resolved(r)
        self.store.save()

    def show_event(self, e):
        start = str_to_dt(e.start)
        if e.all_day:
            sub = "Today (all day)"
        else:
            mins = int((start - datetime.now()).total_seconds() // 60)
            sub = f"{start.strftime('%H:%M')} · " + (f"in {mins} min" if mins > 0 else "now")
        if e.notes:
            sub += f"\n{e.notes[:80]}"
        self._card("📅", e.title, sub, [("OK", lambda: None)])

    # ---------- calendar sync ----------
    def sync_now(self):
        if self._syncing or not self.store.feeds:
            return
        self._syncing = True
        feeds = [f for f in self.store.feeds if f.enabled]

        def work():
            events, status = sync_all(feeds, datetime.now())
            self._sync_sig.done.emit(events, status)

        threading.Thread(target=work, daemon=True, name="saarthi-ical").start()

    def _sync_finished(self, events, status):
        self._syncing = False
        ok_names = {f.name for f in self.store.feeds if status.get(f.id) == ""}
        # keep old events of feeds that failed this time
        kept = [e for e in self.store.feed_events if e.source not in ok_names]
        self.store.feed_events = kept + events
        now = dt_to_str(datetime.now())
        for f in self.store.feeds:
            if f.id in status:
                f.last_error = status[f.id]
                if not status[f.id]:
                    f.last_sync = now
        self.store.save()

    # ---------- UI ----------
    def open_manager(self, tab: str = "reminders"):
        if self.manager is None:
            from .manager import ManagerWindow

            self.manager = ManagerWindow(self.store, self.sync_now, self.buddy.say, self.buddy)
        self.manager.open(tab)

    def open_panel(self, tab: str = "reminders"):
        if self.panel is None:
            from .quick_panel import QuickPanel

            self.panel = QuickPanel(self.buddy)
        if self.panel.isVisible():
            self.panel.hide()
            return
        self.panel.popup(self.buddy.win.frameGeometry(), self.buddy.screen_rect(), tab)

    def quick_note(self):
        text, ok = QInputDialog.getMultiLineText(None, "Saarthi – Quick note", "Note:")
        if ok and text.strip():
            self.store.notes.append(Note(text=text.strip()))
            self.store.save()
            hinglish = self.buddy.cfg["language"] == "hinglish"
            self.buddy.say("Note save ho gaya 📝" if hinglish else "Note saved 📝")

    def _changed(self):
        if self.manager is not None and self.manager.isVisible():
            self.manager.external_change()

    def stop(self):
        if self.manager is not None:
            self.manager.notes._save()
