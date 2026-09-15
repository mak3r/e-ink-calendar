"""Coverage for #178: weather widget redesign and dawn/dusk icon fixes.

See ``.claude/plans/day-view-widget-column-fixes.md`` §2-6. Covers: 24-hour
dawn/dusk times stay within the widget (no 12-hour-format overflow), a
two-word moon phase name wraps onto two lines, the weather widget renders
its forecast as multiple stacked rows (not one ambiguous top icon block),
and all six condition-icon colors (yellow for sun-based icons, blue for
rain/snow, none for cloudy) render correctly.
"""

from __future__ import annotations

from datetime import datetime, timezone

from eink_calendar.render import day_view
from eink_calendar.render.layout_common import MARGIN
from eink_calendar.render.palette import color
from eink_calendar.weather_source.models import (
    ForecastPoint,
    WeatherReading,
    WeatherSnapshot,
)

RESOLUTION = (800, 480)
_WHEN = datetime(2026, 9, 9, tzinfo=timezone.utc)


def _widget_bounds(width: int) -> tuple[int, int]:
    column_right = MARGIN + round((width - 2 * MARGIN) * day_view._COLUMN_FRACTION)
    widget_left = column_right + day_view._WIDGET_GAP
    return widget_left, width - MARGIN


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


def _snapshot(reading: WeatherReading | None, *, sunrise=None, sunset=None, moon_phase="Full Moon"):
    return WeatherSnapshot(
        weather=reading,
        sunrise=sunrise or _WHEN.replace(hour=6, minute=30),
        sunset=sunset or _WHEN.replace(hour=19, minute=45),
        moon_phase=moon_phase,
    )


def test_dawn_dusk_24_hour_time_does_not_overflow_the_widget():
    """A 12-hour ``%I:%M %p`` render of a late time (e.g. 11:59 PM) is wide
    enough to overflow this narrow widget; 24-hour ``%H:%M`` should not."""
    width = RESOLUTION[0]
    _, widget_right = _widget_bounds(width)
    snapshot = _snapshot(
        None, sunrise=_WHEN.replace(hour=23, minute=59), sunset=_WHEN.replace(hour=0, minute=1)
    )
    image = day_view.render([], _WHEN.date(), RESOLUTION, weather=snapshot)

    beyond = [
        x
        for y in range(MARGIN, MARGIN + day_view._WIDGET_DAWN_DUSK_H)
        for x in range(widget_right + 1, width)
        if image.load()[x, y] == (0, 0, 0)
    ]
    assert not beyond, f"dawn/dusk time overflowed the widget: {beyond[:5]}"


def test_two_word_moon_phase_wraps_onto_two_lines():
    width = RESOLUTION[0]
    widget_left, widget_right = _widget_bounds(width)
    moon_top = MARGIN + day_view._WIDGET_DAWN_DUSK_H + day_view._WIDGET_V_GAP
    moon_bottom = moon_top + day_view._WIDGET_MOON_H
    # Since #219 the icon is offset right by _MOON_ICON_OFFSET_X and grown
    # to the wider _ICON_SIZE, and the phase text centers itself in the
    # space to the icon's right rather than hugging it -- text_x0 only
    # needs to bound that space from the icon's (now-shifted) right edge,
    # since the scan below just looks for ink anywhere across the range.
    # +1: the icon's own circle outline touches its computed right edge at
    # icon_right itself, so starting the scan exactly there would pick up
    # that ink and bridge the gap between the two wrapped text lines.
    icon_right = (
        widget_left + day_view._WIDGET_PAD + day_view._MOON_ICON_OFFSET_X + day_view._ICON_SIZE
    )
    text_x0 = icon_right + 1
    text_x1 = widget_right - day_view._WIDGET_PAD
    # Trim a few rows off each end to avoid the rounded-corner border curve.
    text_y0, text_y1 = moon_top + 15, moon_bottom - 15

    one_word = day_view.render(
        [], _WHEN.date(), RESOLUTION, weather=_snapshot(None, moon_phase="Full Moon")
    )
    two_word = day_view.render(
        [], _WHEN.date(), RESOLUTION, weather=_snapshot(None, moon_phase="Waxing Crescent")
    )

    one_bands = _bands(_ink_rows(one_word, text_y0, text_y1, text_x0, text_x1))
    two_bands = _bands(_ink_rows(two_word, text_y0, text_y1, text_x0, text_x1))

    assert len(one_bands) == 1, f"single-word phase should render on one line: {one_bands}"
    assert len(two_bands) == 2, f"two-word phase should wrap onto two lines: {two_bands}"

    beyond = [
        x
        for y in range(moon_top, moon_bottom)
        for x in range(widget_right + 1, width)
        if two_word.load()[x, y] == (0, 0, 0)
    ]
    assert not beyond, f"wrapped moon phase overflowed the widget: {beyond[:5]}"


def test_weather_widget_renders_stacked_forecast_rows_not_a_single_top_block():
    """Regression guard for #178 requirement 5: the old design drew one
    ambiguous icon/temp/condition block; the new one stacks a row per
    forecast period. Multiple forecast points must produce multiple
    vertically separated ink bands, not one contiguous block."""
    width = RESOLUTION[0]
    widget_left, widget_right = _widget_bounds(width)
    weather_top = (
        MARGIN
        + day_view._WIDGET_DAWN_DUSK_H
        + day_view._WIDGET_V_GAP
        + day_view._WIDGET_MOON_H
        + day_view._WIDGET_V_GAP
    )
    reading = WeatherReading(
        temp_f=68.0,
        condition="cloudy",
        high_f=72.0,
        low_f=55.0,
        forecast=[
            ForecastPoint(label="Morning", temp_f=68.0, condition="sunny"),
            ForecastPoint(label="Afternoon", temp_f=70.0, condition="rain"),
            ForecastPoint(label="Tonight", temp_f=60.0, condition="snow"),
        ],
    )
    image = day_view.render(
        [], _WHEN.date(), RESOLUTION, weather=_snapshot(reading)
    )

    inner_lo, inner_hi = widget_left + 5, widget_right - 5
    bands = _bands(_ink_rows(image, weather_top, RESOLUTION[1] - MARGIN, inner_lo, inner_hi))
    # H/L row + 3 forecast rows (each splitting into a label line and an
    # icon/temp line) is comfortably more bands than the old single block
    # would ever produce — the exact count is an implementation detail, the
    # multiplicity is the point.
    assert len(bands) >= 6, f"expected multiple stacked rows, got {len(bands)} bands: {bands}"


def test_all_six_condition_icons_use_expected_accent_colors():
    """Sun-based icons (sunny/partly sunny/partly cloudy) are yellow;
    rain/snow are blue; cloudy uses neither — per #178 requirement 6's
    six-value vocabulary and icon color convention."""
    width = RESOLUTION[0]
    widget_left, widget_right = _widget_bounds(width)
    weather_top = (
        MARGIN
        + day_view._WIDGET_DAWN_DUSK_H
        + day_view._WIDGET_V_GAP
        + day_view._WIDGET_MOON_H
        + day_view._WIDGET_V_GAP
    )
    inner_lo, inner_hi = widget_left + 5, widget_right - 5
    yellow, blue = color("yellow"), color("blue")

    expected = {
        "sunny": (True, False),
        "partly sunny": (True, False),
        "partly cloudy": (True, False),
        "cloudy": (False, False),
        "rain": (False, True),
        "snow": (False, True),
    }
    for condition, (expect_yellow, expect_blue) in expected.items():
        reading = WeatherReading(
            temp_f=60.0,
            condition=condition,
            high_f=70.0,
            low_f=50.0,
            forecast=[ForecastPoint(label="Morning", temp_f=60.0, condition=condition)],
        )
        image = day_view.render([], _WHEN.date(), RESOLUTION, weather=_snapshot(reading))
        px = image.load()
        has_yellow = any(
            px[x, y] == yellow
            for y in range(weather_top, RESOLUTION[1])
            for x in range(inner_lo, inner_hi)
        )
        has_blue = any(
            px[x, y] == blue
            for y in range(weather_top, RESOLUTION[1])
            for x in range(inner_lo, inner_hi)
        )
        assert has_yellow == expect_yellow, f"{condition}: expected yellow={expect_yellow}, got {has_yellow}"
        assert has_blue == expect_blue, f"{condition}: expected blue={expect_blue}, got {has_blue}"
