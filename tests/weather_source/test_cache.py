"""Coverage for #166: the weather cache round-trips a reading and degrades
to empty (never raises) on a missing or corrupt file — mirrors
``calendar_source/cache.py``'s existing contract."""

from __future__ import annotations

from datetime import datetime, timezone

from eink_calendar.weather_source.cache import (
    CachedWeather,
    load_weather_cache,
    save_weather_cache,
)
from eink_calendar.weather_source.models import ForecastPoint, WeatherReading


def test_missing_cache_file_returns_empty_contents(tmp_path):
    cached = load_weather_cache(tmp_path / "weather_cache.json")
    assert cached == CachedWeather(fetched_at=None, reading=None)


def test_corrupt_cache_file_returns_empty_contents(tmp_path):
    path = tmp_path / "weather_cache.json"
    path.write_text("{not valid json", encoding="utf-8")
    cached = load_weather_cache(path)
    assert cached == CachedWeather(fetched_at=None, reading=None)


def test_cache_with_malformed_reading_shape_returns_empty_contents(tmp_path):
    path = tmp_path / "weather_cache.json"
    path.write_text('{"schema_version": 1, "fetched_at": null, "reading": {"temp_f": "oops"}}', encoding="utf-8")
    cached = load_weather_cache(path)
    assert cached == CachedWeather(fetched_at=None, reading=None)


def test_reading_round_trips_through_save_and_load(tmp_path):
    path = tmp_path / "weather_cache.json"
    reading = WeatherReading(
        temp_f=72.5,
        condition="cloudy",
        high_f=78.0,
        low_f=61.0,
        forecast=[
            ForecastPoint(label="Now", temp_f=72.5, condition="cloudy"),
            ForecastPoint(label="Tonight", temp_f=65.0, condition="clear"),
        ],
    )
    fetched_at = datetime(2024, 6, 21, 12, 0, 0, tzinfo=timezone.utc)

    save_weather_cache(path, CachedWeather(fetched_at=fetched_at, reading=reading))
    loaded = load_weather_cache(path)

    assert loaded.fetched_at == fetched_at
    assert loaded.reading == reading
