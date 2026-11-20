"""Weather + commute services running in the background, talking to the buddy."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from . import clock
from . import commute as cm
from .weather import Place, Weather, accessory, fetch_weather, locate_by_ip, summary

WEATHER_EVERY_MS = 30 * 60_000


class _Bg(QObject):
    done = Signal(object, object, object)  # callback, result, error

    def __init__(self):
        super().__init__()
        self.done.connect(lambda cb, res, err: cb(res, err))

    def run(self, fn: Callable[[], Any], cb: Callable[[Any, Exception | None], None]) -> None:
        def work():
            try:
                res, err = fn(), None
            except Exception as e:  # reported to the callback
                res, err = None, e
            self.done.emit(cb, res, err)

        threading.Thread(target=work, daemon=True, name="saarthi-net").start()


def place_from(d: dict | None) -> Place | None:
    return Place(d["name"], float(d["lat"]), float(d["lon"])) if d else None


class Outdoor:
    def __init__(self, buddy):
        self.buddy = buddy
        self.cfg = buddy.cfg
        self.bg = _Bg()
        self.weather: Weather | None = None
        self.place: Place | None = None
        self.weather_error = ""
        self._fetching = False
        self._rain_warned_at: datetime | None = None
        self._commute_busy = False
        self.started = clock.now()

        self.weather_timer = QTimer(timeout=self.refresh_weather)
        self.weather_timer.start(WEATHER_EVERY_MS)
        self.commute_timer = QTimer(timeout=self.check_commute)
        self.commute_timer.start(60_000)
        QTimer.singleShot(1500, self.refresh_weather)
        QTimer.singleShot(5000, self.check_commute)

    @property
    def hinglish(self) -> bool:
        return self.cfg["language"] == "hinglish"

    # ---------------- weather ----------------
    def _resolve_place(self) -> Place:
        manual = place_from(self.cfg["weather_place"])
        if manual:
            return manual
        cached = self.cfg["auto_place"]
        if cached and cached.get("at", "") >= (datetime.now() - timedelta(days=1)).isoformat():
            return place_from(cached)
        p = locate_by_ip()
        self.cfg["auto_place"] = {"name": p.name, "lat": p.lat, "lon": p.lon, "at": datetime.now().isoformat()}
        return p

    def refresh_weather(self, then: Callable[[], None] | None = None) -> None:
        if not self.cfg["weather_enabled"] or self._fetching:
            if not self.cfg["weather_enabled"]:
                self.weather = None
                self._apply_outfit()
            return
        self._fetching = True

        def fn():
            place = self._resolve_place()
            return place, fetch_weather(place.lat, place.lon)

        def done(res, err):
            self._fetching = False
            if err is not None:
                self.weather_error = f"{type(err).__name__}: {err}"[:160]
            else:
                self.place, self.weather = res
                self.weather_error = ""
                self._apply_outfit()
                self._maybe_warn_rain()
            if then:
                then()

        self.bg.run(fn, done)

    def _apply_outfit(self) -> None:
        acc = accessory(self.weather, datetime.now()) if self.weather else None
        self.buddy.skin.accessory = acc
        self.buddy.win.update()

    def _maybe_warn_rain(self) -> None:
        w, now = self.weather, datetime.now()
        if w is None or w.raining:
            return
        soon = w.rain_soon(now, hours=1, prob=60)
        if soon and (self._rain_warned_at is None or now - self._rain_warned_at > timedelta(hours=3)):
            self._rain_warned_at = now
            msg = (
                f"{soon.strftime('%H:%M')} tak baarish aa sakti hai ☔ Bahar jaana ho to chhata le lena"
                if self.hinglish
                else f"Rain likely around {soon.strftime('%H:%M')} ☔"
            )
            self.buddy.say(msg)

    def weather_line(self) -> str | None:
        if not self.weather or not self.place:
            return None
        return summary(self.weather, self.place.name.split(",")[0], self.cfg["language"], datetime.now())

    def say_weather(self) -> None:
        if not self.cfg["weather_enabled"]:
            self.buddy.say("Weather band hai (Settings)" if self.hinglish else "Weather is off (Settings)")
            return

        def speak():
            line = self.weather_line()
            if line:
                self.buddy.say(line, 9000, priority=2)
            else:
                err = self.weather_error or "no data"
                self.buddy.say(("Weather nahi mila 😕 " if self.hinglish else "Couldn't get weather 😕 ") + err)

        stale = self.weather is None or datetime.now() - self.weather.fetched > timedelta(minutes=20)
        if stale:
            self.refresh_weather(then=speak)
        else:
            speak()

    def waiting_for_first_weather(self) -> bool:
        return (
            self.cfg["weather_enabled"]
            and self.weather is None
            and not self.weather_error
            and clock.now() - self.started < 25
        )

    # ---------------- commute ----------------
    def check_commute(self) -> None:
        if not self.cfg["commute_enabled"]:
            return
        now = datetime.now()
        if cm.commute_due(
            now,
            self.cfg["logout"],
            int(self.cfg["commute_before"]),
            list(self.cfg["workdays"]),
            self.cfg["last_commute"],
        ):
            self.cfg["last_commute"] = now.date().isoformat()
            self.commute_now(automatic=True)

    def commute_now(self, automatic: bool = False) -> None:
        home, office = place_from(self.cfg["home"]), place_from(self.cfg["office"])
        if not home or not office:
            msg = (
                "Settings me ghar aur office ka address daalo 🏠🏢"
                if self.hinglish
                else "Set your home and office address in Settings 🏠🏢"
            )
            self.buddy.say(msg)
            if not automatic:
                self.buddy.org.open_manager("settings")
            return
        if self._commute_busy:
            return
        self._commute_busy = True
        provider = self.cfg["commute_provider"]
        key = self.cfg["tomtom_key"] if provider == "tomtom" else self.cfg["google_key"]
        mode = self.cfg["commute_mode"]

        def done(route, err):
            self._commute_busy = False
            if err is not None:
                title = "Traffic check fail 😕" if self.hinglish else "Traffic check failed 😕"
                self.buddy.org._card("🚗", title, f"{type(err).__name__}: {err}"[:160], [("OK", lambda: None)])
                return
            title, detail = cm.message(route, self.cfg["language"])
            w = self.weather
            if w and (w.raining or w.rain_soon(datetime.now(), hours=2)):
                detail += "\n☔ " + ("Raaste me baarish ho sakti hai" if self.hinglish else "Rain on the way")
            icon = "🛵" if mode == "bike" else "🚗"
            self.buddy.org._card(icon, title, detail, [("OK", lambda: None)])
            if route.level == "heavy":
                self.buddy.say(
                    "Traffic bahut hai 😩 thoda ruk ke niklo?"
                    if self.hinglish
                    else "Heavy traffic 😩 maybe leave a bit later?"
                )

        self.bg.run(lambda: cm.route(provider, key, office, home, mode), done)
