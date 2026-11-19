from saarthi.states import Activity, State, StateMachine, Thresholds, resolve


def run(sm, activity, start, seconds, step=0.25):
    t = start
    while t < start + seconds:
        sm.update(activity, t)
        t += step
    return t


def test_classify_basic():
    sm = StateMachine()
    assert sm.classify(Activity()) == State.IDLE
    assert sm.classify(Activity(keys_per_sec=6)) == State.TYPING_FAST
    assert sm.classify(Activity(keys_per_sec=1)) == State.TYPING_SLOW
    assert sm.classify(Activity(scrolls_per_sec=2)) == State.SCROLLING
    assert sm.classify(Activity(idle_seconds=200)) == State.AFK
    assert sm.classify(Activity(idle_seconds=1000)) == State.SLEEPING


def test_video_beats_afk_but_not_forever():
    sm = StateMachine()
    assert sm.classify(Activity(video_playing=True, idle_seconds=1200)) == State.WATCHING
    assert sm.classify(Activity(video_playing=True, idle_seconds=4000)) == State.SLEEPING
    assert sm.classify(Activity(video_playing=True, keys_per_sec=8)) == State.TYPING_FAST


def test_hysteresis_ignores_blips():
    sm = StateMachine()
    sm.update(Activity(), 0)
    sm.update(Activity(keys_per_sec=6), 0.25)
    assert sm.state == State.IDLE
    run(sm, Activity(keys_per_sec=6), 0.5, 2)
    assert sm.state == State.TYPING_FAST


def test_wakes_up_after_sleep():
    sm = StateMachine()
    sm.update(Activity(idle_seconds=1000), 0)
    assert sm.state == State.SLEEPING
    assert sm.update(Activity(keys_per_sec=1), 1) == State.WAKING
    t = run(sm, Activity(keys_per_sec=1), 1.25, 2.5)
    run(sm, Activity(keys_per_sec=1), t, 2)
    assert sm.state == State.TYPING_SLOW


def test_stretch_after_long_session():
    sm = StateMachine(Thresholds(stretch_after_min=0.05))  # 3 seconds
    run(sm, Activity(keys_per_sec=1), 0, 4)
    assert sm.state == State.STRETCH


def test_trigger_and_preview():
    sm = StateMachine()
    sm.trigger(State.ALERT, 0)
    assert sm.update(Activity(keys_per_sec=6), 1) == State.ALERT
    sm.preview = State.SLEEPING
    assert sm.update(Activity(), 20) == State.SLEEPING


def test_resolve_fallback_chain():
    assert resolve(State.TYPING_FAST, {State.IDLE, State.TYPING_SLOW}) == State.TYPING_SLOW
    assert resolve(State.SLEEPING, {State.IDLE}) == State.IDLE
    assert resolve(State.WAKING, {State.IDLE, State.HAPPY}) == State.HAPPY


def test_typing_wins_over_a_background_video():
    sm = StateMachine()
    assert sm.classify(Activity(video_playing=True, keys_per_sec=0.5)) == State.WATCHING  # a stray key
    assert sm.classify(Activity(video_playing=True, keys_per_sec=2.0)) == State.TYPING_SLOW
    assert sm.classify(Activity(video_playing=True, keys_per_sec=6.0)) == State.TYPING_FAST
