from saarthi.activity.counters import RateCounter
from saarthi.activity.media import classify, classify_window_title
from saarthi.lines import line_for


def test_rate_counter_window():
    c = RateCounter(window=2.0)
    for i in range(10):
        c.hit(now=100 + i * 0.1)
    assert c.rate(now=101) == 5.0
    assert c.rate(now=104) == 0.0


def test_youtube_tutorial_in_chrome():
    m = classify(
        "Chrome org.mpris.MediaPlayer2.chromium.instance1",
        "Python FastAPI Tutorial: Full Course for Beginners",
        "Corey Schafer",
    )
    assert m.kind == "video" and m.tutorial


def test_udemy_window_title():
    m = classify("Chrome", "Section 3: Hooks", window_title="React - The Complete Guide | Udemy - Google Chrome")
    assert m.site == "udemy" and m.tutorial


def test_music_is_not_video():
    assert classify("Spotify org.mpris.MediaPlayer2.spotify", "Kesariya").kind == "music"
    assert classify("Chrome", "Kesariya", window_title="YouTube Music").kind == "music"


def test_plain_browser_video_not_tutorial():
    m = classify("Firefox", "Funny cats compilation", window_title="Funny cats - YouTube — Mozilla Firefox")
    assert m.kind == "video" and m.site == "youtube" and not m.tutorial


def test_unknown_player_ignored():
    assert classify("SomeRandomApp", "notification sound") is None


def test_window_title_fallback():
    assert classify_window_title("Inbox - Gmail - Google Chrome") is None
    assert classify_window_title("Learn Rust in 1 hour - YouTube - Google Chrome").tutorial


def test_line_key_falls_back_to_state():
    assert line_for("watching:netflix", "hinglish") is not None


def _fake_evdev():
    from types import SimpleNamespace

    from saarthi.activity.inputs import EvdevInput

    keys, scrolls = RateCounter(10), RateCounter(10)
    e = object.__new__(EvdevInput)
    import threading

    # run the real Thread setup: our names must not clash with Thread internals (_handle, _stop, ...)
    threading.Thread.__init__(e, daemon=True)
    e.keys, e.scrolls, e.touched = keys, scrolls, lambda: None
    e.touch = {"tp": {"two": False, "y": None, "acc": 0.0, "step": 10.0}}

    def ev(t, c, v):
        return SimpleNamespace(type=t, code=c, value=v)

    return e, keys, scrolls, ev


def test_evdev_counts_presses_not_repeats_or_releases():
    e, keys, _, ev = _fake_evdev()
    for v in (1, 2, 2, 0, 1, 0):  # press, repeat, repeat, release, press, release
        e._on_event("kbd", ev(1, 30, v))
    e._on_event("kbd", ev(1, 0x110, 1))  # mouse button isn't typing
    assert keys.rate() * 10 == 2


def test_evdev_wheel_and_touchpad_scroll():
    e, _, scrolls, ev = _fake_evdev()
    e._on_event("mouse", ev(2, 8, -1))
    e._on_event("tp", ev(1, 333, 1))  # two fingers down
    for y in (100, 110, 120, 135):
        e._on_event("tp", ev(3, 54, y))
    e._on_event("tp", ev(1, 333, 0))
    e._on_event("tp", ev(3, 54, 500))  # one finger moving: not a scroll
    assert scrolls.rate() * 10 == 1 + 3
