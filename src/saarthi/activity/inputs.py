"""Keyboard/mouse listeners. PRIVACY: callbacks only record *that* an event
happened (a timestamp). Which key was pressed is never read or stored."""

from __future__ import annotations

import contextlib
import glob
import select
import threading
import time
from collections.abc import Callable

from .. import clock
from .counters import RateCounter

# evdev constants (from linux/input-event-codes.h)
EV_KEY, EV_REL, EV_ABS = 1, 2, 3
KEY_A, KEY_Z, BTN_MISC = 30, 44, 0x100
REL_WHEEL, REL_HWHEEL = 8, 6
BTN_TOOL_DOUBLETAP = 333
ABS_MT_POSITION_Y = 54
TOUCHPAD_SCROLL_STEPS = 30  # a full-height two-finger swipe ~= 30 wheel clicks


class EvdevInput(threading.Thread):
    """Linux (X11 and Wayland). Needs read access to /dev/input (the `input` group)."""

    name = "evdev (/dev/input)"

    def __init__(self, keys: RateCounter, scrolls: RateCounter, touched: Callable[[], None]):
        super().__init__(daemon=True, name="saarthi-evdev")
        import evdev  # noqa: F401  (fail early if missing)

        self.keys, self.scrolls, self.touched = keys, scrolls, touched
        self.devices: dict[str, object] = {}
        self.touch: dict[str, dict] = {}
        self._quit = threading.Event()
        self._scan()
        if not self.devices:
            raise PermissionError("no readable input devices (add yourself to the 'input' group)")

    @staticmethod
    def _kind(dev) -> str | None:
        caps = dev.capabilities()
        keys = set(caps.get(EV_KEY, []))
        rels = set(caps.get(EV_REL, []))
        abss = {a[0] if isinstance(a, tuple) else a for a in caps.get(EV_ABS, [])}
        if KEY_A in keys and KEY_Z in keys:
            return "keyboard"
        if BTN_TOOL_DOUBLETAP in keys and ABS_MT_POSITION_Y in abss:
            return "touchpad"
        if REL_WHEEL in rels:
            return "mouse"
        return None

    def _scan(self) -> None:
        import evdev

        for path in glob.glob("/dev/input/event*"):
            if path in self.devices:
                continue
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue
            kind = self._kind(dev)
            if kind is None:
                dev.close()
                continue
            self.devices[path] = dev
            if kind == "touchpad":
                info = dev.absinfo(ABS_MT_POSITION_Y)
                step = max(1.0, (info.max - info.min) / TOUCHPAD_SCROLL_STEPS)
                self.touch[path] = {"two": False, "y": None, "acc": 0.0, "step": step}

    def summary(self) -> str:
        return f"{len(self.devices)} device(s)"

    def run(self) -> None:
        last_scan = clock.now()
        while not self._quit.is_set():
            if clock.now() - last_scan > 15:
                self._scan()
                last_scan = clock.now()
            devs = list(self.devices.values())
            if not devs:
                time.sleep(1)
                continue
            try:
                ready, _, _ = select.select(devs, [], [], 1.0)
            except (OSError, ValueError):
                self._drop_dead()
                continue
            for dev in ready:
                try:
                    for ev in dev.read():
                        self._on_event(dev.path, ev)
                except OSError:
                    self._drop(dev.path)

    def _on_event(self, path: str, ev) -> None:
        t, code, val = ev.type, ev.code, ev.value
        if t == EV_KEY:
            if val == 1 and code < BTN_MISC:
                self.keys.hit()
            self.touched()
            tp = self.touch.get(path)
            if tp is not None and code == BTN_TOOL_DOUBLETAP:
                tp["two"], tp["y"], tp["acc"] = bool(val), None, 0.0
        elif t == EV_REL:
            if code in (REL_WHEEL, REL_HWHEEL) and val:
                self.scrolls.hit()
            self.touched()
        elif t == EV_ABS:
            self.touched()
            tp = self.touch.get(path)
            if tp is not None and tp["two"] and code == ABS_MT_POSITION_Y:
                if tp["y"] is not None:
                    tp["acc"] += abs(val - tp["y"])
                    while tp["acc"] >= tp["step"]:
                        tp["acc"] -= tp["step"]
                        self.scrolls.hit()
                tp["y"] = val

    def _drop(self, path: str) -> None:
        dev = self.devices.pop(path, None)
        self.touch.pop(path, None)
        if dev is not None:
            with contextlib.suppress(OSError):
                dev.close()

    def _drop_dead(self) -> None:
        for path, dev in list(self.devices.items()):
            try:
                dev.fileno()
            except (OSError, ValueError):
                self._drop(path)

    def stop(self) -> None:
        self._quit.set()


class PynputInput:
    """Windows and Linux X11. On Wayland it only sees XWayland apps."""

    name = "pynput"

    def __init__(self, keys: RateCounter, scrolls: RateCounter, touched: Callable[[], None]):
        from pynput import keyboard, mouse

        self._k = keyboard.Listener(on_press=lambda *_: (keys.hit(), touched()))
        self._m = mouse.Listener(
            on_scroll=lambda *_: (scrolls.hit(), touched()),
            on_click=lambda *_: touched(),
            on_move=lambda *_: touched(),
        )

    def summary(self) -> str:
        return "listening"

    def start(self) -> None:
        self._k.daemon = self._m.daemon = True
        self._k.start()
        self._m.start()

    def stop(self) -> None:
        self._k.stop()
        self._m.stop()
