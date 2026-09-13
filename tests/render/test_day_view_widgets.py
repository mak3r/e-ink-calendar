"""Coverage for #167: the day-view widget column (dawn/dusk, moon phase,
weather). See ``.claude/plans/day-view-widget-column.md``.

Covers: the widget column is blank with no ``weather:`` config, all three
widgets render and stack top-down to fill the panel's full height with a
real ``WeatherSnapshot`` fixture, the weather widget alone is omitted when
the reading is absent (cold start / failed fetch) while dawn/dusk and moon
phase still render, and the calendar key relocates to the date row next to
the widget column instead of the day-name row.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from eink_calendar.calendar_source.models import Event
from eink_calendar.render import day_view
from eink_calendar.render.layout_common import MARGIN, text_size, vendored_font
from eink_calendar.render.palette import color
from eink_calendar.weather_source.models import (
    ForecastPoint,
    WeatherReading,
    WeatherSnapshot,
)

RESOLUTION = (800, 480)
_WHEN = datetime(2026, 9, 9, tzinfo=timezone.utc)


def _snapshot(*, with_reading: bool = True) -> WeatherSnapshot:
    reading = (
        WeatherReading(
            temp_f=68.0,
            condition="cloudy",
            high_f=72.0,
            low_f=55.0,
            forecast=[
                ForecastPoint(label="Morning", temp_f=68.0, condition="cloudy"),
                ForecastPoint(label="Afternoon", temp_f=70.0, condition="cloudy"),
                ForecastPoint(label="Tonight", temp_f=60.0, condition="sunny"),
            ],
        )
        if with_reading
        else None
    )
    return WeatherSnapshot(
        weather=reading,
        sunrise=_WHEN.replace(hour=6, minute=30),
        sunset=_WHEN.replace(hour=19, minute=45),
        moon_phase="Waxing Gibbous",
    )


def _widget_left(width: int) -> int:
    column_right = MARGIN + round((width - 2 * MARGIN) * day_view._COLUMN_FRACTION)
    return column_right + day_view._WIDGET_GAP


def _ink_rows(image, x_lo: int, x_hi: int) -> list[int]:
    px = image.load()
    return [
        y for y in range(image.height) if any(px[x, y] == (0, 0, 0) for x in range(x_lo, x_hi))
    ]


def _bands(rows: list[int]) -> list[tuple[int, int]]:
    bands: list[tuple[int, int]] = []
    for y in rows:
        if bands and y == bands[-1][1] + 1:
            bands[-1] = (bands[-1][0], y)
        else:
            bands.append((y, y))
    return bands


def test_widget_column_blank_when_no_weather_configured():
    width = RESOLUTION[0]
    widget_left = _widget_left(width)
    image = day_view.render([], _WHEN.date(), RESOLUTION)  # weather=None default

    # +2 to skip the single edge pixel where the header rule's own endpoint
    # touches the widget column's left edge.
    rows = _ink_rows(image, widget_left + 2, width)
    assert rows == [], f"expected a blank widget column, found ink at rows {rows}"


def test_full_snapshot_renders_three_widgets_spanning_the_full_panel_height():
    width, height = RESOLUTION
    widget_left = _widget_left(width)
    image = day_view.render([], _WHEN.date(), RESOLUTION, weather=_snapshot())

    bands = _bands(_ink_rows(image, widget_left, width - MARGIN))
    assert len(bands) == 3, f"expected dawn/dusk, moon, and weather widgets: {bands}"

    top, bottom = bands[0][0], bands[-1][1]
    assert top - MARGIN <= 1, f"first widget should start at the top margin: {bands}"
    assert (height - MARGIN) - bottom <= 1, f"last widget should reach the bottom margin: {bands}"


def test_missing_weather_reading_omits_only_the_weather_widget():
    """Cold start / failed fetch: solar/lunar (never cached, can't fail)
    still render; only the third (weather) widget is skipped."""
    width = RESOLUTION[0]
    widget_left = _widget_left(width)
    image = day_view.render(
        [], _WHEN.date(), RESOLUTION, weather=_snapshot(with_reading=False)
    )

    bands = _bands(_ink_rows(image, widget_left, width - MARGIN))
    assert len(bands) == 2, f"expected only dawn/dusk and moon widgets: {bands}"


def test_calendar_key_relocates_to_the_date_row():
    """Per §2: the key moves off the day-name row onto the date row, next to
    where the widget column begins."""
    day_font = vendored_font(bold=True, size=day_view._FONT_DAY_NAME)
    date_font = vendored_font(size=day_view._FONT_DATE)
    day_name_h = text_size("A", font=day_font)[1]
    date_y = MARGIN + day_name_h + day_view._DATE_TOP_GAP
    date_h = text_size("A", font=date_font)[1]

    event = Event(
        id="a",
        summary="X",
        start=_WHEN,
        end=_WHEN + timedelta(hours=1),
        all_day=False,
        calendar_id="primary",
        color="blue",
    )
    image = day_view.render([event], _WHEN.date(), RESOLUTION)
    blue = color("blue")
    px = image.load()

    in_day_name_row = any(
        px[x, y] == blue for y in range(MARGIN, MARGIN + day_name_h) for x in range(image.width)
    )
    in_date_row = any(
        px[x, y] == blue for y in range(date_y, date_y + date_h) for x in range(image.width)
    )
    assert not in_day_name_row, "calendar key should no longer sit on the day-name row"
    assert in_date_row, "calendar key should be on the date row"
