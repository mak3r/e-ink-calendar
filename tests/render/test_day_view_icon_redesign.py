"""Coverage for #197: sunrise/sunset icon redesign and cloud icon rebuild.

Covers: the sunrise/sunset arrow triangle straddles the horizon line (part
above, part below) for both directions, instead of being confined to the
band below it; and the rebuilt cloud icon has a curved bottom silhouette
(no flat base rectangle) whose seam-cleanup ellipse stays clear of the
circles' own bottom edges, so the true outline is never erased.
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
from eink_calendar.weather_source.models import (
    ForecastPoint,
    WeatherReading,
    WeatherSnapshot,
)

RESOLUTION = (800, 480)
_WHEN = datetime(2026, 9, 9, tzinfo=timezone.utc)


def _dawn_dusk_geometry(width: int) -> tuple[int, int, int, float, float]:
    """(sunrise_icon_x0, sunset_icon_x0, icon size, icon_top, horizon_y).

    Since #209, the icon is a fixed ``_DAWN_DUSK_ICON_SIZE`` (no longer
    derived from label/time text width, as #203 had it) and each column is
    centered within its half rather than left-aligned at
    ``x0 + _WIDGET_PAD`` -- this replicates ``_draw_dawn_dusk_widget``'s
    current centering formula (icon_top depends on the fits-to-width time
    font's line height, so it must be computed, not assumed) rather than
    the stale #203-era formula, which would compute the wrong icon
    position and horizon_y for the straddle check below.
    """
    column_right = MARGIN + round((width - 2 * MARGIN) * day_view._COLUMN_FRACTION)
    widget_left = column_right + day_view._WIDGET_GAP
    widget_right = width - MARGIN
    half_w = (widget_right - widget_left) // 2

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
    ink_gap, value_gap = 14, 8
    content_h = (ink_bottom_offset - dome_top_offset) + ink_gap + label_h + value_gap + value_h
    margin = (day_view._WIDGET_DAWN_DUSK_H - content_h) / 2
    icon_top = MARGIN + margin - dome_top_offset
    horizon_y = icon_top + size * 0.45

    sunrise_x0 = round(widget_left + half_w / 2 - size / 2)
    sunset_x0 = round(widget_left + half_w + half_w / 2 - size / 2)
    return sunrise_x0, sunset_x0, size, icon_top, horizon_y


def _has_ink_above(image, x0: int, size: int, icon_top: float, horizon_y: float) -> bool:
    """Any black ink strictly above the horizon line, within the icon's x
    span — the dome only ever occupies y >= horizon_y, so ink up here can
    only be the arrow triangle straddling upward."""
    px = image.load()
    top = int(icon_top)
    bottom = int(horizon_y) - 1  # stop short of the horizon line's own row
    return any(
        px[x, y] == (0, 0, 0)
        for y in range(top, bottom)
        for x in range(x0 - 2, x0 + size + 2)
    )


def test_sunrise_triangle_straddles_the_horizon():
    width = RESOLUTION[0]
    sunrise_x0, _sunset_x0, size, icon_top, horizon_y = _dawn_dusk_geometry(width)
    image = day_view.render(
        [], _WHEN.date(), RESOLUTION,
        weather=WeatherSnapshot(weather=None, sunrise=_WHEN, sunset=_WHEN, moon_phase="Full Moon"),
    )
    assert _has_ink_above(image, sunrise_x0, size, icon_top, horizon_y), (
        "no ink above the horizon for the sunrise icon — triangle no longer straddles"
    )


def test_sunset_triangle_straddles_the_horizon():
    width = RESOLUTION[0]
    _sunrise_x0, sunset_x0, size, icon_top, horizon_y = _dawn_dusk_geometry(width)
    image = day_view.render(
        [], _WHEN.date(), RESOLUTION,
        weather=WeatherSnapshot(weather=None, sunrise=_WHEN, sunset=_WHEN, moon_phase="Full Moon"),
    )
    assert _has_ink_above(image, sunset_x0, size, icon_top, horizon_y), (
        "no ink above the horizon for the sunset icon — triangle no longer straddles"
    )


def _render_single_cloud_icon():
    """Render a single "cloudy" forecast point and return (image, icon_x,
    icon_y, size) for its condition icon, computed the same way
    ``_draw_weather_widget`` positions it."""
    width, height = RESOLUTION
    column_right = MARGIN + round((width - 2 * MARGIN) * day_view._COLUMN_FRACTION)
    widget_left = column_right + day_view._WIDGET_GAP
    weather_top = (
        MARGIN
        + day_view._WIDGET_DAWN_DUSK_H
        + day_view._WIDGET_V_GAP
        + day_view._WIDGET_MOON_H
        + day_view._WIDGET_V_GAP
    )
    pad = day_view._WIDGET_PAD
    hl_value_font = vendored_font(bold=True, size=day_view._FONT_HL_VALUE)
    hl_bottom = weather_top + pad + line_height(hl_value_font)
    label_font = vendored_font(bold=True, size=day_view._FONT_FORECAST_LABEL)
    label_line_h = line_height(label_font)
    size = day_view._FORECAST_ICON_SIZE
    row_h = label_line_h + 2 + size
    weather_bottom = height - MARGIN
    available = (weather_bottom - pad) - hl_bottom
    gap = max(available - row_h, 0) / 2
    row_y = round(hl_bottom + gap)
    icon_y = row_y + label_line_h + 2
    icon_x = widget_left + pad

    reading = WeatherReading(
        temp_f=60.0,
        condition="cloudy",
        high_f=70.0,
        low_f=50.0,
        forecast=[ForecastPoint(label="Afternoon", temp_f=60.0, condition="cloudy")],
    )
    snapshot = WeatherSnapshot(weather=reading, sunrise=_WHEN, sunset=_WHEN, moon_phase="Full Moon")
    image = day_view.render([], _WHEN.date(), RESOLUTION, weather=snapshot)
    return image, icon_x, icon_y, size


def test_cloud_bottom_silhouette_is_curved_not_a_flat_rectangle():
    image, icon_x, icon_y, size = _render_single_cloud_icon()
    px = image.load()

    bottoms = []
    for x in range(icon_x, icon_x + int(size) + 1):
        ys = [y for y in range(icon_y, icon_y + int(size) + 5) if px[x, y] == (0, 0, 0)]
        if ys:
            bottoms.append(max(ys))

    assert bottoms, "no cloud ink found"
    assert max(bottoms) - min(bottoms) >= 4, (
        f"cloud's bottom silhouette is flat (range={max(bottoms) - min(bottoms)}px) — "
        "looks like the old flat-base rectangle, not curved circle outlines"
    )


def test_cloud_seam_ellipse_leaves_the_true_bottom_outline_intact():
    """Regression guard: the seam-cleanup ellipse must stay above the
    circles' own bottom edges (§ _draw_cloud's own documented bounds:
    seam bottom at 0.62*size, circle bottoms at 0.67-0.83*size) so it never
    erases the real silhouette."""
    image, icon_x, icon_y, size = _render_single_cloud_icon()
    px = image.load()

    seam_bottom = icon_y + 0.62 * size
    below_seam = [
        (x, y)
        for x in range(icon_x, icon_x + int(size) + 1)
        for y in range(int(seam_bottom), icon_y + int(size) + 5)
        if px[x, y] == (0, 0, 0)
    ]
    assert below_seam, (
        "no black ink below the seam ellipse's bottom edge — the true cloud "
        "outline appears to have been erased"
    )
