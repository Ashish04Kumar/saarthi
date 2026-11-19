"""Scripted activity for demo mode, and a do-nothing source."""

from __future__ import annotations

from ..states import Activity

SCRIPT: list[tuple[float, Activity]] = [
    (6, Activity()),
    (7, Activity(keys_per_sec=1.2)),
    (7, Activity(keys_per_sec=7)),
    (6, Activity(scrolls_per_sec=2)),
    (8, Activity(video_playing=True, idle_seconds=30, media_site="udemy", media_tutorial=True)),
    (6, Activity(idle_seconds=200)),
    (6, Activity(idle_seconds=1000)),
    (6, Activity(keys_per_sec=7)),
]


class DemoSource:
    def __init__(self, start: float):
        self.start = start

    def read(self, now: float) -> Activity:
        total = sum(d for d, _ in SCRIPT)
        k = (now - self.start) % total
        for d, a in SCRIPT:
            if k < d:
                return a
            k -= d
        return SCRIPT[0][1]

    def status(self) -> dict[str, str]:
        return {"Mode": "demo (scripted activity)"}

    def stop(self) -> None:
        pass


class NullSource(DemoSource):
    def __init__(self):
        pass

    def read(self, now: float) -> Activity:
        return Activity()

    def status(self) -> dict[str, str]:
        return {"Mode": "no detection"}
