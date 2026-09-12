"""Coverage for #166: ``App``'s weather cache-fallback contract.

A failed weather fetch must never blank the widget — ``_refresh_weather``
falls back to the last cached reading, and a cold start with no cache and a
failed fetch degrades to ``weather=None`` (solar/lunar still present) rather
than crashing, exactly like the calendar-fetch failure path this mirrors.
"""

from __future__ import annotations

from pathlib import Path
from urllib.error import URLError

import pytest

from eink_calendar.app import App
from eink_calendar.config import load_config
from eink_calendar.weather_source.cache import load_weather_cache
from eink_calendar.weather_source.models import WeatherReading

_CONFIG = """\
display:
  driver: mock
  output_path: "{output}"
  mock_auto_open: false
  resolution: [800, 480]
refresh:
  daily_time: "05:30"
  timezone: "America/New_York"
view:
  default: day
  week_starts_on: monday
buttons:
  pin_map: {{A: 5, B: 6, C: 16, D: 24}}
  bindings: {{A: cycle_view, B: force_refresh, C: noop, D: noop}}
accounts:
  - name: personal
    credentials_file: "{creds}"
    token_file: "{token}"
    calendars:
      - {{id: "primary", label: "Example", color: red}}
cache:
  path: "{cache}"
{weather}"""

_WEATHER_SECTION = "weather:\n  location: {lat: 40.7128, lon: -74.0060}\n"


def _write_config(tmp_path: Path, *, weather: str = _WEATHER_SECTION) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        _CONFIG.format(
            output=tmp_path / "data" / "last_render.png",
            creds=tmp_path / "creds.json",
            token=tmp_path / "token.json",
            cache=tmp_path / "cache.json",
            weather=weather,
        ),
        encoding="utf-8",
    )
    return config_path


@pytest.fixture
def weather_app(tmp_path: Path) -> App:
    return App(load_config(_write_config(tmp_path)))


def _reading(temp_f: float = 70.0) -> WeatherReading:
    return WeatherReading(temp_f=temp_f, condition="clear", high_f=75.0, low_f=60.0, forecast=[])


def test_cold_start_no_cache_and_failed_fetch_degrades_to_no_weather_data(weather_app, monkeypatch):
    assert weather_app._weather_snapshot.weather is None  # no cache yet at __init__

    monkeypatch.setattr(
        "eink_calendar.app.fetch_weather",
        lambda lat, lon: (_ for _ in ()).throw(URLError("unreachable")),
    )
    weather_app._refresh_weather()

    snapshot = weather_app._weather_snapshot
    assert snapshot.weather is None
    assert snapshot.sunrise is not None
    assert snapshot.sunset is not None
    assert snapshot.moon_phase


def test_failed_fetch_after_a_prior_success_falls_back_to_cached_reading(weather_app, monkeypatch):
    good = _reading(temp_f=68.0)
    monkeypatch.setattr("eink_calendar.app.fetch_weather", lambda lat, lon: good)
    weather_app._refresh_weather()
    assert weather_app._weather_snapshot.weather == good

    monkeypatch.setattr(
        "eink_calendar.app.fetch_weather",
        lambda lat, lon: (_ for _ in ()).throw(URLError("unreachable")),
    )
    weather_app._refresh_weather()

    assert weather_app._weather_snapshot.weather == good


def test_successful_fetch_persists_to_the_weather_cache_file(weather_app, monkeypatch, tmp_path):
    good = _reading(temp_f=55.5)
    monkeypatch.setattr("eink_calendar.app.fetch_weather", lambda lat, lon: good)
    weather_app._refresh_weather()

    cache_path = tmp_path / "weather_cache.json"
    assert cache_path.is_file()
    assert load_weather_cache(cache_path).reading == good


def test_weather_absent_from_config_skips_refresh_entirely(tmp_path, monkeypatch):
    app = App(load_config(_write_config(tmp_path, weather="")))
    assert app._weather_snapshot is None

    called = []
    monkeypatch.setattr("eink_calendar.app.fetch_weather", lambda lat, lon: called.append(1))
    app._refresh_weather()

    assert called == []
    assert app._weather_snapshot is None
