"""Settings tab: weather location and office -> home commute."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from . import commute as cm
from .weather import Place, search_city


def find_place(text: str) -> list[Place]:
    """Search an address, or read a pasted Google Maps link."""
    if cm.is_link(text):
        return [cm.resolve_maps_link(text)]
    return cm.search_address(text)


DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
KEY_HELP = {
    "tomtom": 'Free key: <a href="https://developer.tomtom.com/">developer.tomtom.com</a> → sign up → '
    "copy the API key (no card needed).",
    "google": 'Key: <a href="https://console.cloud.google.com/google/maps-apis">Google Cloud console</a> → '
    "enable <i>Routes API</i> → create API key (needs a billing account).",
    "free": "Uses OpenStreetMap routing with a rush-hour guess. Fine for distance, not for live jams.",
}


def _gray(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet("color: gray")
    lab.setOpenExternalLinks(True)
    return lab


class PlacePicker(QWidget):
    """Text box + Search + results dropdown. Calls on_pick(Place)."""

    def __init__(
        self,
        placeholder: str,
        search: Callable[[str], list[Place]],
        on_pick: Callable[[Place], None],
        current: dict | None,
    ):
        super().__init__()
        self.search_fn, self.on_pick = search, on_pick
        self.query = QLineEdit(placeholderText=placeholder)
        self.query.returnPressed.connect(self.search)
        btn = QPushButton("Search")
        btn.clicked.connect(self.search)
        self.results = QComboBox()
        self.results.setVisible(False)
        self.results.activated.connect(self._picked)
        self.current = QLabel()
        self.current.setWordWrap(True)
        self._places: list[Place] = []
        self.show_current(current)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.query, 1)
        row.addWidget(btn)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(row)
        lay.addWidget(self.results)
        lay.addWidget(self.current)

    def show_current(self, d: dict | None):
        self.current.setText(f"✓ {d['name']}" if d else "<span style='color:gray'>not set</span>")

    def search(self):
        q = self.query.text().strip()
        if not q:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._places = self.search_fn(q)
        except Exception as e:
            QMessageBox.warning(self, "Saarthi", f"Search failed: {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not self._places:
            QMessageBox.information(self, "Saarthi", "Nothing found. Try adding the city name.")
            return
        self.results.clear()
        self.results.addItem(f"{len(self._places)} result(s) — pick one…")
        for p in self._places:
            self.results.addItem(p.name)
        self.results.setVisible(True)
        if len(self._places) == 1:
            self.results.setCurrentIndex(1)
            self._picked(1)
        else:
            self.results.showPopup()

    def _picked(self, idx: int):
        if idx <= 0:
            return
        p = self._places[idx - 1]
        self.on_pick(p)
        self.show_current({"name": p.name})
        self.results.setVisible(False)
        self.query.clear()


class SettingsTab(QScrollArea):
    def __init__(self, buddy):
        super().__init__()
        self.buddy = buddy
        self.cfg = buddy.cfg
        self.setWidgetResizable(True)
        body = QWidget()
        self.setWidget(body)
        lay = QVBoxLayout(body)
        lay.addWidget(self._look_box())
        lay.addWidget(self._wellness_box())
        lay.addWidget(self._weather_box())
        lay.addWidget(self._commute_box())
        lay.addWidget(self._share_box())
        lay.addWidget(_gray("Settings save automatically. API keys stay on this computer in config.json."))
        lay.addStretch(1)

    # ---------------- live link ----------------
    def _share_box(self) -> QGroupBox:
        from . import share as sh

        cfg, share = self.cfg, self.buddy.share
        box = QGroupBox("Couple mode (someone can watch your Saarthi, play with it and chat)")
        f = QFormLayout(box)
        url = QLineEdit(cfg["share_url"], placeholderText="https://saarthi-live.<you>.workers.dev")
        url.editingFinished.connect(lambda: cfg.__setitem__("share_url", url.text().strip()))
        f.addRow("Relay address", url)
        on = QCheckBox("💑 Couple mode: the link, their pokes / football / hug / kiss here too, and chat")
        on.setChecked(share.enabled)
        on.toggled.connect(share.set_enabled)
        f.addRow(on)
        me = QLineEdit(cfg["share_name"], placeholderText="Your name on the page")
        me.editingFinished.connect(lambda: cfg.__setitem__("share_name", me.text().strip()))
        f.addRow("My name", me)
        friend = QLineEdit(cfg["share_friend"], placeholderText="Who you share it with")
        friend.editingFinished.connect(lambda: cfg.__setitem__("share_friend", friend.text().strip()))
        f.addRow("Their name", friend)
        link = QLineEdit(sh.link(cfg), readOnly=True, placeholderText="Set the relay address first")
        f.addRow("Link", link)
        f.addRow(
            _gray(
                "They see your character, a general 'what he's doing' (no titles), chat and the fun lines. "
                "Never your reminders, notes, calendar, weather or traffic."
            )
        )
        return box

    # ---------------- look ----------------
    def _look_box(self) -> QGroupBox:
        box = QGroupBox("Look")
        f = QFormLayout(box)
        combo = QComboBox()
        for key, label in (("auto", "Follow my system"), ("dark", "Dark"), ("light", "Light")):
            combo.addItem(label, key)
        combo.setCurrentIndex(max(0, combo.findData(self.cfg["theme"])))

        def changed():
            from . import theme

            self.cfg["theme"] = theme.MODE = combo.currentData()
            panel = self.buddy.org.panel
            if panel is not None:
                panel.apply_theme()

        combo.currentIndexChanged.connect(changed)
        f.addRow("Panel and cards", combo)
        return box

    # ---------------- wellness ----------------
    def _wellness_box(self) -> QGroupBox:
        cfg = self.cfg
        box = QGroupBox("Breaks and breathing")
        f = QFormLayout(box)

        brk = QCheckBox("Remind me to take breaks (the buddy takes one with you)")
        brk.setChecked(bool(cfg["break_enabled"]))
        brk.toggled.connect(lambda v: cfg.__setitem__("break_enabled", v))
        f.addRow(brk)
        work = QSpinBox(minimum=10, maximum=180, value=int(cfg["work_minutes"]), suffix=" min of work")
        work.valueChanged.connect(lambda v: cfg.__setitem__("work_minutes", v))
        rest = QSpinBox(minimum=1, maximum=60, value=int(cfg["break_minutes"]), suffix=" min break")
        rest.valueChanged.connect(lambda v: cfg.__setitem__("break_minutes", v))
        row = QHBoxLayout()
        row.addWidget(QLabel("After"))
        row.addWidget(work)
        row.addWidget(QLabel("take a"))
        row.addWidget(rest)
        row.addStretch(1)
        f.addRow(row)
        f.addRow(_gray("Common choices: 50 + 10, or Pomodoro 25 + 5. Walking away for 5 minutes resets the timer."))

        br = QCheckBox("Guided breathing a few times a day")
        br.setChecked(bool(cfg["breathing_enabled"]))
        br.toggled.connect(lambda v: cfg.__setitem__("breathing_enabled", v))
        f.addRow(br)
        lo, hi = cfg["breathing_every"]
        every = QSpinBox(minimum=15, maximum=480, value=int(lo), suffix=" min")
        every_hi = QSpinBox(minimum=15, maximum=480, value=int(hi), suffix=" min")

        def gap_changed():
            a, b = sorted((every.value(), every_hi.value()))
            cfg["breathing_every"] = [a, b]

        every.valueChanged.connect(gap_changed)
        every_hi.valueChanged.connect(gap_changed)
        cycles = QSpinBox(minimum=2, maximum=20, value=int(cfg["breathing_cycles"]), suffix=" breaths")
        cycles.valueChanged.connect(lambda v: cfg.__setitem__("breathing_cycles", v))
        row = QHBoxLayout()
        row.addWidget(QLabel("Every"))
        row.addWidget(every)
        row.addWidget(QLabel("to"))
        row.addWidget(every_hi)
        row.addWidget(QLabel(","))
        row.addWidget(cycles)
        row.addStretch(1)
        f.addRow(row)

        lunch = QSpinBox(minimum=10, maximum=120, value=int(cfg["lunch_minutes"]), suffix=" min")
        lunch.valueChanged.connect(lambda v: cfg.__setitem__("lunch_minutes", v))
        lrow = QHBoxLayout()
        lrow.addWidget(QLabel("Lunch status lasts"))
        lrow.addWidget(lunch)
        lrow.addWidget(QLabel("(eats 10–15 min, then strolls and thinks)"))
        lrow.addStretch(1)
        f.addRow(lrow)

        walk = QCheckBox("Walking mode: stroll around the screen now and then (always paces during breaks)")
        walk.setChecked(bool(cfg["walk_enabled"]))
        walk.toggled.connect(lambda v: cfg.__setitem__("walk_enabled", v))
        f.addRow(walk)

        now = QHBoxLayout()
        b1 = QPushButton("Take a break now ☕")
        b1.clicked.connect(lambda: self.buddy.wellness.start_break())
        b2 = QPushButton("Breathe now 🧘")
        b2.clicked.connect(lambda: self.buddy.wellness.start_breathe())
        now.addWidget(b1)
        now.addWidget(b2)
        f.addRow(now)
        return box

    # ---------------- weather ----------------
    def _weather_box(self) -> QGroupBox:
        cfg = self.cfg
        box = QGroupBox("Weather")
        f = QFormLayout(box)
        on = QCheckBox("Show weather, outfits and rain warnings")
        on.setChecked(bool(cfg["weather_enabled"]))
        on.toggled.connect(self._weather_toggled)
        f.addRow(on)
        self.auto = QRadioButton("Automatic (approximate city from your internet connection)")
        manual = QRadioButton("This city:")
        (manual if cfg["weather_place"] else self.auto).setChecked(True)
        self.city = PlacePicker("City name, e.g. Pune", search_city, self._set_city, cfg["weather_place"])
        self.city.setEnabled(manual.isChecked())
        manual.toggled.connect(self.city.setEnabled)
        self.auto.toggled.connect(self._auto_toggled)
        f.addRow(self.auto)
        f.addRow(manual, self.city)
        f.addRow(
            _gray(
                "Automatic mode sends your IP address to ipapi.co (or ipinfo.io) to guess the city. "
                "Weather comes from Open-Meteo."
            )
        )
        btn = QPushButton("Tell me the weather now")
        btn.clicked.connect(self.buddy.outdoor.say_weather)
        f.addRow(btn)
        brief = QTimeEdit(QTime.fromString(cfg["brief_at"], "HH:mm"), displayFormat="HH:mm")
        brief.timeChanged.connect(lambda t: cfg.__setitem__("brief_at", t.toString("HH:mm")))
        f.addRow("Morning brief at", brief)
        f.addRow(_gray("Today's plan and the weather, once a day, as soon as you're at the laptop after this time."))
        return box

    def _weather_toggled(self, on):
        self.cfg["weather_enabled"] = on
        self.buddy.outdoor.refresh_weather()

    def _auto_toggled(self, on):
        if on:
            self.cfg["weather_place"] = None
            self.city.show_current(None)
            self.buddy.outdoor.refresh_weather()

    def _set_city(self, p: Place):
        self.cfg["weather_place"] = {"name": p.name, "lat": p.lat, "lon": p.lon}
        self.buddy.outdoor.refresh_weather()

    # ---------------- commute ----------------
    def _commute_box(self) -> QGroupBox:
        cfg = self.cfg
        box = QGroupBox("Office to home traffic")
        f = QFormLayout(box)
        self.commute_form = f
        on = QCheckBox("Before logout, tell me how long the ride home will take")
        on.setChecked(bool(cfg["commute_enabled"]))
        on.toggled.connect(lambda v: cfg.__setitem__("commute_enabled", v))
        f.addRow(on)
        f.addRow(
            "Home",
            PlacePicker(
                "Address, area, or a Google Maps link", find_place, lambda p: self._set_place("home", p), cfg["home"]
            ),
        )
        f.addRow(
            "Office",
            PlacePicker(
                "Address, area, or a Google Maps link",
                find_place,
                lambda p: self._set_place("office", p),
                cfg["office"],
            ),
        )

        logout = QTimeEdit(QTime.fromString(cfg["logout"], "HH:mm"), displayFormat="HH:mm")
        logout.timeChanged.connect(lambda t: cfg.__setitem__("logout", t.toString("HH:mm")))
        before = QSpinBox(minimum=0, maximum=120, value=int(cfg["commute_before"]), suffix=" min before")
        before.valueChanged.connect(lambda v: cfg.__setitem__("commute_before", v))
        row = QHBoxLayout()
        row.addWidget(logout)
        row.addWidget(QLabel("alert"))
        row.addWidget(before)
        row.addStretch(1)
        f.addRow("Logout at", row)

        days = QHBoxLayout()
        self.day_boxes = []
        for i, name in enumerate(DAYS):
            cb = QCheckBox(name)
            cb.setChecked(i in cfg["workdays"])
            cb.toggled.connect(self._days_changed)
            self.day_boxes.append(cb)
            days.addWidget(cb)
        days.addStretch(1)
        f.addRow("Work days", days)

        mode = QComboBox()
        for k, v in cm.MODES.items():
            mode.addItem(v, k)
        mode.setCurrentIndex(max(0, mode.findData(cfg["commute_mode"])))
        mode.currentIndexChanged.connect(lambda: cfg.__setitem__("commute_mode", mode.currentData()))
        f.addRow("I travel by", mode)

        self.provider = QComboBox()
        for k, v in cm.PROVIDERS.items():
            self.provider.addItem(v, k)
        self.provider.setCurrentIndex(max(0, self.provider.findData(cfg["commute_provider"])))
        self.provider.currentIndexChanged.connect(self._provider_changed)
        f.addRow("Traffic data", self.provider)
        self.key = QLineEdit(echoMode=QLineEdit.EchoMode.Password, placeholderText="Paste API key")
        self.key.editingFinished.connect(self._key_changed)
        self.key_help = _gray("")
        f.addRow("API key", self.key)
        f.addRow("", self.key_help)
        btn = QPushButton("Check traffic now")
        btn.clicked.connect(lambda: self.buddy.outdoor.commute_now())
        f.addRow(btn)
        self._provider_changed()
        return box

    def _set_place(self, which: str, p: Place):
        self.cfg[which] = {"name": p.name, "lat": p.lat, "lon": p.lon}

    def _days_changed(self):
        self.cfg["workdays"] = [i for i, cb in enumerate(self.day_boxes) if cb.isChecked()]

    def _provider_changed(self):
        prov = self.provider.currentData()
        self.cfg["commute_provider"] = prov
        needs_key = prov in ("tomtom", "google")
        self.commute_form.setRowVisible(self.key, needs_key)
        self.key.setText(self.cfg[f"{prov}_key"] if needs_key else "")
        self.key_help.setText(KEY_HELP[prov])

    def _key_changed(self):
        prov = self.provider.currentData()
        if prov in ("tomtom", "google"):
            self.cfg[f"{prov}_key"] = self.key.text().strip()
