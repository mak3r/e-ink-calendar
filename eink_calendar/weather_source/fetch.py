"""Weather (Open-Meteo) and solar/lunar (astral) data for the widget column.

Two different data sources for two different kinds of data — see
``.claude/plans/day-view-widget-column.md`` §3:

- :func:`fetch_weather` — one HTTPS GET to Open-Meteo
  (https://open-meteo.com/en/pricing: no API key, no account, free tier).
  stdlib ``urllib.request`` only — no new HTTP client dependency.
- :func:`compute_solar_lunar` — sunrise/sunset/moon phase via ``astral``,
  computed locally from ``(date, lat, lon)``. No network call, cannot go
  stale, never cached (see ``weather_source/cache.py``).
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime
from urllib.parse import urlencode

from astral import LocationInfo, moon
from astral.sun import sun

from eink_calendar.weather_source.models import ForecastPoint, WeatherReading

__all__ = ["compute_solar_lunar", "fetch_weather"]

# Open-Meteo's forecast endpoint — HTTPS, no auth. See the pricing page cited
# above for the free-tier terms (600 calls/min, non-commercial use).
_API_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT_S = 10

# WMO weather-interpretation codes (what Open-Meteo's weather_code returns),
# mapped to the six-value "northeast US/Canada" vocabulary render/day_view.py's
# per-period hand-drawn icons switch on (#177/#178) — see
# https://open-meteo.com/en/docs for the full WMO code table. Storm and fog
# have no dedicated icon and fall back to the closest of the six (storm ->
# rain, fog -> cloudy) rather than getting their own bucket.
_SUNNY = frozenset({0})
_PARTLY_SUNNY = frozenset({1})
_PARTLY_CLOUDY = frozenset({2})
_CLOUDY = frozenset({3, 45, 48})  # overcast, plus fog's fallback
_SNOW = frozenset(range(71, 78)) | {85, 86}
# Everything else — drizzle/rain/rain-showers (51-67, 80-82), thunderstorms
# (95-99, storm's fallback), and any WMO code Open-Meteo adds later that
# isn't in the sets above — falls through to "rain" as the closest safe
# default rather than raising.

# Same-day forecast strip: local hour -> the point's label (#167's mockup).
_FORECAST_HOURS = (("This Afternoon", 15), ("Tonight", 21))

# astral's moon.phase() returns days-since-new-moon on a 0-27.99 scale (a
# ~29.53-day lunar month); thresholds are the conventional 8-phase breakpoints.
_MOON_PHASE_THRESHOLDS = (
    (1, "New Moon"),
    (7, "Waxing Crescent"),
    (8, "First Quarter"),
    (14, "Waxing Gibbous"),
    (15, "Full Moon"),
    (21, "Waning Gibbous"),
    (22, "Last Quarter"),
    (28, "Waning Crescent"),
)


def fetch_weather(lat: float, lon: float) -> WeatherReading:
    """One Open-Meteo forecast GET for ``(lat, lon)``.

    Raises on any network, HTTP, or parse failure — callers fall back to the
    cached reading (see ``app.py``'s ``refresh_and_render``), matching the
    "a failed fetch must never blank the panel" rule already used for
    calendar events.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,weather_code",
        "hourly": "temperature_2m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "forecast_days": 1,
        "timezone": "auto",
    }
    url = f"{_API_URL}?{urlencode(params)}"
    if not url.startswith("https://api.open-meteo.com/"):  # defense in depth
        raise ValueError(f"unexpected weather API URL: {url}")
    # nosec B310 -- the scheme and host always come from the hardcoded
    # _API_URL constant (asserted just above); only numeric, already-range-
    # validated lat/lon query values (config.py's _build_weather) are
    # interpolated, via urlencode(), so no scheme/host injection is possible.
    with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as response:  # nosec B310
        raw = response.read()
    return _parse_response(json.loads(raw))


def _parse_response(data: dict) -> WeatherReading:
    current = data["current"]
    daily = data["daily"]
    hourly = data["hourly"]

    temp_f = float(current["temperature_2m"])
    condition = _condition_name(int(current["weather_code"]))
    high_f = float(daily["temperature_2m_max"][0])
    low_f = float(daily["temperature_2m_min"][0])

    forecast = [
        ForecastPoint(label="Now", temp_f=temp_f, condition=condition),
        *_same_day_forecast(hourly),
    ]

    return WeatherReading(
        temp_f=temp_f, condition=condition, high_f=high_f, low_f=low_f, forecast=forecast
    )


def _same_day_forecast(hourly: dict) -> list[ForecastPoint]:
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    codes = hourly.get("weather_code", [])

    points = []
    for label, target_hour in _FORECAST_HOURS:
        index = _hour_index(times, target_hour)
        if index is not None and index < len(temps) and index < len(codes):
            points.append(
                ForecastPoint(
                    label=label,
                    temp_f=float(temps[index]),
                    condition=_condition_name(int(codes[index])),
                )
            )
    return points


def _hour_index(times: list[str], target_hour: int) -> int | None:
    """Index of the first ``times`` entry (Open-Meteo's ``"YYYY-MM-DDTHH:MM"``
    hourly timestamps) at ``target_hour`` local time, or ``None`` if absent."""
    for index, timestamp in enumerate(times):
        try:
            hour = int(timestamp[11:13])
        except (IndexError, ValueError):
            continue
        if hour == target_hour:
            return index
    return None


def _condition_name(code: int) -> str:
    if code in _SUNNY:
        return "sunny"
    if code in _PARTLY_SUNNY:
        return "partly sunny"
    if code in _PARTLY_CLOUDY:
        return "partly cloudy"
    if code in _CLOUDY:
        return "cloudy"
    if code in _SNOW:
        return "snow"
    return "rain"


def compute_solar_lunar(
    when: date, lat: float, lon: float, tz_name: str
) -> tuple[datetime, datetime, str]:
    """Sunrise, sunset, and moon phase name for ``when`` at ``(lat, lon)``,
    with sunrise/sunset already converted to ``tz_name`` (e.g. the
    household's configured ``refresh.timezone``).

    Deterministic and local — no network call — so it's safe (and correct)
    to call fresh on every render rather than caching the result. Without
    ``tz_name``, astral's ``LocationInfo`` defaults to UTC and callers would
    get UTC-aware sunrise/sunset — the bug behind #177 (a real device
    showed an evening sunrise and a morning sunset).
    """
    location = LocationInfo(latitude=lat, longitude=lon, timezone=tz_name)
    solar = sun(location.observer, date=when, tzinfo=location.timezone)
    phase_name = _moon_phase_name(moon.phase(when))
    return solar["sunrise"], solar["sunset"], phase_name


def _moon_phase_name(phase: float) -> str:
    for threshold, name in _MOON_PHASE_THRESHOLDS:
        if phase < threshold:
            return name
    return "New Moon"  # phase wraps at 28
