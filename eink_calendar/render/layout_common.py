"""Shared drawing helpers: fonts, text measurement, palette-safe text blitting.

Text is drawn through :func:`draw_text` and measured through :func:`text_size` /
:func:`ellipsize` / :func:`wrap_text`. Every glyph is rendered **without
anti-aliasing** into a 1-bit mask and a solid palette color is pasted through
it, so every pixel in the composite is exactly one of the six
:data:`~eink_calendar.render.palette.PALETTE` colors — no grey anti-alias
fringes for the ``inky`` quantizer to guess at — while still allowing
integer-scaled headings.

Measurement rule
----------------
``PIL.ImageFont.load_default()`` returns different backends across Pillow
versions (a fixed bitmap font <= 10.x, an anti-aliased TrueType ``FreeTypeFont``
from 11.x on), and ``FreeTypeFont.getbbox()`` reports the *anti-aliased* ink
extent, which is narrower and shorter than the same glyphs rendered in 1-bit
mode. Measuring with ``getbbox`` therefore under-sizes the mask and clips every
string. All measurement here goes through :func:`_ink_box`, which asks Pillow
for the bounding box of the pixels ``draw_text`` will *actually* set (mode
``"1"``, no anti-aliasing) — correct regardless of which font backend is active.
"""

from __future__ import annotations

from functools import cache, lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_Font = ImageFont.ImageFont | ImageFont.FreeTypeFont

from eink_calendar.render.palette import color

__all__ = [
    "MARGIN",
    "base_font",
    "draw_text",
    "ellipsize",
    "line_height",
    "text_size",
    "vendored_font",
    "wrap_text",
]

MARGIN = 16

# Sample covering ascenders, capitals and descenders — its rendered height is
# used as the height of every text line so callers can stack lines predictably.
_LINE_SAMPLE = "Agjpqy|_"

_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"


@lru_cache(maxsize=1)
def base_font() -> _Font:
    """A deterministic ~10px font, no anti-aliasing when drawn in mode ``"1"``."""
    try:
        return ImageFont.load_default(size=10)
    except TypeError:  # Pillow < 10.1: no size arg, returns the bitmap font
        return ImageFont.load_default()


@cache
def vendored_font(*, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """The bundled DejaVu Sans font (regular or bold) at ``size`` points.

    Unlike :func:`base_font`, this always loads the vendored TrueType file from
    ``render/assets/fonts/`` — never a system font — so text renders identically
    on the Pi and on a dev Mac.
    """
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(_FONTS_DIR / filename), size=size)


@lru_cache(maxsize=1)
def _measurer() -> ImageDraw.ImageDraw:
    return ImageDraw.Draw(Image.new("1", (1, 1)))


def _ink_box(text: str, font: _Font) -> tuple[int, int, int, int]:
    """``(left, top, right, bottom)`` of the pixels :func:`draw_text` sets for
    ``text`` when drawn at the origin — measured in the same non-antialiased
    mode used for the blit."""
    if not text:
        return (0, 0, 0, 0)
    left, top, right, bottom = _measurer().textbbox((0, 0), text, font=font)
    return int(left), int(top), int(right), int(bottom)


@cache
def line_height(font: _Font | None = None) -> int:
    """Rendered height of one text line at scale 1, in pixels, for ``font``
    (:func:`base_font` if omitted)."""
    return _ink_box(_LINE_SAMPLE, font or base_font())[3]


def text_size(text: str, *, scale: int = 1, font: _Font | None = None) -> tuple[int, int]:
    """Pixel ``(width, height)`` of ``text`` at the given integer scale, using
    ``font`` (:func:`base_font` if omitted).

    Height is the fixed single-line height (see :func:`line_height`) so offsets
    derived from it stack cleanly regardless of ``text``'s own glyphs.
    """
    f = font or base_font()
    width = _ink_box(text, f)[2] if text else 0
    return width * scale, line_height(f) * scale


def draw_text(
    image: Image.Image,
    xy: tuple[int, int],
    text: str,
    *,
    fill: str = "black",
    scale: int = 1,
    font: _Font | None = None,
) -> None:
    """Blit ``text`` onto ``image`` at ``xy`` in palette color ``fill``, using
    ``font`` (:func:`base_font` if omitted).

    ``scale`` is an integer magnification applied with nearest-neighbour
    resampling so headings stay crisp and palette-pure. ``xy`` is the top-left
    of the text line; the box occupies ``text_size(text, scale=scale, font=font)``.
    """
    if not text:
        return
    f = font or base_font()
    box = _ink_box(text, f)
    w = max(box[2], 1)
    h = max(line_height(f), box[3], 1)

    mask = Image.new("1", (w, h), 0)
    ImageDraw.Draw(mask).text((0, 0), text, font=f, fill=1)
    if scale != 1:
        mask = mask.resize((w * scale, h * scale), Image.Resampling.NEAREST)

    swatch = Image.new("RGB", mask.size, color(fill))
    image.paste(swatch, xy, mask)


def ellipsize(text: str, max_width: int, *, scale: int = 1, font: _Font | None = None) -> str:
    """Trim ``text`` (with a trailing ``…``) to fit ``max_width`` pixels.

    Returns ``text`` unchanged when it already fits. Shared by the views so the
    text-fitting logic lives in exactly one place.
    """
    if not text or text_size(text, scale=scale, font=font)[0] <= max_width:
        return text
    trimmed = text
    while trimmed and text_size(f"{trimmed}…", scale=scale, font=font)[0] > max_width:
        trimmed = trimmed[:-1]
    return f"{trimmed}…" if trimmed else ""


def wrap_text(text: str, max_width: int, *, scale: int = 1, font: _Font | None = None) -> list[str]:
    """Greedy word-wrap ``text`` to lines no wider than ``max_width`` pixels."""
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_size(candidate, scale=scale, font=font)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
