"""Weather + solar/lunar snapshot for the day-view widget column.

Two different reliability stories bundled into one object: the Open-Meteo
half (:class:`WeatherReading`) can fail or go stale and is cached; the
astral half (sunrise/sunset/moon phase) is deterministic given
``(date, lat, lon)`` and is recomputed on every render, never cached — see
``weather_source/fetch.py`` and ``weather_source/cache.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

__all__ = ["ForecastPoint", "WeatherReading", "WeatherSnapshot"]


@dataclass(frozen=True)
class ForecastPoint:
    """One same-day forecast entry, e.g. ("This Afternoon", 72.0, "rain")."""

    label: str
    temp_f: float
    condition: str

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "temp_f": self.temp_f, "condition": self.condition}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ForecastPoint:
        return cls(
            label=str(data["label"]),
            temp_f=float(data["temp_f"]),
            condition=str(data["condition"]),
        )


@dataclass(frozen=True)
class WeatherReading:
    """The Open-Meteo-derived half of a snapshot — what actually gets cached."""

    temp_f: float
    condition: str
    high_f: float
    low_f: float
    forecast: list[ForecastPoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "temp_f": self.temp_f,
            "condition": self.condition,
            "high_f": self.high_f,
            "low_f": self.low_f,
            "forecast": [point.to_dict() for point in self.forecast],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeatherReading:
        return cls(
            temp_f=float(data["temp_f"]),
            condition=str(data["condition"]),
            high_f=float(data["high_f"]),
            low_f=float(data["low_f"]),
            forecast=[ForecastPoint.from_dict(item) for item in data.get("forecast", [])],
        )


@dataclass(frozen=True)
class WeatherSnapshot:
    """What ``render/day_view.py`` consumes: a (possibly stale-cached,
    possibly absent) weather reading plus always-fresh solar/lunar figures.

    ``weather`` is ``None`` only when there has never been a successful
    fetch (first run, no cache, current fetch failed) — the renderer
    degrades by omitting the weather widget in that case, per
    ``day-view-widget-column.md`` requirement 7. ``sunrise``/``sunset``/
    ``moon_phase`` are always present: they're computed locally and cannot
    fail.
    """

    weather: WeatherReading | None
    sunrise: datetime
    sunset: datetime
    moon_phase: str
