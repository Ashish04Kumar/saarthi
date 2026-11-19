"""Decides when reminders, calendar events and quotes are due. No Qt here."""

from __future__ import annotations

import calendar
import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .store import Event, Reminder, Store, dt_to_str, str_to_dt


def _hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _add_month(d: datetime, day: int) -> datetime:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=y, month=m, day=min(day, calendar.monthrange(y, m)[1]))


def next_occurrence(r: Reminder, after: datetime) -> datetime | None:
    """First occurrence strictly after `after` (None if it never happens again)."""
    first = str_to_dt(r.at)
    if r.repeat == "once":
        return first if first > after else None
    if r.repeat == "interval":
        step = timedelta(minutes=max(1, r.interval_min))
        t = first
        if t <= after:
            n = int((after - t) / step) + 1
            t = t + n * step
        lo, hi = _hm(r.active_from), _hm(r.active_to)
        for _ in range(2000):
            if lo <= t.time() <= hi:
                return t
            if t.time() > hi:  # jump to tomorrow's window start, aligned to the grid
                start = datetime.combine(t.date() + timedelta(days=1), lo)
            else:
                start = datetime.combine(t.date(), lo)
            n = max(0, -(-int((start - first).total_seconds()) // int(step.total_seconds())))
            t = first + n * step
        return None
    t = first
    if r.repeat == "monthly":
        while t <= after:
            t = _add_month(t, first.day)
        return t
    if t <= after:
        days = (after.date() - t.date()).days
        t = t + timedelta(days=max(0, days))
        while t <= after:
            t += timedelta(days=1)
    if r.repeat == "daily":
        return t
    if r.repeat == "weekdays":
        while t.weekday() >= 5:
            t += timedelta(days=1)
        return t
    if r.repeat == "weekly":
        while t.weekday() != first.weekday():
            t += timedelta(days=1)
        return t
    return None


def schedule(r: Reminder, now: datetime) -> None:
    """(Re)compute r.next_at after creating or editing a reminder."""
    first = str_to_dt(r.at)
    nxt = first if first >= now - timedelta(minutes=1) else next_occurrence(r, now)
    r.next_at = dt_to_str(nxt)
    r.snooze_until = None


def due_at(r: Reminder) -> datetime | None:
    if not r.enabled:
        return None
    return str_to_dt(r.snooze_until) or str_to_dt(r.next_at)


def complete(r: Reminder, now: datetime) -> None:
    """User pressed Done (or dismissed): move to the next occurrence."""
    base = max(now, str_to_dt(r.next_at) or now)
    nxt = next_occurrence(r, base)
    r.next_at = dt_to_str(nxt)
    r.snooze_until = None
    if nxt is None:
        r.enabled = False


def snooze(r: Reminder, now: datetime, minutes: int) -> None:
    r.snooze_until = dt_to_str(now + timedelta(minutes=minutes))


def event_alert_time(e: Event) -> datetime:
    start = str_to_dt(e.start)
    if e.all_day:
        return start.replace(hour=9, minute=0)
    return start - timedelta(minutes=max(0, e.remind_before_min))


def event_key(e: Event) -> str:
    return f"{e.source}|{e.id}|{e.start}"


@dataclass
class Due:
    kind: str  # "reminder" | "event" | "quote"
    title: str
    obj: object = None


class Scheduler:
    def __init__(self, store: Store, rng: random.Random | None = None):
        self.store = store
        self.rng = rng or random.Random()
        self.showing: set[str] = set()  # reminder ids currently on screen
        self.quote_next: dict[str, datetime] = {}

    def check(self, now: datetime, quiet: bool = False) -> list[Due]:
        out: list[Due] = []
        changed = False
        for r in self.store.reminders:
            d = due_at(r)
            if d and d <= now and r.id not in self.showing:
                self.showing.add(r.id)
                out.append(Due("reminder", r.title, r))
        for e in self.store.all_events():
            key = event_key(e)
            if key in self.store.fired:
                continue
            alert = event_alert_time(e)
            start = str_to_dt(e.start)
            end = str_to_dt(e.end) if e.end else start + timedelta(hours=1)
            if alert <= now <= max(end, alert + timedelta(minutes=30)):
                self.store.fired[key] = dt_to_str(now)
                changed = True
                out.append(Due("event", e.title, e))
        cutoff = dt_to_str(now - timedelta(days=3))
        old = [k for k, v in self.store.fired.items() if v < cutoff]
        for k in old:
            del self.store.fired[k]
        changed = changed or bool(old)
        if changed:
            self.store.save(notify=False)

        for q in self.store.quotes:
            if not q.enabled or not q.items:
                self.quote_next.pop(q.id, None)
                continue
            nxt = self.quote_next.get(q.id)
            if nxt is None:
                self.quote_next[q.id] = now + self._gap(q)
            elif now >= nxt:
                self.quote_next[q.id] = now + self._gap(q)
                if not quiet:
                    out.append(Due("quote", self.rng.choice(q.items), q))
        return out

    def _gap(self, q) -> timedelta:
        lo, hi = sorted((max(1, q.every_min), max(1, q.every_max)))
        return timedelta(minutes=self.rng.uniform(lo, hi))

    def resolved(self, r: Reminder) -> None:
        self.showing.discard(r.id)

    def upcoming(self, now: datetime, hours: int = 24) -> list[tuple[datetime, str]]:
        horizon = now + timedelta(hours=hours)
        items = []
        for r in self.store.reminders:
            d = due_at(r)
            if d and now <= d <= horizon:
                items.append((d, r.title))
        for e in self.store.all_events():
            s = str_to_dt(e.start)
            if now - timedelta(hours=1) <= s <= horizon or (e.all_day and s.date() == now.date()):
                items.append((s, e.title))
        return sorted(items)
