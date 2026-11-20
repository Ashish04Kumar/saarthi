"""How Saarthi reacts to the laptop: lines, the battery badge, tired / hot looks, and hopping to a
bigger monitor when one is plugged in."""

from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from .laptop import BATTERY_CRITICAL, CPU_HOT_C, LaptopProbe, LaptopWatch
from .lines import line_for
from .states import State

FLASH_SECONDS = 6.0  # charging / full badge after plugging in
SIM_SECONDS = 10.0
URGENT = {"battery_low", "battery_critical"}
IMPORTANT = {"charger_in", "charger_out", "battery_full", "cpu_hot", "net_down", "net_up", "late_night"}


class _Bridge(QObject):
    changed = Signal()  # emitted from the probe thread, delivered on the UI thread


class LaptopReactions:
    def __init__(self, buddy):
        self.b = buddy
        self.watch = LaptopWatch(started=time.monotonic())
        self.probe = LaptopProbe()
        self._bridge = _Bridge()
        self._bridge.changed.connect(self.tick)
        self.probe.on_change = self._bridge.changed.emit  # react the moment the probe sees a change
        if not buddy.demo:  # demo mode (and tests) fake everything; the Try menu still works
            self.probe.start()
        self._flash: tuple[str, float] | None = None  # (badge, until)
        self._sim: tuple[str | None, float, str | None, float] | None = None  # (badge, %, idle take, until)
        self._power_seen = self._net_seen = 0
        self._snap_seen: object = None
        self.timer = QTimer(timeout=self.tick)
        self.timer.start(1000)  # only for badge / Try-menu timeouts; changes arrive through on_change
        app = buddy.app
        app.screenAdded.connect(lambda _s: QTimer.singleShot(1500, self.to_big_screen))
        app.screenRemoved.connect(lambda _s: QTimer.singleShot(1500, self._still_on_screen))

    def stop(self) -> None:
        self.timer.stop()
        self.probe.stop()

    # ---- loop ----
    def tick(self) -> None:
        now = time.monotonic()
        on = self.b.cfg["laptop_alerts"]
        events: list[tuple[str, dict]] = []
        power, seq = self.probe.power, self.probe.power_seq
        if seq != self._power_seen and power is not None:
            self._power_seen = seq
            ev = self.watch.power(power[0], power[1], now)
            events += ev if on else []
        net, nseq = self.probe.net, self.probe.net_seq
        if nseq != self._net_seen and net is not None:
            self._net_seen = nseq
            ev = self.watch.net(net, now)
            events += ev if on else []
        snap = self.probe.latest
        if snap is not None and snap is not self._snap_seen:
            self._snap_seen = snap
            a = getattr(self.b, "activity", None)
            active = a is not None and a.idle_seconds < 120
            ev = self.watch.update(snap, now, datetime.now().hour, active)
            events += ev if on else []
        for name, kw in events:
            self.react(name, kw)
        self.refresh_looks(now)

    def react(self, name: str, kw: dict) -> None:
        key = name
        if name == "cpu_hot" and kw.get("temp") is not None and kw["temp"] >= CPU_HOT_C:
            key = "cpu_hot_temp"
        if name == "net_up" and kw.get("mins", 0) >= 2:
            key = "net_up_long"
        text = line_for(key, self.b.cfg["language"])
        if not text:
            return
        text = text.format(**kw)
        now = time.monotonic()
        if name == "charger_in":
            self._flash = ("charging", now + FLASH_SECONDS)
            self._cheer(now)
        elif name == "charger_out":
            self._flash = None  # unplugged: drop the green badge at once
        elif name == "battery_full":
            self._flash = ("full", now + FLASH_SECONDS)
        if name in URGENT:
            self.b.alert()
            self.b.say_shared(text, 9000 if name == "battery_critical" else 6000, force=True)
        else:
            from .app import HIGH, NORMAL

            self.b.say_shared(text, 5000, priority=HIGH if name in IMPORTANT else NORMAL)
        self.refresh_looks(now)

    def refresh_looks(self, now: float) -> None:
        win = self.b.win
        if self.b.quiet:
            win.set_badge(None)
            win.set_variant(State.IDLE, None)
            return
        pct = self.probe.power[0] if self.probe.power is not None else 0.0
        badge, take = None, None
        if self._sim is not None and now < self._sim[3]:
            badge, pct, take = self._sim[0], self._sim[1], self._sim[2]
        elif self.b.cfg["laptop_alerts"]:
            self._sim = None
            if self._flash is not None and now < self._flash[1]:
                badge = self._flash[0]
            elif self.watch.low_battery():
                badge = "critical" if pct <= BATTERY_CRITICAL else "low"
            if self.watch.low_battery():
                take = "tired"
            elif self.watch.hot:
                take = "hot"
        a = getattr(self.b, "activity", None)
        critical = take == "tired" and pct <= BATTERY_CRITICAL
        if a is not None and a.music_playing and not critical:
            take = "music"  # headphones on; a low battery still shows in the badge
        win.set_badge(badge, pct)
        win.set_variant(State.IDLE, take)

    def _cheer(self, now: float) -> None:
        sm = self.b.sm
        if not self.b.quiet and sm.preview is None and not sm.busy:
            sm.trigger(State.HAPPY, now)
            self.b.win.set_state(State.HAPPY, now)

    # ---- Try menu ----
    def simulate(self, name: str) -> None:
        now = time.monotonic()
        looks = {
            "battery_low": ("low", 12.0, "tired"),
            "battery_critical": ("critical", 4.0, "tired"),
            "charger_in": ("charging", 40.0, None),
            "battery_full": ("full", 100.0, None),
            "cpu_hot": (None, 0.0, "hot"),
        }
        badge, pct, take = looks.get(name, (None, 0.0, None))
        self._sim = (badge, pct, take, now + SIM_SECONDS)
        kw = {"pct": int(pct), "mins": 3, "days": 4, "vol": 130, "temp": None, "cpu": 95}
        self.react(name, kw)

    # ---- monitors ----
    def to_big_screen(self) -> None:
        """A monitor was plugged in: move to the biggest screen."""
        screens = self.b.app.screens()
        if len(screens) < 2 or self.b.quiet:
            return
        big = max(screens, key=lambda s: s.geometry().width() * s.geometry().height())
        win = self.b.win
        if win.screen() is big:
            return
        self.b.walker.cancel()
        g = big.availableGeometry()
        win.move(g.right() - win.width() - 40, g.bottom() - win.height() - 20)
        self.b.save_position()
        self.b.follow_bubble()
        QTimer.singleShot(400, lambda: self.b.say_shared(line_for("big_screen", self.b.cfg["language"])))

    def _still_on_screen(self) -> None:
        """A monitor was unplugged: come back if we were on it."""
        c = self.b.win.frameGeometry().center()
        if not any(s.availableGeometry().contains(c) for s in self.b.app.screens()):
            self.b.cfg["position"] = None
            self.b.place_window()
