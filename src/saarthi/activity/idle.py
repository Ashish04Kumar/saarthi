"""System-wide idle time (seconds since last keyboard/mouse input)."""

from __future__ import annotations

import ctypes
import ctypes.util
import sys


class WindowsIdle:
    name = "Win32 GetLastInputInfo"

    class _LII(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    def __init__(self):
        self._u32 = ctypes.windll.user32  # type: ignore[attr-defined]
        self._k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        self._k32.GetTickCount.restype = ctypes.c_uint

    def read(self) -> float:
        lii = self._LII(ctypes.sizeof(self._LII), 0)
        self._u32.GetLastInputInfo(ctypes.byref(lii))
        return ((self._k32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0


class MutterIdle:
    """GNOME (X11 and Wayland)."""

    name = "GNOME Mutter IdleMonitor"

    def __init__(self):
        from jeepney.io.blocking import open_dbus_connection

        self.conn = open_dbus_connection(bus="SESSION")
        self.read()

    def read(self) -> float:
        from jeepney import DBusAddress, new_method_call

        addr = DBusAddress(
            "/org/gnome/Mutter/IdleMonitor/Core",
            bus_name="org.gnome.Mutter.IdleMonitor",
            interface="org.gnome.Mutter.IdleMonitor",
        )
        reply = self.conn.send_and_get_reply(new_method_call(addr, "GetIdletime"), timeout=1)
        return reply.body[0] / 1000.0


class X11Idle:
    name = "X11 XScreenSaver"

    class _Info(ctypes.Structure):
        _fields_ = [
            ("window", ctypes.c_ulong),
            ("state", ctypes.c_int),
            ("kind", ctypes.c_int),
            ("til_or_since", ctypes.c_ulong),
            ("idle", ctypes.c_ulong),
            ("event_mask", ctypes.c_ulong),
        ]

    def __init__(self):
        x11 = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11") or "libX11.so.6")
        xss = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Xss") or "libXss.so.1")
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x11.XDefaultRootWindow.restype = ctypes.c_ulong
        xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(self._Info)
        xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(self._Info)]
        self._dpy = x11.XOpenDisplay(None)
        if not self._dpy:
            raise OSError("no X display")
        self._root = x11.XDefaultRootWindow(self._dpy)
        self._xss = xss
        self._info = xss.XScreenSaverAllocInfo()
        self.read()

    def read(self) -> float:
        self._xss.XScreenSaverQueryInfo(self._dpy, self._root, self._info)
        return self._info.contents.idle / 1000.0


class MacIdle:
    """macOS: seconds since the last keyboard/mouse event (no permission needed)."""

    name = "macOS CoreGraphics"

    def __init__(self):
        cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        f = cg.CGEventSourceSecondsSinceLastEventType
        f.argtypes = [ctypes.c_int32, ctypes.c_uint32]
        f.restype = ctypes.c_double
        self._f = f
        self.read()

    def read(self) -> float:
        # kCGEventSourceStateHIDSystemState = 1, kCGAnyInputEventType = ~0
        return float(self._f(1, 0xFFFFFFFF))


def make_idle_probe(session: str):
    """Return the first idle probe that works here, or None."""
    if sys.platform == "win32":
        candidates = [WindowsIdle]
    elif sys.platform == "darwin":
        candidates = [MacIdle]
    elif session == "wayland":
        candidates = [MutterIdle]
    else:
        candidates = [MutterIdle, X11Idle]
    for cls in candidates:
        try:
            return cls()
        except Exception:
            continue
    return None
