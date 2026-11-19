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
