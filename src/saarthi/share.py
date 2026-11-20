"""The live link: show what your Saarthi is doing on a web page, and let the person you share it with
play with the character (poke, tickle, slap, football, pillow, love).

    Saarthi --WebSocket--> relay (Cloudflare Worker, see relay/) --> her browser at <share_url>/v/<room>
            <-- her actions --

Only the character, its animation, a general "what he's doing" (no titles) and lines marked as
shareable leave the laptop. Reminders, notes, calendar, the brief, weather and traffic never do.
All of it is one switch, Couple mode (menu / Settings), off until you turn it on.
The room id and token are made once and kept in config.json.
"""

from __future__ import annotations

import json
import secrets

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtWebSockets import QWebSocket

from . import clock
from .states import State

ACTIONS = ("poke", "tickle", "slap", "ball", "pillow", "love", "kiss", "hug", "angry", "boots", "jeans")
HEARTBEAT = 30.0
REACT = {  # her action -> (state, take, seconds)
    "poke": (State.POKED, None, 1.6),
    "tickle": (State.GIGGLE, None, 2.0),
    "slap": (State.POKED, "slap", 1.6),
    "ball": (State.POKED, "ball", 1.8),
    "pillow": (State.POKED, "pillow", 1.8),
    "love": (State.POKED, "love", 3.0),
    "kiss": (State.POKED, "kiss", 3.2),
    "hug": (State.POKED, "hug", 3.2),
    "angry": (State.POKED, "angry", 3.2),
    "boots": (State.POKED, "boots", 1.6),
    "jeans": (State.POKED, "jeans", 1.6),
}
LINES = {
    "hinglish": {
        "poke": "{n} ne poke kiya 👉",
        "tickle": "{n} ne gudgudi ki 🤭",
        "slap": "{n} ne thappad maara ✋😵",
        "ball": "{n} ne football maari ⚽",
        "pillow": "{n} ne takiya phenka 🛏️💥",
        "love": "{n} ne pyaar bheja ❤️",
        "kiss": "{n} ne kiss bheja 💋",
        "hug": "{n} ne jhappi di 🤗",
        "angry": "{n} gusse me hai 😤 Sorry bolo!",
        "boots": "{n} ne pair pe pair rakh diya 👟😩",
        "jeans": "{n} ne jeans kheenchi 👖",
    },
    "en": {
        "poke": "{n} poked you 👉",
        "tickle": "{n} tickled you 🤭",
        "slap": "{n} slapped you ✋😵",
        "ball": "{n} kicked a football at you ⚽",
        "pillow": "{n} threw a pillow at you 🛏️💥",
        "love": "{n} sent you love ❤️",
        "kiss": "{n} sent you a kiss 💋",
        "hug": "{n} sent you a hug 🤗",
        "angry": "{n} is angry with you 😤 Say sorry!",
        "boots": "{n} stepped on your shoes 👟😩",
        "jeans": "{n} tugged your jeans 👖",
    },
}


def ensure_ids(cfg) -> tuple[str, str]:
    """The room (in the link) and the secret token (only this laptop knows it). Made once."""
    if not cfg["share_room"]:
        cfg["share_room"] = secrets.token_urlsafe(18)
    if not cfg["share_token"]:
        cfg["share_token"] = secrets.token_urlsafe(32)
    return cfg["share_room"], cfg["share_token"]


def link(cfg) -> str:
    base = (cfg["share_url"] or "").rstrip("/")
    return f"{base}/v/{cfg['share_room']}" if base and cfg["share_room"] else ""


def kind_of(buddy) -> str:
    """A general word for what's going on: no titles, no names of things."""
    w = getattr(buddy, "wellness", None)
    if w is not None and w.mode in ("break", "lunch"):
        return w.mode
    if w is not None and w.mode == "breathe":
        return "breathing"
    walker = getattr(buddy, "walker", None)
    if walker is not None and walker.walking:
        return "walking"
    st = buddy.sm.state
    a = getattr(buddy, "activity", None)
    if st in (State.TYPING_FAST, State.TYPING_SLOW):
        return "typing"
    if st == State.SCROLLING:
        return "scrolling"
    if st == State.WATCHING:
        return "tutorial" if a is not None and a.media_tutorial else "video"
    if st == State.AFK:
        return "away"
    if st == State.SLEEPING:
        return "sleeping"
    if a is not None and a.music_playing:
        return "music"
    return "idle"


def view_of(buddy) -> dict:
    """What the page needs to draw exactly what the desktop shows."""
    win = buddy.win
    shown = win.override if win.override is not None else win.state
    return {
        "type": "state",
        "state": shown.value,
        "take": win.variant(shown) or "",
        "mirror": bool(win.mirror),
        "walking": shown == State.WALK,
        "kind": kind_of(buddy),
        "name": buddy.cfg["share_name"] or "Saarthi",
    }


class ShareLink(QObject):
    def __init__(self, buddy):
        super().__init__()
        self.buddy = buddy
        self.cfg = buddy.cfg
        self.ws = QWebSocket()
        self.ws.connected.connect(self._connected)
        self.ws.disconnected.connect(self._disconnected)
        self.ws.textMessageReceived.connect(self._message)
        self.online = False
        self.viewers = 0  # pages open right now (the green dot)
        self.messages: list[dict] = []  # the chat, oldest first: {"from": "viewer"|"owner", "text", "at"}
        self.chat_window = None
        self._sent: dict | None = None
        self._sent_at = 0.0
        self._retry = 2000
        self._reconnect = QTimer(self, singleShot=True, timeout=self.connect_now)
        self._tick = QTimer(self, timeout=self.publish)
        self._tick.start(500)
        if self.enabled:
            self.connect_now()

    # ---- on / off ----
    @property
    def enabled(self) -> bool:
        return bool(self.cfg["share_enabled"] and self.cfg["share_url"])

    def set_enabled(self, on: bool) -> None:
        self.cfg["share_enabled"] = on
        if on:
            ensure_ids(self.cfg)
            self.connect_now()
        else:
            self._reconnect.stop()
            self.ws.close()
            self.viewers = 0
            self.buddy.win.set_presence(False)

    def connect_now(self) -> None:
        if not self.enabled or self.online:
            return
        room, token = ensure_ids(self.cfg)
        base = self.cfg["share_url"].rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
        self.ws.open(QUrl(f"{base}/ws/{room}?role=owner&token={token}"))

    def stop(self) -> None:
        self._tick.stop()
        self._reconnect.stop()
        self.ws.close()

    # ---- socket ----
    def _connected(self) -> None:
        self.online, self._retry, self._sent = True, 2000, None
        self.publish()

    def _disconnected(self) -> None:
        self.online = False
        self.viewers = 0
        self.buddy.win.set_presence(False)
        if self.enabled:
            self._reconnect.start(self._retry)
            self._retry = min(self._retry * 2, 60_000)

    def _send(self, msg: dict) -> None:
        if self.online:
            self.ws.sendTextMessage(json.dumps(msg, ensure_ascii=False))

    # ---- out: what the character does ----
    def publish(self) -> None:
        if not self.online:
            return
        view = view_of(self.buddy)
        now = clock.now()
        if view != self._sent or now - self._sent_at >= HEARTBEAT:
            self._send(view)
            self._sent, self._sent_at = view, now

    def say(self, text: str) -> None:
        self._send({"type": "say", "text": text})

    # ---- in: what she does ----
    def _message(self, text: str) -> None:
        try:
            msg = json.loads(text)
        except ValueError:
            return
        kind = msg.get("type")
        if kind == "viewers" and isinstance(msg.get("count"), int):
            self.on_viewers(msg["count"])
        elif kind == "action" and msg.get("action") in ACTIONS:
            self.on_action(msg["action"])
        elif kind == "history" and isinstance(msg.get("messages"), list):
            self.messages = [m for m in msg["messages"] if isinstance(m, dict)][-50:]
            self._refresh_chat()
        elif kind == "chat" and isinstance(msg.get("text"), str):
            self.messages = (self.messages + [msg])[-50:]
            self._refresh_chat()
            if msg.get("from") == "viewer":
                self.on_chat(msg["text"])

    # ---- who's watching ----
    def on_viewers(self, count: int) -> None:
        was, self.viewers = self.viewers, max(0, count)
        self.buddy.win.set_presence(self.viewers > 0)
        if was == 0 and self.viewers > 0 and not self.buddy.quiet:
            hinglish = self.cfg["language"] == "hinglish"
            name = self.cfg["share_friend"] or ("Koi" if hinglish else "Someone")
            self.buddy.say(f"{name} online hai 💚" if hinglish else f"{name} is online 💚", 4000)

    # ---- chat ----
    def friend_name(self) -> str:
        return self.cfg["share_friend"] or ("Kisi ka message" if self.cfg["language"] == "hinglish" else "Message")

    def send_chat(self, text: str) -> bool:
        if not (self.online and text.strip()):
            return False
        self._send({"type": "chat", "text": text.strip()[:500]})
        return True

    def open_chat(self) -> None:
        from .chat_window import ChatWindow

        if self.chat_window is None:
            self.chat_window = ChatWindow(self)
        self.chat_window.open()

    def _refresh_chat(self) -> None:
        if self.chat_window is not None and self.chat_window.isVisible():
            self.chat_window.refresh()

    def on_chat(self, text: str) -> None:
        """A message from the page: a card you can reply from (never sent back to the page as a bubble)."""
        if self.chat_window is not None and self.chat_window.isVisible():
            return  # already reading the chat
        hinglish = self.cfg["language"] == "hinglish"
        self.buddy.org._card(
            "💬",
            f"{self.friend_name()}: {text[:120]}",
            "",
            [("Jawab do" if hinglish else "Reply", self.open_chat), ("OK", lambda: None)],
        )

    def on_action(self, action: str) -> None:
        b = self.buddy
        if b.quiet:
            return  # screen sharing: she still sees it on her page
        lang = "hinglish" if self.cfg["language"] == "hinglish" else "en"
        line = LINES[lang][action].format(n=self.cfg["share_friend"] or ("Kisi" if lang == "hinglish" else "Someone"))
        now = clock.now()
        state, take, secs = REACT[action]
        if b.sm.preview is None and not b.sm.busy:  # don't break a break / lunch / breathing session
            b.walker.cancel()
            b.sm.trigger(state, now, secs)
            b.win.set_state(state, now)
            b.win.set_variant(state, take)
            b.win.squash()
        from .app import HIGH

        b.say(line, 3500, priority=HIGH, share=True)
