"""The Saarthi window: Reminders, Notes, Calendar and Quotes tabs."""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, Qt, QTime, QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .scheduler import due_at, schedule
from .store import REPEATS, Event, Feed, Note, QuoteList, Reminder, Store, dt_to_str, str_to_dt

ID_ROLE = Qt.ItemDataRole.UserRole


def _fmt(d: datetime | None) -> str:
    if d is None:
        return "—"
    today = datetime.now().date()
    if d.date() == today:
        day = "Today"
    elif d.date() == today + timedelta(days=1):
        day = "Tomorrow"
    else:
        day = d.strftime("%a %d %b")
    return f"{day} {d.strftime('%H:%M')}"


def _qdt(d: datetime) -> QDateTime:
    return QDateTime(QDate(d.year, d.month, d.day), QTime(d.hour, d.minute))


def _buttons(*specs) -> QHBoxLayout:
    row = QHBoxLayout()
    for label, slot in specs:
        if label is None:
            row.addStretch(1)
            continue
        b = QPushButton(label)
        b.clicked.connect(slot)
        row.addWidget(b)
    return row


# ------------------------------------------------------------------ reminders
class RemindersTab(QWidget):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.current: Reminder | None = None

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._select)
        self.list.itemChanged.connect(self._toggled)

        self.title = QLineEdit(placeholderText="e.g. Call mom, Drink water, Submit timesheet")
        self.when = QDateTimeEdit(calendarPopup=True, displayFormat="ddd dd MMM yyyy  HH:mm")
        self.repeat = QComboBox()
        for key, label in REPEATS.items():
            self.repeat.addItem(label, key)
        self.interval = QSpinBox(minimum=1, maximum=24 * 60, value=60, suffix=" min")
        self.active_from = QTimeEdit(QTime(9, 0), displayFormat="HH:mm")
        self.active_to = QTimeEdit(QTime(21, 0), displayFormat="HH:mm")
        self.repeat.currentIndexChanged.connect(self._repeat_changed)

        form = QFormLayout()
        form.addRow("What", self.title)
        form.addRow("When", self.when)
        form.addRow("Repeat", self.repeat)
        self.interval_row = QWidget()
        il = QHBoxLayout(self.interval_row)
        il.setContentsMargins(0, 0, 0, 0)
        il.addWidget(QLabel("Every"))
        il.addWidget(self.interval)
        il.addWidget(QLabel("between"))
        il.addWidget(self.active_from)
        il.addWidget(QLabel("and"))
        il.addWidget(self.active_to)
        form.addRow("", self.interval_row)

        right = QVBoxLayout()
        right.addLayout(form)
        right.addLayout(_buttons(("New", self.new), (None, None), ("Delete", self.delete), ("Save", self.save)))
        right.addWidget(QLabel("<b>Did I actually do it?</b>"))
        self.stats = QLabel()
        self.stats.setStyleSheet("color: gray")
        right.addWidget(self.stats)
        self.history = QListWidget()
        right.addWidget(self.history, 2)
        hint = QLabel("Tip: “Every N minutes” is great for drink-water or posture reminders.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray")
        right.addWidget(hint)

        lay = QHBoxLayout(self)
        lay.addWidget(self.list, 1)
        rw = QWidget()
        rw.setLayout(right)
        lay.addWidget(rw, 1)
        self.refresh()
        self.new()

    def refresh_history(self):
        from .quick_panel import HistoryRow

        done, missed, pending = self.store.stats(7)
        self.stats.setText(f"Last 7 days: {done} ✓ done · {missed} ✗ skipped · {pending} not marked")
        self.history.clear()
        newest = sorted(self.store.history, key=lambda h: h.get("due") or h["at"], reverse=True)[:40]
        for h in newest:
            it = QListWidgetItem()
            row = HistoryRow(h, self._set_outcome)
            it.setSizeHint(row.sizeHint())
            self.history.addItem(it)
            self.history.setItemWidget(it, row)

    def _set_outcome(self, hid, outcome):
        self.store.set_outcome(hid, outcome)
        self.store.save(notify=False)
        done, missed, pending = self.store.stats(7)
        self.stats.setText(f"Last 7 days: {done} ✓ done · {missed} ✗ skipped · {pending} not marked")

    def _repeat_changed(self):
        self.interval_row.setVisible(self.repeat.currentData() == "interval")

    def refresh(self):
        self.refresh_history()
        self.list.blockSignals(True)
        cur = self.current.id if self.current else None
        self.list.clear()
        items = sorted(self.store.reminders, key=lambda r: (not r.enabled, due_at(r) or datetime.max))
        for r in items:
            label = (
                f"{r.title}\n   {_fmt(due_at(r)) if r.enabled else 'done / off'} · {REPEATS.get(r.repeat, r.repeat)}"
            )
            it = QListWidgetItem(label)
            it.setData(ID_ROLE, r.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if r.enabled else Qt.CheckState.Unchecked)
            self.list.addItem(it)
            if r.id == cur:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)

    def _find(self, rid) -> Reminder | None:
        return next((r for r in self.store.reminders if r.id == rid), None)

    def _select(self, item, _prev=None):
        r = self._find(item.data(ID_ROLE)) if item else None
        if r is None:
            return
        self.current = r
        self.title.setText(r.title)
        self.when.setDateTime(_qdt(str_to_dt(r.at)))
        self.repeat.setCurrentIndex(max(0, self.repeat.findData(r.repeat)))
        self.interval.setValue(r.interval_min)
        self.active_from.setTime(QTime.fromString(r.active_from, "HH:mm"))
        self.active_to.setTime(QTime.fromString(r.active_to, "HH:mm"))
        self._repeat_changed()

    def _toggled(self, item):
        r = self._find(item.data(ID_ROLE))
        if r is None:
            return
        r.enabled = item.checkState() == Qt.CheckState.Checked
        if r.enabled:
            schedule(r, datetime.now())
            if r.next_at is None:  # a past one-off: nothing left to remind
                r.enabled = False
        self.store.save()
        QTimer.singleShot(0, self.refresh)

    def new(self):
        self.current = None
        self.list.clearSelection()
        self.title.clear()
        nxt = (datetime.now() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        self.when.setDateTime(_qdt(nxt))
        self.repeat.setCurrentIndex(0)
        self._repeat_changed()
        self.title.setFocus()

    def save(self):
        title = self.title.text().strip()
        if not title:
            self.title.setFocus()
            return
        r = self.current or Reminder(title, "")
        r.title = title
        r.at = dt_to_str(self.when.dateTime().toPython())
        r.repeat = self.repeat.currentData()
        r.interval_min = self.interval.value()
        r.active_from = self.active_from.time().toString("HH:mm")
        r.active_to = self.active_to.time().toString("HH:mm")
        r.enabled = True
        schedule(r, datetime.now())
        if r.next_at is None:
            QMessageBox.information(self, "Saarthi", "That time has already passed. Pick a future time.")
            return
        if self.current is None:
            self.store.reminders.append(r)
            self.current = r
        self.store.save()
        self.refresh()

    def delete(self):
        if self.current and self.current in self.store.reminders:
            self.store.reminders.remove(self.current)
            self.store.save()
            self.refresh()
            self.new()


# ------------------------------------------------------------------ notes
class NotesTab(QWidget):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.current: Note | None = None
        self.search = QLineEdit(placeholderText="Search notes…")
        self.search.textChanged.connect(self.refresh)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._select)
        self.list.itemChanged.connect(self._done_toggled)
        self.editor = QPlainTextEdit(
            placeholderText="Write anything. First line becomes the title. Saved automatically."
        )
        f = QFont()
        f.setPointSize(11)
        self.editor.setFont(f)
        self.editor.textChanged.connect(lambda: self._autosave.start(600))
        self._autosave = QTimer(self, singleShot=True, timeout=self._save)
        self.pin = QCheckBox("Pin to top")
        self.pin.toggled.connect(self._pin)

        left = QVBoxLayout()
        left.addWidget(self.search)
        left.addWidget(self.list)
        left.addLayout(_buttons(("New note", self.new), (None, None), ("Delete", self.delete)))
        lw = QWidget()
        lw.setLayout(left)
        right = QVBoxLayout()
        right.addWidget(self.editor)
        right.addWidget(self.pin)
        rw = QWidget()
        rw.setLayout(right)
        split = QSplitter()
        split.addWidget(lw)
        split.addWidget(rw)
        split.setSizes([260, 520])
        QVBoxLayout(self).addWidget(split)
        self.refresh()
        self.editor.setEnabled(False)

    def refresh(self):
        q = self.search.text().lower().strip()
        self.list.blockSignals(True)
        self.list.clear()
        notes = sorted(self.store.notes, key=lambda n: (not n.done, n.pinned, n.updated), reverse=True)
        for n in notes:
            if q and q not in n.text.lower():
                continue
            it = QListWidgetItem(("📌 " if n.pinned else "") + n.title)
            it.setData(ID_ROLE, n.id)
            it.setToolTip(n.updated.replace("T", " "))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if n.done else Qt.CheckState.Unchecked)
            f = QFont(it.font())
            f.setStrikeOut(n.done)
            it.setFont(f)
            if n.done:
                it.setForeground(QColor("#9AA2B6"))
            self.list.addItem(it)
            if self.current and n.id == self.current.id:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)

    def _select(self, item, _prev=None):
        self._save()
        n = next((n for n in self.store.notes if item and n.id == item.data(ID_ROLE)), None)
        self.current = n
        self.editor.blockSignals(True)
        self.editor.setPlainText(n.text if n else "")
        self.editor.blockSignals(False)
        self.editor.setEnabled(n is not None)
        self.pin.blockSignals(True)
        self.pin.setChecked(bool(n and n.pinned))
        self.pin.blockSignals(False)

    def _save(self):
        self._autosave.stop()
        n = self.current
        if n is None or n.text == self.editor.toPlainText():
            return
        n.text = self.editor.toPlainText()
        n.updated = dt_to_str(datetime.now())
        self.store.save()
        item = self.list.currentItem()
        if item:
            item.setText(("📌 " if n.pinned else "") + n.title)

    def _done_toggled(self, item):
        n = next((n for n in self.store.notes if n.id == item.data(ID_ROLE)), None)
        if n is not None:
            n.done = item.checkState() == Qt.CheckState.Checked
            self.store.save()
            QTimer.singleShot(0, self.refresh)

    def _pin(self, on):
        if self.current:
            self.current.pinned = on
            self.store.save()
            self.refresh()

    def new(self, text: str = ""):
        self._save()
        n = Note(text=text or "")
        self.store.notes.append(n)
        self.store.save()
        self.current = n
        self.search.clear()
        self.refresh()
        self._select(self.list.currentItem())
        self.editor.setFocus()

    def delete(self):
        if self.current and self.current in self.store.notes:
            if (
                QMessageBox.question(self, "Delete note", f"Delete “{self.current.title}”?")
                != QMessageBox.StandardButton.Yes
            ):
                return
            self.store.notes.remove(self.current)
            self.current = None
            self.store.save()
            self.refresh()
            self._select(None)


# ------------------------------------------------------------------ calendar
class CalendarTab(QWidget):
    def __init__(self, store: Store, sync_now):
        super().__init__()
        self.store = store
        self.sync_now = sync_now
        self.current: Event | None = None

        self.cal = QCalendarWidget()
        self.cal.setGridVisible(False)
        self.cal.selectionChanged.connect(self.refresh_day)
        self.cal.currentPageChanged.connect(lambda *_: self.mark_days())

        self.day_list = QListWidget()
        self.day_list.currentItemChanged.connect(self._select)

        self.title = QLineEdit(placeholderText="Event title")
        self.start = QDateTimeEdit(calendarPopup=True, displayFormat="ddd dd MMM  HH:mm")
        self.end = QDateTimeEdit(calendarPopup=True, displayFormat="ddd dd MMM  HH:mm")
        self.all_day = QCheckBox("All day")
        self.remind = QSpinBox(minimum=0, maximum=24 * 60, value=10, suffix=" min before")
        self.start.dateTimeChanged.connect(self._start_moved)
        form = QFormLayout()
        form.addRow("Title", self.title)
        form.addRow("Starts", self.start)
        form.addRow("Ends", self.end)
        form.addRow("", self.all_day)
        form.addRow("Remind", self.remind)
        self.readonly = QLabel()
        self.readonly.setStyleSheet("color: gray")
        self.form_box = QGroupBox("Event")
        fb = QVBoxLayout(self.form_box)
        fb.addLayout(form)
        fb.addWidget(self.readonly)
        fb.addLayout(_buttons(("New", self.new), (None, None), ("Delete", self.delete), ("Save", self.save)))

        # feeds
        self.feeds = QListWidget()
        self.feeds.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.feed_name = QLineEdit(placeholderText="Name, e.g. Work")
        self.feed_url = QLineEdit(placeholderText="Secret iCal address (https://… .ics)")
        feeds_box = QGroupBox("Synced calendars (read-only)")
        fl = QVBoxLayout(feeds_box)
        help_ = QLabel(
            "Google Calendar: Settings → your calendar → <i>Secret address in iCal format</i>. "
            "Outlook: Settings → Shared calendars → Publish → ICS link."
        )
        help_.setWordWrap(True)
        help_.setStyleSheet("color: gray")
        fl.addWidget(self.feeds)
        row = QHBoxLayout()
        row.addWidget(self.feed_name, 1)
        row.addWidget(self.feed_url, 3)
        fl.addLayout(row)
        fl.addLayout(
            _buttons(
                ("Add calendar", self.add_feed), ("Remove", self.remove_feed), (None, None), ("Sync now", self.sync_now)
            )
        )
        fl.addWidget(help_)

        left = QVBoxLayout()
        left.addWidget(self.cal)
        left.addWidget(QLabel("<b>Events on this day</b>"))
        left.addWidget(self.day_list)
        lw = QWidget()
        lw.setLayout(left)
        right = QVBoxLayout()
        right.addWidget(self.form_box)
        right.addWidget(feeds_box)
        rw = QWidget()
        rw.setLayout(right)
        lay = QHBoxLayout(self)
        lay.addWidget(lw, 1)
        lay.addWidget(rw, 1)
        self.refresh()
        self.new()

    def refresh(self):
        self.mark_days()
        self.refresh_day()
        self.refresh_feeds()

    def mark_days(self):
        self.cal.setDateTextFormat(QDate(), QTextCharFormat())
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setForeground(QColor("#3E6FE0"))
        fmt.setFontUnderline(True)
        for e in self.store.all_events():
            d = str_to_dt(e.start)
            self.cal.setDateTextFormat(QDate(d.year, d.month, d.day), fmt)

    def refresh_day(self):
        day = self.cal.selectedDate().toPython()
        self.day_list.blockSignals(True)
        self.day_list.clear()
        for e in self.store.events_on(day):
            when = "All day" if e.all_day else str_to_dt(e.start).strftime("%H:%M")
            src = "" if e.source == "local" else f"   [{e.source}]"
            it = QListWidgetItem(f"{when}  {e.title}{src}")
            it.setData(ID_ROLE, (e.source, e.id, e.start))
            self.day_list.addItem(it)
        self.day_list.blockSignals(False)

    def refresh_feeds(self):
        self.feeds.clear()
        for f in self.store.feeds:
            status = (
                f"error: {f.last_error}"
                if f.last_error
                else (f"synced {f.last_sync.replace('T', ' ')}" if f.last_sync else "not synced yet")
            )
            it = QListWidgetItem(f"{f.name} — {status}")
            it.setData(ID_ROLE, f.id)
            self.feeds.addItem(it)

    def _select(self, item, _prev=None):
        if not item:
            return
        src, eid, start = item.data(ID_ROLE)
        e = next((e for e in self.store.all_events() if (e.source, e.id, e.start) == (src, eid, start)), None)
        if e is None:
            return
        self.current = e
        self.title.setText(e.title)
        self.start.setDateTime(_qdt(str_to_dt(e.start)))
        self.end.setDateTime(_qdt(str_to_dt(e.end) if e.end else str_to_dt(e.start) + timedelta(hours=1)))
        self.all_day.setChecked(e.all_day)
        self.remind.setValue(e.remind_before_min)
        local = e.source == "local"
        for w in (self.title, self.start, self.end, self.all_day, self.remind):
            w.setEnabled(local)
        self.readonly.setText("" if local else f"From “{e.source}” (edit it in that calendar).")

    def _start_moved(self, qdt):
        if self.end.dateTime() <= qdt:
            self.end.setDateTime(qdt.addSecs(3600))

    def new(self):
        self.current = None
        self.day_list.clearSelection()
        for w in (self.title, self.start, self.end, self.all_day, self.remind):
            w.setEnabled(True)
        self.readonly.clear()
        self.title.clear()
        d = self.cal.selectedDate().toPython()
        start = datetime.combine(d, datetime.now().time()).replace(minute=0, second=0, microsecond=0) + timedelta(
            hours=1
        )
        self.start.setDateTime(_qdt(start))
        self.end.setDateTime(_qdt(start + timedelta(hours=1)))
        self.all_day.setChecked(False)
        self.remind.setValue(10)

    def save(self):
        if self.current is not None and self.current.source != "local":
            return
        title = self.title.text().strip()
        if not title:
            self.title.setFocus()
            return
        e = self.current or Event(title, "")
        e.title = title
        s = self.start.dateTime().toPython()
        if self.all_day.isChecked():
            s = s.replace(hour=0, minute=0)
        e.start, e.end = dt_to_str(s), dt_to_str(self.end.dateTime().toPython())
        e.all_day = self.all_day.isChecked()
        e.remind_before_min = self.remind.value()
        if self.current is None:
            self.store.events.append(e)
        else:  # an edited time is a new occurrence for reminder purposes
            self.store.fired = {k: v for k, v in self.store.fired.items() if f"|{e.id}|" not in k}
        self.current = e
        self.store.save()
        self.cal.setSelectedDate(QDate(s.year, s.month, s.day))
        self.refresh()

    def delete(self):
        if self.current and self.current in self.store.events:
            self.store.events.remove(self.current)
            self.store.save()
            self.refresh()
            self.new()

    def add_feed(self):
        url = self.feed_url.text().strip()
        if not url.startswith(("https://", "http://", "webcal://")):
            QMessageBox.warning(self, "Saarthi", "Paste the calendar's iCal link (starts with https:// or webcal://).")
            return
        name = self.feed_name.text().strip() or f"Calendar {len(self.store.feeds) + 1}"
        self.store.feeds.append(Feed(name, url))
        self.store.save()
        self.feed_name.clear()
        self.feed_url.clear()
        self.refresh_feeds()
        self.sync_now()

    def remove_feed(self):
        item = self.feeds.currentItem()
        if not item:
            return
        f = next((f for f in self.store.feeds if f.id == item.data(ID_ROLE)), None)
        if f:
            self.store.feeds.remove(f)
            self.store.feed_events = [e for e in self.store.feed_events if e.source != f.name]
            self.store.save()
            self.refresh()


# ------------------------------------------------------------------ quotes
class QuotesTab(QWidget):
    def __init__(self, store: Store, preview):
        super().__init__()
        self.store = store
        self.preview_cb = preview
        self.current: QuoteList | None = None
        self.lists = QListWidget()
        self.lists.currentItemChanged.connect(self._select)
        self.lists.itemChanged.connect(self._toggled)
        self.name = QLineEdit()
        self.items = QPlainTextEdit(placeholderText="One line per message…")
        self.every_min = QSpinBox(minimum=1, maximum=24 * 60, suffix=" min")
        self.every_max = QSpinBox(minimum=1, maximum=24 * 60, suffix=" min")
        form = QFormLayout()
        form.addRow("List name", self.name)
        gap = QHBoxLayout()
        gap.addWidget(QLabel("every"))
        gap.addWidget(self.every_min)
        gap.addWidget(QLabel("to"))
        gap.addWidget(self.every_max)
        gap.addStretch(1)
        form.addRow("Say one", gap)
        right = QVBoxLayout()
        intro = QLabel(
            "Your own lists of things for the buddy to say now and then: motivation, habits, affirmations, anything."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: gray")
        right.addWidget(intro)
        right.addLayout(form)
        right.addWidget(self.items)
        right.addLayout(_buttons(("Try one now", self.preview), (None, None), ("Save", self.save)))
        left = QVBoxLayout()
        left.addWidget(self.lists)
        left.addLayout(_buttons(("New list", self.new), ("Delete", self.delete)))
        lw, rw = QWidget(), QWidget()
        lw.setLayout(left)
        rw.setLayout(right)
        lay = QHBoxLayout(self)
        lay.addWidget(lw, 1)
        lay.addWidget(rw, 2)
        self.refresh()
        if self.lists.count():
            self.lists.setCurrentRow(0)

    def refresh(self):
        self.lists.blockSignals(True)
        self.lists.clear()
        for q in self.store.quotes:
            it = QListWidgetItem(f"{q.name}  ({len(q.items)})")
            it.setData(ID_ROLE, q.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if q.enabled else Qt.CheckState.Unchecked)
            self.lists.addItem(it)
            if self.current and q.id == self.current.id:
                self.lists.setCurrentItem(it)
        self.lists.blockSignals(False)

    def _find(self, qid):
        return next((q for q in self.store.quotes if q.id == qid), None)

    def _toggled(self, item):
        q = self._find(item.data(ID_ROLE))
        if q:
            q.enabled = item.checkState() == Qt.CheckState.Checked
            self.store.save()

    def _select(self, item, _prev=None):
        q = self._find(item.data(ID_ROLE)) if item else None
        self.current = q
        if q is None:
            return
        self.name.setText(q.name)
        self.items.setPlainText("\n".join(q.items))
        self.every_min.setValue(q.every_min)
        self.every_max.setValue(q.every_max)

    def save(self):
        q = self.current
        if q is None:
            return
        q.name = self.name.text().strip() or q.name
        q.items = [ln.strip() for ln in self.items.toPlainText().splitlines() if ln.strip()]
        q.every_min, q.every_max = sorted((self.every_min.value(), self.every_max.value()))
        self.store.save()
        self.refresh()

    def new(self):
        q = QuoteList("New list", [], True, 30, 60)
        self.store.quotes.append(q)
        self.store.save()
        self.current = q
        self.refresh()
        self._select(self.lists.currentItem())
        self.name.selectAll()
        self.name.setFocus()

    def delete(self):
        if (
            self.current
            and QMessageBox.question(self, "Delete list", f"Delete “{self.current.name}”?")
            == QMessageBox.StandardButton.Yes
        ):
            self.store.quotes.remove(self.current)
            self.current = None
            self.store.save()
            self.refresh()

    def preview(self):
        lines = [ln.strip() for ln in self.items.toPlainText().splitlines() if ln.strip()]
        if lines:
            import random

            self.preview_cb(random.choice(lines))


# ------------------------------------------------------------------ window
class ManagerWindow(QWidget):
    TABS = ("reminders", "notes", "calendar", "quotes", "settings")

    def __init__(self, store: Store, sync_now, say, buddy=None):
        super().__init__()
        self.setWindowTitle("Saarthi")
        self.resize(900, 600)
        self.store = store
        self.tabs = QTabWidget()
        self.reminders = RemindersTab(store)
        self.notes = NotesTab(store)
        self.calendar = CalendarTab(store, sync_now)
        self.quotes = QuotesTab(store, say)
        self.tabs.addTab(self.reminders, "⏰  Reminders")
        self.tabs.addTab(self.notes, "📝  Notes")
        self.tabs.addTab(self.calendar, "📅  Calendar")
        self.tabs.addTab(self.quotes, "💬  Quotes")
        if buddy is not None:
            from .settings_tab import SettingsTab

            self.settings = SettingsTab(buddy)
            self.tabs.addTab(self.settings, "⚙️  Settings")
        QVBoxLayout(self).addWidget(self.tabs)
        self._refresh_timer = QTimer(self, timeout=self.reminders.refresh)
        self._refresh_timer.start(30_000)

    def open(self, tab: str = "reminders"):
        self.tabs.setCurrentIndex(self.TABS.index(tab))
        self.external_change()  # always show the latest data
        self.show()
        self.raise_()
        self.activateWindow()

    def external_change(self):
        """Store changed elsewhere (quick panel, reminder card, calendar sync): show it here too."""
        self.reminders.refresh()
        self.calendar.refresh()
        self.notes.refresh()
        self.quotes.refresh()

    def closeEvent(self, e):
        self.notes._save()
        super().closeEvent(e)
