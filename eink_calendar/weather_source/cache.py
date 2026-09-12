"""JSON cache of the last-fetched weather reading.

Mirrors ``calendar_source/cache.py``: Open-Meteo has no uptime guarantee
(see ``.claude/plans/day-view-widget-column.md`` §3.2), so every successful
fetch is written here and read back when the next fetch fails, keeping the
weather widget showing the last good reading instead of blanking. Only the
Open-Meteo half is cached — solar/lunar is recomputed fresh on every render
(see ``weather_source/fetch.py``) and never touches this file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from eink_calendar.calendar_source.local_files import write_private_text
from eink_calendar.weather_source.models import WeatherReading

__all__ = ["CachedWeather", "load_weather_cache", "save_weather_cache"]

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CachedWeather:
    """The cached reading plus when it was fetched (``None`` = never)."""

    fetched_at: datetime | None = None
    reading: WeatherReading | None = None


def load_weather_cache(path: str | os.PathLike[str]) -> CachedWeather:
    """Load the weather cache, returning empty contents if missing or corrupt."""
    cache_path = Path(path).expanduser()
    try:
        raw = cache_path.read_text(encoding="utf-8")
    except OSError:
        return CachedWeather()

    try:
        data = json.loads(raw)
        fetched_raw = data.get("fetched_at")
        fetched_at = datetime.fromisoformat(fetched_raw) if fetched_raw else None
        reading_raw = data.get("reading")
        reading = WeatherReading.from_dict(reading_raw) if reading_raw else None
    except (ValueError, TypeError, AttributeError, KeyError):
        # Corrupt JSON, wrong shape, or a malformed reading — start clean
        # rather than crash the display on boot.
        return CachedWeather()

    return CachedWeather(fetched_at=fetched_at, reading=reading)


def save_weather_cache(path: str | os.PathLike[str], contents: CachedWeather) -> None:
    """Write the weather cache atomically."""
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "fetched_at": contents.fetched_at.isoformat() if contents.fetched_at else None,
        "reading": contents.reading.to_dict() if contents.reading else None,
    }
    write_private_text(path, json.dumps(payload, indent=2))
