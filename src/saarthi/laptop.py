"""What the laptop itself is up to: battery, charger, CPU heat, internet, uptime, headphones, volume.

Two halves:
* LaptopProbe: a background thread that reads the machine every few seconds (psutil + small
  per-OS helpers) and keeps the latest Snapshot. Nothing here talks to the UI.
* LaptopWatch: pure logic. Feed it snapshots and it returns the moments worth a reaction
  ("battery_low", "charger_in", "net_down", ...), with thresholds and cool-downs so it never nags.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field

BATTERY_LEVELS = (15, 10)  # warn once when it drops below each of these
BATTERY_CRITICAL = 5  # below this: loud, and again every CRITICAL_REPEAT seconds
CRITICAL_REPEAT = 120.0
CPU_BUSY = 85.0  # % averaged over CPU_WINDOW seconds
CPU_WINDOW = 90.0
CPU_HOT_C = 88.0  # hottest CPU sensor
CPU_COOL_C = 75.0
HOT_REPEAT = 15 * 60.0
UPTIME_DAYS = 3.0
UPTIME_REPEAT = 24 * 3600.0
UPTIME_FIRST_AFTER = 10 * 60.0  # don't open with "restart your laptop"
LATE_HOURS = range(0, 5)  # 00:00-04:59
LATE_REPEAT = 45 * 60.0
VOLUME_LOUD = 100


@dataclass
class Snapshot:
    battery: float | None = None  # %; None = no battery (desktop) or unknown
    plugged: bool | None = None
    cpu: float | None = None  # % busy since the last reading
    temp: float | None = None  # hottest CPU sensor, deg C (Linux only)
    online: bool | None = None
    uptime_days: float | None = None
    headphones: bool | None = None
    muted: bool | None = None
    volume: int | None = None  # %; can go past 100 on Linux


@dataclass
class LaptopWatch:
    started: float = 0.0
    _prev: Snapshot = field(default_factory=Snapshot)
    _warned: int = 101  # lowest battery level already warned about
    _critical_at: float = -1e9
    _full_said: bool = False
    _cpu: deque = field(default_factory=deque)  # (time, %)
    hot: bool = False
    _hot_at: float = -1e9
    _online: bool | None = None
    _net_vote: list = field(default_factory=list)
    _down_since: float = 0.0
    _uptime_at: float = -1e9
    _late_at: float = -1e9

    def low_battery(self) -> bool:
        p = self._prev
        return p.battery is not None and p.plugged is False and p.battery <= BATTERY_LEVELS[0]

    def update(self, s: Snapshot, now: float, hour: int = 12, active: bool = True) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        prev = self._prev
        out += self._battery(prev, s, now)
        out += self._heat(s, now)
        out += self._network(s, now)
        if (
            s.uptime_days is not None
            and s.uptime_days >= UPTIME_DAYS
            and now - self.started >= UPTIME_FIRST_AFTER
            and now - self._uptime_at >= UPTIME_REPEAT
        ):
            self._uptime_at = now
            out.append(("uptime", {"days": int(s.uptime_days)}))
        if prev.headphones is not None and s.headphones is not None and s.headphones != prev.headphones:
            out.append(("headphones_on" if s.headphones else "headphones_off", {}))
        if prev.muted is not None and s.muted is not None and s.muted != prev.muted:
            out.append(("muted" if s.muted else "unmuted", {}))
        if prev.volume is not None and s.volume is not None and not s.muted and prev.volume < VOLUME_LOUD <= s.volume:
            out.append(("volume_max", {"vol": s.volume}))
        if hour in LATE_HOURS and active and now - self._late_at >= LATE_REPEAT:
            self._late_at = now
            out.append(("late_night", {}))
        self._prev = s
        return out

    # ---- pieces ----
    def _battery(self, prev: Snapshot, s: Snapshot, now: float) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        if s.battery is None or s.plugged is None:
            return out
        pct = int(round(s.battery))
        if prev.plugged is not None and s.plugged != prev.plugged:
            out.append(("charger_in", {"pct": pct}) if s.plugged else ("charger_out", {"pct": pct}))
        if s.plugged:
            self._warned = 101
            if pct >= 100 and not self._full_said and prev.plugged is not None:
                self._full_said = True
                out.append(("battery_full", {}))
            if pct < 95:
                self._full_said = False
            return out
        self._full_said = False
        if pct <= BATTERY_CRITICAL:
            if now - self._critical_at >= CRITICAL_REPEAT:
                self._critical_at = now
                self._warned = BATTERY_CRITICAL
                out.append(("battery_critical", {"pct": pct}))
            return out
        for level in BATTERY_LEVELS:
            if pct <= level < self._warned:
                self._warned = level
                out.append(("battery_low", {"pct": pct}))
                break
        return out

    def _heat(self, s: Snapshot, now: float) -> list[tuple[str, dict]]:
        if s.cpu is not None:
            self._cpu.append((now, s.cpu))
        while self._cpu and now - self._cpu[0][0] > CPU_WINDOW:
            self._cpu.popleft()
        span = self._cpu[-1][0] - self._cpu[0][0] if len(self._cpu) > 1 else 0.0
        avg = sum(c for _, c in self._cpu) / len(self._cpu) if self._cpu else 0.0
        busy = span >= CPU_WINDOW * 0.8 and avg >= CPU_BUSY
        too_hot = s.temp is not None and s.temp >= CPU_HOT_C
        if busy or too_hot:
            was = self.hot
            self.hot = True
            if not was and now - self._hot_at >= HOT_REPEAT:
                self._hot_at = now
                return [("cpu_hot", {"cpu": int(avg), "temp": int(s.temp) if s.temp is not None else None})]
        elif self.hot and avg < 60 and (s.temp is None or s.temp < CPU_COOL_C):
            self.hot = False
        return []

    def _network(self, s: Snapshot, now: float) -> list[tuple[str, dict]]:
        if s.online is None:
            return []
        self._net_vote = (self._net_vote + [s.online])[-2:]
        if len(self._net_vote) < 2 or self._net_vote[0] != self._net_vote[1]:
            return []  # two readings in a row before we believe a change
        if self._online is None:
            self._online = s.online
            if not s.online:
                self._down_since = now
            return []
        if s.online == self._online:
            return []
        self._online = s.online
        if not s.online:
            self._down_since = now
            return [("net_down", {})]
        return [("net_up", {"mins": max(1, int((now - self._down_since) / 60))})]


# ---------------- probes ----------------
def _run(cmd: list[str], timeout: float = 2.0) -> str:
    try:
        return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def audio_linux() -> tuple[bool | None, bool | None, int | None]:
    """(headphones, muted, volume%) from PulseAudio / PipeWire's pactl."""
    if not shutil.which("pactl"):
        return None, None, None
    sink = _run(["pactl", "get-default-sink"]).strip()
    muted = vol = None
    m = _run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
    if m:
        muted = "yes" in m.lower()
    v = re.search(r"(\d+)%", _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"]))
    if v:
        vol = int(v.group(1))
    if not sink:
        return None, muted, vol
    port = ""
    block = _run(["pactl", "list", "sinks"]).split(f"Name: {sink}", 1)
    if len(block) == 2:
        p = re.search(r"Active Port:\s*(.+)", block[1])
        port = p.group(1) if p else ""
    phones = any(k in (sink + " " + port).lower() for k in ("headphone", "headset", "bluez", "earbud", "airpods"))
    return phones, muted, vol


def audio_mac() -> tuple[bool | None, bool | None, int | None]:
    out = _run(["osascript", "-e", "get volume settings"])
    v = re.search(r"output volume:(\d+)", out)
    m = re.search(r"output muted:(true|false)", out)
    return None, (m.group(1) == "true") if m else None, int(v.group(1)) if v else None


def online(timeout: float = 2.0) -> bool:
    """Can we reach the internet at all? (Opens a TCP connection, sends nothing.)"""
    for host in (("1.1.1.1", 53), ("8.8.8.8", 53)):
        with contextlib.suppress(OSError):
            socket.create_connection(host, timeout=timeout).close()
            return True
    return False


def cpu_temp(psutil) -> float | None:
    if not hasattr(psutil, "sensors_temperatures"):
        return None
    try:
        temps = psutil.sensors_temperatures()
    except (OSError, RuntimeError):
        return None
    for key in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz"):
        vals = [t.current for t in temps.get(key, []) if t.current and 0 < t.current < 130]
        if vals:
            return max(vals)
    return None


class LaptopProbe(threading.Thread):
    """Reads the machine every `every` seconds; `latest` is the newest Snapshot (or None)."""

    def __init__(self, every: float = 5.0, net_every: float = 15.0):
        super().__init__(name="saarthi-laptop", daemon=True)
        self.every, self.net_every = every, net_every
        self.latest: Snapshot | None = None
        self._quit = threading.Event()
        self._online: bool | None = None
        self._net_at = 0.0

    def stop(self) -> None:
        self._quit.set()

    def run(self) -> None:
        try:
            import psutil
        except ImportError:
            psutil = None
        if psutil is not None:
            psutil.cpu_percent(None)  # first call only primes the counter
        while not self._quit.is_set():
            with contextlib.suppress(Exception):  # a broken sensor must never kill the thread
                self.latest = self.read(psutil)
            self._quit.wait(self.every)

    def read(self, psutil) -> Snapshot:
        s = Snapshot()
        if psutil is not None:
            with contextlib.suppress(Exception):
                b = psutil.sensors_battery()
                if b is not None:
                    s.battery, s.plugged = float(b.percent), bool(b.power_plugged)
            s.cpu = psutil.cpu_percent(None)
            s.temp = cpu_temp(psutil)
            s.uptime_days = (time.time() - psutil.boot_time()) / 86400
        now = time.monotonic()
        if now - self._net_at >= self.net_every:
            self._net_at = now
            self._online = online()
        s.online = self._online
        if sys.platform.startswith("linux"):
            s.headphones, s.muted, s.volume = audio_linux()
        elif sys.platform == "darwin":
            s.headphones, s.muted, s.volume = audio_mac()
        return s
