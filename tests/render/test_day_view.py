"""Render-level assertions for the day view.

Regression guard for #60: the day-view header (weekday title, ``%d %B %Y`` line,
divider rule) stacked on top of itself because ``text_size`` under-reported
height. These tests render the view and check the header bands occupy disjoint
vertical ranges and that event summaries are not clipped at the right edge.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone

import pytest

from eink_calendar.calendar_source.models import Event
from eink_calendar.render import day_view
from eink_calendar.render.layout_common import MARGIN
from eink_calendar.render.palette import PALETTE

RESOLUTION = (800, 480)
_PALETTE_RGB = set(PALETTE.values())


def _events():
    day = datetime(2026, 9, 9, tzinfo=timezone.utc)
    return [
        Event(
            id="a",
            summary="Gus - first day of school dismissal at the north entrance",
            start=day,
            end=day + timedelta(days=1),
            all_day=True,
            calendar_id="primary",
            color="blue",
        ),
        Event(
            id="b",
            summary="Heldeberg Meeting with the whole extended planning committee",
            start=day.replace(hour=19),
            end=day.replace(hour=20),
            all_day=False,
            calendar_id="primary",
            color="red",
        ),
    ]


def _black_columns(image, y):
    px = image.load()
    assert px is not None
    return [x for x in range(image.width) if px[x, y] == (0, 0, 0)]


def _ink_rows(image, y_max, x_lo, x_hi):
    """y values in ``[0, y_max)`` that have at least one black pixel in the
    x band ``[x_lo, x_hi)``."""
    px = image.load()
    assert px is not None
    rows = []
    for y in range(y_max):
        if any(px[x, y] == (0, 0, 0) for x in range(x_lo, x_hi)):
            rows.append(y)
    return rows


def _bands(rows):
    """Collapse a sorted row list into ``(top, bottom)`` contiguous bands."""
    bands = []
    for y in rows:
        if bands and y == bands[-1][1] + 1:
            bands[-1] = (bands[-1][0], y)
        else:
            bands.append((y, y))
    return bands


@pytest.fixture
def rendered():
    return day_view.render(_events(), datetime(2026, 9, 9, tzinfo=timezone.utc).date(), RESOLUTION)


def test_divider_rule_spans_the_width(rendered):
    width = rendered.width
    span = width - 2 * MARGIN
    divider_ys = [
        y
        for y in range(150)
        if len([x for x in _black_columns(rendered, y) if MARGIN <= x <= width - MARGIN])
        >= span * 0.9
    ]
    assert divider_ys, "no full-width divider rule found in the header"


def test_header_bands_do_not_overlap(rendered):
    width = rendered.width
    span = width - 2 * MARGIN

    divider_y = next(
        y
        for y in range(150)
        if len([x for x in _black_columns(rendered, y) if MARGIN <= x <= width - MARGIN])
        >= span * 0.9
    )

    # Ink bands strictly above the divider, in the left half (title + date line).
    header_rows = [
        y for y in _ink_rows(rendered, divider_y, MARGIN, width // 2) if y < divider_y
    ]
    bands = _bands(header_rows)

    assert len(bands) >= 2, f"title and date line are not vertically separated: {bands}"
    # Every header band clears the divider with at least one blank row of gap.
    assert bands[-1][1] < divider_y - 1, f"date line touches the divider: {bands[-1]} vs {divider_y}"
    # Bands are mutually disjoint (guaranteed by construction) and ordered.
    for (_, lower), (upper, _) in itertools.pairwise(bands):
        assert upper > lower + 1, f"header bands overlap/touch: {bands}"


def test_event_summaries_are_not_clipped_at_the_right_edge(rendered):
    width = rendered.width
    # Nothing should be painted in the right margin; a clipped-and-overflowing
    # render (or one that ignores the wrap width) would bleed into it.
    px = rendered.load()
    assert px is not None
    for y in range(rendered.height):
        for x in range(width - MARGIN + 1, width):
            assert px[x, y] != (0, 0, 0), f"ink in the right margin at {(x, y)}"


def test_day_view_output_is_palette_pure(rendered):
    assert set(rendered.getdata()) <= _PALETTE_RGB


def test_empty_day_still_renders_header_and_placeholder():
    image = day_view.render([], datetime(2026, 9, 9, tzinfo=timezone.utc).date(), RESOLUTION)
    assert set(image.getdata()) <= _PALETTE_RGB
    # some ink exists (the header + "No events")
    assert any(v == (0, 0, 0) for v in image.getdata())
