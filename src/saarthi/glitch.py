"""Send Saarthi's state (schema.SaarthiState) to your Glitch, when `glitch_url` is set.

POSTs JSON to <glitch_url>/api/saarthi/state when the moment changes, and at least every HEARTBEAT
seconds so Glitch knows Saarthi is alive. Runs on its own thread: the app only hands over the latest
state. Standard library only; never raises into the app.
"""

from __future__ import annotations

import contextlib
import json
import threading
import urllib.error
import urllib.request

from . import clock
from .schema import SaarthiState

HEARTBEAT = 30.0
PATH = "/api/saarthi/state"


class GlitchLink:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.latest: SaarthiState | None = None
        self.sent: SaarthiState | None = None
        self.sent_at = 0.0  # clock.now() of the last good send
        self.error = ""  # why the last send failed, for "What I see…"
        self._wake = threading.Event()
        self._quit = threading.Event()

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def start(self) -> None:
        if self.enabled:
            threading.Thread(target=self._loop, name="saarthi-glitch", daemon=True).start()

    def stop(self) -> None:
        self._quit.set()
        self._wake.set()

    def offer(self, state: SaarthiState) -> None:
        """Called on every app tick: cheap. Wakes the sender only when the moment changed."""
        self.latest = state
        if not state.same_moment(self.sent):
            self._wake.set()

    def _loop(self) -> None:
        while not self._quit.is_set():
            self._wake.wait(HEARTBEAT)
            self._wake.clear()
            if self._quit.is_set():
                return
            with contextlib.suppress(Exception):
                self.send_due(clock.now())

    def send_due(self, now: float) -> bool:
        s = self.latest
        if s is None:
            return False
        if s.same_moment(self.sent) and now - self.sent_at < HEARTBEAT:
            return False
        if self.post(s):
            self.sent, self.sent_at, self.error = s, now, ""
            return True
        return False

    def post(self, state: SaarthiState) -> bool:
        req = urllib.request.Request(
            self.url + PATH,
            data=state.model_dump_json().encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                res.read()
            return True
        except urllib.error.HTTPError as e:
            self.error = f"HTTP {e.code}"
        except (urllib.error.URLError, OSError) as e:
            self.error = type(e).__name__
        return False


def describe(link: GlitchLink) -> str:
    if not link.enabled:
        return "not connected (set glitch_url in config.json)"
    if link.sent_at:
        return f"{link.url}: sent {int(clock.now() - link.sent_at)} s ago"
    return f"{link.url}: not reached yet{f' ({link.error})' if link.error else ''}"


def to_json(state: SaarthiState) -> str:
    return json.dumps(json.loads(state.model_dump_json()), indent=2, ensure_ascii=False)
