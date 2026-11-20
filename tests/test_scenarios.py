"""End-to-end 'what wins when two things happen at once' checks, on a real (offscreen) buddy."""

import json
import os
import time

import pytest

from saarthi import clock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def buddy(tmp_path_factory):
    cfg_home = tmp_path_factory.mktemp("cfg")
    os.environ["XDG_CONFIG_HOME"] = str(cfg_home)
    (cfg_home / "saarthi").mkdir()
    (cfg_home / "saarthi" / "config.json").write_text(
        json.dumps({"weather_enabled": False, "welcomed": True, "chatter_minutes": [600, 600]})
    )
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from saarthi.app import Saarthi

    b = Saarthi(app, demo=True)
    b.wellness.timer.stop()  # tests drive wellness by hand
    b.app_ = app
    b.win.move(300, 500)
    yield b
    # tear down while the QApplication is still alive, so Qt objects die in the right order
    import gc

    b.shutdown()
    for w in app.topLevelWidgets():
        w.close()
        w.deleteLater()
    for t in (
        b.tick_timer,
        b.chatter_timer,
        b.org.timer,
        b.org.sync_timer,
        b.outdoor.weather_timer,
        b.outdoor.commute_timer,
        b.walker.step_timer,
        b.walker.stroll_timer,
        b.walker.pause_timer,
    ):
        t.stop()
    app.processEvents()
    del b
    gc.collect()
    app.processEvents()


def pump(b, sec):
    end = time.time() + sec
    while time.time() < end:
        b.app_.processEvents()
        time.sleep(0.01)


def reset(b):
    from saarthi.states import Activity

    b.wellness.stop(quiet=True)
    b.walker.cancel()
    for c in list(b.org.cards):
        c.close()
    if b.org.panel is not None:
        b.org.panel.hide()
    b.bubble.hide()
    b._speech.clear()
    b.simulate(Activity(), 60)
    b.sm.end_transient(clock.now())
    pump(b, 0.6)


def test_chitchat_never_cuts_an_important_line(buddy):
    from saarthi.app import HIGH, LOW, NORMAL

    reset(buddy)
    buddy.say("Yaad hai na? Call mom", 4000, priority=HIGH)
    buddy.say("random chit-chat", priority=LOW)
    assert buddy.bubble.text == "Yaad hai na? Call mom"
    assert buddy._speech == []  # chit-chat is dropped, not queued
    buddy.say("Morning brief", 3000, priority=NORMAL)
    assert buddy.bubble.text == "Yaad hai na? Call mom"  # waits its turn
    buddy.bubble.hide()
    pump(buddy, 0.7)
    assert buddy.bubble.text == "Morning brief"


def test_reminder_during_a_break_keeps_the_break(buddy):
    from saarthi.states import State
    from saarthi.store import Reminder

    reset(buddy)
    buddy.wellness.start_break(1)
    buddy.org.show_reminder(Reminder("Demo", "2026-01-01T10:00"), demo=True)
    pump(buddy, 0.3)
    buddy.tick()
    assert buddy.sm.state == State.BREAK and buddy.wellness.mode == "break"
    assert len(buddy.org.cards) == 1  # the reminder still shows up


def test_typing_through_a_break_cancels_it(buddy):
    from saarthi.states import Activity, State

    reset(buddy)
    buddy.wellness.start_break(1)
    active_before = buddy.sm.active_minutes
    buddy.simulate(Activity(keys_per_sec=5), 30)
    buddy.tick()
    buddy.wellness.streak.seconds = 44.9  # pretend 45 s of typing already happened
    buddy.wellness._last_tick = clock.now() - 0.5
    buddy.wellness.tick()
    assert buddy.wellness.mode is None
    assert buddy.sm.state != State.BREAK
    assert buddy.wellness.break_snooze and buddy.wellness.break_snooze > clock.now()
    assert buddy.sm.active_minutes >= active_before  # work time is not wiped
    assert "zaroori" in buddy.bubble.text or "important" in buddy.bubble.text


def test_breathing_stops_a_walk(buddy):
    reset(buddy)
    buddy.walker.walk_to(buddy.win.x() - 250)
    assert buddy.walker.walking
    buddy.wellness.start_breathe()
    assert not buddy.walker.walking and buddy.win.override is None


def test_no_wandering_while_panel_or_card_is_open(buddy, monkeypatch):
    import random

    reset(buddy)
    buddy.tick()
    monkeypatch.setattr(random, "random", lambda: 0.0)  # "always decide to stroll"
    buddy.org.open_panel()
    pump(buddy, 0.2)
    buddy.walker._maybe_stroll()
    assert not buddy.walker.walking
    buddy.org.panel.hide()
    buddy.walker._maybe_stroll()
    assert buddy.walker.walking  # free to stroll again
    buddy.walker.cancel()


def test_no_wandering_while_typing(buddy, monkeypatch):
    import random

    from saarthi.states import Activity

    reset(buddy)
    monkeypatch.setattr(random, "random", lambda: 0.0)
    buddy.simulate(Activity(keys_per_sec=7), 30)
    for _ in range(8):
        buddy.tick()
        pump(buddy, 0.25)
    buddy.walker._maybe_stroll()
    assert not buddy.walker.walking


def test_lunch_eats_then_strolls_slowly_and_thinks(buddy):
    from saarthi.states import State

    reset(buddy)
    buddy.wellness.set_status("lunch")
    assert buddy.wellness.status == "lunch" and buddy.sm.state == State.EAT
    buddy.wellness.eat_until = clock.now() - 1  # pretend 10-15 min of eating went by
    buddy.wellness._last_tick = clock.now()
    buddy.wellness.tick()
    assert buddy.sm.state == State.THINK
    assert buddy.walker.pacing and buddy.walker.pace_factor < 1  # slow stroll
    buddy.walker._paused()  # a stop on the stroll: think out loud
    assert "🤔" in buddy.bubble.text
    buddy.wellness.set_status("working")
    assert buddy.wellness.status == "working" and not buddy.walker.pacing
    assert buddy.sm.state == State.HAPPY


def test_typing_during_lunch_asks_instead_of_cancelling(buddy):
    from saarthi.states import Activity

    reset(buddy)
    buddy.wellness.set_status("lunch")
    buddy.simulate(Activity(keys_per_sec=5), 30)
    buddy.tick()
    buddy.wellness.streak.seconds = 44.9
    buddy.wellness._last_tick = clock.now() - 0.5
    buddy.wellness.tick()
    assert buddy.wellness.status == "lunch"  # you set lunch yourself, so it only asks
    assert len(buddy.org.cards) == 1


def test_switching_status_break_to_lunch(buddy):
    from saarthi.states import State

    reset(buddy)
    buddy.wellness.set_status("break")
    assert buddy.wellness.status == "break" and buddy.walker.pacing
    buddy.wellness.set_status("lunch")
    assert buddy.wellness.status == "lunch" and buddy.sm.state == State.EAT
    assert not buddy.walker.walking  # sits down to eat


def test_quiet_mode_hides_everything_and_comes_back(buddy):
    from saarthi.store import Reminder

    reset(buddy)
    pos, size = buddy.win.pos(), buddy.win.height()
    buddy.set_quiet(True)
    assert buddy.win.height() == 90 + buddy.win.credit_height()  # small, in the corner
    buddy.say("hello", force=True)
    assert not buddy.bubble.isVisible()  # silent, even for important lines
    buddy.org.show_reminder(Reminder("Demo", "2026-01-01T10:00"), demo=True)
    assert buddy.org.cards and not buddy.org.cards[-1].isVisible()  # waits, not lost
    buddy.on_click(0.2)
    assert buddy.win.override is not None  # no reactions on screen
    buddy.set_quiet(False)
    assert buddy.win.height() == size and buddy.win.pos() == pos
    assert buddy.org.cards[-1].isVisible()  # the reminder shows up now


def test_clicking_active_status_again_turns_it_off(buddy, monkeypatch):
    from saarthi.duration_dialog import DurationDialog

    monkeypatch.setattr(DurationDialog, "ask", staticmethod(lambda kind, minutes, editing=False: (minutes, False)))
    reset(buddy)
    buddy.org.open_panel()
    panel = buddy.org.panel
    panel._set_status("lunch")
    assert buddy.wellness.status == "lunch"
    panel._set_status("lunch")
    assert buddy.wellness.status == "working"
    buddy.toggle_status("break")
    buddy.toggle_status("break")
    assert buddy.wellness.status == "working"


def test_panel_changes_show_up_in_full_window_and_delete_works(buddy):
    reset(buddy)
    buddy.org.open_manager("notes")
    buddy.org.open_panel("notes")
    panel = buddy.org.panel
    panel.n_text.setText("Sync check note")
    panel.add_note()
    titles = [buddy.org.manager.notes.list.item(i).text() for i in range(buddy.org.manager.notes.list.count())]
    assert any("Sync check note" in t for t in titles)  # full window updated right away
    note = next(n for n in buddy.org.store.notes if n.text == "Sync check note")
    panel._delete_note(note)
    assert note not in buddy.org.store.notes
    buddy.org.manager.hide()


def test_minutes_picker_sets_and_changes_session_length(buddy, monkeypatch):
    from saarthi.duration_dialog import DurationDialog

    reset(buddy)
    asked = {}

    def fake_ask(kind, minutes, editing=False):
        asked[(kind, editing)] = minutes
        return (25, True) if not editing else (90, False)

    monkeypatch.setattr(DurationDialog, "ask", staticmethod(fake_ask))
    default_before = buddy.cfg["lunch_minutes"]
    assert buddy.toggle_status("lunch")
    assert asked[("lunch", False)] == default_before  # offered the default (60 min)
    assert 24 * 60 < buddy.wellness.ends - clock.now() <= 25 * 60
    assert buddy.cfg["lunch_minutes"] == 25  # "make it default" was ticked
    buddy.change_session_time()
    assert 89 * 60 < buddy.wellness.ends - clock.now() <= 90 * 60  # updated while running
    monkeypatch.setattr(DurationDialog, "ask", staticmethod(lambda *a, **k: None))
    buddy.toggle_status("lunch")  # same status again: back to work, no question asked
    assert buddy.wellness.status == "working"
    assert not buddy.toggle_status("break")  # cancelled picker: nothing starts
    assert buddy.wellness.status == "working"
    buddy.cfg["lunch_minutes"] = default_before


def test_music_puts_headphones_on_even_on_low_battery(buddy, monkeypatch):
    from saarthi.states import Activity, State

    lap = buddy.laptop
    now = clock.now()
    buddy.activity = Activity(music_playing=True)
    lap.refresh_looks(now)
    assert buddy.win.variant(State.IDLE) == "music"
    monkeypatch.setattr(lap.watch, "low_battery", lambda: True)
    monkeypatch.setattr(lap.probe, "power", (12.0, False))
    lap.refresh_looks(now)
    assert buddy.win.variant(State.IDLE) == "music" and buddy.win.badge == "low"  # badge still says it
    monkeypatch.setattr(lap.probe, "power", (4.0, False))
    lap.refresh_looks(now)
    assert buddy.win.variant(State.IDLE) == "tired"  # at 5% the battery wins
    buddy.activity = Activity()
    monkeypatch.setattr(lap.watch, "low_battery", lambda: False)
    lap.refresh_looks(now)
    assert buddy.win.variant(State.IDLE) is None


def test_no_strolls_while_tired(buddy, monkeypatch):
    import random

    from saarthi.states import State

    buddy.walker.cancel()
    buddy.cfg["walk_enabled"] = True
    monkeypatch.setattr(random, "random", lambda: 0.0)  # "always decide to stroll"
    buddy.sm.state = State.IDLE
    buddy.win.set_variant(State.IDLE, "tired")
    buddy.walker._maybe_stroll()
    assert not buddy.walker.walking
    buddy.win.set_variant(State.IDLE, None)


def test_morning_brief_waits_for_its_time(buddy, monkeypatch):
    from datetime import datetime

    from saarthi.organizer import brief_time
    from saarthi.states import State

    org = buddy.org
    shown = []
    monkeypatch.setattr(org, "brief_now", lambda now=None, delay_ms=0: shown.append(now))
    buddy.cfg["brief_at"] = "10:45"
    org.store.meta.pop("last_brief", None)
    org.maybe_brief(datetime(2026, 11, 21, 9, 30), State.IDLE)
    org.maybe_brief(datetime(2026, 11, 21, 10, 44), State.IDLE)
    assert shown == []
    org.maybe_brief(datetime(2026, 11, 21, 10, 50), State.AFK)  # away: waits until you're back
    assert shown == []
    org.maybe_brief(datetime(2026, 11, 21, 11, 5), State.TYPING_FAST)
    org.maybe_brief(datetime(2026, 11, 21, 15, 0), State.IDLE)  # once a day
    assert len(shown) == 1
    assert brief_time("7:5") == "07:05" and brief_time("nonsense") == "05:00"
    buddy.cfg["brief_at"] = "05:00"


def test_scroll_tip_only_after_a_long_stretch(buddy, monkeypatch):
    from saarthi import app as app_mod
    from saarthi.states import State

    said = []
    monkeypatch.setattr(buddy, "say", lambda text, *a, **k: said.append(text))
    buddy._scroll = None
    t0 = 1000.0
    for t in range(0, 100, 5):  # 100 s of scrolling: nothing yet
        buddy._long_scroll(State.SCROLLING, t0 + t)
    assert said == []
    buddy._long_scroll(State.IDLE, t0 + 110)  # a short pause to read
    for t in range(115, 130, 5):
        buddy._long_scroll(State.SCROLLING, t0 + t)
    assert len(said) == 1  # 2 min into the stretch
    for t in range(130, 400, 5):
        buddy._long_scroll(State.SCROLLING, t0 + t)
    assert len(said) == 1  # not again for 10 min
    buddy._long_scroll(State.IDLE, t0 + 400 + app_mod.SCROLL_PAUSE_OK + 1)  # a real stop
    buddy._long_scroll(State.SCROLLING, t0 + 500)
    assert buddy._scroll[0] == t0 + 500 and len(said) == 1  # a new stretch starts from zero


@pytest.mark.parametrize("kind", ["lunch", "break"])
def test_sessions_keep_time_while_the_lid_is_closed(buddy, monkeypatch, kind):
    """Saarthi's clock counts through sleep: a 60-min lunch is over after 2 h with the lid closed."""
    from saarthi import clock

    w = buddy.wellness
    (w.start_lunch if kind == "lunch" else w.start_break)(60 if kind == "lunch" else 5)
    assert w.mode == kind
    real = clock.now()
    monkeypatch.setattr(clock, "now", lambda: real + 2 * 3600)  # lid closed for two hours
    w._last_tick = real + 2 * 3600 - 0.5
    for _ in range(3):
        w.tick()
    assert w.mode is None  # the session ended on the first tick after waking up


def test_clock_counts_through_sleep_on_linux():
    import sys
    import time

    from saarthi import clock

    if sys.platform.startswith("linux"):
        # BOOTTIME includes time suspended, so it's never behind the monotonic clock
        assert clock.now() >= time.monotonic() - 0.01
