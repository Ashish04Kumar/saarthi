from datetime import datetime

from saarthi.commute import Route, commute_due, message, parse_google, parse_osrm, parse_tomtom
from saarthi.weather import Weather, accessory, parse_forecast, summary

FORECAST = {
    "current": {"temperature_2m": 23.2, "apparent_temperature": 23.5, "weather_code": 0, "is_day": 1},
    "daily": {"temperature_2m_max": [27.0], "temperature_2m_min": [12.0]},
    "hourly": {
        "time": ["2026-11-19T12:00", "2026-11-19T13:00", "2026-11-19T14:00", "2026-11-19T15:00"],
        "precipitation_probability": [0, 5, 70, 80],
        "precipitation": [0, 0, 1.2, 2.0],
        "weather_code": [0, 1, 61, 63],
    },
}


def test_parse_forecast_and_rain_soon():
    w = parse_forecast(FORECAST)
    assert w.temp == 23.2 and not w.raining
    assert w.rain_soon(datetime(2026, 11, 19, 12, 30), hours=2) == datetime(2026, 11, 19, 14)
    assert w.rain_soon(datetime(2026, 11, 19, 12, 30), hours=1) is None
    s = summary(w, "Delhi", "hinglish", datetime(2026, 11, 19, 12, 30))
    assert "23°C" in s and "14:00" in s


def test_accessory():
    now = datetime(2026, 11, 19, 12)
    base = dict(t_max=30, t_min=20, hourly=[])
    assert accessory(Weather(temp=20, feels=20, code=63, is_day=True, **base), now) == "umbrella"
    assert accessory(Weather(temp=8, feels=6, code=0, is_day=True, **base), now) == "scarf"
    assert accessory(Weather(temp=40, feels=43, code=0, is_day=True, **base), now) == "shades"
    assert accessory(Weather(temp=25, feels=25, code=1, is_day=True, **base), now) is None


def test_route_parsers_and_levels():
    tt = parse_tomtom(
        {
            "routes": [
                {
                    "summary": {
                        "travelTimeInSeconds": 3000,
                        "noTrafficTravelTimeInSeconds": 1800,
                        "lengthInMeters": 22000,
                        "trafficDelayInSeconds": 1200,
                    }
                }
            ]
        }
    )
    assert tt.live and round(tt.minutes) == 50 and tt.level == "heavy" and round(tt.delay) == 20
    g = parse_google({"routes": [{"duration": "1500s", "staticDuration": "1400s", "distanceMeters": 12000}]})
    assert g.level == "light"
    o = parse_osrm({"routes": [{"duration": 1500, "distance": 23000}]}, datetime(2026, 11, 19, 18))  # Thu rush
    assert not o.live and o.level == "unknown" and round(o.minutes) == 40


def test_commute_due_window():
    wd = [0, 1, 2, 3, 4]
    assert not commute_due(datetime(2026, 11, 19, 18, 0), "18:30", 15, wd, None)
    assert commute_due(datetime(2026, 11, 19, 18, 15), "18:30", 15, wd, None)
    assert not commute_due(datetime(2026, 11, 19, 18, 15), "18:30", 15, wd, "2026-11-19")
    assert not commute_due(datetime(2026, 11, 22, 18, 15), "18:30", 15, wd, None)  # Sunday
    assert not commute_due(datetime(2026, 11, 19, 19, 20), "18:30", 15, wd, None)  # too late


def test_message():
    t, d = message(Route(50, 30, 22, True, "tomtom"), "hinglish")
    assert "50" in t and "20 min extra" in d
    t, d = message(Route(40, 25, 23, False, "free"), "en")
    assert "Estimate" in d


def test_parse_google_maps_urls():
    from saarthi.commute import is_link, parse_maps_url

    full = (
        "https://www.google.com/maps/place/Some+Office,+Ring+Rd,+City/@12.9716,77.5946,17z/"
        "data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d12.971599!4d77.594566!16s"
    )
    p = parse_maps_url(full)
    assert p.name == "Some Office" and (p.lat, p.lon) == (12.971599, 77.594566)  # exact pin wins
    p = parse_maps_url("https://www.google.com/maps/@19.07,72.87,15z")
    assert (p.lat, p.lon) == (19.07, 72.87)
    assert parse_maps_url("https://maps.app.goo.gl/abc") is None  # short link: needs resolving
    assert is_link(" https://maps.app.goo.gl/abc ") and not is_link("MG Road, Pune")
