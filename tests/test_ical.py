from datetime import datetime

from saarthi.ical_sync import parse_ics

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:standup@x
DTSTART:20261116T043000Z
DTEND:20261116T044500Z
RRULE:FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR
SUMMARY:Standup
END:VEVENT
BEGIN:VEVENT
UID:holiday@x
DTSTART;VALUE=DATE:20261120
DTEND;VALUE=DATE:20261121
SUMMARY:Holiday
END:VEVENT
BEGIN:VEVENT
UID:cancel@x
DTSTART:20261121T100000Z
DTEND:20261121T110000Z
STATUS:CANCELLED
SUMMARY:Cancelled thing
END:VEVENT
END:VCALENDAR
"""


def test_parse_recurring_allday_and_cancelled():
    evs = parse_ics(ICS, "Work", datetime(2026, 11, 19, 8, 0))
    titles = [e.title for e in evs]
    assert "Cancelled thing" not in titles
    hol = [e for e in evs if e.title == "Holiday"]
    assert hol and hol[0].all_day and hol[0].start == "2026-11-20T00:00"
    standups = [e for e in evs if e.title == "Standup"]
    assert len(standups) >= 30  # weekdays over ~60 days
    assert all(e.source == "Work" for e in evs)
