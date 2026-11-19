"""What the laptop itself is up to: battery, charger, CPU heat, internet, uptime, headphones, volume.

Two halves:
* LaptopProbe: a background thread that keeps the latest readings. It sleeps until the OS tells it
  something changed: on Linux UPower (charger, battery) and NetworkManager (Wi-Fi / LAN) send D-Bus
  signals and `pactl subscribe` reports audio changes. Only CPU load and temperature, which have no
  events, are sampled (every 5 s). Without those events (Windows, macOS) it checks once a second.
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
    _plugged: bool | None = None  # last known charger state
    _pct: float | None = None
    _warned: int = 101  # lowest battery level already warned about
    _critical_at: float = -1e9
    _full_said: bool = False
    _cpu: deque = field(default_factory=deque)  # (time, %)
    hot: bool = False
    _hot_at: float = -1e9
    _online: bool | None = None
    _down_since: float = 0.0
    _uptime_at: float = -1e9
    _late_at: float = -1e9

    def low_battery(self) -> bool:
        return self._pct is not None and self._plugged is False and self._pct <= BATTERY_LEVELS[0]

    def update(self, s: Snapshot, now: float, hour: int = 12, active: bool = True) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        prev = self._prev
        if s.battery is not None and s.plugged is not None:
            out += self.power(s.battery, s.plugged, now)
        out += self._heat(s, now)
        if s.online is not None:
            out += self.net(s.online, now)
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
    def power(self, battery: float, plugged: bool, now: float) -> list[tuple[str, dict]]:
        """Battery % and charger state. Called the moment either changes (the probe checks ~2x a second)."""
        out: list[tuple[str, dict]] = []
        was = self._plugged
        self._plugged, self._pct = plugged, battery
        pct = int(round(battery))
        if was is not None and plugged != was:
            out.append(("charger_in", {"pct": pct}) if plugged else ("charger_out", {"pct": pct}))
        if plugged:
            self._warned = 101
            if pct >= 100 and not self._full_said and was is not None:
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

    def net(self, online: bool, now: float) -> list[tuple[str, dict]]:
        """Internet on/off. The probe already filters out single failed checks, so trust it."""
        if self._online is None:  # first reading: just remember it
            self._online = online
            if not online:
                self._down_since = now
            return []
        if online == self._online:
            return []
        self._online = online
        if not online:
            self._down_since = now
            return [("net_down", {})]
        return [("net_up", {"mins": int((now - self._down_since) / 60)})]


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


def has_link(psutil=None) -> bool | None:
    """Is any network (Wi-Fi / LAN) connected? Cheap enough to ask twice a second."""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/net/route", encoding="ascii") as f:
                next(f, None)
                return any(len(c) > 2 and c[1] == "00000000" and c[0] != "lo" for c in (ln.split() for ln in f))
        except OSError:
            pass
    if psutil is None:
        return None
    try:
        stats, addrs = psutil.net_if_stats(), psutil.net_if_addrs()
    except (OSError, RuntimeError):
        return None
    for name, st in stats.items():
        if not st.isup or name.lower().startswith(("lo", "loopback")):
            continue
        if any(
            a.family == socket.AF_INET and not a.address.startswith(("127.", "169.254.")) for a in addrs.get(name, [])
        ):
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
    """Keeps `power`, `net` and `latest` (CPU, temperature, uptime, audio) up to date and calls
    `on_change()` (from this thread) whenever any of them changes."""

    def __init__(self, every: float = 5.0, net_every: float = 15.0, poll: float = 1.0):
        super().__init__(name="saarthi-laptop", daemon=True)
        self.every, self.net_every, self.poll = every, net_every, poll
        self.on_change = lambda: None
        self.latest: Snapshot | None = None  # everything except battery and internet
        self.power: tuple[float, bool] | None = None  # (battery %, plugged)
        self.power_seq = 0  # bumped on every change of `power`
        self.net: bool | None = None  # online? (link up and the internet answers)
        self.net_seq = 0
        self.events = False  # True while D-Bus change signals are arriving (no need to poll)
        self.audio_events = False  # True while `pactl subscribe` runs
        self._link: bool | None = None
        self._fails = 0
        self._retry_until = 0.0
        self._checking = False
        self._quit = threading.Event()
        self._kick = threading.Event()  # "something changed, look now"
        self._audio_kick = threading.Event()
        self._pactl: subprocess.Popen | None = None
        self._net_at = 0.0
        self._audio: tuple[bool | None, bool | None, int | None] = (None, None, None)

    def stop(self) -> None:
        self._quit.set()
        self._kick.set()
        if self._pactl is not None:
            with contextlib.suppress(OSError):
                self._pactl.terminate()

    def run(self) -> None:
        try:
            import psutil
        except ImportError:
            psutil = None
        if psutil is not None:
            psutil.cpu_percent(None)  # first call only primes the counter
        if sys.platform.startswith("linux"):
            threading.Thread(target=self._dbus_loop, name="saarthi-dbus", daemon=True).start()
            threading.Thread(target=self._pactl_loop, name="saarthi-pactl", daemon=True).start()
        next_full = next_audio = 0.0
        while not self._quit.is_set():
            now = time.monotonic()
            with contextlib.suppress(Exception):  # a broken sensor must never kill the thread
                changed = self.read_power(psutil)
                changed |= self.watch_net(psutil)
                if self._audio_kick.is_set() or now >= next_audio:
                    self._audio_kick.clear()
                    next_audio = now + (60.0 if self.audio_events else self.every)
                    audio = self.read_audio()
                    if audio != self._audio:
                        self._audio = audio
                        next_full = 0.0  # publish it now
                if now >= next_full:
                    next_full = now + self.every
                    self.latest = self.read(psutil, self._audio)
                    changed = True
                if changed:
                    self.on_change()
            wait = next_full - time.monotonic()
            if not self.events:
                wait = min(wait, self.poll)
            if self._link and not self._checking:
                wait = min(wait, self._net_at - time.monotonic())
            self._kick.wait(max(0.05, wait))
            self._kick.clear()

    def _dbus_loop(self) -> None:
        """Wake up when UPower or NetworkManager announce a change."""
        try:
            from jeepney import MatchRule, message_bus
            from jeepney.io.blocking import open_dbus_connection

            conn = open_dbus_connection(bus="SYSTEM")
        except Exception:
            return
        try:
            for rule in (
                MatchRule(type="signal", sender="org.freedesktop.UPower"),
                MatchRule(
                    type="signal", sender="org.freedesktop.NetworkManager", path="/org/freedesktop/NetworkManager"
                ),
            ):
                conn.send_and_get_reply(message_bus.AddMatch(rule), timeout=3)
            self.events = True
            last_pct = None
            while not self._quit.is_set():
                try:
                    msg = conn.receive(timeout=2.0)
                except TimeoutError:
                    continue
                body = msg.body if isinstance(msg.body, tuple) else ()
                changed = body[1] if len(body) > 1 and isinstance(body[1], dict) else None
                if changed is not None and str(msg.header.fields.get(1, "")).startswith("/org/freedesktop/UPower"):
                    # while charging UPower reports the power draw every second: ignore that noise
                    pct = changed.get("Percentage")
                    pct = int(pct[1]) if isinstance(pct, tuple) and len(pct) == 2 else None
                    wanted = {"Online", "State", "IsPresent"} & set(changed)
                    if not wanted and (pct is None or pct == last_pct):
                        continue
                    last_pct = pct if pct is not None else last_pct
                self._kick.set()
        except Exception:
            pass
        finally:
            self.events = False
            with contextlib.suppress(Exception):
                conn.close()

    def _pactl_loop(self) -> None:
        """`pactl subscribe` prints a line whenever a speaker / headphone / volume changes."""
        if not shutil.which("pactl"):
            return
        try:
            self._pactl = subprocess.Popen(
                ["pactl", "subscribe"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
            )
        except OSError:
            return
        self.audio_events = True
        try:
            for line in self._pactl.stdout:
                if self._quit.is_set():
                    break
                low = line.lower()
                if " on sink #" in low or " on server" in low or " on card #" in low:
                    self._audio_kick.set()
                    self._kick.set()
        finally:
            self.audio_events = False

    def read_audio(self) -> tuple[bool | None, bool | None, int | None]:
        if sys.platform.startswith("linux"):
            return audio_linux()
        if sys.platform == "darwin":
            return audio_mac()
        return None, None, None

    def read_power(self, psutil) -> bool:
        """Charger and battery (a few tiny sysfs reads). True if they changed."""
        if psutil is None:
            return False
        b = psutil.sensors_battery()
        if b is None:
            return False
        power = (round(float(b.percent), 1), bool(b.power_plugged))
        if power == self.power:
            return False
        self.power = power
        self.power_seq += 1
        return True

    def _set_net(self, online: bool) -> bool:
        if online == self.net:
            return False
        self.net = online
        self.net_seq += 1
        return True

    def watch_net(self, psutil) -> None:
        """Wi-Fi drops are seen at once (no route); after it reconnects we keep asking the internet
        every 2 s until it answers, then every net_every s."""
        now = time.monotonic()
        link = has_link(psutil)
        changed = False
        if link != self._link:
            self._link = link
            if link is False:
                self._fails = 0
                changed = self._set_net(False)
            else:
                self._net_at, self._retry_until = 0.0, now + 30.0
        if link is False or self._checking or now < self._net_at:
            return changed
        self._checking = True
        threading.Thread(target=self._check_net, name="saarthi-net", daemon=True).start()
        return changed

    def _check_net(self) -> None:
        try:
            ok = online()
            now = time.monotonic()
            if ok:
                self._fails = 0
                if self._set_net(True):
                    self.on_change()
                self._net_at = now + self.net_every
                return
            self._fails += 1
            if (self._fails >= 2 or self.net is None) and self._set_net(False):  # one failure isn't "offline"
                self.on_change()
            quick = now < self._retry_until or self._fails < 2
            self._net_at = now + (2.0 if quick else self.net_every)
        finally:
            self._checking = False
            self._kick.set()  # let the main loop plan the next check

    def read(self, psutil, audio: tuple | None = None) -> Snapshot:
        s = Snapshot()
        if psutil is not None:
            s.cpu = psutil.cpu_percent(None)
            s.temp = cpu_temp(psutil)
            s.uptime_days = (time.time() - psutil.boot_time()) / 86400
        s.headphones, s.muted, s.volume = audio if audio is not None else self.read_audio()
        return s
