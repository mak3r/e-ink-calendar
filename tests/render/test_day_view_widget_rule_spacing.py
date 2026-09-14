"""Coverage for #191: widget-column rule overreach and weather-row spacing.

See ``.claude/plans/day-view-widget-rule-and-spacing-fixes.md``. Covers: the
header rule ends at the event column's true right edge (``column_right``),
not 12px further out at the widget gap (``widget_left``); and the weather
widget's forecast rows are space-around distributed across the widget's
actual available height (equal leading/between/trailing slack) instead of
packed near the top with a small fixed gap.
"""

from __future__ import annotations

from datetime import datetime, timezone

from eink_calendar.render import day_view
from eink_calendar.render.layout_common import MARGIN
from eink_calendar.weather_source.models import (
    ForecastPoint,
    WeatherReading,
    WeatherSnapshot,
)

RESOLUTION = (800, 480)
_WHEN = datetime(2026, 9, 9, tzinfo=timezone.utc)


def _column_bounds(width: int) -> tuple[int, int]:
    column_right = MARGIN + round((width - 2 * MARGIN) * day_view._COLUMN_FRACTION)
    widget_left = column_right + day_view._WIDGET_GAP
    return column_right, widget_left


def _black_columns(image, y: int) -> list[int]:
    px = image.load()
    return [x for x in range(image.width) if px[x, y] == (0, 0, 0)]


def _find_rule_row(image, column_right: int) -> int:
    span = column_right - MARGIN
    for y in range(150):
        xs = [x for x in _black_columns(image, y) if MARGIN <= x <= column_right]
        if len(xs) >= span * 0.9:
            return y
    raise AssertionError("no header rule found")


def _ink_rows(image, y_lo: int, y_hi: int, x_lo: int, x_hi: int) -> list[int]:
    px = image.load()
    return [y for y in range(y_lo, y_hi) if any(px[x, y] == (0, 0, 0) for x in range(x_lo, x_hi))]


def _bands(rows: list[int]) -> list[tuple[int, int]]:
    bands: list[tuple[int, int]] = []
    for y in rows:
        if bands and y == bands[-1][1] + 1:
            bands[-1] = (bands[-1][0], y)
        else:
            bands.append((y, y))
    return bands


def test_header_rule_ends_at_the_event_column_not_the_widget_gap():
    width = RESOLUTION[0]
    column_right, widget_left = _column_bounds(width)
    image = day_view.render([], _WHEN.date(), RESOLUTION)

    rule_y = _find_rule_row(image, column_right)
    rule_xs = _black_columns(image, rule_y)
    rule_end = max(x for x in rule_xs if x <= widget_left)

    assert rule_end <= column_right, (
        f"rule extends to x={rule_end}, past the event column's right edge at {column_right}"
    )


def test_single_forecast_row_has_equal_leading_and_trailing_slack():
    """Regression guard for #191: with one forecast row, space-around must
    split the widget's leftover height evenly before and after the row —
    not pack it immediately below H/L with a small fixed gap and leave the
    rest of the widget's height unused below."""
    width, height = RESOLUTION
    _, widget_left = _column_bounds(width)
    widget_right = width - MARGIN
    weather_top = (
        MARGIN
        + day_view._WIDGET_DAWN_DUSK_H
        + day_view._WIDGET_V_GAP
        + day_view._WIDGET_MOON_H
        + day_view._WIDGET_V_GAP
    )
    weather_bottom = height - MARGIN

    reading = WeatherReading(
        temp_f=60.0,
        condition="cloudy",
        high_f=70.0,
        low_f=50.0,
        forecast=[ForecastPoint(label="Afternoon", temp_f=60.0, condition="cloudy")],
    )
    snapshot = WeatherSnapshot(weather=reading, sunrise=_WHEN, sunset=_WHEN, moon_phase="Full Moon")
    image = day_view.render([], _WHEN.date(), RESOLUTION, weather=snapshot)

    inner_lo, inner_hi = widget_left + 5, widget_right - 5
    rows = _ink_rows(image, weather_top, weather_bottom, inner_lo, inner_hi)
    bands = _bands(rows)

    # Drop the widget's own top/bottom border bands; what's left is the H/L
    # row followed by the single forecast row (its label and icon/temp may
    # or may not merge into one band depending on the icon shape, so treat
    # everything after the H/L band as the row's content).
    content_bands = bands[1:-1]
    assert len(content_bands) >= 2, f"expected H/L row + one forecast row: {bands}"
    hl_band, *row_bands = content_bands

    leading = row_bands[0][0] - hl_band[1] - 1
    trailing = (weather_bottom - 1) - row_bands[-1][1]

    assert leading > 50, f"leading gap too small, row still packed near the top: {leading}"
    assert trailing > 50, f"trailing gap too small, row still packed near the top: {trailing}"
    assert abs(leading - trailing) <= 15, (
        f"leading/trailing slack not evenly split: leading={leading} trailing={trailing}"
    )
