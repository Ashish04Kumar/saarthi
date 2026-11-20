"""The chat with whoever has your live link: their messages and your replies (themed, small, on top)."""

from __future__ import annotations

import html
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from . import theme

EMOJIS = "😀😂🤣😊😍🥰😘😜😎🤗🤔😴😢😭😡😤🙄😇🥺👍👎👏🙏💪❤️💔💕💋🔥🎉☕🍕⚽🎧💻📚🌙⭐✨"

STYLE = """
QWidget#chat { background: $bg; }
* { color: $text; font-size: 13px; }
QLabel#title { font-size: 15px; font-weight: bold; }
QTextBrowser { background: $surface; border: 1px solid $border; border-radius: 10px; padding: 6px; }
QLineEdit { background: $surface; border: 1px solid $border; border-radius: 10px; padding: 8px 10px; }
QPushButton { background: $accent; color: white; border: 0; border-radius: 10px; padding: 8px 16px; font-weight: bold; }
QPushButton:disabled { background: $soft; color: $muted; }
QToolButton { background: $soft; border: 1px solid $border; border-radius: 10px; padding: 4px 8px; font-size: 16px; }
QToolButton#emoji { background: transparent; border: 0; font-size: 20px; padding: 2px; }
"""


class ChatWindow(QWidget):
    def __init__(self, share):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Window)
        self.share = share
        self.setObjectName("chat")
        self.setWindowTitle("Saarthi · chat")
        self.setPalette(theme.palette())
        self.setStyleSheet(theme.css(STYLE))
        self.resize(360, 440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        self.title = QLabel(objectName="title")
        lay.addWidget(self.title)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        self.input = QLineEdit(placeholderText="Reply…", maxLength=500)
        self.input.returnPressed.connect(self.send)
        self.btn = QPushButton("Send")
        self.btn.clicked.connect(self.send)
        self.emoji = QToolButton(text="😊", toolTip="Emoji")
        self.emoji.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.emoji.setMenu(self._emoji_menu())
        row.addWidget(self.emoji)
        row.addWidget(self.input, 1)
        row.addWidget(self.btn)
        lay.addLayout(row)
        self.refresh()

    def _emoji_menu(self) -> QMenu:
        menu = QMenu(self)
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setSpacing(2)
        chars = [c for c in EMOJIS if c not in "\ufe0f"]
        for i, ch in enumerate(chars):
            b = QToolButton(text=ch, objectName="emoji")
            b.clicked.connect(lambda _=False, e=ch: (self.input.insert(e), menu.close(), self.input.setFocus()))
            grid.addWidget(b, i // 8, i % 8)
        act = QWidgetAction(menu)
        act.setDefaultWidget(grid_w)
        menu.addAction(act)
        return menu

    def refresh(self) -> None:
        friend = self.share.friend_name()
        self.title.setText(f"💬 {friend}")
        c = theme.colors()
        rows = []
        for m in self.share.messages:
            mine = m.get("from") == "owner"
            when = datetime.fromtimestamp(m.get("at", 0) / 1000).strftime("%H:%M")
            who = "You" if mine else friend
            align = "right" if mine else "left"
            bg = c["accent"] if mine else c["soft"]
            fg = "white" if mine else c["text"]
            small = "#e8ecff" if mine else c["muted"]
            rows.append(
                f'<table width="100%" cellspacing="0" cellpadding="0"><tr><td align="{align}">'
                f'<table cellpadding="7" style="background:{bg}; color:{fg};"><tr><td>'
                f"{html.escape(m.get('text', ''))}<br><span style='font-size:10px; color:{small};'>"
                f"{html.escape(who)} · {when}</span></td></tr></table></td></tr></table>"
            )
        if not rows:
            rows.append(f"<p style='color:{c['muted']}; text-align:center;'>No messages yet</p>")
        self.view.setHtml("".join(rows))
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
        ok = self.share.online
        self.btn.setEnabled(ok)
        self.input.setEnabled(ok)
        if not ok:
            self.input.setPlaceholderText("Live link is off or not connected")
        else:
            self.input.setPlaceholderText("Reply…")

    def send(self) -> None:
        text = self.input.text().strip()
        if text and self.share.send_chat(text):
            self.input.clear()

    def open(self) -> None:
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
