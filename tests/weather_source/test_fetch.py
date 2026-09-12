"""Coverage for #166: the weather_source data layer (Open-Meteo + astral).

Companion to #169. Covers ``compute_solar_lunar`` against known real-world
values, ``fetch_weather``'s response parsing (condition-code mapping and
same-day forecast extraction), and that it raises rather than swallowing a
network/parse failure — the cache-fallback contract lives one layer up, in
``app.py``'s ``_refresh_weather`` (see ``tests/test_app_weather_refresh.py``).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Self
from unittest.mock import patch

from eink_calendar.weather_source.fetch import compute_solar_lunar, fetch_weather

# New York City, summer solstice 2024 — a fixed, reproducible (date, lat, lon)
# triple. Sunrise time is in local-evening terms (astral computes against the
# UTC calendar date, so a negative-UTC-offset location's sunset can land on
# the UTC date *before* the requested local date — the wall-clock time itself
# is still the correct evening sunset).
_NYC_LAT, _NYC_LON = 40.7128, -74.0060
_SOLSTICE = date(2024, 6, 21)


def test_compute_solar_lunar_matches_known_values_for_a_fixed_date_and_location():
    sunrise, sunset, moon_phase = compute_solar_lunar(_SOLSTICE, _NYC_LAT, _NYC_LON)

    assert sunrise == datetime(2024, 6, 21, 9, 25, 23, 756609, tzinfo=timezone.utc)
    assert sunset == datetime(2024, 6, 21, 0, 30, 22, 694990, tzinfo=timezone.utc)
    assert moon_phase == "Waxing Gibbous"


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
    assert reading.condition == "clear"
    assert reading.high_f == 78.0
    assert reading.low_f == 61.0

    labels = [point.label for point in reading.forecast]
    assert labels == ["Now", "This Afternoon", "Tonight"]
    afternoon = next(p for p in reading.forecast if p.label == "This Afternoon")
    assert afternoon.temp_f == 70.0 + 15


def test_fetch_weather_maps_storm_condition_code():
    with patch(
        "eink_calendar.weather_source.fetch.urllib.request.urlopen",
        return_value=_FakeResponse(_open_meteo_response(weather_code=95)),
    ):
        reading = fetch_weather(_NYC_LAT, _NYC_LON)
    assert reading.condition == "storm"


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
