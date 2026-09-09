"""JSON cache of the last-fetched event list.

The display must still render something useful when the network or Google is
down at refresh time, so every successful fetch is written to
``data/cache.json`` (path from config) and read back on the next boot. A missing
or corrupt cache file is not an error — it just means "no events yet".
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from eink_calendar.calendar_source.local_files import write_private_text
from eink_calendar.calendar_source.models import Event

__all__ = ["CacheContents", "load_cache", "save_cache"]

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CacheContents:
    """The cached events plus when they were fetched (``None`` = never)."""

    fetched_at: datetime | None = None
    events: list[Event] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.fetched_at is None and not self.events


def load_cache(path: str | os.PathLike[str]) -> CacheContents:
    """Load the cache, returning empty contents if it is missing or corrupt."""
    cache_path = Path(path).expanduser()
    try:
        raw = cache_path.read_text(encoding="utf-8")
    except OSError:
        return CacheContents()

    try:
        data = json.loads(raw)
        fetched_raw = data.get("fetched_at")
        fetched_at = datetime.fromisoformat(fetched_raw) if fetched_raw else None
        events = [Event.from_dict(item) for item in data.get("events", [])]
    except (ValueError, TypeError, AttributeError):
        # Corrupt JSON, wrong shape, or a malformed event — start clean rather
        # than crash the display on boot.
        return CacheContents()

    return CacheContents(fetched_at=fetched_at, events=events)


def save_cache(path: str | os.PathLike[str], contents: CacheContents) -> None:
    """Write the cache atomically as a ``0600`` file in a ``0700`` directory.

    ``cache.json`` holds personal data (event titles/times/descriptions), so it
    must not be world-readable regardless of the process umask — see
    :mod:`eink_calendar.calendar_source.local_files`.
    """
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "fetched_at": contents.fetched_at.isoformat() if contents.fetched_at else None,
        "events": [event.to_dict() for event in contents.events],
    }
    write_private_text(path, json.dumps(payload, indent=2))
