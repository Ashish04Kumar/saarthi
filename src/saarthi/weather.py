"""Weather from Open-Meteo (free, no API key) + location helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .net import get_json

# WMO weather codes -> (English, Hinglish, emoji)
CODES: dict[int, tuple[str, str, str]] = {
    0: ("clear sky", "aasmaan saaf", "☀️"),
    1: ("mostly clear", "zyadatar saaf", "🌤️"),
    2: ("partly cloudy", "thode baadal", "⛅"),
    3: ("overcast", "baadal chhaye", "☁️"),
    45: ("fog", "kohra", "🌫️"),
    48: ("freezing fog", "ghana kohra", "🌫️"),
    51: ("light drizzle", "halki boondabaandi", "🌦️"),
    53: ("drizzle", "boondabaandi", "🌦️"),
    55: ("heavy drizzle", "tez boondabaandi", "🌧️"),
    61: ("light rain", "halki baarish", "🌦️"),
    63: ("rain", "baarish", "🌧️"),
    65: ("heavy rain", "tez baarish", "🌧️"),
    66: ("freezing rain", "thandi baarish", "🌧️"),
    67: ("heavy freezing rain", "tez thandi baarish", "🌧️"),
    71: ("light snow", "halki barf", "🌨️"),
    73: ("snow", "barf", "🌨️"),
    75: ("heavy snow", "bhaari barf", "❄️"),
    77: ("snow grains", "barf ke daane", "🌨️"),
    80: ("light showers", "halki bauchhar", "🌦️"),
    81: ("showers", "bauchhar", "🌧️"),
    82: ("violent showers", "zordaar baarish", "⛈️"),
    85: ("snow showers", "barf ki bauchhar", "🌨️"),
    86: ("heavy snow showers", "bhaari barf", "❄️"),
    95: ("thunderstorm", "toofan aur bijli", "⛈️"),
    96: ("thunderstorm with hail", "toofan + ole", "⛈️"),
    99: ("thunderstorm with heavy hail", "toofan + bade ole", "⛈️"),
}
WET_CODES = {51, 53, 55, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}


def describe(code: int, language: str = "hinglish") -> tuple[str, str]:
    en, hi, emoji = CODES.get(code, ("unknown", "pata nahi", "🌡️"))
    return (hi if language == "hinglish" else en), emoji


@dataclass
class Place:
    name: str
    lat: float
    lon: float


@dataclass
class Weather:
    temp: float
    feels: float
    code: int
    is_day: bool
    t_max: float
    t_min: float
    hourly: list[tuple[datetime, int, float, int]] = field(default_factory=list)  # time, rain %, mm, code
    fetched: datetime = field(default_factory=datetime.now)

    @property
    def raining(self) -> bool:
        return self.code in WET_CODES

    def rain_soon(self, now: datetime, hours: int = 2, prob: int = 50) -> datetime | None:
        """Start time of likely rain within `hours`, or None."""
        lo = now.replace(minute=0, second=0, microsecond=0)
        hi = lo + timedelta(hours=hours, minutes=59)
        for t, p, mm, code in self.hourly:
            if lo <= t <= hi and (p >= prob or mm >= 0.5 or code in WET_CODES):
                return t
        return None


def accessory(w: Weather | None, now: datetime) -> str | None:
    """What Bit should wear."""
    if w is None:
        return None
    if w.raining or w.rain_soon(now, hours=1, prob=70):
        return "umbrella"
    if w.feels <= 14:
        return "scarf"
    if w.feels >= 34 and w.is_day:
        return "shades"
    return None


def summary(w: Weather, place: str, language: str, now: datetime) -> str:
    desc, emoji = describe(w.code, language)
    soon = w.rain_soon(now, hours=3)
    if language == "hinglish":
        s = f"{place}: {w.temp:.0f}°C, {desc} {emoji} (aaj {w.t_min:.0f}–{w.t_max:.0f}°)"
        if w.raining:
            s += "\nBaarish ho rahi hai, chhata le jaana ☂️"
        elif soon:
            s += f"\n{soon.strftime('%H:%M')} ke aas paas baarish ho sakti hai ☂️"
        elif w.feels >= 38:
            s += "\nBahut garmi hai, paani peete rehna 💧"
        elif w.feels <= 10:
            s += "\nThand hai, jacket pehen lena 🧥"
    else:
        s = f"{place}: {w.temp:.0f}°C, {desc} {emoji} (today {w.t_min:.0f}–{w.t_max:.0f}°)"
        if w.raining:
            s += "\nIt's raining, take an umbrella ☂️"
        elif soon:
            s += f"\nRain likely around {soon.strftime('%H:%M')} ☂️"
        elif w.feels >= 38:
            s += "\nVery hot, stay hydrated 💧"
        elif w.feels <= 10:
            s += "\nIt's cold, wear a jacket 🧥"
    return s


# ---------------- network ----------------


def parse_forecast(d: dict) -> Weather:
    cur, daily, hourly = d["current"], d["daily"], d.get("hourly", {})
    hours = [
        (datetime.fromisoformat(t), int(p or 0), float(mm or 0), int(c or 0))
        for t, p, mm, c in zip(
            hourly.get("time", []),
            hourly.get("precipitation_probability", []),
            hourly.get("precipitation", []),
            hourly.get("weather_code", []),
            strict=False,
        )
    ]
    return Weather(
        temp=float(cur["temperature_2m"]),
        feels=float(cur["apparent_temperature"]),
        code=int(cur["weather_code"]),
        is_day=bool(cur.get("is_day", 1)),
        t_max=float(daily["temperature_2m_max"][0]),
        t_min=float(daily["temperature_2m_min"][0]),
        hourly=hours,
    )


def fetch_weather(lat: float, lon: float) -> Weather:
    # timezone=auto returns local times for that place; for your own location that's your clock.
    d = get_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,weather_code,is_day",
            "hourly": "precipitation_probability,precipitation,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min",
            "forecast_hours": 12,
            "forecast_days": 1,
            "timezone": "auto",
        },
    )
    return parse_forecast(d)


def search_city(name: str) -> list[Place]:
    d = get_json("https://geocoding-api.open-meteo.com/v1/search", {"name": name, "count": 5})
    out = []
    for r in d.get("results", []) or []:
        label = ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x)
        out.append(Place(label, float(r["latitude"]), float(r["longitude"])))
    return out


def locate_by_ip() -> Place:
    """Approximate city from your public IP (sent to ipapi.co, falls back to ipinfo.io)."""
    try:
        d = get_json("https://ipapi.co/json/", timeout=8)
        return Place(d.get("city") or "Your area", float(d["latitude"]), float(d["longitude"]))
    except Exception:
        d = get_json("https://ipinfo.io/json", timeout=8)
        lat, lon = d["loc"].split(",")
        return Place(d.get("city") or "Your area", float(lat), float(lon))
