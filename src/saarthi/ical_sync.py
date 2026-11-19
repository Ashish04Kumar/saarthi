"""Read-only calendar sync from iCal (.ics) links: Google, Outlook, Apple, etc."""

from __future__ import annotations

import urllib.request
from datetime import date, datetime, timedelta

from . import __version__
from .store import Event, Feed, dt_to_str

LOOKBACK_DAYS = 1
LOOKAHEAD_DAYS = 60


def _local_naive(v) -> tuple[datetime, bool]:
    if isinstance(v, datetime):
        if v.tzinfo is not None:
            v = v.astimezone().replace(tzinfo=None)
        return v, False
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day), True
    raise ValueError(f"unsupported date value {v!r}")


def parse_ics(text: str | bytes, feed_name: str, now: datetime) -> list[Event]:
    import icalendar
    import recurring_ical_events

    cal = icalendar.Calendar.from_ical(text)
    start, end = now - timedelta(days=LOOKBACK_DAYS), now + timedelta(days=LOOKAHEAD_DAYS)
    out = []
    for comp in recurring_ical_events.of(cal).between(start, end):
        if str(comp.get("STATUS", "")).upper() == "CANCELLED":
            continue
        s, all_day = _local_naive(comp.decoded("DTSTART"))
        e = None
        if comp.get("DTEND") is not None:
            e, _ = _local_naive(comp.decoded("DTEND"))
        elif comp.get("DURATION") is not None:
            e = s + comp.decoded("DURATION")
        uid = str(comp.get("UID", "")) or f"{s.isoformat()}-{comp.get('SUMMARY')}"
        out.append(
            Event(
                title=str(comp.get("SUMMARY", "(no title)")),
                start=dt_to_str(s),
                end=dt_to_str(e),
                all_day=all_day,
                notes=str(comp.get("LOCATION", "") or ""),
                source=feed_name,
                id=uid,
            )
        )
    return out


def fetch(feed: Feed, timeout: float = 20) -> bytes:
    url = feed.url.strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://") :]
    if not url.startswith(("https://", "http://")):
        raise ValueError("URL must start with https:// or webcal://")
    req = urllib.request.Request(url, headers={"User-Agent": f"Saarthi/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (scheme checked above)
        return resp.read(20 * 1024 * 1024)


def sync_all(feeds: list[Feed], now: datetime) -> tuple[list[Event], dict[str, str]]:
    """Fetch every enabled feed. Returns (events, {feed_id: error or ''})."""
    events: list[Event] = []
    status: dict[str, str] = {}
    for f in feeds:
        if not f.enabled:
            continue
        try:
            events += parse_ics(fetch(f), f.name, now)
            status[f.id] = ""
        except Exception as e:  # report per-feed, keep going
            status[f.id] = f"{type(e).__name__}: {e}"[:200]
    return events, status
