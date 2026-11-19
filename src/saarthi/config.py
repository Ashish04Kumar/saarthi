"""User config stored as JSON in the platform's config folder."""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "skin": "bundled:saarthi",  # the 3D Saarthi character; "builtin:bit" is the cartoon robot
    "size": 160,
    "position": None,  # [x, y] or None for bottom-right
    "language": "hinglish",
    "bubbles": True,
    "chatter_minutes": [20, 40],
    # weather
    "weather_enabled": True,
    "weather_place": None,  # {"name", "lat", "lon"}; None = approximate from IP
    "auto_place": None,  # cached IP lookup
    # commute
    "commute_enabled": False,
    "home": None,
    "office": None,
    "logout": "18:30",
    "commute_before": 15,
    "workdays": [0, 1, 2, 3, 4],
    "commute_provider": "free",
    "commute_mode": "car",
    "tomtom_key": "",
    "google_key": "",
    "last_commute": None,
    # wellness
    "break_enabled": True,
    "work_minutes": 50,
    "break_minutes": 5,
    "breathing_enabled": True,
    "breathing_every": [20, 20],  # minutes, random in this range
    "breathing_cycles": 5,
    "walk_enabled": True,
    "lunch_minutes": 60,
    "laptop_alerts": True,  # battery, charger, heat, internet, headphones, volume, late night
    "developer": False,  # the author's own machine: hides the developer credit
    "theme": "auto",  # auto / dark / light for Saarthi's own pop-ups
}


OLD_NAMES = {"win32": "DeskBuddy", "darwin": "DeskBuddy", "linux": "deskbuddy"}  # before the rename


def _base_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def config_dir() -> Path:
    base = _base_dir()
    d = base / ("saarthi" if sys.platform.startswith("linux") else "Saarthi")
    if not d.exists():
        _migrate_from_old_name(base, d)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _migrate_from_old_name(base: Path, new: Path) -> None:
    """The app used to be called DeskBuddy: bring its settings, notes, reminders and skins along."""
    import shutil

    old = base / OLD_NAMES["linux" if sys.platform.startswith("linux") else sys.platform]
    if not old.is_dir() or old == new:
        return
    try:
        shutil.copytree(old, new)
    except OSError:
        return
    cfg = new / "config.json"
    try:
        text = cfg.read_text(encoding="utf-8")
        # skins copied along: point at the new folder
        cfg.write_text(text.replace(json.dumps(str(old))[1:-1], json.dumps(str(new))[1:-1]), encoding="utf-8")
    except OSError:
        pass


class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or config_dir() / "config.json"
        self.data: dict[str, Any] = dict(DEFAULTS)
        with contextlib.suppress(FileNotFoundError, ValueError):
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))

    def __getitem__(self, key: str) -> Any:
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
