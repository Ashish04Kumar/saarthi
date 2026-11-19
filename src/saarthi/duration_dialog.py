"""Small themed pop-up: how many minutes for a lunch or break (also to change a running one)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout

from . import theme

PRESETS = {"lunch": (30, 45, 60, 90), "break": (5, 10, 15, 20)}
TITLES = {"lunch": "🍱 Lunch kitne minute?", "break": "☕ Break kitne minute?"}
STYLE = """
QDialog { background: $bg; }
* { color: $text; font-size: 13px; }
QLabel#title { font-size: 16px; font-weight: bold; }
QLabel#sub { color: $sub; font-size: 12px; }
QSpinBox { padding: 6px 8px; border: 1px solid $border; border-radius: 8px; background: $surface; font-size: 18px; }
QPushButton { background: $soft; border: 1px solid $border; border-radius: 10px; padding: 6px 12px; }
QPushButton:hover { background: $hover; }
QPushButton#preset:checked { background: $accent; color: white; border-color: $accent; }
QPushButton#go { background: $accent; color: white; border-color: $accent; font-weight: bold; padding: 7px 18px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid $muted; border-radius: 5px; background: $surface; }
QCheckBox::indicator:checked { background: $green; border-color: $green; }
"""


class DurationDialog(QDialog):
    def __init__(self, kind: str, minutes: int, editing: bool = False):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog)
        self.setWindowTitle("Saarthi")
        self.setPalette(theme.palette())
        self.setStyleSheet(theme.css(STYLE))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        title = (
            TITLES[kind] if not editing else ("🍱 Lunch ka time badlo" if kind == "lunch" else "☕ Break ka time badlo")
        )
        lay.addWidget(QLabel(title, objectName="title"))
        lay.addWidget(QLabel("Kitne minute aur?" if editing else "Apne hisaab se set karo", objectName="sub"))

        self.spin = QSpinBox(minimum=1, maximum=240, value=max(1, int(minutes)), suffix=" min")
        lay.addWidget(self.spin)
        row = QHBoxLayout()
        self.presets = []
        for m in PRESETS[kind]:
            b = QPushButton(f"{m}", objectName="preset", checkable=True)
            b.setChecked(m == minutes)
            b.clicked.connect(lambda _=False, m=m: self.spin.setValue(m))
            row.addWidget(b)
            self.presets.append((m, b))
        lay.addLayout(row)
        self.spin.valueChanged.connect(self._sync_presets)

        self.make_default = QCheckBox("Isko default bana do")
        if not editing:
            lay.addWidget(self.make_default)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        go = QPushButton("Update" if editing else "Shuru karo", objectName="go")
        go.setDefault(True)
        go.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(go)
        lay.addLayout(btns)
        self.setFixedWidth(330)

    def _sync_presets(self, v):
        for m, b in self.presets:
            b.setChecked(m == v)

    @staticmethod
    def ask(kind: str, minutes: int, editing: bool = False) -> tuple[int, bool] | None:
        """(minutes, make_default) or None if cancelled."""
        d = DurationDialog(kind, minutes, editing)
        if d.exec() == QDialog.DialogCode.Accepted:
            return d.spin.value(), d.make_default.isChecked()
        return None
