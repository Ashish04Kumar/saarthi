"""First-run welcome, and a friendly fix-it card when typing detection needs a permission."""

from __future__ import annotations

import sys
from datetime import date

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

WAYLAND_CMD = "sudo usermod -aG input $USER"


def typing_problem(source) -> str | None:
    """'wayland' / 'mac' / 'missing' when typing can't be seen properly, else None."""
    status = getattr(source, "status", lambda: {})().get("Typing & scroll", "")
    if not status or status.startswith("evdev"):
        return None
    if "partial" in status or (sys.platform.startswith("linux") and "unavailable" in status):
        return "wayland"
    if sys.platform == "darwin":
        return "mac"
    if "unavailable" in status:
        return "missing"
    return None


class Onboarding:
    def __init__(self, buddy):
        self.buddy = buddy
        self.cfg = buddy.cfg
        QTimer.singleShot(2500, self.run)

    def run(self):
        hinglish = self.cfg["language"] == "hinglish"
        if not self.cfg.data.get("welcomed"):
            self.cfg["welcomed"] = True
            msg = (
                (
                    "Namaste! Main tumhara Saarthi 👋\n• Double-click: reminders & notes\n"
                    "• Right-click: menu (🧪 Try features)\n• Pakad ke kahin bhi le jao"
                )
                if hinglish
                else (
                    "Hi! I'm your Saarthi 👋\n• Double-click: reminders & notes\n"
                    "• Right-click: menu (🧪 Try features)\n• Drag me anywhere"
                )
            )
            self.buddy.say(msg, 12000, force=True)
            QTimer.singleShot(13000, self.check_typing)
        else:
            self.check_typing()

    def check_typing(self):
        problem = typing_problem(self.buddy.source)
        today = date.today().isoformat()
        if problem is None or self.cfg.data.get("typing_help_shown") == today:
            return
        self.cfg["typing_help_shown"] = today
        hinglish = self.cfg["language"] == "hinglish"
        title = "Main tumhari typing nahi dekh pa raha 🙈" if hinglish else "I can't see your typing yet 🙈"
        sub = (
            "Ek baar ki permission chahiye (sirf speed, kya type kiya wo kabhi nahi)."
            if hinglish
            else "It needs a one-time permission (speed only, never what you type)."
        )
        self.buddy.org._card(
            "⌨️",
            title,
            sub,
            [
                ("Kaise? 🔧" if hinglish else "How? 🔧", lambda: self.show_help(problem)),
                ("Baad me" if hinglish else "Later", lambda: None),
            ],
        )

    def show_help(self, problem: str | None = None):
        problem = problem or typing_problem(self.buddy.source) or "ok"
        box = QMessageBox()
        box.setWindowTitle("Saarthi – typing detection")
        if problem == "wayland":
            box.setText("<b>Wayland hides keyboard activity from apps.</b>")
            box.setInformativeText(
                "Run this once in a terminal, then <b>log out and log back in</b>:<br><br>"
                f"<code>{WAYLAND_CMD}</code><br><br>"
                "This lets programs you run read input devices. If you'd rather not, choose "
                "<b>“Ubuntu on Xorg”</b> from the ⚙ button on the login screen instead.<br><br>"
                "Saarthi only counts how fast you type, never which keys."
            )
            copy = box.addButton("Copy command", QMessageBox.ButtonRole.ActionRole)
        elif problem == "mac":
            box.setText("<b>macOS needs your OK to see keyboard activity.</b>")
            box.setInformativeText(
                "Open <b>System Settings → Privacy & Security</b>, then turn Saarthi (or Terminal / Python) "
                "on under <b>Accessibility</b> and <b>Input Monitoring</b>. Quit and start Saarthi again."
            )
            copy = None
        else:
            box.setText("Typing detection is working ✅" if problem == "ok" else "Typing detection is unavailable.")
            box.setInformativeText("Right-click → What I see… shows live readings.")
            copy = None
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if copy is not None and box.clickedButton() is copy:
            QApplication.clipboard().setText(WAYLAND_CMD)
            self.buddy.say(
                "Command copy ho gaya 📋 Terminal me paste karo"
                if self.cfg["language"] == "hinglish"
                else "Command copied 📋",
                force=True,
            )
