"""Double-click panel: see and add reminders and notes right next to the buddy."""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QEvent, QRect, QRectF, Qt, QTime, QTimer
from PySide6.QtGui import QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .scheduler import due_at, schedule
from .store import REPEATS, Note, Reminder, Store, dt_to_str, str_to_dt

ID = Qt.ItemDataRole.UserRole
INK = "#1B2440"
# Our own light look, so the panel stays readable with dark system themes too.
STYLE = """
* { color: $text; font-size: 13px; }
QLabel#head { font-size: 17px; font-weight: bold; }
QLabel#sub { color: $sub; font-size: 12px; }
QLabel#weather { color: $sub; font-size: 12px; }
QLabel#section { font-weight: bold; color: $tabtext; margin-top: 4px; }
QLabel#done { color: $done; text-decoration: line-through; }
QLineEdit, QTimeEdit, QComboBox {
    padding: 5px 8px; border: 1px solid $border; border-radius: 8px; background: $surface; color: $text;
    selection-background-color: $accent; selection-color: white;
}
QLineEdit:focus, QTimeEdit:focus, QComboBox:focus { border-color: $accent; }
QComboBox QAbstractItemView { background: $surface; color: $text; selection-background-color: $item_sel;
    selection-color: $text; border: 1px solid $border; }
QTimeEdit::up-button, QTimeEdit::down-button { width: 16px; }
QPushButton { background: $soft; border: 1px solid $border; border-radius: 8px; padding: 5px 10px; }
QPushButton:hover { background: $hover; }
QPushButton#status { background: $surface; border: 1px solid $chip_border; border-radius: 12px; padding: 6px 4px; }
QPushButton#status:checked { background: $accent; color: white; border-color: $accent; font-weight: bold; }
QPushButton#chip { background: $surface; border: 1px solid $chip_border; border-radius: 12px; padding: 7px 4px;
    font-size: 12px; }
QPushButton#chip:hover { background: $item_sel; border-color: $accent; }
QPushButton#chip:checked { background: #7A4DD8; color: white; border-color: #7A4DD8; font-weight: bold; }
QPushButton#add { background: $accent; color: white; border-color: $accent; font-weight: bold; }
QPushButton#add:hover { background: $accent_hover; }
QPushButton#icon { padding: 3px 8px; }
QPushButton#trash { background: transparent; border: none; padding: 2px 6px; color: $muted; font-size: 14px; }
QPushButton#trash:hover { background: $red; color: white; border-radius: 6px; }
QPushButton#yes, QPushButton#no { padding: 2px 0px; font-size: 14px; font-weight: bold; min-height: 22px; }
QPushButton#yes:checked { background: $green; color: white; border-color: $green; }
QPushButton#no:checked { background: $red; color: white; border-color: $red; }
QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid $muted; border-radius: 5px; background: $surface; }
QCheckBox::indicator:checked { background: $green; border-color: $green; }
QListWidget { border: 1px solid $chip_border; border-radius: 10px; background: $surface; padding: 3px; color: $text; }
QListWidget::item { padding: 2px 2px; border-radius: 6px; }
QListWidget::item:selected { background: $item_sel; color: $text; }
QListWidget::item:hover { background: $item_hover; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: $tab; color: $tabtext; border-radius: 9px; padding: 6px 12px; margin-right: 4px; }
QTabBar::tab:selected { background: $accent; color: white; }
QMenu { background: $surface; color: $text; border: 1px solid $border; }
QMenu::item:selected { background: $item_sel; }
QToolTip { background: $text; color: $bg; border: none; }
"""
WHEN = [("today", "Aaj"), ("tomorrow", "Kal"), ("daily", "Roz"), ("weekdays", "Weekdays"), ("hourly", "Har ghante")]


def light_palette() -> QPalette:
    """Palette for our pop-ups (name kept for older callers); follows the chosen theme."""
    from . import theme

    return theme.palette()


def _fmt(d: datetime | None) -> str:
    if d is None:
        return "—"
    today = datetime.now().date()
    day = "Aaj" if d.date() == today else ("Kal" if d.date() == today + timedelta(days=1) else d.strftime("%d %b"))
    return f"{day} {d.strftime('%H:%M')}"


class HistoryRow(QWidget):
    def __init__(self, entry: dict, on_set):
        super().__init__()
        self.entry = entry
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        self.setMinimumHeight(36)
        due = str_to_dt(entry.get("due")) or str_to_dt(entry["at"])
        lab = QLabel(f"{entry['title']}  <span style='color:{theme.colors()['muted']}'>· {_fmt(due)}</span>")
        lab.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(lab, 1)
        self.yes = QPushButton("✓", objectName="yes", checkable=True)
        self.no = QPushButton("✗", objectName="no", checkable=True)
        self.yes.setToolTip("Kiya")
        self.no.setToolTip("Nahi kiya")
        self.yes.setChecked(entry["outcome"] == "done")
        self.no.setChecked(entry["outcome"] == "missed")
        self.yes.clicked.connect(lambda on: on_set(entry["id"], "done" if on else "pending"))
        self.no.clicked.connect(lambda on: on_set(entry["id"], "missed" if on else "pending"))
        for b in (self.yes, self.no):
            b.setFixedSize(38, 26)
            lay.addWidget(b)


class ItemRow(QWidget):
    """One reminder or note: [checkbox] text [🗑]."""

    def __init__(self, text: str, on_delete, done: bool | None = None, on_check=None, on_open=None):
        super().__init__()
        self.on_open = on_open
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 2, 2)
        if done is not None:
            from PySide6.QtWidgets import QCheckBox

            box = QCheckBox()
            box.setChecked(done)
            box.toggled.connect(on_check)
            lay.addWidget(box)
        lab = QLabel(text, objectName="done" if done else "")
        lab.setWordWrap(True)
        lay.addWidget(lab, 1)
        trash = QPushButton("🗑", objectName="trash")
        trash.setToolTip("Delete")
        trash.clicked.connect(on_delete)
        lay.addWidget(trash)
        self.setMinimumHeight(32)

    def mouseDoubleClickEvent(self, e):
        if self.on_open:
            self.on_open()


class QuickPanel(QWidget):
    def __init__(self, buddy):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self.setObjectName("panel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)  # stay visible on macOS
        self.setPalette(light_palette())
        self.apply_theme()
        self.buddy = buddy
        store: Store = buddy.org.store
        self.store, self.open_manager, self.say = store, buddy.org.open_manager, buddy.say
        self.setFixedSize(420, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(8)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.greet = QLabel(objectName="head")
        self.when = QLabel(objectName="sub")
        titles.addWidget(self.greet)
        titles.addWidget(self.when)
        head.addLayout(titles, 1)
        for text, tip, slot in (
            ("⤢", "Open the full window", lambda: self._go(lambda: self.open_manager(self._tab_name()))),
            ("✕", "Close (Esc)", self.hide),
        ):
            b = QPushButton(text, objectName="icon")
            b.setToolTip(tip)
            b.clicked.connect(slot)
            head.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)
        self.weather = QLabel(objectName="weather")
        self.weather.setWordWrap(True)
        root.addWidget(self.weather)

        status_row = QHBoxLayout()
        status_row.setSpacing(4)
        status_row.addWidget(QLabel("Status", objectName="section"))
        self.status_btns = {}
        for key, label in (("working", "💻 Working"), ("break", "☕ Break"), ("lunch", "🍱 Lunch")):
            btn = QPushButton(label, objectName="status", checkable=True)
            btn.clicked.connect(lambda _=False, k=key: self._set_status(k))
            status_row.addWidget(btn, 1)
            self.status_btns[key] = btn
        root.addLayout(status_row)
        note_row = QHBoxLayout()
        self.status_note = QLabel(objectName="sub")
        note_row.addWidget(self.status_note, 1)
        self.change_time = QPushButton("⏱ Time badlo", objectName="icon")
        self.change_time.setToolTip("Change how many minutes are left")
        self.change_time.clicked.connect(lambda: self._go(self.buddy.change_session_time))
        note_row.addWidget(self.change_time)
        root.addLayout(note_row)
        self.quiet_btn = QPushButton("🤫  Quiet mode for screen share", objectName="chip", checkable=True)
        self.quiet_btn.setToolTip("Hide in a corner: no pop-ups, bubbles or walks. Click again to come back.")
        self.quiet_btn.toggled.connect(self._quiet_toggled)
        root.addWidget(self.quiet_btn)

        grid = QGridLayout()
        grid.setSpacing(6)
        b = buddy
        actions = [
            ("🧘 Breathe", "1-minute guided breathing", lambda: b.wellness.start_breathe()),
            ("🚶 Walk", "Stroll across the screen", lambda: b.walker.walk_random(on_arrive=b.save_position)),
            ("🌦 Weather", "Weather now", lambda: b.outdoor.say_weather()),
            ("🚗 Traffic", "Time to get home", lambda: b.outdoor.commute_now()),
            ("📅 Calendar", "Open the calendar", lambda: b.org.open_manager("calendar")),
            ("⚙ Settings", "Settings", lambda: b.org.open_manager("settings")),
        ]
        for i, (label, tip, fn) in enumerate(actions):
            chip = QPushButton(label, objectName="chip")
            chip.setToolTip(tip)
            chip.clicked.connect(lambda _=False, fn=fn: self._go(fn))
            grid.addWidget(chip, i // 3, i % 3)
        root.addLayout(grid)
        self.stats = QLabel(objectName="sub")
        root.addWidget(self.stats)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._reminders_tab(), "⏰ Reminders")
        self.tabs.addTab(self._notes_tab(), "📝 Notes")
        self.tabs.addTab(self._today_tab(), "📅 Aaj")
        root.addWidget(self.tabs, 1)
        self._tidy_lists()
        store.on_change(lambda: self.isVisible() and self.refresh())

    def _quiet_toggled(self, on: bool):
        self.buddy.set_quiet(on)
        if on:
            self.hide()

    def _set_status(self, key: str):
        going_on = key != "working" and key != self.buddy.wellness.status
        if going_on:
            self.hide()  # the minutes picker shows up on its own
        started = self.buddy.toggle_status(key)  # asks minutes for break/lunch; same one again = off
        self._refresh_status()
        if going_on and not started:
            self.show()  # cancelled: come back

    def _refresh_status(self):
        w = self.buddy.wellness
        cur = w.status
        for key, btn in self.status_btns.items():
            btn.setChecked(key == cur)
        import time as _t

        left = max(0, int(w.ends - _t.monotonic())) if w.mode else 0
        notes = {
            "working": "Kaam chalu 💪",
            "break": f"☕ Break pe, {left // 60} min baaki",
            "lunch": f"🍱 Lunch pe, {left // 60} min baaki",
            "breathe": "🧘 Breathing chal rahi hai",
        }
        self.status_note.setText(notes.get(cur, ""))
        self.change_time.setVisible(cur in ("break", "lunch"))

    def _tidy_lists(self):
        from PySide6.QtWidgets import QListView

        for lst in (self.r_list, self.h_list, self.n_list, self.t_list):
            lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            lst.setResizeMode(QListView.ResizeMode.Adjust)

    def apply_theme(self):
        self.setPalette(light_palette())
        self.setStyleSheet(theme.css(STYLE))

    def _go(self, fn):
        self.hide()
        fn()

    def _tab_name(self) -> str:
        return ("reminders", "notes", "calendar")[self.tabs.currentIndex()]

    # ---------------- today ----------------
    def _today_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        self.e_title = QLineEdit(placeholderText="Aaj ka event, e.g. Team call")
        self.e_title.returnPressed.connect(self.add_event)
        lay.addWidget(self.e_title)
        row = QHBoxLayout()
        self.e_time = QTimeEdit(displayFormat="HH:mm")
        add = QPushButton("+ Event", objectName="add")
        add.clicked.connect(self.add_event)
        cal = QPushButton("📅 Calendar")
        cal.clicked.connect(lambda: self._go(lambda: self.open_manager("calendar")))
        row.addWidget(self.e_time)
        row.addStretch(1)
        row.addWidget(cal)
        row.addWidget(add)
        lay.addLayout(row)
        lay.addWidget(QLabel("Aaj ka schedule", objectName="section"))
        self.t_list = QListWidget()
        lay.addWidget(self.t_list, 1)
        return w

    def add_event(self):
        from .store import Event

        title = self.e_title.text().strip()
        if not title:
            self.e_title.setFocus()
            return
        t = self.e_time.time()
        start = datetime.now().replace(hour=t.hour(), minute=t.minute(), second=0, microsecond=0)
        self.store.events.append(Event(title, dt_to_str(start), dt_to_str(start + timedelta(hours=1))))
        self.store.save()
        self.e_title.clear()
        self.say(f"📅 {start.strftime('%H:%M')} {title} add ho gaya, 10 min pehle yaad dilaunga")
        self.refresh()

    # ---------------- reminders ----------------
    def _reminders_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        self.r_title = QLineEdit(placeholderText="Kya yaad dilaun? e.g. Paani piyo")
        self.r_title.returnPressed.connect(self.add_reminder)
        lay.addWidget(self.r_title)
        row = QHBoxLayout()
        self.r_time = QTimeEdit(displayFormat="HH:mm")
        self.r_when = QComboBox()
        for key, label in WHEN:
            self.r_when.addItem(label, key)
        add = QPushButton("+ Add", objectName="add")
        add.clicked.connect(self.add_reminder)
        row.addWidget(self.r_time)
        row.addWidget(self.r_when, 1)
        row.addWidget(add)
        lay.addLayout(row)

        lay.addWidget(QLabel("Aane wale", objectName="section"))
        self.r_list = QListWidget()
        self.r_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.r_list.customContextMenuRequested.connect(self._reminder_menu)
        self.r_list.itemDoubleClicked.connect(lambda _: (self.hide(), self.open_manager("reminders")))
        lay.addWidget(self.r_list, 5)

        lay.addWidget(QLabel("Kiya ya nahi?  (✓ kiya · ✗ nahi kiya)", objectName="section"))
        self.h_list = QListWidget()
        lay.addWidget(self.h_list, 3)
        return w

    def add_reminder(self):
        title = self.r_title.text().strip()
        if not title:
            self.r_title.setFocus()
            return
        now = datetime.now()
        t = self.r_time.time()
        when = self.r_when.currentData()
        at = now.replace(hour=t.hour(), minute=t.minute(), second=0, microsecond=0)
        repeat = {"daily": "daily", "weekdays": "weekdays", "hourly": "interval"}.get(when, "once")
        moved = False
        if when == "tomorrow":
            at += timedelta(days=1)
        elif when == "today" and at <= now:
            at += timedelta(days=1)
            moved = True
        r = Reminder(title, dt_to_str(at), repeat=repeat, interval_min=60)
        schedule(r, now)
        self.store.reminders.append(r)
        self.store.save()
        self.r_title.clear()
        msg = f"Theek hai, {_fmt(due_at(r))} pe yaad dilaunga ⏰"
        if moved:
            msg += " (aaj ka time nikal gaya tha)"
        self.say(msg)
        self.refresh()

    def _reminder_menu(self, pos):
        item = self.r_list.itemAt(pos)
        if not item:
            return
        r = next((r for r in self.store.reminders if r.id == item.data(ID)), None)
        if r is None:
            return
        m = QMenu(self)
        m.addAction("Delete", lambda: (self.store.reminders.remove(r), self.store.save(), self.refresh()))
        m.addAction("Turn off", lambda: (setattr(r, "enabled", False), self.store.save(), self.refresh()))
        m.exec(self.r_list.mapToGlobal(pos))

    def _set_outcome(self, hid, outcome):
        self.store.set_outcome(hid, outcome)
        self.store.save(notify=False)
        self._refresh_stats()
        if outcome == "done":
            self.say("Shabash! 🎉")

    # ---------------- notes ----------------
    def _notes_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        row = QHBoxLayout()
        self.n_text = QLineEdit(placeholderText="Naya note ya to-do…")
        self.n_text.returnPressed.connect(self.add_note)
        add = QPushButton("+ Add", objectName="add")
        add.clicked.connect(self.add_note)
        row.addWidget(self.n_text, 1)
        row.addWidget(add)
        lay.addLayout(row)
        self.n_list = QListWidget()
        self.n_list.itemDoubleClicked.connect(lambda _: (self.hide(), self.open_manager("notes")))
        self.n_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.n_list.customContextMenuRequested.connect(self._note_menu)
        lay.addWidget(self.n_list, 1)
        hint = QLabel("Tick = ho gaya · 🗑 = delete · double-click = poora note kholo", objectName="sub")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        return w

    def add_note(self):
        text = self.n_text.text().strip()
        if not text:
            return
        self.store.notes.append(Note(text=text))
        self.store.save()
        self.n_text.clear()
        self.refresh()

    def _find_note(self, nid):
        return next((n for n in self.store.notes if n.id == nid), None)

    def _delete_reminder(self, r):
        if r in self.store.reminders:
            self.store.reminders.remove(r)
            self.store.save()
            self.say(f"🗑 “{r.title}” delete ho gaya", priority=2)
            self.refresh()

    def _delete_note(self, n):
        if n in self.store.notes:
            self.store.notes.remove(n)
            self.store.save()
            self.say(f"🗑 “{n.title}” delete ho gaya", priority=2)
            self.refresh()

    def _set_done(self, n, on: bool):
        n.done = on
        n.updated = dt_to_str(datetime.now())
        self.store.save()
        if on:
            self.say("Ek kaam khatam! ✅")
        QTimer.singleShot(0, self.refresh)

    def _note_toggled(self, item):
        n = self._find_note(item.data(ID))
        if n is None:
            return
        n.done = item.checkState() == Qt.CheckState.Checked
        n.updated = dt_to_str(datetime.now())
        self.store.save(notify=False)
        self._style_note(item, n)
        if n.done:
            self.say("Ek kaam khatam! ✅")

    def _note_menu(self, pos):
        item = self.n_list.itemAt(pos)
        n = self._find_note(item.data(ID)) if item else None
        if n is None:
            return
        m = QMenu(self)
        m.addAction(
            "Unpin" if n.pinned else "Pin to top",
            lambda: (setattr(n, "pinned", not n.pinned), self.store.save(), self.refresh()),
        )
        m.addAction("Delete", lambda: (self.store.notes.remove(n), self.store.save(), self.refresh()))
        m.exec(self.n_list.mapToGlobal(pos))

    def _style_note(self, item, n):
        f = QFont(item.font())
        f.setStrikeOut(n.done)
        item.setFont(f)
        item.setForeground(theme.q("done") if n.done else theme.q("text"))

    # ---------------- refresh / show ----------------
    def _refresh_stats(self):
        done, missed, pending = self.store.stats(7)
        parts = [f"Is hafte: {done} ✓ kiya", f"{missed} ✗ nahi kiya"]
        if pending:
            parts.append(f"{pending} baaki")
        self.stats.setText(" · ".join(parts))

    def refresh(self):
        self._refresh_stats()
        self._refresh_today()
        self.r_list.clear()
        upcoming = sorted((r for r in self.store.reminders if due_at(r)), key=lambda r: due_at(r))
        for r in upcoming:
            rep = "" if r.repeat == "once" else f"  ({REPEATS.get(r.repeat, r.repeat)})"
            row = ItemRow(
                f"{_fmt(due_at(r))}  ·  {r.title}{rep}",
                lambda _=False, r=r: self._delete_reminder(r),
                on_open=lambda: self._go(lambda: self.open_manager("reminders")),
            )
            it = QListWidgetItem()
            it.setData(ID, r.id)
            it.setSizeHint(row.sizeHint())
            self.r_list.addItem(it)
            self.r_list.setItemWidget(it, row)
        if not upcoming:
            it = QListWidgetItem("Koi reminder nahi. Upar se add karo 👆")
            it.setForeground(theme.q("muted"))
            self.r_list.addItem(it)

        self.h_list.clear()
        newest = sorted(self.store.history, key=lambda h: h.get("due") or h["at"], reverse=True)
        pending = [h for h in newest if h["outcome"] == "pending"]
        rest = [h for h in newest if h["outcome"] != "pending"]
        for h in (pending + rest)[:12]:
            it = QListWidgetItem()
            row = HistoryRow(h, self._set_outcome)
            it.setSizeHint(row.sizeHint())
            self.h_list.addItem(it)
            self.h_list.setItemWidget(it, row)
        if not self.store.history:
            it = QListWidgetItem("Reminder aane ke baad yahan mark karna ✓ / ✗")
            it.setForeground(theme.q("muted"))
            self.h_list.addItem(it)

        self.n_list.blockSignals(True)
        self.n_list.clear()
        notes = sorted(self.store.notes, key=lambda n: (n.done, not n.pinned, -_ts(n.updated)))
        for n in notes:
            row = ItemRow(
                ("📌 " if n.pinned else "") + n.title,
                lambda _=False, n=n: self._delete_note(n),
                done=n.done,
                on_check=lambda on, n=n: self._set_done(n, on),
                on_open=lambda: self._go(lambda: self.open_manager("notes")),
            )
            it = QListWidgetItem()
            it.setData(ID, n.id)
            it.setSizeHint(row.sizeHint())
            self.n_list.addItem(it)
            self.n_list.setItemWidget(it, row)
        if not notes:
            it = QListWidgetItem("Koi note nahi. Upar likh ke + Add 👆")
            it.setForeground(theme.q("muted"))
            self.n_list.addItem(it)
        self.n_list.blockSignals(False)

    def _refresh_header(self):
        now = datetime.now()
        hinglish = self.buddy.cfg["language"] == "hinglish"
        part = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Good evening"
        self.greet.setText(f"{part}! 👋")
        self.when.setText(now.strftime("%A, %d %B · %H:%M"))
        if not self.buddy.cfg["weather_enabled"]:
            text = "Weather band hai (Settings)" if hinglish else "Weather is off (Settings)"
        else:
            text = self.buddy.outdoor.weather_line() or ("🌦 Weather aa raha hai…" if hinglish else "🌦 Loading weather…")
        self.weather.setText(text)
        self.weather.setVisible(True)

    def _refresh_today(self):
        self.t_list.clear()
        now = datetime.now()
        end = now.replace(hour=23, minute=59)
        rows = []
        for e in self.store.events_on(now.date()):
            s = str_to_dt(e.start)
            rows.append((s, ("Poora din" if e.all_day else s.strftime("%H:%M")), f"📅 {e.title}", s < now))
        for r in self.store.reminders:
            d = due_at(r)
            if d and now <= d <= end:
                rows.append((d, d.strftime("%H:%M"), f"⏰ {r.title}", False))
        for _, when, text, past in sorted(rows):
            it = QListWidgetItem(f"{when}   {text}")
            if past:
                it.setForeground(theme.q("done"))
            self.t_list.addItem(it)
        if not rows:
            it = QListWidgetItem("Aaj kuch nahi hai. Upar se event add karo 👆")
            it.setForeground(theme.q("muted"))
            self.t_list.addItem(it)

    def popup(self, anchor: QRect, screen: QRect, tab: str = "reminders"):
        self.tabs.setCurrentIndex({"reminders": 0, "notes": 1, "today": 2}.get(tab, 0))
        self._refresh_header()
        self._refresh_status()
        self.apply_theme()
        self.quiet_btn.blockSignals(True)
        self.quiet_btn.setChecked(self.buddy.quiet)
        self.quiet_btn.blockSignals(False)
        nxt = (datetime.now() + timedelta(hours=1)).replace(minute=0)
        self.r_time.setTime(QTime(nxt.hour, nxt.minute))
        self.e_time.setTime(QTime(nxt.hour, nxt.minute))
        self.refresh()
        x = anchor.left() - self.width() - 8
        if x < screen.left():
            x = anchor.right() + 8
        y = max(screen.top() + 8, min(anchor.bottom() - self.height(), screen.bottom() - self.height() - 8))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(50, (self.r_title if tab == "reminders" else self.n_text).setFocus)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            QTimer.singleShot(150, lambda: (not self.isActiveWindow()) and self._maybe_hide())
        super().changeEvent(e)

    def _maybe_hide(self):
        # keep open while a child popup (time picker, menu) has focus
        from PySide6.QtWidgets import QApplication

        if QApplication.activePopupWidget() is None and QApplication.activeWindow() is None:
            self.hide()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(theme.q("outline"), 2))
        p.setBrush(theme.q("bg"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 16, 16)


def _ts(s: str) -> float:
    d = str_to_dt(s)
    return d.timestamp() if d else 0.0
