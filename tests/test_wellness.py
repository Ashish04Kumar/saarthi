from saarthi.lines import line_for
from saarthi.states import Activity, State, StateMachine
from saarthi.wellness_logic import CYCLE, break_due, breath_phase, mmss


def test_breath_phases():
    assert breath_phase(0)[0] == "in" and breath_phase(0)[2] == 0
    assert breath_phase(3.99)[0] == "in" and breath_phase(3.99)[2] > 0.99
    assert breath_phase(4.5) == ("hold", 2, 1.0)
    ph, left, lvl = breath_phase(7)
    assert ph == "out" and left == 5 and 0 < lvl < 1
    assert breath_phase(CYCLE)[0] == "in"


def test_break_due_and_snooze():
    assert not break_due(49, 50, None, 0)
    assert break_due(50, 50, None, 0)
    assert not break_due(60, 50, 100, 50)
    assert break_due(60, 50, 100, 101)
    assert mmss(299.6) == "5:00" and mmss(61) == "1:01"


def test_break_state_is_sticky_and_endable():
    sm = StateMachine()
    sm.trigger(State.BREAK, 0, 300)
    assert sm.busy
    assert sm.update(Activity(keys_per_sec=8), 10) == State.BREAK
    sm.end_transient(20)
    assert not sm.busy and sm.state == State.IDLE


def test_new_lines_format():
    assert "{brk}" in line_for("break_offer", "hinglish") or "break" in line_for("break_offer", "hinglish")
    assert line_for("breathe_in", "en").startswith("Breathe in")


def test_typing_streak_allows_short_pauses():
    from saarthi.wellness_logic import TypingStreak

    s = TypingStreak(pause_allowed=8)
    for _ in range(40):
        s.update(3.0, 0.5)  # 20 s typing
    for _ in range(10):
        s.update(0.0, 0.5)  # 5 s thinking: still the same streak
    assert s.update(3.0, 0.5) == 20.5
    for _ in range(20):
        s.update(0.0, 0.5)  # 10 s quiet: streak over
    assert s.seconds == 0
