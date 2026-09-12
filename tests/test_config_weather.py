"""Coverage for #166: ``config.weather`` — optional, strictly validated when
present. Mirrors the pattern in ``tests/test_config_output_path.py``: a local
config template with a ``{weather}`` slot rather than the shared fixture, so
each test controls the section directly."""

from __future__ import annotations

from pathlib import Path

import pytest

from eink_calendar.config import ConfigError, load_config

_CONFIG = """\
display:
  driver: mock
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
    credentials_file: "/nonexistent/creds.json"
    token_file: "/nonexistent/token.json"
    calendars:
      - {{id: primary, label: Example, color: red}}
cache:
  path: "cache.json"
{weather}
"""


def _write_config(directory: Path, *, weather: str = "") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "config.yaml"
    path.write_text(_CONFIG.format(weather=weather), encoding="utf-8")
    return path


def test_weather_section_absent_is_none(tmp_path):
    cfg = load_config(_write_config(tmp_path))
    assert cfg.weather is None


def test_valid_weather_section_parses(tmp_path):
    weather = "weather:\n  location: {lat: 40.7128, lon: -74.0060}\n"
    cfg = load_config(_write_config(tmp_path, weather=weather))
    assert cfg.weather is not None
    assert cfg.weather.lat == 40.7128
    assert cfg.weather.lon == -74.0060


@pytest.mark.parametrize(
    "location",
    [
        "{lat: 999, lon: -74.0060}",  # lat out of range
        "{lat: 40.7128, lon: 999}",  # lon out of range
        "{lat: -91, lon: 0}",
        "{lat: 0, lon: 181}",
        '{lat: "north", lon: -74.0060}',  # non-numeric lat
        "{lat: 40.7128, lon: -74.0060, extra_ignored_is_fine: true}",
    ],
)
def test_weather_location_validation(tmp_path, location):
    weather = f"weather:\n  location: {location}\n"
    cfg_path = _write_config(tmp_path, weather=weather)
    if "extra_ignored_is_fine" in location:
        assert load_config(cfg_path).weather is not None
        return
    with pytest.raises(ConfigError, match="weather.location"):
        load_config(cfg_path)


def test_weather_location_missing_lon_key_raises(tmp_path):
    weather = "weather:\n  location: {lat: 40.7128}\n"
    with pytest.raises(ConfigError, match="weather.location"):
        load_config(_write_config(tmp_path, weather=weather))


def test_weather_section_missing_location_key_raises(tmp_path):
    weather = "weather:\n  nickname: home\n"
    with pytest.raises(ConfigError, match="weather"):
        load_config(_write_config(tmp_path, weather=weather))


def test_weather_section_not_a_mapping_raises(tmp_path):
    weather = "weather: not-a-mapping\n"
    with pytest.raises(ConfigError, match="weather"):
        load_config(_write_config(tmp_path, weather=weather))


def test_weather_location_not_a_mapping_raises(tmp_path):
    weather = "weather:\n  location: not-a-mapping\n"
    with pytest.raises(ConfigError, match="weather.location"):
        load_config(_write_config(tmp_path, weather=weather))


def test_weather_location_boolean_lat_is_rejected(tmp_path):
    """``bool`` is an ``int`` subclass in Python — must not slip past the
    numeric-range check as a valid latitude."""
    weather = "weather:\n  location: {lat: true, lon: 0}\n"
    with pytest.raises(ConfigError, match="weather.location"):
        load_config(_write_config(tmp_path, weather=weather))
