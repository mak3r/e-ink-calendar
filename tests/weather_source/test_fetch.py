"""Coverage for #166: the weather_source data layer (Open-Meteo + astral).

Companion to #169. Covers ``compute_solar_lunar`` against known real-world
values, ``fetch_weather``'s response parsing (condition-code mapping and
same-day forecast extraction), and that it raises rather than swallowing a
network/parse failure — the cache-fallback contract lives one layer up, in
``app.py``'s ``_refresh_weather`` (see ``tests/test_app_weather_refresh.py``).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Self
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from eink_calendar.weather_source.fetch import (
    _condition_name,
    compute_solar_lunar,
    fetch_weather,
)

# New York City, a fixed, reproducible (date, lat, lon, timezone) fixture.
_NYC_LAT, _NYC_LON = 40.7128, -74.0060
_NYC_TZ = "America/New_York"
_FIXED_DATE = date(2026, 9, 11)


def test_compute_solar_lunar_matches_known_values_for_a_fixed_date_and_location():
    sunrise, sunset, moon_phase = compute_solar_lunar(
        _FIXED_DATE, _NYC_LAT, _NYC_LON, _NYC_TZ
    )

    assert sunrise == datetime(2026, 9, 11, 6, 33, 6, 62604, tzinfo=ZoneInfo(_NYC_TZ))
    assert sunset == datetime(2026, 9, 11, 19, 11, 24, 293604, tzinfo=ZoneInfo(_NYC_TZ))
    assert moon_phase == "New Moon"


def test_compute_solar_lunar_returns_local_time_not_utc():
    """Regression guard for #177: without a timezone conversion, sunrise
    would land in the UTC morning and read as an evening time locally (a
    real device showed an evening sunrise and a morning sunset)."""
    sunrise, sunset, _ = compute_solar_lunar(_FIXED_DATE, _NYC_LAT, _NYC_LON, _NYC_TZ)

    assert sunrise.utcoffset() != timedelta(0)
    assert sunrise.hour < 12, "NYC sunrise should be a local morning hour"
    assert sunset.hour >= 12, "NYC sunset should be a local afternoon/evening hour"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "sunny"),
        (1, "partly sunny"),
        (2, "partly cloudy"),
        (3, "cloudy"),
        (45, "cloudy"),  # fog falls back to cloudy — no dedicated icon
        (48, "cloudy"),
        (61, "rain"),
        (80, "rain"),
        (71, "snow"),
        (85, "snow"),
        (95, "rain"),  # storm falls back to rain — no dedicated icon
        (99, "rain"),
        (200, "rain"),  # unknown code -> safe default, never raises
    ],
)
def test_condition_name_maps_wmo_codes_to_the_six_value_vocabulary(code, expected):
    assert _condition_name(code) == expected


def _open_meteo_response(*, weather_code: int = 0) -> bytes:
    return json.dumps(
        {
            "current": {"temperature_2m": 72.5, "weather_code": weather_code},
            "daily": {"temperature_2m_max": [78.0], "temperature_2m_min": [61.0]},
            "hourly": {
                "time": [f"2024-06-21T{h:02d}:00" for h in range(24)],
                "temperature_2m": [70.0 + h for h in range(24)],
                "weather_code": [weather_code] * 24,
            },
        }
    ).encode("utf-8")


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_fetch_weather_parses_current_and_same_day_forecast():
    with patch(
        "eink_calendar.weather_source.fetch.urllib.request.urlopen",
        return_value=_FakeResponse(_open_meteo_response(weather_code=0)),
    ):
        reading = fetch_weather(_NYC_LAT, _NYC_LON)

    assert reading.temp_f == 72.5
    assert reading.condition == "sunny"
    assert reading.high_f == 78.0
    assert reading.low_f == 61.0

    labels = [point.label for point in reading.forecast]
    assert labels == ["Morning", "This Afternoon", "Tonight"]
    afternoon = next(p for p in reading.forecast if p.label == "This Afternoon")
    assert afternoon.temp_f == 70.0 + 15


def test_fetch_weather_falls_back_to_rain_for_a_storm_wmo_code():
    with patch(
        "eink_calendar.weather_source.fetch.urllib.request.urlopen",
        return_value=_FakeResponse(_open_meteo_response(weather_code=95)),
    ):
        reading = fetch_weather(_NYC_LAT, _NYC_LON)
    assert reading.condition == "rain"


def test_fetch_weather_raises_on_malformed_json():
    with patch(
        "eink_calendar.weather_source.fetch.urllib.request.urlopen",
        return_value=_FakeResponse(b"not json"),
    ):
        try:
            fetch_weather(_NYC_LAT, _NYC_LON)
        except ValueError:
            pass
        else:
            raise AssertionError("expected fetch_weather to raise on malformed JSON")


def test_fetch_weather_raises_on_network_error():
    from urllib.error import URLError

    with patch(
        "eink_calendar.weather_source.fetch.urllib.request.urlopen",
        side_effect=URLError("network unreachable"),
    ):
        try:
            fetch_weather(_NYC_LAT, _NYC_LON)
        except URLError:
            pass
        else:
            raise AssertionError("expected fetch_weather to propagate a network error")


def test_fetch_weather_raises_on_non_200_response():
    from urllib.error import HTTPError

    with patch(
        "eink_calendar.weather_source.fetch.urllib.request.urlopen",
        side_effect=HTTPError(url="", code=503, msg="Service Unavailable", hdrs=None, fp=None),
    ):
        try:
            fetch_weather(_NYC_LAT, _NYC_LON)
        except HTTPError:
            pass
        else:
            raise AssertionError("expected fetch_weather to propagate a non-200 response")
