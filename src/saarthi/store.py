"""Reminders, notes, calendar events and quote lists, saved to data.json."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any

ISO = "%Y-%m-%dT%H:%M"


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def dt_to_str(d: datetime | None) -> str | None:
    return d.strftime(ISO) if d else None


def str_to_dt(s: str | None) -> datetime | None:
    return datetime.strptime(s[:16], ISO) if s else None


REPEATS = {
    "once": "Once",
    "daily": "Every day",
    "weekdays": "Weekdays (Mon–Fri)",
    "weekly": "Every week",
    "monthly": "Every month",
    "interval": "Every N minutes",
}


@dataclass
class Reminder:
    title: str
    at: str  # first occurrence, ISO local time
    repeat: str = "once"
    interval_min: int = 60
    active_from: str = "09:00"  # interval reminders only fire inside this window
    active_to: str = "21:00"
    enabled: bool = True
    next_at: str | None = None
    snooze_until: str | None = None
    id: str = field(default_factory=new_id)


@dataclass
class Note:
    text: str = ""
    pinned: bool = False
    done: bool = False  # notes double as a to-do list
    created: str = field(default_factory=lambda: dt_to_str(datetime.now()))
    updated: str = field(default_factory=lambda: dt_to_str(datetime.now()))
    id: str = field(default_factory=new_id)

    @property
    def title(self) -> str:
        first = self.text.strip().splitlines()[0] if self.text.strip() else "Untitled"
        return first[:60]


@dataclass
class Event:
    title: str
    start: str
    end: str | None = None
    all_day: bool = False
    notes: str = ""
    remind_before_min: int = 10
    source: str = "local"  # "local" or the feed name
    id: str = field(default_factory=new_id)


@dataclass
class Feed:
    name: str
    url: str
    enabled: bool = True
    last_sync: str | None = None
    last_error: str = ""
    id: str = field(default_factory=new_id)


@dataclass
class QuoteList:
    name: str
    items: list[str] = field(default_factory=list)
    enabled: bool = True
    every_min: int = 45  # random gap between min..max minutes
    every_max: int = 90
    id: str = field(default_factory=new_id)


NO_SMOKING = [
    "Ek cigarette = 11 minute zindagi kam. Worth it nahi hai bhai 🚭",
    "Craving sirf 3–5 minute rehti hai. Paani piyo, walk karo, nikal jayegi 💪",
    "Har din bina cigarette = paisa bhi bacha, saans bhi 💸",
    "20 minute bina smoke: heart rate normal hone lagta hai ❤️",
    "Tum cigarette se zyada strong ho. Pakka 😎",
    "Craving aaye to 10 deep breaths. Main gin raha hoon 🫁",
    "Jo paisa cigarette pe jaata, us se kuch achha khareedo 🎁",
    "Ghar wale tumhe lamba dekhna chahte hain 🙏",
    "Smoke-free streak mat todna, kal khud pe proud feel karoge 🏆",
    "Chai ke saath cigarette ki aadat? Aaj sirf chai ☕",
    # hair
    "Cigarette se baal jaldi safed hote hain 👴 Smokers me kam umar me safedi ka risk zyada hota hai",
    "Smoking baalon ki jadon tak khoon aur oxygen kam pahunchati hai, hair fall badhta hai 💇",
    "Kaale ghane baal chahiye? Cigarette chhodo, baal bhi shukriya bolenge 🙌",
    # skin
    "Smoking skin tak oxygen kam karti hai, isliye chehra dull aur thaka hua lagta hai 😶",
    "Cigarette collagen todti hai, jhurriyan jaldi aati hain. Glow chahiye? No smoking ✨",
    "Smoker ka chehra umar se saalon pehle budha dikhne lagta hai. Young rehna hai? 🚭",
    "Chhodne ke kuch hafton me blood flow sudharta hai aur chehre pe glow wapas aane lagta hai 🌟",
    "Hothon aur aankhon ke aas-paas ki jhurriyan smokers me jaldi aati hain. Chehra bachao 😊",
    # brain
    "Nicotine dimaag ko craving ka gulaam banata hai 🧠 Asli aazaadi bina cigarette ke",
    "Smoking se stroke ka risk badhta hai. Dimaag ko bachao 🧠❤️",
    "Cigarette stress kam nahi karti, bas craving shaant karti hai. Asli calm bina iske 😌",
    "Smoking chhodne ke ~1 mahine me dimaag ke nicotine receptors normal hone lagte hain 🧠✨",
    "Smoking yaaddasht aur focus pe bura asar daalti hai. Sharp dimaag = no smoking 🎯",
]


def _load(cls, d: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in names})


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.reminders: list[Reminder] = []
        self.notes: list[Note] = []
        self.events: list[Event] = []  # local events only
        self.feeds: list[Feed] = []
        self.quotes: list[QuoteList] = []
        self.fired: dict[str, str] = {}  # event-occurrence key -> when fired
        self.history: list[dict] = []  # fired reminders: {id, rid, title, due, outcome, at}
        self.meta: dict[str, Any] = {}
        self.feed_events: list[Event] = []  # from iCal feeds (cached, not user-edited)
        self._listeners: list[Callable[[], None]] = []
        self.load()

    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            raw = None
        if raw is None:
            self.quotes = [QuoteList("No smoking motivation", list(NO_SMOKING), True, 40, 40)]
            self.save()
            return
        self.reminders = [_load(Reminder, d) for d in raw.get("reminders", [])]
        self.notes = [_load(Note, d) for d in raw.get("notes", [])]
        self.events = [_load(Event, d) for d in raw.get("events", [])]
        self.feeds = [_load(Feed, d) for d in raw.get("feeds", [])]
        self.quotes = [_load(QuoteList, d) for d in raw.get("quotes", [])]
        self.feed_events = [_load(Event, d) for d in raw.get("feed_events", [])]
        self.fired = raw.get("fired", {})
        self.history = raw.get("history", [])
        self.meta = raw.get("meta", {})

    def save(self, notify: bool = True) -> None:
        data = {
            "version": 1,
            "reminders": [asdict(r) for r in self.reminders],
            "notes": [asdict(n) for n in self.notes],
            "events": [asdict(e) for e in self.events],
            "feeds": [asdict(f) for f in self.feeds],
            "quotes": [asdict(q) for q in self.quotes],
            "feed_events": [asdict(e) for e in self.feed_events],
            "fired": self.fired,
            "history": self.history[-500:],
            "meta": self.meta,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
        if notify:
            for cb in list(self._listeners):
                cb()

    # ---------- reminder follow-up ("did I actually do it?") ----------
    def log_fired(self, r: Reminder, due: str | None) -> dict:
        for h in self.history:  # a snoozed reminder firing again reuses its entry
            if h["rid"] == r.id and h["due"] == due and h["outcome"] == "pending":
                return h
        h = {
            "id": new_id(),
            "rid": r.id,
            "title": r.title,
            "due": due,
            "outcome": "pending",
            "at": dt_to_str(datetime.now()),
        }
        self.history.append(h)
        return h

    def set_outcome(self, hid: str, outcome: str) -> None:
        for h in self.history:
            if h["id"] == hid:
                h["outcome"] = outcome
                h["at"] = dt_to_str(datetime.now())

    def stats(self, days: int = 7) -> tuple[int, int, int]:
        """(done, missed, pending) over the last `days` days."""
        from datetime import timedelta

        cutoff = dt_to_str(datetime.now() - timedelta(days=days))
        recent = [h for h in self.history if (h.get("due") or h["at"]) >= cutoff]
        return tuple(sum(h["outcome"] == k for h in recent) for k in ("done", "missed", "pending"))

    def all_events(self) -> list[Event]:
        return self.events + self.feed_events

    def events_on(self, day) -> list[Event]:
        out = [e for e in self.all_events() if str_to_dt(e.start).date() == day]
        return sorted(out, key=lambda e: (not e.all_day, e.start))
