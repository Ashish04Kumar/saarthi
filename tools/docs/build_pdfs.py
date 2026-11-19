"""Build docs/Saarthi-Technical.pdf and docs/Saarthi-Features-Guide.pdf.

    pip install reportlab
    python tools/docs/build_pdfs.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from reportlab.platypus import KeepTogether  # noqa: E402

from pdfkit import DOCS, P, PageBreak, Spacer, build, bullets, code, image, table  # noqa: E402


# ---------------------------------------------------------------- technical
def technical() -> list:
    s: list = []
    s += [P("Saarthi", "title"),
          P("Technical documentation: architecture, how each part works, data, packaging and tests", "subtitle"),
          image("states.png", 150, "The built-in mascot “Bit” in all 18 states (sprite skins can replace it).")]

    s += [P("1. Overview", "h1"),
          P("Saarthi is a cross-platform desktop companion. A transparent, always-on-top character lives on the "
            "screen and reacts to what the user is doing (typing speed, scrolling, videos, idle time), keeps "
            "reminders, notes and a calendar, runs wellness sessions (breaks, lunch, guided breathing), shows "
            "weather and the commute home, and can walk around the screen. Everything runs locally; the only network "
            "calls are the optional weather, location, routing and calendar lookups listed in section 10."),
          P("2. Technology", "h1"),
          table([["Part", "Choice", "Why"],
                 ["Language", "Python 3.10+", "One codebase for Linux, Windows and macOS"],
                 ["UI", "PySide6 (Qt 6, LGPL)", "Frameless translucent windows, tray, timers, local sockets"],
                 ["Linux input", "evdev (+ pynput fallback)", "Reads /dev/input on Wayland and X11"],
                 ["Windows / macOS input", "pynput", "Global keyboard and mouse listeners"],
                 ["Linux D-Bus", "jeepney", "GNOME idle monitor and MPRIS media players"],
                 ["Windows media", "winrt Media.Control", "What the system media overlay is playing"],
                 ["Calendar", "icalendar, recurring-ical-events", "Read-only iCal feeds with recurrence"],
                 ["3D avatar tool", "numpy (dev only)", "Signed-distance-field raymarcher that renders sprite frames"],
                 ["Docs", "reportlab", "These PDFs"]], [34, 52, 88])]

    s += [P("3. Architecture", "h1"),
          P("The app is a single Qt process. <b>Saarthi</b> (app.py) owns the window, speech bubble, tray "
            "menu and the state machine, and wires together four helpers: <b>Organizer</b> (reminders, notes, "
            "calendar, quotes, cards), <b>Outdoor</b> (weather, commute), <b>Wellness</b> (break, lunch, "
            "breathing, status) and <b>Walker</b> (moving the window). Activity sources run their own threads and "
            "are polled; network calls run on worker threads and report back through Qt signals."),
          table([["Module", "Responsibility"],
                 ["__main__.py", "CLI (--demo, --snapshot, --quit), single-instance check, X11 on Wayland"],
                 ["app.py", "Main controller: tick loop, speech queue, clicks, menus, quiet mode, Try features"],
                 ["states.py", "States, thresholds, StateMachine (hysteresis, transient states, fallbacks)"],
                 ["window.py", "Transparent window, 30 fps painting, squash/breath scaling, mirroring, drag"],
                 ["bubble.py / card.py", "Speech bubble; pop-up cards with action buttons"],
                 ["quick_panel.py", "Double-click panel: status, quick actions, reminders, notes, today"],
                 ["manager.py / settings_tab.py", "Full window: Reminders, Notes, Calendar, Quotes, Settings"],
                 ["activity/", "Counters, input backends, idle probes, media/window-title probes, demo source"],
                 ["organizer.py, scheduler.py, store.py", "Data model, due-time maths, cards, morning brief"],
                 ["ical_sync.py", "Fetch + expand iCal feeds"],
                 ["wellness.py, wellness_logic.py", "Break / lunch / breathing sessions, typing streaks"],
                 ["walker.py", "Random strolls, break and lunch pacing, return home"],
                 ["outdoor.py, weather.py, commute.py, net.py", "Weather, outfits, rain warning, routing"],
                 ["skin.py, mascot.py", "Skin loading (folders/GIF/sprite sheets); procedural mascot"],
                 ["theme.py, onboarding.py, system.py", "Dark/light theme; first-run help; autostart, single instance"],
                 ["tools/avatar/", "3D avatar renderer (engine, model, poses, build_skin)"]], [56, 118])]

    s += [P("4. Runtime loop and timers", "h1"),
          table([["Timer", "Every", "Does"],
                 ["Window repaint", "33 ms (30 fps)", "Draws the current state; squash, breathing scale, mirror"],
                 ["App tick", "250 ms", "Reads activity → StateMachine.update → state-change lines"],
                 ["Wellness tick", "500 ms", "Session countdowns, typing streaks, break/breathing offers"],
                 ["Organizer check", "5 s", "Due reminders, event alerts, quotes, morning brief"],
                 ["Stroll check", "15 s", "18% chance to stroll when idle and nothing is open"],
                 ["Commute check", "60 s", "Logout alert window"],
                 ["Activity poller thread", "1 s / 2 s", "Idle time; window title + media every 2 s"],
                 ["Calendar sync", "15 min", "Re-download iCal feeds on a worker thread"],
                 ["Weather", "30 min", "Open-Meteo forecast, outfit, rain warning"],
                 ["Chit-chat", "20–40 min", "A random line (low priority)"]], [40, 30, 104])]

    s += [P("5. Activity detection", "h1"),
          table([["Signal", "Linux Wayland", "Linux X11", "Windows", "macOS"],
                 ["Typing / scroll", "evdev (input group)", "evdev or pynput", "pynput", "pynput (Accessibility)"],
                 ["Idle time", "GNOME Mutter D-Bus", "Mutter / XScreenSaver", "GetLastInputInfo", "CoreGraphics"],
                 ["Media playing", "MPRIS", "MPRIS + xprop title", "Media session + title",
                  "Spotify/Music + browser tab"]], [26, 37, 37, 37, 37]),
          P("Privacy: input listeners only record a timestamp per key press (kept 3 s to compute keys per second). "
            "Key codes are never read or stored. Touchpad two-finger movement is converted to scroll ticks. Video "
            "context is classified from player names and titles: course sites (Udemy, Coursera …) or words like "
            "“tutorial”, “course”, “for beginners” mark a tutorial; music players and YouTube Music count as music."),
          P("State machine", "h2"),
          table([["Rule", "Value"],
                 ["Typing fast / slow", "≥ 4 keys/s / ≥ 0.3 keys/s"],
                 ["Scrolling", "≥ 0.8 scroll ticks/s"],
                 ["Away (AFK) / asleep", "180 s / 900 s without input (3600 s while a video plays)"],
                 ["Hysteresis", "A new state must hold 1.2 s (away/asleep switch immediately)"],
                 ["Transient states", "waking 2.5 s, happy 2.5 s, alert 8 s, poked 1.6 s, giggle 2 s"],
                 ["Sessions", "break, lunch (eat → think), breathe: held until the session ends"],
                 ["Fallbacks", "Missing skin states fall back, e.g. typing_fast → typing_slow → idle, eat → break"]],
                [48, 126])]

    s += [P("6. Who goes first (arbitration)", "h1"),
          bullets([
              "<b>Speech queue.</b> Every line has a priority: LOW (chit-chat, state lines, music), NORMAL "
              "(quotes, brief, rain), HIGH (reminders, replies to the user, sessions). A line never replaces a more "
              "important one that is still showing: NORMAL/HIGH lines wait in a queue (max 4), LOW lines are dropped.",
              "<b>Sessions</b> (break, lunch, breathing) suppress non-forced speech, quotes, chatter and strolls. "
              "Reminder cards still appear; the session keeps running.",
              "<b>User first.</b> Mouse-down cancels any walk; single click is delayed by the double-click "
              "interval so a double-click never triggers a poke.",
              "<b>Quiet mode</b> (screen share) shrinks the buddy to 90 px in the corner, hides bubbles, cards, "
              "panel and tray messages, and blocks offers and strolls. Cards created meanwhile are kept hidden and "
              "shown when quiet mode ends.",
              "<b>Walking guards</b>: no strolls while typing, during sessions, while a panel/card is open, or in "
              "quiet mode; breathing cancels a walk."])]

    s += [P("7. Reminders, calendar, quotes", "h1"),
          bullets([
              "Repeat types: once, daily, weekdays, weekly, monthly (clamped to month length), every N minutes "
              "inside an active window (default 09:00–21:00).",
              "Each reminder stores <i>next_at</i> and <i>snooze_until</i>. When it fires a history entry is logged "
              "(outcome pending). Done → outcome done and next occurrence; Skipped → outcome missed; 10m/1h → snooze.",
              "Weekly stats count done / missed / pending over the last 7 days.",
              "Events alert <i>remind_before</i> minutes early (default 10); all-day events at 09:00. "
              "Fired alerts are remembered for 3 days so they never repeat.",
              "Quote lists pick a random line every <i>min…max</i> minutes (the no-smoking list: 40 min), "
              "skipped while typing fast, away, asleep or in a session.",
              "Morning brief: first time you're active after 05:00 each day; waits up to 25 s for weather."])]

    s += [P("8. Wellness", "h1"),
          table([["Session", "How it works"],
                 ["Break offer", "After 50 min of active time (input within the last minute). 5 min away resets it."],
                 ["Break", "Default 5 min (picker). Paces around with chai; pauses 6–12 s. Typing ~45 s "
                           "continuously cancels it and asks again in 15 min (work time is kept)."],
                 ["Lunch", "Default 60 min (picker). Eats for 10–15 min (≤ 60% of the time), then strolls slowly "
                           "(0.55× speed) with 15–30 s thinking stops. 45 s of typing asks “lunch over?”."],
                 ["Breathing", "Offered every 20 min (configurable range), skipped while typing fast, watching, "
                               "away or asleep. 5 breaths of 12 s: in 4 s, hold 2 s, out 6 s. 10 s typing stops it."],
                 ["Status", "Working / Break / Lunch from the panel or menu; picking the active one again ends it. "
                            "“Time badlo” changes the minutes left of a running break or lunch."]], [30, 144])]

    s += [P("9. Walking", "h1"),
          P("The Walker moves the window along the bottom of the current screen at 0.38 × window height per "
            "second (0.55× for lunch strolls) and shows the WALK animation, mirrored when walking left. Break and "
            "lunch pacing remembers the home position and walks back when the session ends.")]

    s += [P("10. Network services", "h1"),
          table([["Service", "Used for", "Key"],
                 ["Open-Meteo", "Weather forecast and city search", "none"],
                 ["ipapi.co / ipinfo.io", "Approximate city from IP (only in automatic mode)", "none"],
                 ["OSRM (OpenStreetMap)", "Free route time + rush-hour factor (1.6 / 1.2)", "none"],
                 ["Nominatim", "Address search, only when Search is pressed", "none"],
                 ["Google Maps links", "Pasted links are expanded to read the pinned coordinates", "none"],
                 ["TomTom Routing", "Live traffic", "free key"],
                 ["Google Routes API", "Live traffic", "billing key"],
                 ["iCal links", "Google / Outlook / Apple calendar (read-only)", "secret link"]], [40, 104, 30])]

    s += [P("11. Data and configuration", "h1"),
          table([["OS", "Config + data folder", "Installed app"],
                 ["Linux", "~/.config/saarthi/", "~/.local/share/saarthi/venv"],
                 ["Windows", "%APPDATA%\\Saarthi\\", "%LOCALAPPDATA%\\Saarthi\\venv"],
                 ["macOS", "~/Library/Application Support/Saarthi/", "…/Saarthi/app/venv"]], [24, 80, 70]),
          P("config.json holds settings (skin, size, language, theme, weather, commute, wellness, walking). "
            "data.json holds reminders, notes, events, feeds, quote lists, reminder history and cached feed events. "
            "Both are written atomically (temp file + rename). Custom skins live in the <i>skins/</i> sub-folder.")]

    s += [P("12. Skins and the 3D avatar", "h1"),
          P("A skin is a folder with <i>skin.json</i> and frames per state (PNG sequence, GIF or sprite sheet). "
            "The avatar tool renders a full-body character with a numpy signed-distance-field raymarcher: "
            "spheres, capsules, ellipsoids and boxes combined with smooth unions, toon shading, ambient occlusion, "
            "rim light and outlines, at 2× supersampling. Appearance is a <i>Look</i> (skin, hair, beard, shirt, "
            "slim, sleeves, watch …) and each state is a <i>Pose</i> function of time."),
          code("python tools/avatar/build_skin.py ~/.config/saarthi/skins/me --name \"Me\""),
          P("13. Packaging, startup and control", "h1"),
          bullets([
              "install.sh (Linux/macOS) and install.ps1 / install.bat (Windows) create a private virtualenv, "
              "add an app-menu entry / ~/Applications app / Start-menu shortcut, and start the app. "
              "<i>--autostart</i> and <i>--uninstall</i> are supported; no admin rights needed.",
              "Start with the computer: ~/.config/autostart (Linux), HKCU Run key (Windows), LaunchAgent (macOS).",
              "Single instance through a QLocalServer: launching again shows the running buddy; "
              "<i>saarthi --quit</i> asks it to close."]),
          P("14. Tests", "h1"),
          P("53 automated tests (pytest): state machine, rate counters, media classification, evdev event "
            "handling, scheduler maths, iCal parsing, weather/route parsing, Maps links, autostart, typing streaks, "
            "and 13 end-to-end scenarios on a real offscreen buddy (speech priorities, sessions vs reminders, typing "
            "cancels a break, lunch flow, minutes picker, quiet mode, panel ↔ full-window sync, delete, walking guards)."),
          code("pip install -e \".[dev]\"\npytest\nruff check src tests"),
          P("15. Known limitations", "h1"),
          bullets([
              "Windows and macOS code paths are written but not yet tested on real machines.",
              "Linux Wayland needs the input group for typing detection; the window runs via XWayland.",
              "Free commute times are estimates; live traffic needs a TomTom or Google key.",
              "Calendar sync is read-only."])]
    return s


# ---------------------------------------------------------------- features guide
def features() -> list:
    s: list = []
    s += [P("Saarthi", "title"),
          P("Features and user guide: what it does, when it runs, how to use and track everything", "subtitle"),
          image("panel.png", 80, "The double-click panel (dark theme).")]

    s += [P("1. Install, start and stop", "h1"),
          table([["", "Linux / macOS", "Windows"],
                 ["Install", "./install.sh   (add --autostart)", "double-click install.bat"],
                 ["Start", "App menu → Saarthi, or <b>saarthi</b>", "Start menu / Desktop → Saarthi"],
                 ["Stop", "<b>saarthi --quit</b>, or right-click → Quit", "right-click → Quit"],
                 ["Update", "git pull, then ./install.sh", "git pull, then install.bat"],
                 ["Uninstall", "./install.sh --uninstall", "install.ps1 -Uninstall"]], [22, 82, 70]),
          P("Linux Wayland: to let it see your typing, run <b>sudo usermod -aG input $USER</b> once and log out "
            "and back in. Saarthi already uses it on its next start, even before you log out.", "note")]

    s += [P("2. Talking to your buddy", "h1"),
          table([["Do this", "What happens"],
                 ["Single click on the head", "“Oye!”: rubs its head"],
                 ["Single click on the body", "Giggles (tickled)"],
                 ["Click 4 times in 3 s", "Gets dizzy"],
                 ["Double-click", "Opens the panel: status, quick actions, reminders, notes, today"],
                 ["Right-click", "The menu (status, quiet mode, Try features, settings …)"],
                 ["Drag", "Move it anywhere (also stops a walk)"]], [52, 122])]

    s += [P("3. When it does what", "h1"),
          table([["When", "What it does"],
                 ["App starts", "Welcome tips (first run); a card if typing detection needs permission"],
                 ["First time you're active each day", "Morning brief: today's events/reminders + weather"],
                 ["Typing fast", "Types furiously, sweats"],
                 ["Typing slowly / thinking", "Hand on chin, thought bubble"],
                 ["Scrolling", "Eyes go up and down"],
                 ["Video or tutorial playing", "Popcorn; lines for Udemy, tutorials, YouTube"],
                 ["Music playing", "Sometimes comments on the music"],
                 ["3 min no input / 15 min", "Dozes off / falls asleep (Zzz)"],
                 ["You come back", "Jumps up: “Aa gaye!”"],
                 ["Reminder time", "Holds up a “!” sign + card: Done / Skipped / 10 min / 1 h"],
                 ["10 min before an event", "Event card (synced calendars every 15 min)"],
                 ["50 min of work", "Suggests a break"],
                 ["Every 20 min", "Offers guided breathing"],
                 ["Every 40 min", "A no-smoking motivation line (your own quote lists)"],
                 ["Every 20–40 min", "A random fun line (skipped if something important is showing)"],
                 ["Idle, walking mode on", "Strolls along the bottom of the screen"],
                 ["15 min before logout (work days)", "Time to get home + traffic"],
                 ["Every 30 min", "Weather update; warns before rain"]], [62, 112])]

    s += [KeepTogether([P("4. Status: Working, Break, Lunch", "h1"),
                        image("minutes-picker.png", 70,
                              "Picking Break or Lunch asks for minutes (Lunch 60, Break 5 by default).")]),
          bullets([
              "Pick a status in the panel (top row) or right-click → Status. Clicking the active one again ends it.",
              "<b>Break</b>: walks around with chai, countdown in the bubble. Keep typing ~45 s and it assumes "
              "something important came up: break cancelled, offered again in 15 min.",
              "<b>Lunch</b>: eats for 10–15 min, then strolls slowly and stops to think. Typing 45 s asks "
              "“Lunch over?”. Lunch resets your work timer.",
              "<b>Time badlo</b> in the panel changes the minutes left. Tick “Isko default bana do” to save "
              "your usual length.",
              "<b>Quiet mode</b> (panel button or menu) for screen sharing: tiny, in the corner, no pop-ups. "
              "Reminders that come due meanwhile appear when you turn it off."])]

    s += [P("5. Reminders, notes and calendar", "h1"),
          bullets([
              "Panel → Reminders: type, pick a time and Aaj / Kal / Roz / Weekdays / Har ghante, press + Add.",
              "Panel → Notes: quick notes that work as a to-do list (tick = done). The bin button deletes; double-click "
              "opens the full note.",
              "Panel → Aaj: today's events and reminders; add an event for today.",
              "Full window (right-click → Open Saarthi): all reminders with repeat options, notes with search "
              "and pin, the calendar with iCal sync, quote lists, settings."]),
          P("Tracking: did I actually do it?", "h2"),
          P("Every reminder that fires is logged. Mark it ✓ (did it) or ✗ (skipped) on the card or later in "
            "“Kiya ya nahi?”. The panel shows <i>Is hafte: N ✓ kiya · N ✗ nahi kiya</i>; the full window shows the "
            "last 7 days and up to 40 recent entries.")]

    s += [P("6. Wellness", "h1"),
          table([["Feature", "Default", "Change it in"],
                 ["Break reminder", "after 50 min work, 5 min break", "Settings → Breaks and breathing"],
                 ["Breathing", "every 20 min, 5 breaths (4 in · 2 hold · 6 out)", "Settings"],
                 ["Lunch length", "60 min", "Settings, or the minutes picker"],
                 ["Walking mode", "on", "Menu or Settings"]], [36, 76, 62])]

    s += [P("7. Quotes (no-smoking)", "h1"),
          P("The “No smoking motivation” list speaks one line every 40 minutes: health facts on lungs, heart, "
            "hair (premature greying, hair fall), skin (dullness, wrinkles, glow coming back after quitting) and the "
            "brain (cravings, stroke risk, focus). Edit or add your own lists in Quotes; each list has its own gap.")]

    s += [P("8. Weather and the way home", "h1"),
          bullets([
              "Weather follows your city (automatic from your connection, or one you choose). Bit dresses for it: "
              "umbrella, beanie and scarf, or shades.",
              "Settings → Office to home traffic: home, office (address or a Google Maps link), logout time, work "
              "days, car or two-wheeler, and data source (free estimate, TomTom or Google with a key)."])]

    s += [P("9. Checking that everything works", "h1"),
          P("<b>Right-click → What I see…</b> shows live:"),
          table([["Field", "Meaning"],
                 ["Typing & scroll / Idle time / Video", "Which detector is active on your system"],
                 ["Keys/sec, Scrolls/sec, Idle, Media", "Live readings"],
                 ["Mood", "The current state"],
                 ["Session", "Break / lunch / breathing and time left"],
                 ["Next break / Next breathing", "Minutes until the next offer"],
                 ["Walking, Next reminder/event", "Walking status; the next thing on your schedule"]], [62, 112]),
          P("<b>Right-click → Try features</b> triggers any feature on demand: each activity for 10 s, poke, "
            "tickle, dizzy, walk, a demo reminder, an event alert, the morning brief, a quote, a break offer, a "
            "1-minute break, breathing, weather, rain warning, traffic and outfits.")]

    s += [P("10. Troubleshooting", "h1"),
          table([["Problem", "Fix"],
                 ["Typing has no effect (Linux Wayland)", "Join the input group and log out/in (see section 1). "
                                                          "Menu → Fix typing detection… explains it."],
                 ["Window doesn't appear (Linux)", "sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1"],
                 ["macOS ignores typing", "System Settings → Privacy & Security → Accessibility and Input "
                                          "Monitoring → allow Saarthi / Python, then restart it"],
                 ["Two buddies?", "Not possible: launching again just shows the running one"],
                 ["Want silence", "Quiet mode, or turn off Speech bubbles in the menu"]], [56, 118]),
          P("11. Privacy", "h1"),
          P("Saarthi counts how fast you type, never what you type. Your notes, reminders and settings stay in "
            "your config folder. Network use: weather, approximate location (automatic mode only), routes, address "
            "search when you press Search, and calendar links you add.")]
    return s


if __name__ == "__main__":
    build(DOCS / "Saarthi-Technical.pdf", "Technical documentation", technical())
    build(DOCS / "Saarthi-Features-Guide.pdf", "Features and user guide", features())
    print("wrote", DOCS / "Saarthi-Technical.pdf")
    print("wrote", DOCS / "Saarthi-Features-Guide.pdf")
