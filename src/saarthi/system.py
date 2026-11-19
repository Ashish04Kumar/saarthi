"""OS integration: one buddy at a time, and starting with the computer."""

from __future__ import annotations

import contextlib
import getpass
import os
import shlex
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

APP_ID = "io.github.saarthi"


# ---------------- single instance ----------------


class SingleInstance(QObject):
    """If Saarthi is already running, wake that one up instead of starting a second buddy."""

    activated = Signal()
    quit_requested = Signal()

    def __init__(self):
        super().__init__()
        self.name = f"saarthi-{getpass.getuser()}"
        self.server: QLocalServer | None = None

    def send(self, message: bytes) -> bool:
        """Send a message to the running Saarthi. False if none is running."""
        sock = QLocalSocket()
        sock.connectToServer(self.name)
        if not sock.waitForConnected(500):
            return False
        sock.write(message)
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        return True

    def already_running(self) -> bool:
        sock = QLocalSocket()
        sock.connectToServer(self.name)
        if sock.waitForConnected(300):
            sock.write(b"show")
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
            return True
        QLocalServer.removeServer(self.name)  # clean up after a crash
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_connection)
        self.server.listen(self.name)
        return False

    def _on_connection(self):
        conn = self.server.nextPendingConnection()
        if conn is None:
            return
        conn.waitForReadyRead(300)
        message = bytes(conn.readAll())
        conn.close()
        if message.startswith(b"quit"):
            self.quit_requested.emit()
        else:
            self.activated.emit()


# ---------------- start with the computer ----------------


def launch_command() -> list[str]:
    if os.environ.get("APPIMAGE"):  # Linux AppImage
        return [os.environ["APPIMAGE"]]
    if getattr(sys, "frozen", False):  # PyInstaller build
        return [sys.executable]
    exe = sys.executable
    if sys.platform == "win32" and exe.lower().endswith("python.exe"):
        exe = exe[:-10] + "pythonw.exe"  # no console window
    return [exe, "-m", "saarthi"]


def _linux_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / "saarthi.desktop"


def _mac_file() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"


def migrate_old_autostart() -> None:
    """If 'start with my computer' was on under the old name (DeskBuddy), switch it to Saarthi."""
    try:
        if sys.platform == "win32":
            import winreg

            key = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_ALL_ACCESS) as k:
                winreg.QueryValueEx(k, "DeskBuddy")
                winreg.DeleteValue(k, "DeskBuddy")
            set_autostart(True)
        elif sys.platform == "darwin":
            old = Path.home() / "Library" / "LaunchAgents" / "io.github.deskbuddy.plist"
            if old.exists():
                old.unlink()
                set_autostart(True)
        else:
            old = _linux_file().with_name("deskbuddy.desktop")
            if old.exists():
                old.unlink()
                set_autostart(True)
    except OSError:
        pass


def autostart_enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, "Saarthi")
                return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return _mac_file().exists()
    return _linux_file().exists()


def set_autostart(on: bool) -> None:
    cmd = launch_command()
    if sys.platform == "win32":
        import subprocess
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE
        ) as k:
            if on:
                winreg.SetValueEx(k, "Saarthi", 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                with contextlib.suppress(OSError):
                    winreg.DeleteValue(k, "Saarthi")
        return
    if sys.platform == "darwin":
        f = _mac_file()
        if not on:
            f.unlink(missing_ok=True)
            return
        args = "\n".join(f"        <string>{a}</string>" for a in cmd)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{APP_ID}</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>RunAtLoad</key><true/>
</dict>
</plist>
""")
        return
    f = _linux_file()
    if not on:
        f.unlink(missing_ok=True)
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        "[Desktop Entry]\nType=Application\nName=Saarthi\n"
        "Comment=Your animated desktop companion\n"
        f"Exec={' '.join(shlex.quote(c) for c in cmd)}\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
