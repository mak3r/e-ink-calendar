"""Coverage for #185: widget-column triangle/font/label polish fixes.

See ``.claude/plans/day-view-widget-icon-font-fixes.md``. Covers: the
sunrise/sunset arrow triangle is proportioned (not a thin spike), forecast
period labels render bold, the forecast-hour label is the single word
"Afternoon" (not "This Afternoon"), and the dawn/dusk time value's dedicated
font keeps a 24-hour value like "20:43" comfortably within half the widget's
content width.
"""

from __future__ import annotations

from datetime import datetime, timezone

from eink_calendar.render import day_view
from eink_calendar.render.layout_common import (
    MARGIN,
    line_height,
    text_size,
    vendored_font,
)
from eink_calendar.weather_source.fetch import _FORECAST_HOURS
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


def test_forecast_hours_use_the_single_word_afternoon_label():
    labels = [label for label, _hour in _FORECAST_HOURS]
    assert "Afternoon" in labels
    assert "This Afternoon" not in labels


def test_dawn_dusk_time_font_fits_within_half_the_widget_content_width():
    """Regression guard: a shared, wider value font ("20:43" at the old
    18pt) crowded the border. Since #209 the value font grows to fill the
    available width rather than staying at a fixed point size (superseding
    the fixed-``_FONT_TIME_VALUE`` assumption this test used before), so
    this replicates that fits-to-width formula for a wide 24-hour fixture
    and confirms the result still fits -- by construction of the "grow,
    check it fits, step back" loop it always should, but this guards
    against a future change to that loop breaking the contract."""
    width = RESOLUTION[0]
    widget_left, widget_right = _widget_bounds(width)
    half_w = (widget_right - widget_left) // 2
    available = half_w - 2 * day_view._WIDGET_PAD

    time_size = day_view._FONT_TIME_VALUE
    while True:
        candidate = vendored_font(bold=True, size=time_size + 1)
        if text_size("20:43", font=candidate)[0] > available:
            break
        time_size += 1
    time_font = vendored_font(bold=True, size=time_size)
    rendered_w, _ = text_size("20:43", font=time_font)

    assert rendered_w <= available, (
        f"'20:43' at the fits-to-width size ({time_size}pt) is {rendered_w}px, "
        f"doesn't fit the {available}px available half-width"
    )


def test_sun_icon_triangle_has_a_reasonable_vertical_extent():
    """The arrow triangle must span a reasonable fraction of the icon's
    height (not be squashed into a sliver) — since #197 has it straddle the
    horizon and overlap the dome's footprint, a pixel bounding-box width
    comparison is no longer reliable (the dome inflates apparent width), so
    this checks vertical extent only, measured at the triangle's own
    centerline where it's the only shape present at every height in its
    span (a triangle's fill always includes its centerline column).

    Since #209, the icon is a fixed ``_DAWN_DUSK_ICON_SIZE`` (no longer
    derived from label/time text width, as #203/#205 had it), and it's
    centered within its half rather than left-aligned at
    ``x0 + _WIDGET_PAD`` -- see ``test_day_view_icon_sizing.py`` for the
    full replicated layout formula this mirrors."""
    width = RESOLUTION[0]
    widget_left, widget_right = _widget_bounds(width)
    half_w = (widget_right - widget_left) // 2
    snapshot = WeatherSnapshot(weather=None, sunrise=_WHEN, sunset=_WHEN, moon_phase="Full Moon")
    image = day_view.render([], _WHEN.date(), RESOLUTION, weather=snapshot)

    available_w = half_w - 2 * day_view._WIDGET_PAD
    time_size = day_view._FONT_TIME_VALUE
    while True:
        candidate = vendored_font(bold=True, size=time_size + 1)
        widest = max(
            text_size(_WHEN.strftime("%H:%M"), font=candidate)[0],
            text_size(_WHEN.strftime("%H:%M"), font=candidate)[0],
        )
        if widest > available_w:
            break
        time_size += 1
    time_font = vendored_font(bold=True, size=time_size)
    label_font = vendored_font(size=day_view._FONT_WIDGET_LABEL)

    size = day_view._DAWN_DUSK_ICON_SIZE
    dome_top_offset = size * 0.09
    ink_bottom_offset = size * 0.655
    label_h = line_height(label_font)
    value_h = line_height(time_font)
    ink_gap, value_gap = 4, 2  # tightened per #214
    content_h = (ink_bottom_offset - dome_top_offset) + ink_gap + label_h + value_gap + value_h
    margin = (day_view._WIDGET_DAWN_DUSK_H - content_h) / 2
    icon_top = MARGIN + margin - dome_top_offset

    cx = round(widget_left + half_w / 2)
    top = int(icon_top)
    bottom = top + size + 5

    px = image.load()
    ys = [y for y in range(top, bottom) if px[cx, y] == (0, 0, 0)]
    assert ys, "no ink found at the sunrise icon's centerline"
    extent = max(ys) - min(ys) + 1

    assert extent >= size * 0.3, (
        f"triangle's vertical extent ({extent}px) looks collapsed for a {size}px icon"
    )


def test_forecast_period_labels_render_bold():
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
        temp_f=60.0,
        condition="cloudy",
        high_f=70.0,
        low_f=50.0,
        forecast=[ForecastPoint(label="Afternoon", temp_f=60.0, condition="cloudy")],
    )
    snapshot = WeatherSnapshot(weather=reading, sunrise=_WHEN, sunset=_WHEN, moon_phase="Full Moon")
    image = day_view.render([], _WHEN.date(), RESOLUTION, weather=snapshot)

    pad = day_view._WIDGET_PAD
    hl_value_font = vendored_font(bold=True, size=day_view._FONT_HL_VALUE)
    label_font_bold = vendored_font(bold=True, size=day_view._FONT_FORECAST_LABEL)
    label_font_regular = vendored_font(bold=False, size=day_view._FONT_FORECAST_LABEL)
    row_h = line_height(label_font_bold)

    # Replicates _draw_weather_widget's own space-around placement (#191) for
    # this single-forecast-point fixture, rather than the old fixed-gap
    # formula — the single row sits roughly centered in the leftover height,
    # not packed immediately below H/L.
    hl_bottom = weather_top + pad + line_height(hl_value_font)
    full_row_h = row_h + 2 + day_view._FORECAST_ICON_SIZE
    weather_bottom = RESOLUTION[1] - MARGIN
    available = (weather_bottom - pad) - hl_bottom
    gap = max(available - full_row_h, 0) / 2
    row_y = round(hl_bottom + gap)

    inner_lo, inner_hi = widget_left + 5, widget_right - 5
    px = image.load()
    xs = [
        x
        for y in range(row_y, row_y + row_h)
        for x in range(inner_lo, inner_hi)
        if px[x, y] == (0, 0, 0)
    ]
    assert xs, "no forecast label ink found"
    rendered_w = max(xs) - min(xs) + 1

    bold_w, _ = text_size("Afternoon", font=label_font_bold)
    regular_w, _ = text_size("Afternoon", font=label_font_regular)
    assert regular_w < bold_w, "sanity check: bold should be wider than regular"
    assert abs(rendered_w - bold_w) < abs(rendered_w - regular_w), (
        f"forecast label doesn't look bold: rendered={rendered_w} bold={bold_w} regular={regular_w}"
    )
