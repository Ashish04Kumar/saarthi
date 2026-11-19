"""Thread-safe event-rate counter. Stores timestamps only, never what was pressed."""

from __future__ import annotations

import threading
import time
from collections import deque


class RateCounter:
    def __init__(self, window: float = 3.0):
        self.window = window
        self._events: deque[float] = deque()
        self._lock = threading.Lock()
        self.last: float | None = None

    def hit(self, now: float | None = None, n: int = 1) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            for _ in range(n):
                self._events.append(now)
            self.last = now
            self._trim(now)

    def rate(self, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        with self._lock:
            self._trim(now)
            return len(self._events) / self.window

    def _trim(self, now: float) -> None:
        cutoff = now - self.window
        while self._events and self._events[0] < cutoff:
            self._events.popleft()
        if len(self._events) > 5000:  # safety cap
            for _ in range(len(self._events) - 5000):
                self._events.popleft()
