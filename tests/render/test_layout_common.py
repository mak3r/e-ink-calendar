"""Direct coverage of the text measure/blit helpers in ``layout_common``.

Regression guard for #60: the helpers under-measured every string (they sized
the 1-bit mask from ``FreeTypeFont.getbbox()`` anti-aliased deltas and drew at
the mask origin), so glyphs past the reported box were cropped. These tests
render real pixels and assert the ink reaches the measured width and that a
trailing character actually adds ink on the right — both fail on the pre-#60
`develop` + Pillow 12.x.
"""

from __future__ import annotations

from PIL import Image

from eink_calendar.render import layout_common
from eink_calendar.render.layout_common import draw_text, line_height, text_size


def _ink_bbox(text: str, *, scale: int = 1, pad: int = 40):
    """Draw ``text`` on a white canvas at ``(pad, pad)`` and return the bounding
    box of the black pixels, as ``(left, top, right, bottom)`` relative to the
    draw origin (or ``None`` if nothing was drawn)."""
    w, h = text_size(text, scale=scale)
    canvas = Image.new("RGB", (w + 3 * pad, h + 3 * pad), (255, 255, 255))
    draw_text(canvas, (pad, pad), text, fill="black", scale=scale)

    pixels = canvas.load()
    assert pixels is not None
    xs: list[int] = []
    ys: list[int] = []
    for y in range(canvas.height):
        for x in range(canvas.width):
            if pixels[x, y] == (0, 0, 0):
                xs.append(x - pad)
                ys.append(y - pad)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def test_multi_word_string_ink_reaches_measured_width():
    text = "Clipping regression guard"
    width, _ = text_size(text)
    bbox = _ink_bbox(text)

    assert bbox is not None
    left, _, right, _ = bbox
    # Full string drawn: ink starts at the left edge and reaches the measured
    # right edge (pre-#60 the tail glyphs were cropped, landing well short).
    assert left <= 1
    assert width - 3 <= right <= width, f"ink right={right}, measured width={width}"


def test_trailing_character_adds_ink_on_the_right():
    base = _ink_bbox("regression")
    longer = _ink_bbox("regressionX")

    assert base is not None and longer is not None
    # A fixed-width right-edge clip (the #60 symptom: "Wednesday" -> "Wednesda")
    # would swallow the extra glyph and leave the right edge unchanged.
    assert longer[2] > base[2] + 2


def test_descenders_are_not_clipped_at_the_bottom():
    # 'y', 'g', 'p', 'q' drop below the baseline; the mask must be tall enough.
    no_desc = _ink_bbox("nao")
    desc = _ink_bbox("yggpq")

    assert no_desc is not None and desc is not None
    assert desc[3] > no_desc[3], "descender ink was clipped at the mask bottom"
    assert desc[3] <= line_height()


def test_line_height_is_stable_regardless_of_glyphs():
    # text_size height must not depend on whether the string has tall/low glyphs
    # — day_view / week_view stack header lines on this value.
    assert text_size("x")[1] == text_size("Agjpqy|_")[1] == line_height()


def test_scale_multiplies_the_rendered_box():
    w1, h1 = text_size("Mon")
    w3, h3 = text_size("Mon", scale=3)
    assert (w3, h3) == (w1 * 3, h1 * 3)

    unscaled = _ink_bbox("Mon")
    scaled = _ink_bbox("Mon", scale=3)
    assert unscaled is not None and scaled is not None
    # nearest-neighbour ×3: the rendered ink box triples too (small slack for
    # the mask's own trailing blank column).
    assert scaled[2] >= unscaled[2] * 3 - 4


def test_blitted_text_is_palette_pure():
    canvas = Image.new("RGB", (200, 40), (255, 255, 255))
    draw_text(canvas, (4, 4), "palette check", fill="black")
    assert set(canvas.getdata()) <= {(255, 255, 255), (0, 0, 0)}


def test_base_font_is_cached_and_deterministic():
    layout_common.base_font.cache_clear()
    assert layout_common.base_font() is layout_common.base_font()
