"""Saarthi's state, in one place (Pydantic): the parent schema.

Everything Saarthi works out about what you're doing on this computer, and what the character is doing
about it, goes into one `SaarthiState`. The app builds it on every tick from the same readings the
animation uses, so this is exactly what drives the character. When a Glitch is set (config `glitch_url`),
this is what gets sent to it (see glitch.py); Glitch decides how to use it.

Only what you're doing goes in. Weather, traffic, battery, reminders, breaks, lunch and walking are
Saarthi's own features and stay out. Keep this file the single source: bump SCHEMA_VERSION when a field
changes meaning.
"""

from __future__ import annotations

import socket
import sys
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1

MediaKind = Literal["music", "video", "tutorial"]
TypingSpeed = Literal["none", "slow", "fast"]


class Media(BaseModel):
    """What is playing. On YouTube: music, a tutorial, or any other video (see activity/media.py)."""

    kind: MediaKind
    site: str = ""  # "youtube", "udemy", "youtube_music", "netflix" … ("" when unknown)
    title: str = ""
    channel: str = ""  # artist or YouTube channel, when the player tells


class SaarthiState(BaseModel):
    schema_version: int = SCHEMA_VERSION
    source: str = Field(default="linux", max_length=20)  # linux / windows / macos (android: the phone app)
    device: str = Field(default="", max_length=60)
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # what Saarthi saw
    typing: TypingSpeed = "none"
    keys_per_sec: float = 0.0  # how fast, never which keys
    scrolling: bool = False
    scrolls_per_sec: float = 0.0
    idle_seconds: int = 0
    media: Media | None = None  # None = nothing playing

    # what the character is doing about it
    state: str = "idle"  # the animation: idle / typing_fast / typing_slow / scrolling / watching / afk / sleeping …
    take: str = ""  # its variant, e.g. "notes" (tutorial) or "popcorn" (other video)

    def same_moment(self, other: SaarthiState | None) -> bool:
        """True if nothing worth telling changed (rates and idle seconds tick all the time)."""
        if other is None:
            return False
        keep = {"typing", "scrolling", "media", "state", "take"}
        away = (self.idle_seconds >= 120, other.idle_seconds >= 120)
        return self.model_dump(include=keep) == other.model_dump(include=keep) and away[0] == away[1]


def platform_name() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, sys.platform)[:20]


def build(activity, state: str, take: str = "", fast_kps: float = 4.0, slow_kps: float = 0.3,
          scroll_ps: float = 0.8) -> SaarthiState:  # fmt: skip
    """SaarthiState from the app's Activity (states.Activity) and the character's state + take."""
    a = activity
    media = None
    if a.video_playing or a.music_playing:
        kind = "music" if a.music_playing else ("tutorial" if a.media_tutorial else "video")
        media = Media(kind=kind, site=a.media_site or "", title=a.media_title, channel=a.media_channel)
    typing = "fast" if a.keys_per_sec >= fast_kps else ("slow" if a.keys_per_sec >= slow_kps else "none")
    return SaarthiState(
        source=platform_name(),
        device=socket.gethostname()[:60],
        typing=typing,
        keys_per_sec=round(a.keys_per_sec, 1),
        scrolling=a.scrolls_per_sec >= scroll_ps,
        scrolls_per_sec=round(a.scrolls_per_sec, 1),
        idle_seconds=int(max(0, a.idle_seconds)),
        media=media,
        state=state,
        take=take,
    )
