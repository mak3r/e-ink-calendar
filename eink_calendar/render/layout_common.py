"""Shared drawing helpers: fonts, text wrapping, palette-safe text blitting.

Text is drawn through :func:`draw_text` / :func:`text_size`, which render with
Pillow's built-in bitmap font (no anti-aliasing) into a 1-bit mask and paste a
solid palette color through it. That keeps every pixel in the composite exactly
one of the six :data:`~eink_calendar.render.palette.PALETTE` colors — no grey
anti-alias fringes for the ``inky`` quantizer to guess at — while still allowing
integer-scaled headings.
"""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

_Font = ImageFont.ImageFont | ImageFont.FreeTypeFont

from eink_calendar.render.palette import color

__all__ = [
    "MARGIN",
    "base_font",
    "draw_text",
    "text_size",
    "wrap_text",
]

MARGIN = 16


@lru_cache(maxsize=1)
def base_font() -> _Font:
    """Pillow's built-in ~10px bitmap font (deterministic, no anti-aliasing)."""
    return ImageFont.load_default()


def _measure(text: str) -> tuple[int, int]:
    font = base_font()
    bbox = font.getbbox(text)
    return int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])


def text_size(text: str, *, scale: int = 1) -> tuple[int, int]:
    """Pixel ``(width, height)`` of ``text`` at the given integer scale."""
    w, h = _measure(text)
    return w * scale, h * scale


def draw_text(
    image: Image.Image,
    xy: tuple[int, int],
    text: str,
    *,
    fill: str = "black",
    scale: int = 1,
) -> None:
    """Blit ``text`` onto ``image`` at ``xy`` in palette color ``fill``.

    ``scale`` is an integer magnification applied with nearest-neighbour
    resampling so headings stay crisp and palette-pure.
    """
    if not text:
        return
    w, h = _measure(text)
    w, h = max(w, 1), max(h, 1)

    mask = Image.new("1", (w, h), 0)
    ImageDraw.Draw(mask).text((0, 0), text, font=base_font(), fill=1)
    if scale != 1:
        mask = mask.resize((w * scale, h * scale), Image.Resampling.NEAREST)

    swatch = Image.new("RGB", mask.size, color(fill))
    image.paste(swatch, xy, mask)


def wrap_text(text: str, max_width: int, *, scale: int = 1) -> list[str]:
    """Greedy word-wrap ``text`` to lines no wider than ``max_width`` pixels."""
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_size(candidate, scale=scale)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
