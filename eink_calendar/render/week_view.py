"""Week view: seven day columns with each day's events listed beneath."""

from __future__ import annotations

from datetime import date, timedelta

from PIL import Image, ImageDraw

from eink_calendar.calendar_source.models import Event
from eink_calendar.render.layout_common import MARGIN, base_font, draw_text, text_size
from eink_calendar.render.palette import ACCENT_COLORS, color

__all__ = ["render", "week_start"]

_HEADER_H = 40


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

    draw_text(image, (MARGIN, MARGIN - 4), f"Week of {start:%d %b %Y}", fill="black", scale=2)

    grid_top = MARGIN + text_size("A", scale=2)[1] + 8
    col_w = (width - 2 * MARGIN) // 7
    line_h = text_size("Ag")[1]

    for i, day in enumerate(days):
        x0 = MARGIN + i * col_w
        x1 = x0 + col_w
        is_today = day == when
        if is_today:
            draw.rectangle([(x0, grid_top), (x1, grid_top + _HEADER_H)], fill=color("yellow"))
        draw.rectangle([(x0, grid_top), (x1, height - MARGIN)], outline=color("black"))
        draw_text(image, (x0 + 4, grid_top + 3), day.strftime("%a"), fill="black")
        draw_text(image, (x0 + 4, grid_top + 3 + line_h), day.strftime("%d"), fill="black", scale=2)

        day_events = sorted(
            (e for e in events if e.start.date() <= day <= e.end.date()),
            key=lambda e: (not e.all_day, e.start),
        )
        y = grid_top + _HEADER_H + 4
        for event in day_events:
            if y > height - MARGIN - line_h:
                break
            draw.rectangle([(x0 + 4, y + 2), (x0 + 10, y + 8)], fill=color(_swatch_color(event)))
            label = ("• " if event.all_day else f"{event.start:%H:%M} ") + event.summary
            clipped = _clip(label, col_w - 16)
            draw_text(image, (x0 + 14, y), clipped, fill="black")
            y += line_h + 2

    return image


def _clip(text: str, max_width: int) -> str:
    font = base_font()
    if font.getbbox(text)[2] <= max_width:
        return text
    while text and font.getbbox(text + "…")[2] > max_width:
        text = text[:-1]
    return text + "…" if text else ""
