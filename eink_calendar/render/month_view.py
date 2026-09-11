"""Month view: a calendar grid with per-day event bars."""

from __future__ import annotations

import calendar as _calendar
from datetime import date

from PIL import Image, ImageDraw

from eink_calendar.calendar_source.models import Event
from eink_calendar.render.layout_common import MARGIN, draw_text, text_size
from eink_calendar.render.palette import ACCENT_COLORS, color

__all__ = ["render"]

_MAX_BARS = 3


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

    firstweekday = 6 if week_starts_on == "sunday" else 0
    cal = _calendar.Calendar(firstweekday=firstweekday)
    weeks = cal.monthdatescalendar(when.year, when.month)

    draw_text(image, (MARGIN, MARGIN - 4), when.strftime("%B %Y"), fill="black", scale=3)

    grid_top = MARGIN + text_size("A", scale=3)[1] + 10
    col_w = (width - 2 * MARGIN) // 7
    row_h = (height - MARGIN - grid_top) // len(weeks)
    line_h = text_size("Ag")[1]

    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            x0 = MARGIN + c * col_w
            y0 = grid_top + r * row_h
            in_month = day.month == when.month
            if day == when:
                draw.rectangle([(x0, y0), (x0 + col_w, y0 + row_h)], fill=color("yellow"))
            draw.rectangle([(x0, y0), (x0 + col_w, y0 + row_h)], outline=color("black"))
            draw_text(
                image,
                (x0 + 4, y0 + 3),
                str(day.day),
                fill="black" if in_month else "white",
            )
            if not in_month:
                continue

            day_events = sorted(
                (e for e in events if e.occurs_on(day)),
                key=lambda e: (not e.all_day, e.start),
            )
            by = y0 + 6 + line_h
            for event in day_events[:_MAX_BARS]:
                draw.rectangle(
                    [(x0 + 3, by), (x0 + col_w - 3, by + 5)],
                    fill=color(_swatch_color(event)),
                )
                by += 8
            extra = len(day_events) - _MAX_BARS
            if extra > 0 and by < y0 + row_h - line_h:
                draw_text(image, (x0 + 4, by), f"+{extra}", fill="black")

    return image
