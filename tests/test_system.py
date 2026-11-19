import sys

from saarthi import system


def test_linux_autostart_roundtrip(tmp_path, monkeypatch):
    if not sys.platform.startswith("linux"):
        return
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert not system.autostart_enabled()
    system.set_autostart(True)
    text = (tmp_path / "autostart" / "saarthi.desktop").read_text()
    assert "Exec=" in text and "saarthi" in text
    assert system.autostart_enabled()
    system.set_autostart(False)
    assert not system.autostart_enabled()


def test_launch_command_prefers_appimage(monkeypatch):
    monkeypatch.setenv("APPIMAGE", "/opt/Saarthi.AppImage")
    assert system.launch_command() == ["/opt/Saarthi.AppImage"]
    monkeypatch.delenv("APPIMAGE")
    assert system.launch_command()[-2:] == ["-m", "saarthi"]


class _Src:
    def __init__(self, text):
        self.text = text

    def status(self):
        return {"Typing & scroll": self.text}


def test_typing_problem_detection(monkeypatch):
    from saarthi.onboarding import typing_problem

    assert typing_problem(_Src("evdev (/dev/input): 3 device(s)")) is None
    monkeypatch.setattr("sys.platform", "linux")
    assert typing_problem(_Src("pynput: listening (partial: only apps running under XWayland). ...")) == "wayland"
    assert typing_problem(_Src("pynput: listening")) is None


def test_old_deskbuddy_data_moves_to_saarthi(tmp_path, monkeypatch):
    import json

    if not sys.platform.startswith("linux"):
        return
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    old = tmp_path / "deskbuddy"
    (old / "skins" / "me").mkdir(parents=True)
    (old / "data.json").write_text('{"notes": [{"text": "keep me"}]}')
    (old / "config.json").write_text(json.dumps({"skin": f"folder:{old / 'skins' / 'me'}"}))

    from saarthi.config import Config, config_dir

    new = config_dir()
    assert new == tmp_path / "saarthi"
    assert "keep me" in (new / "data.json").read_text()
    assert Config()["skin"] == f"folder:{new / 'skins' / 'me'}"
    assert old.exists()  # the old folder is left untouched as a backup
