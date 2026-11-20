"""Is a video/tutorial/music playing? Pure classifier + platform probes."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass

BROWSERS = ("chrome", "chromium", "firefox", "brave", "edge", "opera", "vivaldi", "zen", "librewolf", "safari")
VIDEO_APPS = (
    "vlc",
    "mpv",
    "totem",
    "celluloid",
    "smplayer",
    "haruna",
    "mplayer",
    "videos",
    "movies",
    "media player",
    "potplayer",
    "kodi",
)
MUSIC_APPS = (
    "spotify",
    "rhythmbox",
    "lollypop",
    "amberol",
    "elisa",
    "clementine",
    "strawberry",
    "audacious",
    "musicbee",
    "foobar",
    "itunes",
    "music",
)
SITES = {
    "udemy": "udemy",
    "coursera": "coursera",
    "youtube": "youtube",
    "netflix": "netflix",
    "prime video": "prime",
    "hotstar": "hotstar",
    "linkedin learning": "linkedin",
    "pluralsight": "pluralsight",
    "skillshare": "skillshare",
}
COURSE_SITES = {"udemy", "coursera", "linkedin", "pluralsight", "skillshare"}
TUTORIAL = re.compile(
    r"\b(tutorial|course|lecture|lesson|learn(ing)?|beginners?|crash course|how to|explained|"
    r"bootcamp|masterclass|chapter|part \d+|full course|in \d+ (minutes|hours)|interview prep|dsa|"
    r"sikho|seekho|sikhe|seekhe|samjho|samjhe|padhai|in hindi)\b",
    re.IGNORECASE,
)
# A song on plain YouTube: the channel gives it away ("Arijit Singh - Topic", VEVO, music labels) ...
MUSIC_CHANNEL = re.compile(
    r"(- topic$|vevo|t-series|zee music|sony music|tips official|saregama|speed records|white hill|"
    r"desi music factory|yrf|times music|aditya music|lahari|think music|warner music|universal music|"
    r"atlantic records|lofi girl)",
    re.IGNORECASE,
)
# weaker hints in a channel name: checked after the study words
MUSIC_CHANNEL_HINT = re.compile(r"(music|records|entertainers|beats|melod|orchestra|band\b)", re.IGNORECASE)
# ... or the title does
MUSIC_TITLE = re.compile(
    r"(\bofficial (music |lyric(al)? )?(video|audio)\b|\blyrics?\b|\blyrical\b|\b(full|video|audio) song\b|"
    r"\bsongs?\b|\bft\.|\bfeat\.|\bjukebox\b|\bremix\b|\blo-?fi\b|\bslowed\b|\bmashup\b|\(audio\)|"
    r"\bmusic\b|\bmusicians?\b|\binstrumental\b|\borchestra\b|\bsymphony\b|\bconcert\b|\bunplugged\b|"
    r"\bkaraoke\b|\bcover\b|\bplaylist\b|\bbgm\b|\bost\b|\bsoundtrack\b|\bqawwali\b|\bghazal\b|"
    r"\bbhajan\b|\bsitar\b|\bflute\b|\bpiano\b|\bguitar\b|\bvioli?n\b|\btabla\b|\bsaxophone\b|\btrumpet\b)",
    re.IGNORECASE,
)


def youtube_kind(title: str, channel: str = "", window_title: str = "") -> str:
    """For a video in a browser: "music", "tutorial" or "video".
    A music label's channel wins; then study words ("Guitar lesson: Tum Hi Ho" is a tutorial); then music
    words in the title or channel name ("Instrumental theme", "Siddharth Entertainers")."""
    if MUSIC_CHANNEL.search(channel.strip()):
        return "music"
    if TUTORIAL.search(title) or TUTORIAL.search(window_title):
        return "tutorial"
    if MUSIC_TITLE.search(title) or MUSIC_TITLE.search(window_title) or MUSIC_CHANNEL_HINT.search(channel):
        return "music"
    return "video"


@dataclass
class MediaInfo:
    kind: str  # "video" or "music"
    site: str | None = None
    tutorial: bool = False
    title: str = ""
    player: str = ""
    channel: str = ""  # artist / YouTube channel, when the player tells


def _has(name: str, words: tuple[str, ...]) -> bool:
    n = name.lower()
    return any(w in n for w in words)


def site_of(*texts: str) -> str | None:
    blob = " ".join(texts).lower()
    if "youtube music" in blob:
        return "youtube_music"
    for needle, site in SITES.items():
        if needle in blob:
            return site
    return None


def classify(player: str, title: str, artist: str = "", window_title: str = "") -> MediaInfo | None:
    """Classify something that is currently *playing*."""
    site = site_of(window_title, title)
    if site == "youtube_music" or (_has(player, MUSIC_APPS) and not _has(player, BROWSERS)):
        return MediaInfo("music", "youtube_music" if site == "youtube_music" else None, False, title, player, artist)
    if not (_has(player, BROWSERS) or _has(player, VIDEO_APPS) or site):
        return None
    if site in COURSE_SITES:
        return MediaInfo("video", site, True, title, player, artist)
    kind = youtube_kind(title, artist, window_title)
    if kind == "music":
        return MediaInfo("music", site, False, title, player, artist)
    return MediaInfo("video", site, kind == "tutorial", title, player, artist)


def classify_window_title(window_title: str) -> MediaInfo | None:
    """Fallback when we only know the focused window's title (no playback status)."""
    site = site_of(window_title)
    if site is None or site == "youtube_music":
        return None
    if site in COURSE_SITES:
        return MediaInfo("video", site, True, window_title, "window")
    kind = youtube_kind("", "", window_title)
    if kind == "music":
        return MediaInfo("music", site, False, window_title, "window")
    return MediaInfo("video", site, kind == "tutorial", window_title, "window")


# ---------------- probes ----------------


class MprisProbe:
    """Linux: ask media players (incl. Chrome/Firefox tabs) over D-Bus what is playing."""

    name = "MPRIS (D-Bus)"

    def __init__(self):
        from jeepney.io.blocking import open_dbus_connection

        self.conn = open_dbus_connection(bus="SESSION")

    def _get(self, bus, iface, prop):
        from jeepney import DBusAddress, new_method_call

        addr = DBusAddress("/org/mpris/MediaPlayer2", bus_name=bus, interface="org.freedesktop.DBus.Properties")
        reply = self.conn.send_and_get_reply(new_method_call(addr, "Get", "ss", (iface, prop)), timeout=1)
        return reply.body[0][1]

    def read(self, window_title: str = "") -> MediaInfo | None:
        from jeepney.bus_messages import message_bus

        names = self.conn.send_and_get_reply(message_bus.ListNames(), timeout=1).body[0]
        best = None
        for bus in names:
            if not bus.startswith("org.mpris.MediaPlayer2."):
                continue
            try:
                if self._get(bus, "org.mpris.MediaPlayer2.Player", "PlaybackStatus") != "Playing":
                    continue
                ident = self._get(bus, "org.mpris.MediaPlayer2", "Identity") or bus
                md = self._get(bus, "org.mpris.MediaPlayer2.Player", "Metadata")
            except Exception:
                continue
            title = md.get("xesam:title", ("s", ""))[1] or ""
            artist = md.get("xesam:artist", ("as", []))[1]
            artist = ", ".join(artist) if isinstance(artist, list) else str(artist)
            info = classify(f"{ident} {bus}", title, artist, window_title)
            if info and (best is None or (info.kind == "video" and best.kind != "video")):
                best = info
        return best


class WindowsMediaProbe:
    """Windows 10+: System Media Transport Controls (what the media overlay shows)."""

    name = "Windows media session"

    def __init__(self):
        from winrt.windows.media.control import (  # type: ignore
            GlobalSystemMediaTransportControlsSessionManager as Manager,
        )

        self._Manager = Manager
        import asyncio

        self._loop = asyncio.new_event_loop()

    async def _read(self, window_title):
        mgr = await self._Manager.request_async()
        best = None
        for s in mgr.get_sessions():
            info = s.get_playback_info()
            if int(info.playback_status) != 4:  # 4 = Playing
                continue
            props = await s.try_get_media_properties_async()
            app = s.source_app_user_model_id or ""
            m = classify(app, props.title or "", props.artist or "", window_title)
            if m and (best is None or (m.kind == "video" and best.kind != "video")):
                best = m
        return best

    def read(self, window_title: str = "") -> MediaInfo | None:
        return self._loop.run_until_complete(self._read(window_title))


def _osascript(script: str, timeout: float = 2.0) -> str:
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout, check=False)
    return out.stdout.strip()


class MacMediaProbe:
    """macOS: is Spotify / Apple Music playing? (macOS asks once to allow controlling them)."""

    name = "macOS Music/Spotify"

    def __init__(self):
        from pathlib import Path

        apps = []
        if Path("/Applications/Spotify.app").exists():
            apps.append("Spotify")
        if Path("/System/Applications/Music.app").exists():
            apps.append("Music")
        lines = ['set out to ""']
        for app in apps:  # only reference installed apps, or the script won't compile
            lines.append(
                f'if application "{app}" is running then\n'
                f'  tell application "{app}" to if player state is playing then '
                f'set out to out & "{app}|" & (name of current track) & linefeed\n'
                "end if"
            )
        lines.append("return out")
        self.script = "\n".join(lines)

    def read(self, window_title: str = "") -> MediaInfo | None:
        for line in _osascript(self.script).splitlines():
            app, _, title = line.partition("|")
            info = classify(app, title, "", window_title)
            if info:
                return info
        return None


class MacTitleProbe:
    """macOS: the frontmost app, or the active tab title when it's Chrome / Safari / Edge / Brave."""

    name = "macOS front window (AppleScript)"
    BROWSERS = {
        "Google Chrome": "title of active tab of front window",
        "Microsoft Edge": "title of active tab of front window",
        "Brave Browser": "title of active tab of front window",
        "Safari": "name of current tab of front window",
    }

    def __init__(self):
        if sys.platform != "darwin":
            raise OSError("macOS only")
        self.read()

    def read(self) -> str:
        front = _osascript(
            'tell application "System Events" to get name of first application process whose frontmost is true'
        )
        expr = self.BROWSERS.get(front)
        if not expr:
            return front
        title = _osascript(f'tell application "{front}" to if (count of windows) > 0 then get {expr}')
        return f"{title} - {front}" if title else front


class WindowTitleProbe:
    """Title of the focused window (Windows, or X11 / XWayland windows on Linux)."""

    def __init__(self):
        if sys.platform == "win32":
            import ctypes

            self._u32 = ctypes.windll.user32
            self.name = "Win32 foreground window"
        else:
            subprocess.run(["xprop", "-version"], capture_output=True, check=True, timeout=2)
            self.name = "xprop (X11)"

    def read(self) -> str:
        if sys.platform == "win32":
            import ctypes

            hwnd = self._u32.GetForegroundWindow()
            n = self._u32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            self._u32.GetWindowTextW(hwnd, buf, n + 1)
            return buf.value
        out = subprocess.run(
            ["xprop", "-root", "_NET_ACTIVE_WINDOW"], capture_output=True, text=True, timeout=1, check=False
        ).stdout
        m = re.search(r"window id # (0x[0-9a-f]+)", out)
        if not m or m.group(1) == "0x0":
            return ""
        out = subprocess.run(
            ["xprop", "-id", m.group(1), "_NET_WM_NAME"], capture_output=True, text=True, timeout=1, check=False
        ).stdout
        m = re.search(r'= "(.*)"', out)
        return m.group(1) if m else ""
