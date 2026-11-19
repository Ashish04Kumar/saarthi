"""Live 'What I see' window: which detectors are active and current readings."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QVBoxLayout


class StatusDialog(QDialog):
    def __init__(self, buddy):
        super().__init__()
        self.buddy = buddy
        self.setWindowTitle("Saarthi – What I see")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        intro = QLabel("I only count <b>how fast</b> you type and scroll, never <b>what</b> you type.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.form = QFormLayout()
        lay.addLayout(self.form)
        self.labels: dict[str, QLabel] = {}
        self._timer = QTimer(self, timeout=self.refresh)
        self._timer.start(500)
        self.refresh()

    def _set(self, key: str, value: str) -> None:
        if key not in self.labels:
            lab = QLabel()
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.labels[key] = lab
            self.form.addRow(f"<b>{key}</b>", lab)
        self.labels[key].setText(value)

    def refresh(self) -> None:
        b = self.buddy
        for k, v in b.source.status().items():
            self._set(k, v)
        a = b.source.read(time.monotonic())
        self._set("Keys / sec", f"{a.keys_per_sec:.1f}")
        self._set("Scrolls / sec", f"{a.scrolls_per_sec:.1f}")
        self._set("Idle", f"{a.idle_seconds:.0f} s")
        if a.video_playing:
            media = f"video{' (tutorial)' if a.media_tutorial else ''}"
            media += f" on {a.media_site}" if a.media_site else ""
            media += f": {a.media_title[:60]}" if a.media_title else ""
        elif a.music_playing:
            media = f"music: {a.media_title[:60]}"
        else:
            media = "nothing playing"
        self._set("Media", media)
        self._set("Mood", b.sm.state.value.replace("_", " "))
        w, now = b.wellness, time.monotonic()
        if w.mode == "break":
            session = f"break, {int(w.ends - now)} s left (typing for 45 s cancels it)"
        elif w.mode == "lunch":
            session = (
                f"lunch, {int(w.ends - now) // 60} min left ({'eating' if b.sm.state.value == 'eat' else 'strolling'})"
            )
        elif w.mode == "breathe":
            session = f"breathing, {int(w.ends - now)} s left"
        else:
            session = "none"
        self._set("Session", session)
        if b.cfg["break_enabled"]:
            left = max(0.0, float(b.cfg["work_minutes"]) - b.sm.active_minutes)
            if w.break_snooze and w.break_snooze > now:
                left = max(left, (w.break_snooze - now) / 60)
            self._set("Next break", f"in ~{left:.0f} min of work (walking away 5 min resets it)")
        else:
            self._set("Next break", "off")
        self._set(
            "Next breathing",
            f"in ~{max(0, (w.next_breath - now) / 60):.0f} min" if b.cfg["breathing_enabled"] else "off",
        )
        self._set("Walking", ("walking now" if b.walker.walking else "on") if b.cfg["walk_enabled"] else "off")
        nxt = b.org.scheduler.upcoming(__import__("datetime").datetime.now(), 24)
        self._set("Next reminder/event", f"{nxt[0][0].strftime('%H:%M')} {nxt[0][1]}" if nxt else "none today")
        self._set("Active for", f"{b.sm.active_minutes:.0f} min (break at {b.cfg['work_minutes']})")

    def closeEvent(self, e):
        self._timer.stop()
        super().closeEvent(e)
