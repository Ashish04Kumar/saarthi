"""Entry point: `python -m saarthi` or the `saarthi` command."""

from __future__ import annotations

import argparse
import os
import sys


def _regain_input_group() -> None:
    """Linux: you joined the 'input' group but haven't logged out yet, so this session doesn't have it.
    Restart ourselves through `sg input` (no password needed for members) so typing detection works now."""
    if not sys.platform.startswith("linux") or os.environ.get("SAARTHI_SG"):
        return
    import getpass
    import grp
    import shlex
    import shutil

    try:
        group = grp.getgrnam("input")
    except KeyError:
        return
    if group.gr_gid in os.getgroups() or os.getegid() == group.gr_gid:
        return  # already have it
    if getpass.getuser() not in group.gr_mem or not shutil.which("sg"):
        return  # not a member: the app will explain how to fix it
    os.environ["SAARTHI_SG"] = "1"
    cmd = " ".join(shlex.quote(c) for c in [sys.executable, "-m", "saarthi", *sys.argv[1:]])
    import contextlib

    with contextlib.suppress(OSError):  # if it fails, carry on without the group
        os.execvp("sg", ["sg", "input", "-c", cmd])


def _prefer_x11_on_wayland() -> None:
    # Wayland forbids apps from positioning windows or keeping them on top.
    # XWayland allows both, so use it unless the user chose a platform.
    if (
        sys.platform.startswith("linux")
        and os.environ.get("XDG_SESSION_TYPE") == "wayland"
        and "QT_QPA_PLATFORM" not in os.environ
    ):
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def snapshot(out_dir: str, skin_id: str | None, accessory: str | None = None) -> None:
    """Render every state to PNG (for README/tests). Works headless."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication

    from . import skin as skins
    from .config import Config
    from .states import State

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    sk = skins.load(skin_id or Config()["skin"])
    sk.accessory = accessory
    os.makedirs(out_dir, exist_ok=True)
    cell, cols = 220, 4
    states = list(State)
    rows = (len(states) + cols - 1) // cols
    sheet = QPixmap(cell * cols, (cell + 24) * rows)
    sheet.fill(QColor("#F3F5FA"))
    sp = QPainter(sheet)
    f = QFont()
    f.setPointSize(11)
    sp.setFont(f)
    for i, st in enumerate(states):
        pix = QPixmap(cell, cell)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        sk.paint(p, QRectF(0, 0, cell, cell), st, 1.3, 0.35)
        p.end()
        pix.save(os.path.join(out_dir, f"{st.value}.png"))
        x, y = (i % cols) * cell, (i // cols) * (cell + 24)
        sp.drawPixmap(x, y, pix)
        sp.setPen(QColor("#1B2440"))
        sp.drawText(QRectF(x, y + cell, cell, 22), Qt.AlignmentFlag.AlignCenter, st.value)
    sp.end()
    sheet.save(os.path.join(out_dir, "all_states.png"))
    print(f"wrote {len(states)} states to {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="saarthi", description="Your animated desktop companion.")
    ap.add_argument("--demo", action="store_true", help="cycle through activities to show every animation")
    ap.add_argument("--snapshot", metavar="DIR", help="render every state to PNGs and exit")
    ap.add_argument("--skin", help="skin id to use with --snapshot")
    ap.add_argument("--accessory", help="umbrella / scarf / shades, for --snapshot")
    ap.add_argument("--quit", action="store_true", help="close the running Saarthi")
    args = ap.parse_args()

    if args.snapshot:
        snapshot(args.snapshot, args.skin, args.accessory)
        return

    if args.quit:
        from PySide6.QtCore import QCoreApplication

        from .system import SingleInstance

        _app = QCoreApplication(sys.argv)  # noqa: F841
        print("Saarthi closed." if SingleInstance().send(b"quit") else "Saarthi isn't running.")
        return

    _regain_input_group()
    _prefer_x11_on_wayland()
    from PySide6.QtWidgets import QApplication

    from .app import Saarthi

    app = QApplication(sys.argv)
    app.setApplicationName("Saarthi")
    app.setDesktopFileName("saarthi")  # matches the installed .desktop file on Linux
    app.setQuitOnLastWindowClosed(False)
    from pathlib import Path

    from PySide6.QtGui import QIcon

    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "icon.png")))

    from .system import SingleInstance

    instance = SingleInstance()
    if instance.already_running():
        print("Saarthi is already running; showing it.")
        return
    from .system import migrate_old_autostart

    migrate_old_autostart()
    buddy = Saarthi(app, demo=args.demo)
    instance.activated.connect(buddy.wake_from_launcher)
    instance.quit_requested.connect(app.quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
