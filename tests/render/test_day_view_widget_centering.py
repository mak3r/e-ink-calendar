"""Coverage for #219: moon/weather/dawn-dusk widget centering and offset
tweaks that weren't exercised by any existing test (as opposed to the
formula updates in ``test_day_view_icon_sizing.py``,
``test_day_view_icon_redesign.py``, and ``test_day_view_weather_widget.py``,
which patch existing assertions to match the new formulas).

Covers: the weather widget's ``H:70° L:45°`` row now centers horizontally
instead of hugging the left padding; each forecast row's icon+temp group
centers independently of its (still left-anchored) period label; and the
moon icon is nudged right of the plain padding-only position it used to
sit at.
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


def _widget_bounds(width: int) -> tuple[int, int]:
    column_right = MARGIN + round((width - 2 * MARGIN) * day_view._COLUMN_FRACTION)
    widget_left = column_right + day_view._WIDGET_GAP
    return widget_left, width - MARGIN


def _weather_top() -> int:
    return (
        MARGIN
        + day_view._WIDGET_DAWN_DUSK_H
        + day_view._WIDGET_V_GAP
        + day_view._WIDGET_MOON_H
        + day_view._WIDGET_V_GAP
    )


def _first_ink_x(image, y_lo: int, y_hi: int, x_lo: int, x_hi: int) -> int | None:
    px = image.load()
    xs = [x for y in range(y_lo, y_hi) for x in range(x_lo, x_hi) if px[x, y] == (0, 0, 0)]
    return min(xs) if xs else None


def test_hl_row_centers_horizontally_in_the_widget():
    """The old H/L row was drawn flush against the left padding; #219
    centers the whole ``H:70° L:45°`` group within the widget's inner
    width instead."""
    width = RESOLUTION[0]
    widget_left, widget_right = _widget_bounds(width)
    weather_top = _weather_top()
    pad = day_view._WIDGET_PAD

    hl_label_font = vendored_font(bold=True, size=day_view._FONT_HL_LABEL)
    hl_value_font = vendored_font(bold=True, size=day_view._FONT_HL_VALUE)
    high_f, low_f = 70.0, 45.0
    hl_widths = [
        text_size(prefix, font=hl_label_font)[0] + 3 + text_size(f"{round(temp)}°", font=hl_value_font)[0]
        for prefix, temp in (("H:", high_f), ("L:", low_f))
    ]
    hl_total_w = sum(hl_widths) + 14  # matches _draw_weather_widget's hl_segment_gap
    available_w = (widget_right - pad) - (widget_left + pad)
    expected_hx = widget_left + pad + max((available_w - hl_total_w) // 2, 0)
    old_left_aligned_x = widget_left + pad
    assert expected_hx > old_left_aligned_x + 5, (
        "fixture doesn't leave enough slack to distinguish centered from "
        "left-aligned -- pick H/L values with a narrower rendered width"
    )

    hl_top = weather_top + pad
    row_y_lo, row_y_hi = hl_top, hl_top + line_height(hl_value_font)

    reading = WeatherReading(temp_f=60.0, condition="cloudy", high_f=high_f, low_f=low_f, forecast=[])
    snapshot = WeatherSnapshot(weather=reading, sunrise=_WHEN, sunset=_WHEN, moon_phase="Full Moon")
    image = day_view.render([], _WHEN.date(), RESOLUTION, weather=snapshot)

    actual_x = _first_ink_x(image, row_y_lo, row_y_hi, widget_left + 3, widget_right - 3)
    assert actual_x is not None, "no ink found in the H/L row"
    assert abs(actual_x - expected_hx) <= 2, (
        f"H/L row starts at x={actual_x}, expected the centered position "
        f"x={expected_hx} (old left-aligned position was x={old_left_aligned_x})"
    )


def test_forecast_label_stays_fixed_while_icon_temp_group_centers_independently_per_row():
    """#219: the period label stays anchored at ``forecast_x0`` for every
    row, but each row's icon+temp group centers itself within the widget
    independently -- so two rows with very different temp digit counts
    (``9°`` vs ``100°``) must show the same label x-start but different
    icon x-starts."""
    width = RESOLUTION[0]
    widget_left, widget_right = _widget_bounds(width)
    weather_top = _weather_top()
    pad = day_view._WIDGET_PAD

    hl_value_font = vendored_font(bold=True, size=day_view._FONT_HL_VALUE)
    hl_bottom = weather_top + pad + line_height(hl_value_font)
    label_font = vendored_font(bold=True, size=day_view._FONT_FORECAST_LABEL)
    temp_font = vendored_font(bold=True, size=day_view._FONT_FORECAST_TEMP)
    label_line_h = line_height(label_font)
    size = day_view._FORECAST_ICON_SIZE
    row_h = label_line_h + 2 + size
    available_w = (widget_right - pad) - (widget_left + pad)
    forecast_x0 = widget_left + pad + day_view._FORECAST_OFFSET_X

    forecast = [
        ForecastPoint(label="Morning", temp_f=9.0, condition="sunny"),
        ForecastPoint(label="Afternoon", temp_f=100.0, condition="sunny"),
    ]
    n = len(forecast)
    weather_bottom = RESOLUTION[1] - MARGIN
    available = (weather_bottom - pad) - hl_bottom
    slack = max(available - row_h * n, 0)
    gap = slack / (n + 1)

    row_y = hl_bottom + gap
    predicted_icon_x = []
    row_bounds = []
    for point in forecast:
        icon_y = round(row_y) + label_line_h + 2
        icon_temp_w = size + pad + text_size(f"{round(point.temp_f)}°", font=temp_font)[0]
        icon_x = widget_left + pad + max((available_w - icon_temp_w) // 2, 0)
        predicted_icon_x.append(icon_x)
        row_bounds.append((round(row_y), icon_y))
        row_y += row_h + gap

    assert predicted_icon_x[0] != predicted_icon_x[1], (
        "fixture doesn't actually distinguish per-row centering -- the two "
        "temp strings produced the same predicted icon x"
    )

    reading = WeatherReading(temp_f=60.0, condition="cloudy", high_f=70.0, low_f=50.0, forecast=forecast)
    snapshot = WeatherSnapshot(weather=reading, sunrise=_WHEN, sunset=_WHEN, moon_phase="Full Moon")
    image = day_view.render([], _WHEN.date(), RESOLUTION, weather=snapshot)

    for (label_row_y, icon_row_y), expected_icon_x in zip(row_bounds, predicted_icon_x):
        label_x = _first_ink_x(image, label_row_y, label_row_y + label_line_h, widget_left + 3, widget_right - 3)
        icon_x = _first_ink_x(image, icon_row_y, icon_row_y + size, widget_left + 3, widget_right - 3)
        assert label_x is not None and icon_x is not None, "no ink found for a forecast row"
        assert abs(label_x - forecast_x0) <= 2, (
            f"label starts at x={label_x}, expected the fixed forecast_x0={forecast_x0}"
        )
        assert abs(icon_x - expected_icon_x) <= 2, (
            f"icon starts at x={icon_x}, expected the centered position x={expected_icon_x}"
        )


def test_moon_icon_is_offset_right_of_the_padding_only_position():
    """#219 added ``_MOON_ICON_OFFSET_X`` so the moon icon no longer sits
    flush at ``x0 + _WIDGET_PAD`` -- confirm there's no ink in the gap
    between the old padding-only position and the new offset one."""
    width = RESOLUTION[0]
    widget_left, _widget_right = _widget_bounds(width)
    moon_top = MARGIN + day_view._WIDGET_DAWN_DUSK_H + day_view._WIDGET_V_GAP

    pad = day_view._WIDGET_PAD
    padding_only_x0 = widget_left + pad
    icon_x0 = widget_left + pad + day_view._MOON_ICON_OFFSET_X
    assert icon_x0 > padding_only_x0, (
        "fixture doesn't exercise a real offset -- _MOON_ICON_OFFSET_X is 0"
    )
    icon_y0 = moon_top + (day_view._WIDGET_MOON_H - day_view._ICON_SIZE) // 2
    mid_y = icon_y0 + day_view._ICON_SIZE // 2

    snapshot = WeatherSnapshot(weather=None, sunrise=_WHEN, sunset=_WHEN, moon_phase="Full Moon")
    image = day_view.render([], _WHEN.date(), RESOLUTION, weather=snapshot)
    px = image.load()

    before_offset = [x for x in range(padding_only_x0, icon_x0) if px[x, mid_y] == (0, 0, 0)]
    assert not before_offset, (
        f"found ink at {before_offset} between the old padding-only position "
        f"({padding_only_x0}) and the new offset one ({icon_x0}) -- icon "
        "doesn't look shifted right"
    )
    at_and_after = [x for x in range(icon_x0, icon_x0 + day_view._ICON_SIZE) if px[x, mid_y] == (0, 0, 0)]
    assert at_and_after, "no moon icon ink found at its offset midline row"
