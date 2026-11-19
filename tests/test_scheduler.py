import random
from datetime import datetime

from saarthi.scheduler import Scheduler, complete, next_occurrence, schedule, snooze
from saarthi.store import Event, QuoteList, Reminder, Store

D = datetime


def test_once_and_daily():
    r = Reminder("x", "2026-11-19T10:00")
    assert next_occurrence(r, D(2026, 11, 19, 9)) == D(2026, 11, 19, 10)
    assert next_occurrence(r, D(2026, 11, 19, 11)) is None
    r.repeat = "daily"
    assert next_occurrence(r, D(2026, 11, 25, 10)) == D(2026, 11, 26, 10)
    assert next_occurrence(r, D(2026, 11, 25, 9, 59)) == D(2026, 11, 25, 10)


def test_weekdays_and_weekly():
    r = Reminder("standup", "2026-11-20T10:00", repeat="weekdays")  # Friday
    assert next_occurrence(r, D(2026, 11, 20, 10)) == D(2026, 11, 23, 10)  # Monday
    r = Reminder("gym", "2026-11-19T07:00", repeat="weekly")  # Thursday
    assert next_occurrence(r, D(2026, 11, 19, 8)) == D(2026, 11, 26, 7)


def test_monthly_clamps_short_months():
    r = Reminder("rent", "2026-01-31T09:00", repeat="monthly")
    assert next_occurrence(r, D(2026, 1, 31, 10)) == D(2026, 2, 28, 9)


def test_interval_respects_window():
    r = Reminder(
        "water", "2026-11-19T09:00", repeat="interval", interval_min=90, active_from="09:00", active_to="18:00"
    )
    assert next_occurrence(r, D(2026, 11, 19, 9, 30)) == D(2026, 11, 19, 10, 30)
    assert next_occurrence(r, D(2026, 11, 19, 17, 31)) == D(2026, 11, 19, 18, 0)  # window is inclusive
    assert next_occurrence(r, D(2026, 11, 19, 18, 1)) == D(2026, 11, 20, 9, 0)


def test_complete_snooze_and_scheduler(tmp_path):
    s = Store(tmp_path / "d.json")
    r = Reminder("call mom", "2026-11-19T18:00", repeat="daily")
    schedule(r, D(2026, 11, 19, 12))
    s.reminders.append(r)
    sch = Scheduler(s)
    assert not [d for d in sch.check(D(2026, 11, 19, 17, 59)) if d.kind == "reminder"]
    due = [d for d in sch.check(D(2026, 11, 19, 18, 0)) if d.kind == "reminder"]
    assert len(due) == 1
    assert not [d for d in sch.check(D(2026, 11, 19, 18, 1)) if d.kind == "reminder"]  # not twice
    snooze(r, D(2026, 11, 19, 18, 1), 10)
    sch.resolved(r)
    assert not [d for d in sch.check(D(2026, 11, 19, 18, 5)) if d.kind == "reminder"]
    assert [d for d in sch.check(D(2026, 11, 19, 18, 11)) if d.kind == "reminder"]
    complete(r, D(2026, 11, 19, 18, 12))
    assert r.next_at == "2026-11-20T18:00" and r.snooze_until is None


def test_once_disables_after_done():
    r = Reminder("x", "2026-11-19T10:00")
    schedule(r, D(2026, 11, 19, 9))
    complete(r, D(2026, 11, 19, 10))
    assert not r.enabled


def test_event_fires_once(tmp_path):
    s = Store(tmp_path / "d.json")
    s.events.append(Event("Meeting", "2026-11-19T15:00", remind_before_min=10))
    sch = Scheduler(s)
    assert not [d for d in sch.check(D(2026, 11, 19, 14, 49)) if d.kind == "event"]
    assert [d for d in sch.check(D(2026, 11, 19, 14, 50)) if d.kind == "event"]
    assert not [d for d in Scheduler(Store(tmp_path / "d.json")).check(D(2026, 11, 19, 14, 51)) if d.kind == "event"]


def test_quotes_seeded_and_spaced(tmp_path):
    s = Store(tmp_path / "d.json")
    assert s.quotes and s.quotes[0].name.startswith("No smoking")
    s.quotes = [QuoteList("q", ["a", "b"], True, 10, 10)]
    sch = Scheduler(s, random.Random(1))
    assert not sch.check(D(2026, 1, 1, 9, 0))  # first call only schedules
    assert not [d for d in sch.check(D(2026, 1, 1, 9, 9)) if d.kind == "quote"]
    assert [d for d in sch.check(D(2026, 1, 1, 9, 10)) if d.kind == "quote"]
