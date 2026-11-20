"""Live activity detection: picks the best backends for this OS/session."""

from __future__ import annotations

import contextlib
import os
import sys
import threading
import time

from ..states import Activity
from .counters import RateCounter
from .demo import DemoSource, NullSource
from .idle import make_idle_probe
from .media import (
    MacMediaProbe,
    MacTitleProbe,
    MediaInfo,
    MprisProbe,
    WindowsMediaProbe,
    WindowTitleProbe,
    classify_window_title,
)

__all__ = ["DemoSource", "LiveSource", "NullSource", "session_type"]

WAYLAND_HINT = "Run once, then log out and back in:  sudo usermod -aG input $USER"
MAC_HINT = (
    "macOS: allow Saarthi in System Settings → Privacy & Security → Accessibility "
    "and Input Monitoring, then restart it."
)


def session_type() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return os.environ.get("XDG_SESSION_TYPE", "x11").lower() or "x11"


class LiveSource:
    def __init__(self):
        self.session = session_type()
        self.keys = RateCounter(window=3.0)
        self.scrolls = RateCounter(window=2.0)
        self.last_input: float | None = None
        self.notes: dict[str, str] = {}

        self.input = self._start_input()
        self._idle = 0.0
        self._idle_at = time.monotonic()
        self._has_idle = False
        self.media: MediaInfo | None = None
        self.window_title = ""
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._poller = threading.Thread(target=self._poll_loop, daemon=True, name="saarthi-poll")
        self._poller.start()
        self._ready.wait(3)

    # ---------- input ----------
    def _touched(self) -> None:
        self.last_input = time.monotonic()

    def _start_input(self):
        # On Wayland pynput is a partial fallback: it only sees XWayland apps.
        order = (["evdev"] if sys.platform.startswith("linux") else []) + ["pynput"]
        errors = []
        for name in order:
            try:
                if name == "evdev":
                    from .inputs import EvdevInput

                    backend = EvdevInput(self.keys, self.scrolls, self._touched)
                else:
                    from .inputs import PynputInput

                    backend = PynputInput(self.keys, self.scrolls, self._touched)
                backend.start()
                partial = name == "pynput" and self.session == "wayland"
                self.notes["Typing & scroll"] = f"{backend.name}: {backend.summary()}" + (
                    " (partial: only apps running under XWayland). " + WAYLAND_HINT if partial else ""
                )
                if sys.platform == "darwin":
                    self.notes["Typing & scroll"] += ". " + MAC_HINT
                return backend
            except Exception as e:
                errors.append(f"{name}: {e}")
        hint = f" {WAYLAND_HINT}" if sys.platform.startswith("linux") else ""
        self.notes["Typing & scroll"] = "unavailable (" + "; ".join(errors) + ")." + hint
        return None

    # ---------- polling (idle + media), off the UI thread ----------
    def _poll_loop(self) -> None:
        idle = make_idle_probe(self.session)
        self._has_idle = idle is not None
        self.notes["Idle time"] = idle.name if idle else "from input events only"

        title_probe = media_probe = None
        with contextlib.suppress(Exception):
            if sys.platform == "darwin":
                title_probe = MacTitleProbe()
            elif sys.platform == "win32" or self.session == "x11":
                title_probe = WindowTitleProbe()
        try:
            if sys.platform == "win32":
                media_probe = WindowsMediaProbe()
            elif sys.platform == "darwin":
                media_probe = MacMediaProbe()
            else:
                media_probe = MprisProbe()
        except Exception as e:
            self.notes["Video / tutorials"] = f"window titles only ({type(e).__name__})"
        if media_probe:
            self.notes["Video / tutorials"] = media_probe.name + (f" + {title_probe.name}" if title_probe else "")
        elif title_probe:
            self.notes["Video / tutorials"] = f"{title_probe.name} (title guess)"
        elif "Video / tutorials" not in self.notes:
            self.notes["Video / tutorials"] = "unavailable"
        self._ready.set()

        tick = 0
        while not self._stop.is_set():
            if idle:
                with contextlib.suppress(Exception):
                    self._idle, self._idle_at = idle.read(), time.monotonic()
            if tick % 2 == 0:
                title = ""
                if title_probe:
                    try:
                        title = title_probe.read()
                    except Exception:
                        title = ""
                self.window_title = title
                media = None
                if media_probe:
                    try:
                        media = media_probe.read(title)
                    except Exception:
                        media = None
                if media is None and title:
                    guess = classify_window_title(title)
                    # Only a guess: count it once you've stopped touching things for a bit.
                    if guess and self.idle_seconds() >= 8:
                        media = guess
                self.media = media
            tick += 1
            self._stop.wait(1.0)

    # ---------- public ----------
    def idle_seconds(self, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        candidates = []
        if self._has_idle:
            candidates.append(self._idle + (now - self._idle_at))
        if self.last_input is not None:
            candidates.append(now - self.last_input)
        return max(0.0, min(candidates)) if candidates else 0.0

    def read(self, now: float) -> Activity:
        m = self.media
        return Activity(
            keys_per_sec=self.keys.rate(now),
            scrolls_per_sec=self.scrolls.rate(now),
            idle_seconds=self.idle_seconds(now),
            video_playing=bool(m and m.kind == "video"),
            music_playing=bool(m and m.kind == "music"),
            media_site=m.site if m else None,
            media_tutorial=bool(m and m.tutorial),
            media_title=m.title if m else "",
            media_channel=m.channel if m else "",
        )

    def status(self) -> dict[str, str]:
        return dict(self.notes)

    def stop(self) -> None:
        self._stop.set()
        if self.input is not None:
            self.input.stop()
