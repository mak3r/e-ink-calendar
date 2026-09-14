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
    18pt) crowded the border; the dedicated smaller font must leave room."""
    width = RESOLUTION[0]
    widget_left, widget_right = _widget_bounds(width)
    half_w = (widget_right - widget_left) // 2
    available = half_w - day_view._WIDGET_PAD

    time_font = vendored_font(bold=True, size=day_view._FONT_TIME_VALUE)
    rendered_w, _ = text_size("20:43", font=time_font)

    assert rendered_w <= available, (
        f"'20:43' at {day_view._FONT_TIME_VALUE}pt is {rendered_w}px, "
        f"doesn't fit the {available}px available half-width"
    )


def test_sun_icon_triangle_is_proportioned_not_a_spike():
    """The arrow triangle's base and height must be within a reasonable
    ratio of each other (not a thin spike stretched to fill its band)."""
    width = RESOLUTION[0]
    widget_left, _ = _widget_bounds(width)
    snapshot = WeatherSnapshot(weather=None, sunrise=_WHEN, sunset=_WHEN, moon_phase="Full Moon")
    image = day_view.render([], _WHEN.date(), RESOLUTION, weather=snapshot)

    size = day_view._ICON_SIZE
    horizon_y = MARGIN + day_view._WIDGET_PAD + size * 0.45
    # Matches _draw_sun_icon's own `band_top = horizon_y + 3` — skips past
    # the horizon line's own row(s) so it doesn't get measured as part of
    # the triangle.
    band_top = int(horizon_y) + 3
    band_bottom = MARGIN + day_view._WIDGET_PAD + size + 2

    icon_x0 = widget_left + day_view._WIDGET_PAD - 2
    icon_x1 = widget_left + day_view._WIDGET_PAD + size + 2

    px = image.load()
    points = [
        (x, y)
        for y in range(band_top, band_bottom)
        for x in range(icon_x0, icon_x1)
        if px[x, y] == (0, 0, 0)
    ]
    assert points, "no triangle ink found in the sunrise arrow band"
    xs = [x for x, _y in points]
    ys = [y for _x, y in points]
    tri_w = max(xs) - min(xs) + 1
    tri_h = max(ys) - min(ys) + 1

    ratio = max(tri_w, tri_h) / min(tri_w, tri_h)
    assert ratio <= 1.3, f"triangle reads as a spike, not proportioned: width={tri_w} height={tri_h}"


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
