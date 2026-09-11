"""Regression guard for #140: all-day exclusive-end-date boundary in month view.

Each day's event bars are drawn inside that day's own grid cell (a distinct,
non-overlapping rectangle), so cropping to a single cell and checking for the
event's bar color is enough to tell whether it rendered on that day — using
the same week-grid the view itself builds, so the cell geometry can't drift
out of sync with the source.
"""

from __future__ import annotations

import calendar as _calendar
from datetime import date, datetime, timedelta, timezone

from eink_calendar.calendar_source.models import Event
from eink_calendar.render import month_view
from eink_calendar.render.layout_common import MARGIN, text_size
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


def _cell_box(width: int, height: int, anchor: date, day: date) -> tuple[int, int, int, int]:
    firstweekday = 6 if WEEK_STARTS_ON == "sunday" else 0
    weeks = _calendar.Calendar(firstweekday=firstweekday).monthdatescalendar(
        anchor.year, anchor.month
    )
    r, c = next((r, c) for r, week in enumerate(weeks) for c, d in enumerate(week) if d == day)

    grid_top = MARGIN + text_size("A", scale=3)[1] + 10
    col_w = (width - 2 * MARGIN) // 7
    row_h = (height - MARGIN - grid_top) // len(weeks)
    x0 = MARGIN + c * col_w
    y0 = grid_top + r * row_h
    return x0, y0, x0 + col_w, y0 + row_h


def _cell_has_color(image, box: tuple[int, int, int, int], rgb: tuple[int, int, int]) -> bool:
    x0, y0, x1, y1 = box
    px = image.load()
    return any(px[x, y] == rgb for x in range(x0, x1) for y in range(y0, y1))


def test_single_day_all_day_event_does_not_leak_into_the_next_cell():
    anchor = date(2026, 9, 1)
    event_day = date(2026, 9, 10)
    leak_day = event_day + timedelta(days=1)
    event = _all_day_event(event_day, leak_day)

    image = month_view.render([event], anchor, RESOLUTION, WEEK_STARTS_ON)
    blue = color("blue")

    assert _cell_has_color(image, _cell_box(*RESOLUTION, anchor, event_day), blue)
    assert not _cell_has_color(image, _cell_box(*RESOLUTION, anchor, leak_day), blue)


def test_multi_day_all_day_event_spans_its_exclusive_range():
    anchor = date(2026, 9, 1)
    start = date(2026, 9, 8)
    end = date(2026, 9, 11)  # exclusive: occurs on 8, 9, 10 — not 11
    event = _all_day_event(start, end)

    image = month_view.render([event], anchor, RESOLUTION, WEEK_STARTS_ON)
    blue = color("blue")

    for day in (start, start + timedelta(days=1), start + timedelta(days=2)):
        assert _cell_has_color(image, _cell_box(*RESOLUTION, anchor, day), blue)
    assert not _cell_has_color(image, _cell_box(*RESOLUTION, anchor, end), blue)
