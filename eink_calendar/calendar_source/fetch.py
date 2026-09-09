"""Google Calendar fetch — one request per calendar covering the whole month.

Per the design, each refresh pulls the full month window (padded to whole weeks)
for every calendar in a single ``events().list`` call with ``singleEvents=True``.
Day and Week views then filter that cached month client-side, so cycling the
view with button A never triggers a network request.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from eink_calendar.calendar_source.models import Event

__all__ = ["build_service", "fetch_calendar_events", "month_window"]

_MAX_RESULTS = 2500


def build_service(credentials: Credentials) -> Any:
    """Build a read-only Calendar API client. ``cache_discovery=False`` keeps it
    quiet on read-only filesystems and avoids an oauth2client dependency."""
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def month_window(when: date) -> tuple[datetime, datetime]:
    """UTC ``(time_min, time_max)`` covering ``when``'s month, padded to whole
    weeks so a Week view straddling a month boundary still has its events."""
    first_of_month = when.replace(day=1)
    if first_of_month.month == 12:
        next_month = first_of_month.replace(year=first_of_month.year + 1, month=1)
    else:
        next_month = first_of_month.replace(month=first_of_month.month + 1)

    start = first_of_month - timedelta(days=7)
    end = next_month + timedelta(days=7)
    return (
        datetime.combine(start, time.min, tzinfo=timezone.utc),
        datetime.combine(end, time.min, tzinfo=timezone.utc),
    )


def fetch_calendar_events(
    service: Any,
    calendar_id: str,
    *,
    color: str,
    when: date,
) -> list[Event]:
    """Return one month's worth of :class:`Event` for ``calendar_id`` in a single
    API call. ``color`` is stamped onto every returned event for rendering."""
    time_min, time_max = month_window(when)
    response = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=_MAX_RESULTS,
        )
        .execute()
    )

    items: list[dict[str, Any]] = response.get("items", [])
    return [
        Event.from_api(item, calendar_id=calendar_id, color=color) for item in items
    ]
