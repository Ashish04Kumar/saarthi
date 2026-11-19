"""Wires everything together: window, bubble, tray, state machine, chatter."""

from __future__ import annotations

import random
import time

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import skin as skins
from .activity import DemoSource, LiveSource, NullSource
from .bubble import Bubble
from .config import Config, config_dir
from .lines import LANGUAGES, line_for
from .organizer import Organizer
from .outdoor import Outdoor
from .states import TRANSIENT, State, StateMachine
from .walker import Walker
from .wellness import Wellness
from .window import BuddyWindow

SIZES = {"Small": 110, "Medium": 160, "Large": 220, "Huge": 300}
CHATTY = {State.TYPING_FAST, State.WATCHING, State.WAKING, State.STRETCH, State.SCROLLING}
AUTO_LINE_GAP = 60.0  # seconds between unprompted state-change lines
# What the character does while you watch: a study video gets notes / hand-on-chin / trying the code,
# anything else gets popcorn / a laugh / a cold drink. It switches between them every so often.
STUDY_TAKES = ("notes", "chin", "try")
FUN_TAKES = ("popcorn", "laugh", "sip")
TAKE_SECONDS = (25.0, 50.0)


def pick_watch_take(study: bool, available: set[str], current: str | None = None) -> str | None:
    """A watching animation that suits the video, different from the current one when possible."""
    pool = [v for v in (STUDY_TAKES if study else FUN_TAKES) if v in available]
    if not pool:
        return None
    return random.choice([v for v in pool if v != current] or pool)


# How important a line is. A line never cuts off a more important one that's still showing:
# it waits its turn (LOW lines are simply skipped instead of waiting).
LOW, NORMAL, HIGH = 0, 1, 2
STATUSES = [("working", "💻 Working"), ("break", "☕ Break"), ("lunch", "🍱 Lunch")]


class Saarthi:
    def __init__(self, app: QApplication, demo: bool = False):
        self.app = app
        self.cfg = Config()
        self.skin = skins.load(self.cfg["skin"])
        from . import theme

        theme.MODE = self.cfg["theme"]
        self.sm = StateMachine()
        self.demo = demo
        self.source = self.make_source(demo)
        self.last_line_at = 0.0
        self.music_was_playing = False
        self.status_dialog = None
        app.aboutToQuit.connect(self.shutdown)

        from . import CREDIT

        self.win = BuddyWindow(self.skin, self.cfg["size"], credit=None if self.cfg["developer"] else CREDIT)
        self.bubble = Bubble()
        self._bubble_prio = LOW
        self._speech: list[tuple[str, int | None, int]] = []
        self.bubble.closed.connect(self._next_line)
        self.win.clicked.connect(self.on_click)
        self.win.double_clicked.connect(lambda: self.org.open_panel())
        self.win.moved.connect(self.follow_bubble)
        self.win.drag_finished.connect(self.save_position)
        self.win.context_menu.connect(self.show_menu)

        self.org = Organizer(self)
        self.outdoor = Outdoor(self)
        self.walker = Walker(self)
        from .onboarding import Onboarding

        self.onboarding = Onboarding(self)
        self.wellness = Wellness(self)
        from .laptop_react import LaptopReactions

        self.laptop = LaptopReactions(self)
        self._sim: tuple | None = None  # (Activity, until) from the Try menu
        self._watch: tuple[bool, float] | None = None  # (study video?, switch take at) while watching
        self._clicks: list[float] = []
        self.quiet = False  # screen-share mode: small, in a corner, no pop-ups
        self._quiet_saved: tuple | None = None
        self.menu = QMenu()
        self.build_menu()
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.make_icon())
            self.tray.setToolTip("Saarthi")
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(self.on_tray)
            self.tray.show()

        self.place_window()
        self.win.show()

        self.tick_timer = QTimer(timeout=self.tick)
        self.tick_timer.start(250)
        self.chatter_timer = QTimer(singleShot=True, timeout=self.chatter)
        self.schedule_chatter()
        if self.cfg.data.get("welcomed"):
            QTimer.singleShot(800, lambda: self.say(line_for(State.WAKING, self.cfg["language"])))

    # ---------- loop ----------
    def tick(self):
        now = time.monotonic()
        before = self.sm.state
        activity = self.source.read(now)
        if self._sim is not None:
            if now < self._sim[1]:
                activity = self._sim[0]
            else:
                self._sim = None
        self.activity = activity
        state = self.sm.update(activity, now)
        music_started = activity.music_playing and not self.music_was_playing
        if music_started and now - self.last_line_at > AUTO_LINE_GAP and random.random() < 0.5:
            self.say(line_for("music", self.cfg["language"]), priority=LOW)
        self.music_was_playing = activity.music_playing
        self.win.set_state(state, self.sm.entered_at if self.sm.preview is None else self.win.state_started)
        self._update_watch_take(state, activity, now)
        if state != before and self.sm.preview is None:
            self.on_state_change(state, now)

    def _update_watch_take(self, state: State, activity, now: float) -> None:
        if state != State.WATCHING:
            self._watch = None
            return
        study = bool(activity.media_tutorial)
        if self._watch is None or self._watch[0] != study or now >= self._watch[1]:
            take = pick_watch_take(study, self.skin.variants(State.WATCHING), self.win.variant(State.WATCHING))
            self.win.set_variant(State.WATCHING, take)
            self._watch = (study, now + random.uniform(*TAKE_SECONDS))

    def on_state_change(self, state: State, now: float):
        chatty = state in CHATTY and now - self.last_line_at > AUTO_LINE_GAP
        if state in TRANSIENT or (chatty and random.random() < 0.6):
            self.say(line_for(self.line_key(state), self.cfg["language"]), priority=LOW)

    def line_key(self, state: State):
        a = getattr(self, "activity", None)
        if state == State.WATCHING and a is not None:
            if a.media_site in ("udemy", "youtube") and not (a.media_site == "youtube" and a.media_tutorial):
                return f"watching:{a.media_site}"
            if a.media_tutorial:
                return "watching:tutorial"
        return state

    def chatter(self):
        if self.sm.state not in (State.SLEEPING, State.TYPING_FAST) and not self.wellness.active:
            self.say(line_for("random", self.cfg["language"]), priority=LOW)
        self.schedule_chatter()

    def schedule_chatter(self):
        lo, hi = self.cfg["chatter_minutes"]
        self.chatter_timer.start(int(random.uniform(lo, hi) * 60_000))

    # ---------- speech ----------
    def say(self, text: str | None, ms: int | None = None, force: bool = False, priority: int | None = None):
        """Show a line. force = part of a session / direct reply to the user (HIGH priority)."""
        if not text or not (self.cfg["bubbles"] or force) or self.quiet:
            return
        prio = priority if priority is not None else (HIGH if force else NORMAL)
        if not force and getattr(self, "wellness", None) is not None and self.wellness.active:
            return  # don't cover the break / breathing countdown
        if self.bubble.isVisible() and self.bubble.remaining_ms() > 300 and self._bubble_prio > prio:
            if prio > LOW and all(t != text for t, _, _ in self._speech):
                self._speech.append((text, ms, prio))
                del self._speech[:-4]  # keep the queue short
            return
        self._show_line(text, ms, prio)

    def _show_line(self, text: str, ms: int | None, prio: int):
        self.last_line_at = time.monotonic()
        self._bubble_prio = prio
        self.bubble.say(text, self.win.body_rect(), self.screen_rect(), ms)

    def _next_line(self):
        self._bubble_prio = LOW
        if not self._speech or not self.win.isVisible():
            self._speech.clear()
            return
        best = max(range(len(self._speech)), key=lambda i: self._speech[i][2])  # most important, oldest first
        text, ms, prio = self._speech.pop(best)
        QTimer.singleShot(400, lambda: self._show_line(text, ms, prio))

    def follow_bubble(self):
        self.bubble.follow(self.win.body_rect(), self.screen_rect())
        self.org._place_cards()

    def screen_rect(self):
        scr = self.win.screen() or self.app.primaryScreen()
        return scr.availableGeometry()

    # ---------- interaction ----------
    def on_click(self, part: str = "body"):
        """Single click: poke the head, tickle the belly, step on the shoes, tug the jeans,
        or annoy it by clicking a lot."""
        if self.quiet:
            return  # stays still while you share your screen
        now = time.monotonic()
        self.win.squash()
        lang = self.cfg["language"]
        if self.wellness.active:
            msg = {
                "break": "Break chal raha hai ☕ (double-click → 💻 Working)",
                "lunch": "Lunch chal raha hai 🍱 (double-click → 💻 Working)",
            }.get(self.wellness.mode, "Saath me saans lo 🧘 (right-click → Status → Working)")
            self.say(msg if lang == "hinglish" else "Session running (Status → Working to stop)", 2500, force=True)
            return
        self._clicks = [c for c in self._clicks if now - c < 3] + [now]
        take = None
        if len(self._clicks) >= 4:
            state, key = State.POKED, "dizzy"
            self._clicks.clear()
        elif part in ("boots", "jeans"):
            state, key, take = State.POKED, part, part
        elif part == "head":
            state, key = State.POKED, "poked"
        else:
            state, key = State.GIGGLE, "giggle"
        if self.sm.preview is None:
            self.sm.trigger(state, now)
            self.win.set_state(state, now)
            self.win.set_variant(State.POKED, take)
        self.say(line_for(key, lang), 2500, priority=HIGH)

    def toggle_status(self, key: str) -> bool:
        """Pick a status; picking the current one again goes back to Working.
        Break and lunch first ask how many minutes. Returns False if cancelled."""
        if key == self.wellness.status and key != "working":
            key = "working"
        if key in ("break", "lunch"):
            from .duration_dialog import DurationDialog

            cfg_key = f"{key}_minutes"
            answer = DurationDialog.ask(key, int(self.cfg[cfg_key]))
            if answer is None:
                self._sync_status_menu()
                return False
            minutes, make_default = answer
            if make_default:
                self.cfg[cfg_key] = minutes
            (self.wellness.start_lunch if key == "lunch" else self.wellness.start_break)(minutes)
            return True
        self.wellness.set_status(key)
        return True

    def change_session_time(self):
        """Running break/lunch: set new minutes left."""
        w = self.wellness
        if w.mode not in ("break", "lunch"):
            return
        from .duration_dialog import DurationDialog

        left = max(1, round((w.ends - time.monotonic()) / 60))
        answer = DurationDialog.ask(w.mode, left, editing=True)
        if answer is not None:
            w.set_remaining(answer[0])

    def _sync_status_menu(self):
        cur = self.wellness.status
        for key, a in getattr(self, "status_actions", {}).items():
            a.setChecked(key == cur)

    def show_about(self):
        from PySide6.QtWidgets import QMessageBox

        from . import AUTHOR, AUTHOR_EMAIL, __version__

        QMessageBox.about(
            None,
            "About Saarthi",
            f"<b>Saarthi {__version__}</b><br>Your animated desktop companion.<br><br>"
            f"Developer: <b>{AUTHOR}</b><br><a href='mailto:{AUTHOR_EMAIL}'>{AUTHOR_EMAIL}</a><br>"
            "<a href='https://github.com/Ashish04Kumar/saarthi'>github.com/Ashish04Kumar/saarthi</a>",
        )

    def wake_from_launcher(self):
        """Launched again from the app menu while already running: just come forward."""
        self.win.show()
        self.win.raise_()
        self.say("Main yahin hoon! 👋" if self.cfg["language"] == "hinglish" else "I'm right here! 👋", force=True)

    def set_quiet(self, on: bool):
        """Screen-share mode: shrink into a corner and stay silent; turning it off restores everything."""
        if on == self.quiet:
            return
        self.quiet = on
        org = self.org
        if on:
            self._quiet_saved = (self.win.pos(), self.cfg["size"])
            self.walker.cancel()
            self._speech.clear()
            self.bubble.hide()
            if org.panel is not None:
                org.panel.hide()
            for c in org.cards:
                c.hide()
            self.win.set_size(90)
            g = self.screen_rect()
            self.win.move(g.right() - self.win.width() - 6, g.bottom() - self.win.height() - 2)
            self.win.set_override(State.IDLE)
        else:
            pos, size = self._quiet_saved or (self.win.pos(), self.cfg["size"])
            self.win.set_size(size)
            self.win.move(pos)
            self.win.set_override(None)
            for c in org.cards:
                c.show()
            org._place_cards()
            self.say("Wapas aa gaya! 👋" if self.cfg["language"] == "hinglish" else "I'm back! 👋", priority=HIGH)
        if hasattr(self, "quiet_action"):
            self.quiet_action.setChecked(on)

    def alert(self):
        if self.quiet:
            return
        now = time.monotonic()
        if self.sm.preview is None and not self.sm.busy:
            self.sm.trigger(State.ALERT, now)
            self.win.set_state(State.ALERT, now)

    def shutdown(self):
        self.source.stop()
        self.laptop.stop()
        self.org.stop()

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def toggle_visible(self):
        if self.win.isVisible():
            self.win.hide()
            self.bubble.hide()
        else:
            self.win.show()
            self.win.raise_()

    def show_menu(self, pos: QPoint):
        self.menu.popup(pos)

    # ---------- placement ----------
    def place_window(self):
        pos = self.cfg["position"]
        screens = [s.availableGeometry() for s in self.app.screens()]
        if pos and any(g.contains(QPoint(*pos)) for g in screens):
            self.win.move(*pos)
            return
        g = self.app.primaryScreen().availableGeometry()
        self.win.move(g.right() - self.win.width() - 40, g.bottom() - self.win.height() - 20)

    def save_position(self):
        p = self.win.pos()
        self.cfg["position"] = [p.x(), p.y()]

    # ---------- menu ----------
    def build_menu(self):
        m = self.menu
        m.clear()
        m.addAction("Reminders && notes (double-click)", lambda: self.org.open_panel())
        m.addAction("Open Saarthi…", lambda: self.org.open_manager())
        m.addAction("Quick note…", lambda: self.org.quick_note())
        m.addAction("Add reminder…", lambda: self.org.open_manager("reminders"))
        m.addAction("Calendar…", lambda: self.org.open_manager("calendar"))
        m.addAction("Weather now", lambda: self.outdoor.say_weather())
        m.addAction("Traffic to home now", lambda: self.outdoor.commute_now())
        m.addAction("Settings…", lambda: self.org.open_manager("settings"))
        m.addSeparator()
        status = m.addMenu("Status")
        sg = QActionGroup(status)
        self.status_actions = {}
        for key, label in STATUSES:
            a = QAction(label, status, checkable=True)
            a.triggered.connect(lambda _=False, k=key: self.toggle_status(k))
            sg.addAction(a)
            status.addAction(a)
            self.status_actions[key] = a
        status.aboutToShow.connect(self._sync_status_menu)
        m.aboutToShow.connect(self._sync_status_menu)
        m.addAction("Breathing exercise now 🧘", lambda: self.wellness.start_breathe())
        self.quiet_action = QAction("🤫 Quiet mode (screen share)", m, checkable=True)
        self.quiet_action.toggled.connect(self.set_quiet)
        m.addAction(self.quiet_action)
        m.addSeparator()
        m.addAction("Show / Hide", self.toggle_visible)
        m.addAction("Say something", lambda: self.say(line_for("random", self.cfg["language"])))
        m.addAction("What I see…", self.show_status)
        m.addAction("Fix typing detection…", lambda: self.onboarding.show_help())
        m.addSeparator()

        preview = m.addMenu("Preview animation")
        group = QActionGroup(preview)
        auto = QAction("Auto (follow my activity)", preview, checkable=True, checked=True)
        auto.triggered.connect(lambda: self.set_preview(None))
        group.addAction(auto)
        preview.addAction(auto)
        preview.addSeparator()
        for st in State:
            a = QAction(st.value.replace("_", " ").title(), preview, checkable=True)
            a.triggered.connect(lambda _=False, s=st: self.set_preview(s))
            group.addAction(a)
            preview.addAction(a)

        demo = QAction("Demo mode (cycle activities)", m, checkable=True, checked=self.demo)
        demo.toggled.connect(self.set_demo)
        m.addAction(demo)
        self.build_try_menu(m.addMenu("🧪 Try features"))
        walk = QAction("Walking mode (strolls around)", m, checkable=True, checked=bool(self.cfg["walk_enabled"]))
        walk.toggled.connect(lambda v: self.cfg.__setitem__("walk_enabled", v))
        m.addAction(walk)
        lap = QAction(
            "Laptop alerts (battery, heat, internet…)", m, checkable=True, checked=bool(self.cfg["laptop_alerts"])
        )
        lap.toggled.connect(lambda v: (self.cfg.__setitem__("laptop_alerts", v), self.laptop.refresh_looks(0)))
        m.addAction(lap)
        from .system import autostart_enabled, set_autostart

        boot = QAction("Start with my computer", m, checkable=True, checked=autostart_enabled())
        boot.toggled.connect(set_autostart)
        m.addAction(boot)
        m.addSeparator()

        skin_menu = m.addMenu("Character")
        sg = QActionGroup(skin_menu)
        for sid, name in skins.discover(config_dir()).items():
            a = QAction(name, skin_menu, checkable=True, checked=sid == self.cfg["skin"])
            a.triggered.connect(lambda _=False, s=sid: self.set_skin(s))
            sg.addAction(a)
            skin_menu.addAction(a)
        skin_menu.addSeparator()
        skin_menu.addAction("Open skins folder…", self.open_skins_folder)

        size_menu = m.addMenu("Size")
        zg = QActionGroup(size_menu)
        for label, px in SIZES.items():
            a = QAction(label, size_menu, checkable=True, checked=px == self.cfg["size"])
            a.triggered.connect(lambda _=False, v=px: self.set_size(v))
            zg.addAction(a)
            size_menu.addAction(a)

        lang_menu = m.addMenu("Language")
        lg = QActionGroup(lang_menu)
        for code, label in LANGUAGES.items():
            a = QAction(label, lang_menu, checkable=True, checked=code == self.cfg["language"])
            a.triggered.connect(lambda _=False, c=code: self.cfg.__setitem__("language", c))
            lg.addAction(a)
            lang_menu.addAction(a)

        bub = QAction("Speech bubbles", m, checkable=True, checked=bool(self.cfg["bubbles"]))
        bub.toggled.connect(lambda v: self.cfg.__setitem__("bubbles", v))
        m.addAction(bub)
        m.addSeparator()
        m.addAction("About Saarthi", self.show_about)
        m.addAction("Quit", self.app.quit)

    # ---------- Try features ----------
    def simulate(self, activity, seconds: float = 10):
        """Pretend you're doing something for a few seconds."""
        self.sm.preview = None
        self._sim = (activity, time.monotonic() + seconds)

    def build_try_menu(self, t: QMenu):
        from datetime import datetime, timedelta

        from .states import Activity
        from .store import Event, Reminder, dt_to_str

        now_s = lambda: dt_to_str(datetime.now())  # noqa: E731
        act = t.addMenu("What I'm doing (10 s)")
        for label, a in (
            ("Typing fast", Activity(keys_per_sec=7)),
            ("Typing slowly", Activity(keys_per_sec=1)),
            ("Scrolling", Activity(scrolls_per_sec=2)),
            ("Watching a tutorial", Activity(video_playing=True, media_tutorial=True, idle_seconds=20)),
            ("Watching YouTube", Activity(video_playing=True, media_site="youtube", idle_seconds=20)),
            ("Away from laptop", Activity(idle_seconds=200)),
            ("Asleep (long away)", Activity(idle_seconds=1000)),
        ):
            act.addAction(label, lambda a=a: self.simulate(a))
        t.addSeparator()
        t.addAction("Poke head", lambda: (self._clicks.clear(), self.on_click("head")))
        t.addAction("Tickle belly", lambda: (self._clicks.clear(), self.on_click("body")))
        t.addAction("Step on the shoes", lambda: (self._clicks.clear(), self.on_click("boots")))
        t.addAction("Tug the jeans", lambda: (self._clicks.clear(), self.on_click("jeans")))
        t.addAction("Click too much (dizzy)", lambda: [self.on_click("body") for _ in range(4)])
        t.addAction("Walk somewhere", lambda: self.walker.walk_random(on_arrive=self.save_position))
        t.addSeparator()
        t.addAction(
            "Reminder pops up", lambda: self.org.show_reminder(Reminder("Demo: Paani piyo 💧", now_s()), demo=True)
        )
        t.addAction(
            "Calendar event alert",
            lambda: self.org.show_event(Event("Demo: Team meeting", dt_to_str(datetime.now() + timedelta(minutes=10)))),
        )
        t.addAction("Morning brief", lambda: self.org.brief_now())
        t.addAction("Random quote", self._try_quote)
        t.addSeparator()
        t.addAction("Break suggestion (50 min done)", lambda: self.wellness.offer_break())
        t.addAction("1-minute break (walks + chai)", lambda: self.wellness.start_break(1))
        t.addAction("Breathing exercise (2 breaths)", self._try_breathe)
        t.addSeparator()
        lap = t.addMenu("💻 Laptop")
        for label, name in (
            ("Battery low (12%)", "battery_low"),
            ("Battery critical (4%)", "battery_critical"),
            ("Charger plugged in", "charger_in"),
            ("Charger unplugged", "charger_out"),
            ("Battery full", "battery_full"),
            ("Laptop running hot", "cpu_hot"),
            ("Internet gone", "net_down"),
            ("Internet back", "net_up"),
            ("No restart for days", "uptime"),
            ("Headphones in", "headphones_on"),
            ("Headphones out", "headphones_off"),
            ("Muted", "muted"),
            ("Volume past 100%", "volume_max"),
            ("Working past midnight", "late_night"),
            ("Second monitor plugged in", "big_screen"),
        ):
            if name == "big_screen":
                lap.addAction(
                    label,
                    lambda: (
                        self.laptop.to_big_screen()
                        if len(self.app.screens()) > 1
                        else self.say(line_for("big_screen", self.cfg["language"]), force=True)
                    ),
                )
            else:
                lap.addAction(label, lambda n=name: self.laptop.simulate(n))
        t.addAction("Weather now", lambda: self.outdoor.say_weather())
        t.addAction("Rain warning", lambda: self.say("15:00 tak baarish aa sakti hai ☔ Chhata le lena", force=True))
        t.addAction("Traffic to home", lambda: self.outdoor.commute_now())
        outfit = t.addMenu("Weather outfit (Bit only)")
        for label, acc in (("Umbrella", "umbrella"), ("Beanie + scarf", "scarf"), ("Shades", "shades"), ("None", None)):
            outfit.addAction(label, lambda acc=acc: (setattr(self.skin, "accessory", acc), self.win.update()))

    def _try_quote(self):
        lists = [q for q in self.org.store.quotes if q.items]
        if lists:
            self.say(random.choice(random.choice(lists).items), force=True)

    def _try_breathe(self):
        cycles = self.cfg["breathing_cycles"]
        self.cfg.data["breathing_cycles"] = 2
        self.wellness.start_breathe()
        self.cfg.data["breathing_cycles"] = cycles

    def set_preview(self, state: State | None):
        self.walker.cancel()
        self.sm.preview = state
        now = time.monotonic()
        if state is not None:
            self.win.set_state(state, now)
            self.win.state_started = now

    @staticmethod
    def make_source(demo: bool):
        if demo:
            return DemoSource(time.monotonic())
        try:
            return LiveSource()
        except Exception as e:  # never let detection crash the buddy
            print(f"[saarthi] activity detection disabled: {e}")
            return NullSource()

    def set_demo(self, on: bool):
        if on == self.demo:
            return
        self.source.stop()
        self.demo = on
        self.source = self.make_source(on)

    def show_status(self):
        from .status_dialog import StatusDialog

        if self.status_dialog is None or not self.status_dialog.isVisible():
            self.status_dialog = StatusDialog(self)
        self.status_dialog.show()
        self.status_dialog.raise_()
        self.status_dialog.activateWindow()

    def set_skin(self, sid: str):
        self.cfg["skin"] = sid
        acc = self.skin.accessory
        self.skin = skins.load(sid)
        self.skin.accessory = acc
        self.win.set_skin(self.skin, self.cfg["size"])
        if self.tray:
            self.tray.setIcon(self.make_icon())

    def set_size(self, px: int):
        self.cfg["size"] = px
        bottom_right = self.win.frameGeometry().bottomRight()
        self.win.set_size(px)
        self.win.move(bottom_right.x() - self.win.width() + 1, bottom_right.y() - self.win.height() + 1)
        self.save_position()

    def open_skins_folder(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        d = config_dir() / "skins"
        d.mkdir(exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def make_icon(self) -> QIcon:
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        self.skin.paint(p, QRectF(0, 0, 64, 64), State.IDLE, 0.0, 0.0)
        p.end()
        return QIcon(pix)
