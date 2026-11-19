"""Office -> home travel time. Free estimate (OSRM) or live traffic (TomTom / Google)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .net import get_json
from .weather import Place

PROVIDERS = {
    "free": "Free estimate (no live traffic)",
    "tomtom": "TomTom (live traffic, free API key)",
    "google": "Google Maps (live traffic, API key)",
}
MODES = {"car": "Car", "bike": "Two-wheeler"}


@dataclass
class Route:
    minutes: float
    normal_minutes: float | None  # without traffic, when the provider knows
    km: float
    live: bool
    provider: str

    @property
    def delay(self) -> float:
        return max(0.0, self.minutes - self.normal_minutes) if self.normal_minutes else 0.0

    @property
    def level(self) -> str:
        """light / moderate / heavy (or unknown without live data)."""
        if not self.live or not self.normal_minutes:
            return "unknown"
        ratio = self.minutes / max(1.0, self.normal_minutes)
        if ratio < 1.15:
            return "light"
        if ratio < 1.4:
            return "moderate"
        return "heavy"


LEVEL_EMOJI = {"light": "🟢", "moderate": "🟡", "heavy": "🔴", "unknown": "⚪"}


def rush_factor(now: datetime) -> float:
    """Rough multiplier for the free estimate, which knows nothing about traffic."""
    if now.weekday() < 5 and (8 <= now.hour < 11 or 17 <= now.hour < 21):
        return 1.6
    return 1.2


# ---------------- parsers (pure, tested) ----------------


def parse_osrm(d: dict, now: datetime) -> Route:
    r = d["routes"][0]
    base = r["duration"] / 60
    return Route(base * rush_factor(now), base, r["distance"] / 1000, False, "free")


def parse_tomtom(d: dict) -> Route:
    s = d["routes"][0]["summary"]
    total = s["travelTimeInSeconds"] / 60
    normal = s.get("noTrafficTravelTimeInSeconds")
    if normal is None:
        normal = (s["travelTimeInSeconds"] - s.get("trafficDelayInSeconds", 0)) / 60
    else:
        normal /= 60
    return Route(total, normal, s["lengthInMeters"] / 1000, True, "tomtom")


def parse_google(d: dict) -> Route:
    r = d["routes"][0]
    total = float(r["duration"].rstrip("s")) / 60
    normal = float(r.get("staticDuration", r["duration"]).rstrip("s")) / 60
    return Route(total, normal, r.get("distanceMeters", 0) / 1000, True, "google")


# ---------------- network ----------------


def parse_maps_url(url: str) -> Place | None:
    """Read the place out of a full Google Maps URL (exact pin first, then the map centre)."""
    import re
    from urllib.parse import unquote_plus

    name = "Pinned place"
    m = re.search(r"/maps/place/([^/@?]+)", url)
    if m:
        name = unquote_plus(m.group(1)).split(",")[0].strip()[:80] or name
    for pat in (
        r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
        r"@(-?\d+\.\d+),(-?\d+\.\d+)",
        r"[?&](?:q|query|ll)=(-?\d+\.\d+),\s*(-?\d+\.\d+)",
    ):
        m = re.search(pat, url)
        if m:
            return Place(name, float(m.group(1)), float(m.group(2)))
    return None


def resolve_maps_link(link: str) -> Place:
    """Accept a Google Maps link (short maps.app.goo.gl or full) and return the place."""
    import urllib.request

    from .net import USER_AGENT

    link = link.strip()
    place = parse_maps_url(link)
    if place:
        return place
    req = urllib.request.Request(link, headers={"User-Agent": USER_AGENT}, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (only http(s) links reach here)
        final = resp.geturl()
    place = parse_maps_url(final)
    if not place:
        raise ValueError("Couldn't find a location in that link. Open the place in Google Maps and share it again.")
    return place


def is_link(text: str) -> bool:
    return text.strip().startswith(("http://", "https://"))


def search_address(q: str) -> list[Place]:
    """OpenStreetMap Nominatim. Called only when you press Search (their policy: max 1 req/s)."""
    d = get_json("https://nominatim.openstreetmap.org/search", {"q": q, "format": "jsonv2", "limit": 5})
    return [Place(r.get("display_name", q)[:120], float(r["lat"]), float(r["lon"])) for r in d]


def route(provider: str, key: str, origin: Place, dest: Place, mode: str, now: datetime | None = None) -> Route:
    now = now or datetime.now()
    if provider == "tomtom":
        if not key:
            raise ValueError("TomTom API key missing (Settings)")
        travel = "motorcycle" if mode == "bike" else "car"
        url = f"https://api.tomtom.com/routing/1/calculateRoute/{origin.lat},{origin.lon}:{dest.lat},{dest.lon}/json"
        d = get_json(
            url, {"key": key, "traffic": "true", "travelMode": travel, "departAt": "now", "computeTravelTimeFor": "all"}
        )
        return parse_tomtom(d)
    if provider == "google":
        if not key:
            raise ValueError("Google Maps API key missing (Settings)")
        body = {
            "origin": {"location": {"latLng": {"latitude": origin.lat, "longitude": origin.lon}}},
            "destination": {"location": {"latLng": {"latitude": dest.lat, "longitude": dest.lon}}},
            "travelMode": "TWO_WHEELER" if mode == "bike" else "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
        }
        d = get_json(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            body=body,
            headers={
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters",
            },
        )
        return parse_google(d)
    d = get_json(
        f"https://router.project-osrm.org/route/v1/driving/{origin.lon},{origin.lat};{dest.lon},{dest.lat}",
        {"overview": "false"},
    )
    return parse_osrm(d, now)


# ---------------- when to alert ----------------


def alert_time(logout: str, before_min: int, day: datetime) -> datetime:
    h, m = (int(x) for x in logout.split(":"))
    return datetime.combine(day.date(), time(h, m)) - timedelta(minutes=before_min)


def commute_due(now: datetime, logout: str, before_min: int, workdays: list[int], last_date: str | None) -> bool:
    if now.weekday() not in workdays or last_date == now.date().isoformat():
        return False
    at = alert_time(logout, before_min, now)
    return at <= now <= at + timedelta(minutes=before_min + 30)


def message(r: Route, language: str) -> tuple[str, str]:
    """(title, detail) for the commute card."""
    mins = round(r.minutes)
    e = LEVEL_EMOJI[r.level]
    if language == "hinglish":
        names = {"light": "kam", "moderate": "theek-thaak", "heavy": "bahut zyada", "unknown": "pata nahi"}
        title = f"Ghar tak ~{mins} min {e}"
        if r.live:
            detail = f"Traffic {names[r.level]}" + (f", {round(r.delay)} min extra" if r.delay >= 3 else "")
        else:
            detail = f"Andaza (live traffic nahi). Normal time {round(r.normal_minutes or mins)} min"
    else:
        title = f"~{mins} min to home {e}"
        if r.live:
            detail = f"Traffic {r.level}" + (f", +{round(r.delay)} min" if r.delay >= 3 else "")
        else:
            detail = f"Estimate (no live traffic). Normal time {round(r.normal_minutes or mins)} min"
    return title, f"{detail} · {r.km:.0f} km"
