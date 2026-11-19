from saarthi.laptop import LaptopWatch, Snapshot


def names(events):
    return [n for n, _ in events]


def test_battery_warns_once_per_level_then_loudly():
    w = LaptopWatch()
    assert names(w.update(Snapshot(battery=40, plugged=False), 0)) == []
    assert names(w.update(Snapshot(battery=15, plugged=False), 10)) == ["battery_low"]
    assert w.low_battery()
    assert names(w.update(Snapshot(battery=14, plugged=False), 20)) == []  # no nagging
    assert names(w.update(Snapshot(battery=10, plugged=False), 30)) == ["battery_low"]
    assert names(w.update(Snapshot(battery=5, plugged=False), 40)) == ["battery_critical"]
    assert names(w.update(Snapshot(battery=5, plugged=False), 60)) == []
    assert names(w.update(Snapshot(battery=4, plugged=False), 170)) == ["battery_critical"]  # again after 2 min


def test_charger_in_out_and_full():
    w = LaptopWatch()
    w.update(Snapshot(battery=12, plugged=False), 0)
    ev = w.update(Snapshot(battery=12, plugged=True), 5)
    assert ev == [("charger_in", {"pct": 12})] and not w.low_battery()
    assert names(w.update(Snapshot(battery=100, plugged=True), 10)) == ["battery_full"]
    assert names(w.update(Snapshot(battery=100, plugged=True), 15)) == []
    assert names(w.update(Snapshot(battery=99, plugged=False), 20)) == ["charger_out"]
    # warnings start fresh after a charge
    assert names(w.update(Snapshot(battery=15, plugged=False), 30)) == ["battery_low"]


def test_no_battery_no_events():
    w = LaptopWatch()
    assert w.update(Snapshot(), 0) == [] and w.update(Snapshot(cpu=10), 5) == []


def test_hot_needs_sustained_load_or_high_temp():
    w = LaptopWatch()
    out = []
    for t in range(0, 60, 5):  # one minute of load isn't enough
        out += w.update(Snapshot(cpu=99), t)
    assert out == [] and not w.hot
    for t in range(60, 100, 5):
        out += w.update(Snapshot(cpu=99), t)
    assert names(out) == ["cpu_hot"] and w.hot
    for t in range(100, 300, 5):
        out += w.update(Snapshot(cpu=5), t)
    assert not w.hot and names(out) == ["cpu_hot"]
    w2 = LaptopWatch()
    assert names(w2.update(Snapshot(cpu=10, temp=92), 0)) == ["cpu_hot"]


def test_internet_changes_are_immediate_and_silent_at_start():
    w = LaptopWatch()
    assert w.net(True, 0) == [] and w.net(True, 1) == []
    assert w.net(False, 2) == [("net_down", {})]
    assert w.net(True, 3) == [("net_up", {"mins": 0})]  # quick toggles each get their line
    assert w.net(False, 4) == [("net_down", {})]
    assert w.net(True, 184) == [("net_up", {"mins": 3})]


def test_power_reacts_to_every_quick_toggle():
    w = LaptopWatch()
    assert w.power(50, False, 0) == []
    seq = [w.power(50, p, t) for t, p in enumerate((True, False, True, False), 1)]
    assert [names(e) for e in seq] == [["charger_in"], ["charger_out"], ["charger_in"], ["charger_out"]]


def test_probe_sees_wifi_drop_at_once_and_retries_after_reconnect(monkeypatch):
    from saarthi import laptop

    link = {"up": True}
    answers = []
    monkeypatch.setattr(laptop, "has_link", lambda _ps=None: link["up"])
    monkeypatch.setattr(laptop, "online", lambda timeout=2.0: answers.pop(0) if answers else True)
    started = []
    monkeypatch.setattr(
        laptop.threading,
        "Thread",
        lambda target, **kw: type("T", (), {"start": lambda self: (started.append(1), target())})(),
    )
    p = laptop.LaptopProbe()
    p.watch_net(None)
    assert p.net is True
    link["up"] = False
    p.watch_net(None)
    assert p.net is False  # Wi-Fi off: no waiting for a check
    link["up"] = True
    answers[:] = [False]  # DHCP not ready yet
    p.watch_net(None)
    assert p.net is False and p._net_at - laptop.time.monotonic() < 2.5  # tries again in 2 s
    p._net_at = 0
    p.watch_net(None)
    assert p.net is True


def test_uptime_late_night_audio():
    w = LaptopWatch(started=0)
    assert w.update(Snapshot(uptime_days=4.2), 60) == []  # not right after launch
    assert w.update(Snapshot(uptime_days=4.2), 700) == [("uptime", {"days": 4})]
    assert w.update(Snapshot(uptime_days=4.2), 800) == []
    w = LaptopWatch()
    assert names(w.update(Snapshot(), 0, hour=0, active=True)) == ["late_night"]
    assert w.update(Snapshot(), 60, hour=0, active=True) == []
    assert w.update(Snapshot(), 9999, hour=2, active=False) == []  # not if you're away
    w = LaptopWatch()
    w.update(Snapshot(headphones=False, muted=False, volume=60), 0)
    assert names(w.update(Snapshot(headphones=True, muted=False, volume=60), 5)) == ["headphones_on"]
    assert names(w.update(Snapshot(headphones=True, muted=True, volume=60), 10)) == ["muted"]
    assert names(w.update(Snapshot(headphones=True, muted=False, volume=120), 15)) == ["unmuted", "volume_max"]
    assert w.update(Snapshot(headphones=True, muted=False, volume=150), 20) == []  # already loud


def test_every_event_has_lines_in_both_languages():
    from saarthi.lines import line_for

    for key in (
        "battery_low",
        "battery_critical",
        "charger_in",
        "charger_out",
        "battery_full",
        "cpu_hot",
        "cpu_hot_temp",
        "net_down",
        "net_up",
        "uptime",
        "headphones_on",
        "headphones_off",
        "muted",
        "unmuted",
        "volume_max",
        "late_night",
        "big_screen",
    ):
        for lang in ("hinglish", "en"):
            text = line_for(key, lang)
            assert text and text.format(pct=5, mins=3, days=4, vol=130, temp=90)


def test_probe_reads_this_machine_without_crashing():
    import psutil

    from saarthi.laptop import LaptopProbe

    p = LaptopProbe()
    p._net_at = 1e18  # skip the internet check in tests
    s = p.read(psutil)
    assert s.cpu is not None and s.uptime_days is not None and s.uptime_days >= 0
