"""In-memory event models and Calendar API normalization.

No network calls live here — ``fetch.py`` does the talking to Google and hands
raw API event dicts to :meth:`Event.from_api`. This module only knows how to
normalize the two event shapes the Calendar API returns (timed events carry
``start.dateTime``; all-day events carry ``start.date``) and how to round-trip
an :class:`Event` through plain JSON-compatible dicts for the cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

__all__ = ["Event", "parse_api_datetime"]


def parse_api_datetime(node: dict[str, Any]) -> tuple[datetime, bool]:
    """Normalize a Calendar API ``start``/``end`` node to ``(datetime, all_day)``.

    - Timed events have ``{"dateTime": "2026-09-09T14:30:00-04:00"}`` — returned
      as a timezone-aware :class:`datetime`.
    - All-day events have ``{"date": "2026-09-09"}`` — returned as midnight UTC
      of that day, with ``all_day=True``. (Google's all-day ``end.date`` is
      exclusive; callers that care handle that themselves.)
    """
    if node.get("dateTime"):
        raw = str(node["dateTime"])
        # Python's fromisoformat handles a trailing 'Z' from 3.11 onward.
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed, False

    if node.get("date"):
        day = date.fromisoformat(str(node["date"]))
        return datetime(day.year, day.month, day.day, tzinfo=timezone.utc), True

    raise ValueError(f"datetime node has neither 'dateTime' nor 'date': {node!r}")


@dataclass(frozen=True)
class Event:
    """A single calendar event, normalized across timed and all-day shapes."""

    id: str
    summary: str
    start: datetime
    end: datetime
    all_day: bool
    calendar_id: str
    color: str
    location: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any], *, calendar_id: str, color: str) -> Event:
        """Build an :class:`Event` from a Calendar API ``events.list`` item.

        ``calendar_id`` and ``color`` come from config — the API item itself does
        not know which configured calendar it belongs to.
        """
        start, start_all_day = parse_api_datetime(raw.get("start", {}))
        end, end_all_day = parse_api_datetime(raw.get("end", {}))
        return cls(
            id=str(raw.get("id", "")),
            summary=str(raw.get("summary", "(no title)")),
            start=start,
            end=end,
            all_day=start_all_day and end_all_day,
            calendar_id=calendar_id,
            color=color,
            location=raw.get("location"),
        )

    def occurs_on(self, day: date) -> bool:
        """Whether this event should be shown on ``day``.

        All-day events' ``end`` is Google's *exclusive* all-day boundary (see
        :func:`parse_api_datetime`) — a single-day all-day event has
        ``end.date() == start.date() + 1 day``, so its last visible day is
        ``day < end.date()``, not ``day <= end.date()``. Timed events keep an
        inclusive end-day comparison since their ``end`` is a real instant
        (e.g. a meeting ending at 00:30 the next day still touches that day).
        """
        if self.all_day:
            return self.start.date() <= day < self.end.date()
        return self.start.date() <= day <= self.end.date()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (datetimes as ISO 8601 strings)."""
        return {
            "id": self.id,
            "summary": self.summary,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "all_day": self.all_day,
            "calendar_id": self.calendar_id,
            "color": self.color,
            "location": self.location,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """Inverse of :meth:`to_dict`."""
        try:
            return cls(
                id=str(data["id"]),
                summary=str(data["summary"]),
                start=datetime.fromisoformat(data["start"]),
                end=datetime.fromisoformat(data["end"]),
                all_day=bool(data["all_day"]),
                calendar_id=str(data["calendar_id"]),
                color=str(data["color"]),
                location=data.get("location"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"malformed cached event: {exc}") from exc
