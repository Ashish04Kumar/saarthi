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


def test_youtube_music_video_and_tutorial_are_told_apart():
    def kind(title, channel=""):
        m = classify("Chrome", title, channel, window_title=f"{title} - YouTube - Google Chrome")
        return "tutorial" if m.kind == "video" and m.tutorial else m.kind

    assert kind("Kesariya - Brahmastra | Official Video", "Sony Music India") == "music"
    assert kind("Tum Hi Ho", "Arijit Singh - Topic") == "music"
    assert kind("Pasoori (Lyrics) ft. Shae Gill", "Coke Studio") == "music"
    assert kind("JavaScript Tutorial For Beginners", "Intellipaat") == "tutorial"
    assert kind("Python full course in Hindi", "CodeWithHarry") == "tutorial"
    assert kind("Guitar lesson: Tum Hi Ho song", "Guitar Guru") == "tutorial"  # study words beat song words
    assert kind("INSTRUMENTAL THEME MUSIC | LAXMIKANT PYARELAL | 40 MUSICIANS", "Siddharth Entertainers") == "music"
    assert kind("Sitar for focus and calm", "Shanti") == "music"
    assert kind("Music theory for beginners", "Music Matters") == "tutorial"  # study words beat music hints
    assert kind("Live at the hall", "The Sky Band") == "music"  # channel hint
    assert kind("Piano tutorial: Tum Hi Ho", "Learn Keys") == "tutorial"  # study words beat instrument words
    assert kind("Manali trip vlog | Day 2", "Travel Bro") == "video"
    assert kind("Kapil Sharma Show Ep 12", "SET India") == "video"


def test_lines_take_turns_instead_of_repeating():
    from saarthi.lines import LINES, line_for
    from saarthi.states import State

    options = LINES["en"][State.SCROLLING]
    for _ in range(3):
        said = [line_for(State.SCROLLING, "en") for _ in options]
        assert sorted(said) == sorted(options)  # each one once per round
    assert not any("five more minutes" in line for line in options)
    seq = [line_for(State.SCROLLING, "en") for _ in range(40)]
    assert all(a != b for a, b in zip(seq, seq[1:], strict=False))  # never twice in a row
