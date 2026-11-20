import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_bundled_saarthi_is_the_default_and_loads_everywhere(tmp_path):
    _app()
    from saarthi import skin
    from saarthi.config import DEFAULTS
    from saarthi.states import State

    assert DEFAULTS["skin"] == skin.DEFAULT_SKIN == "bundled:saarthi"
    found = skin.discover(tmp_path)
    assert "bundled:saarthi" in found and "builtin:bit" in found
    s = skin.load("bundled:saarthi")
    assert set(State) <= s.states()  # every state has frames
    assert type(skin.load("builtin:bit")).__name__ == "BitSkin"
    assert type(skin.load("bundled:missing")).__name__ == "BitSkin"  # graceful fallback


def test_credit_shows_unless_developer():
    _app()
    from saarthi import CREDIT, skin
    from saarthi.window import BuddyWindow

    sk = skin.load("builtin:bit")
    shown = BuddyWindow(sk, 160, credit=CREDIT)
    hidden = BuddyWindow(sk, 160, credit=None)
    assert "Ashish Kumar" in CREDIT and "ashishishere11@gmail.com" in CREDIT
    assert shown.height() == 160 + shown.credit_height() > hidden.height() == 160


def test_bundled_skin_has_study_and_fun_watching_takes():
    _app()
    from saarthi import skin
    from saarthi.app import FUN_TAKES, STUDY_TAKES
    from saarthi.states import State

    s = skin.load("bundled:saarthi")
    assert set(STUDY_TAKES) | set(FUN_TAKES) <= s.variants(State.WATCHING)
    assert s.variants(State.SLEEPING) == set()


def test_watch_take_suits_the_video():
    from saarthi.app import FUN_TAKES, STUDY_TAKES, pick_watch_take

    every = set(STUDY_TAKES) | set(FUN_TAKES)
    for _ in range(30):
        assert pick_watch_take(True, every) in STUDY_TAKES  # no popcorn during a tutorial
        assert pick_watch_take(False, every) in FUN_TAKES
        assert pick_watch_take(True, every, "notes") != "notes"  # switches to something new
    assert pick_watch_take(True, {"popcorn"}) is None  # skin without study takes: plain watching
    assert pick_watch_take(False, {"popcorn"}, "popcorn") == "popcorn"


def test_sprite_variant_keys_load(tmp_path):
    _app()
    import json

    from PySide6.QtGui import QColor, QImage

    from saarthi import skin
    from saarthi.states import State

    for sub, color in (("w", "red"), ("wn", "blue")):
        (tmp_path / sub).mkdir()
        img = QImage(8, 8, QImage.Format.Format_ARGB32)
        img.fill(QColor(color))
        img.save(str(tmp_path / sub / "0.png"))
    (tmp_path / "skin.json").write_text(
        json.dumps(
            {
                "states": {
                    "watching": {"frames": "w/*.png"},
                    "watching.notes": {"frames": "wn/*.png"},
                    "bogus.x": {"frames": "w/*.png"},
                }
            }
        )
    )
    s = skin.SpriteSkin(tmp_path)
    assert s.states() == {State.WATCHING} and s.variants(State.WATCHING) == {"notes"}


def test_clicks_only_count_on_the_character():
    _app()
    from PySide6.QtCore import QPoint

    from saarthi import skin
    from saarthi.window import BuddyWindow

    w = BuddyWindow(skin.load("bundled:saarthi"), 200, credit=None)
    w.resize(w.size())
    w.grab()  # renders one frame
    assert w._hits_character(QPoint(w.width() // 2, int(w.height() * 0.75)))  # the body
    assert not w._hits_character(QPoint(2, 2))  # empty corner
    body = w._body
    assert not body.isEmpty() and body.top() > 0  # head is below the window top: bubble can sit lower


def test_clicking_shoes_and_jeans_is_told_apart():
    _app()
    from PySide6.QtCore import QPoint

    from saarthi import skin
    from saarthi.states import State
    from saarthi.window import BuddyWindow

    sk = skin.load("bundled:saarthi")
    assert {"boots", "jeans"} <= sk.variants(State.POKED)
    assert {"tired", "hot", "music"} <= sk.variants(State.IDLE)
    w = BuddyWindow(sk, 256, credit=None)
    w.grab()
    seen = {
        w.part_at(QPoint(x, y))
        for x in range(0, w.width(), 4)
        for y in range(0, w.height(), 4)
        if w._hits_character(QPoint(x, y))
    }
    assert {"head", "body", "jeans", "boots"} <= seen
    assert w.part_at(QPoint(w.width() // 2, w._body.top() + 10)) == "head"
