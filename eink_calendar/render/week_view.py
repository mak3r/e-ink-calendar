"""Week view: seven day columns with each day's events listed beneath."""

from __future__ import annotations

from datetime import date, timedelta

from PIL import Image, ImageDraw

from eink_calendar.calendar_source.models import Event
from eink_calendar.render.layout_common import (
    MARGIN,
    draw_text,
    ellipsize,
    line_height,
    text_size,
)
from eink_calendar.render.palette import ACCENT_COLORS, color

__all__ = ["render", "week_start"]

# Vertical pad above the "%a" line and below the "%d" line in a day cell.
_HEADER_PAD = 3


def week_start(when: date, week_starts_on: str) -> date:
    """The date of the first day of the week containing ``when``."""
    anchor = 6 if week_starts_on == "sunday" else 0
    delta = (when.weekday() - anchor) % 7
    return when - timedelta(days=delta)


def _swatch_color(event: Event) -> str:
    return event.color if event.color in ACCENT_COLORS else "black"


def render(
    events: list[Event],
    when: date,
    resolution: tuple[int, int],
    week_starts_on: str,
) -> Image.Image:
    width, height = resolution
    image = Image.new("RGB", resolution, color("white"))
    draw = ImageDraw.Draw(image)

    start = week_start(when, week_starts_on)
    days = [start + timedelta(days=i) for i in range(7)]

    draw_text(image, (MARGIN, MARGIN), f"Week of {start:%d %b %Y}", fill="black", scale=2)

    grid_top = MARGIN + text_size("A", scale=2)[1] + 10
    col_w = (width - 2 * MARGIN) // 7
    line_h = line_height()
    # Cell header holds the "%a" line then "%d" at scale 2, padded top and bottom.
    header_h = 2 * _HEADER_PAD + 3 * line_h

    for i, day in enumerate(days):
        x0 = MARGIN + i * col_w
        x1 = x0 + col_w
        is_today = day == when
        if is_today:
            draw.rectangle([(x0, grid_top), (x1, grid_top + header_h)], fill=color("yellow"))
        draw.rectangle([(x0, grid_top), (x1, height - MARGIN)], outline=color("black"))
        draw_text(image, (x0 + 4, grid_top + _HEADER_PAD), day.strftime("%a"), fill="black")
        draw_text(
            image,
            (x0 + 4, grid_top + _HEADER_PAD + line_h),
            day.strftime("%d"),
            fill="black",
            scale=2,
        )

        day_events = sorted(
            (e for e in events if e.occurs_on(day)),
            key=lambda e: (not e.all_day, e.start),
        )
        y = grid_top + header_h + 4
        for event in day_events:
            if y > height - MARGIN - line_h:
                break
            draw.rectangle([(x0 + 4, y + 3), (x0 + 10, y + 9)], fill=color(_swatch_color(event)))
            # The swatch already marks all-day events; timed events get a HH:MM.
            label = event.summary if event.all_day else f"{event.start:%H:%M} {event.summary}"
            draw_text(image, (x0 + 14, y), ellipsize(label, col_w - 18), fill="black")
            y += line_h + 3

    return image
