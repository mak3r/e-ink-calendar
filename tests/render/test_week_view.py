"""Regression guard for #140: all-day exclusive-end-date boundary in week view.

Each day's events are drawn inside that day's own column (a distinct,
non-overlapping x-range), so cropping to a single column and checking for the
event's swatch color is enough to tell whether it rendered on that day —
without replicating the row-layout math.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from eink_calendar.calendar_source.models import Event
from eink_calendar.render import week_view
from eink_calendar.render.layout_common import MARGIN
from eink_calendar.render.palette import color

RESOLUTION = (800, 480)
WEEK_STARTS_ON = "monday"


def _all_day_event(start: date, end: date, event_color: str = "blue") -> Event:
    return Event(
        id="a",
        summary="All-day reminder",
        start=datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
        end=datetime(end.year, end.month, end.day, tzinfo=timezone.utc),
        all_day=True,
        calendar_id="primary",
        color=event_color,
    )


def _column_has_color(image, day_index: int, rgb: tuple[int, int, int]) -> bool:
    col_w = (image.width - 2 * MARGIN) // 7
    x0 = MARGIN + day_index * col_w
    x1 = x0 + col_w
    px = image.load()
    return any(px[x, y] == rgb for x in range(x0, x1) for y in range(image.height))


def test_single_day_all_day_event_does_not_leak_into_the_next_column():
    # 2026-09-10 is a Thursday; week (Monday-start) is 2026-09-07..09-13.
    week_anchor = date(2026, 9, 7)
    event_day = date(2026, 9, 10)
    event = _all_day_event(event_day, event_day + timedelta(days=1))

    image = week_view.render([event], week_anchor, RESOLUTION, WEEK_STARTS_ON)
    blue = color("blue")

    assert _column_has_color(image, (event_day - week_anchor).days, blue)
    leak_index = (event_day - week_anchor).days + 1
    assert not _column_has_color(image, leak_index, blue)


def test_multi_day_all_day_event_spans_its_exclusive_range():
    week_anchor = date(2026, 9, 7)
    start = date(2026, 9, 8)
    end = date(2026, 9, 11)  # exclusive: occurs on 8, 9, 10 — not 11
    event = _all_day_event(start, end)

    image = week_view.render([event], week_anchor, RESOLUTION, WEEK_STARTS_ON)
    blue = color("blue")

    for day in (start, start + timedelta(days=1), start + timedelta(days=2)):
        assert _column_has_color(image, (day - week_anchor).days, blue)
    assert not _column_has_color(image, (end - week_anchor).days, blue)
