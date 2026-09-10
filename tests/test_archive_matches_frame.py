"""The archived ``last_render.png`` byte-equals the frame sent to the display (#92).

Covers AC-1: after any render, the on-disk archive is exactly the image handed
to ``display.set_image()`` — for the mock driver, for the real inky driver
(against a fake panel), and end to end through ``App``.
"""

from __future__ import annotations

import io
import stat
import sys
import types
from datetime import datetime, timezone

import pytest
from PIL import Image

from eink_calendar.config import load_config
from eink_calendar.display.base import ARCHIVE_MODE
from eink_calendar.display.inky_driver import InkyDisplay
from eink_calendar.display.mock_driver import MockDisplay


def _frame(seed: int = 0) -> Image.Image:
    img = Image.new("RGB", (12, 8), (255, 255, 255))
    img.putpixel((seed % 12, seed % 8), (220, 40, 40))
    return img


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def test_mock_display_archives_the_exact_staged_frame(tmp_path):
    target = tmp_path / "data" / "last_render.png"
    display = MockDisplay(archive_path=target, data_dir=target.parent)

    frame = _frame(3)
    display.set_image(frame)
    display.show()

    assert target.read_bytes() == _png_bytes(frame)
    assert stat.S_IMODE(target.stat().st_mode) == ARCHIVE_MODE


@pytest.fixture
def fake_inky(monkeypatch):
    """Install a fake ``inky`` package so InkyDisplay constructs off-hardware."""
    pushed: dict[str, object] = {}

    class _FakePanel:
        def set_image(self, image):
            pushed["image"] = image.copy()

        def show(self):
            pushed["shown"] = True

    auto_mod = types.ModuleType("inky.auto")
    auto_mod.auto = lambda: _FakePanel()
    inky_mod = types.ModuleType("inky")
    inky_mod.auto = auto_mod
    monkeypatch.setitem(sys.modules, "inky", inky_mod)
    monkeypatch.setitem(sys.modules, "inky.auto", auto_mod)
    return pushed


def test_inky_archive_equals_the_frame_pushed_to_the_panel(tmp_path, fake_inky):
    target = tmp_path / "data" / "last_render.png"
    display = InkyDisplay(archive_path=target, data_dir=target.parent)

    frame = _frame(5)
    display.set_image(frame)
    display.show()

    archived = Image.open(target)
    assert list(archived.getdata()) == list(frame.convert("RGB").getdata())
    # exactly what the archive holds is what went to the panel
    assert list(fake_inky["image"].getdata()) == list(archived.getdata())
    assert fake_inky["shown"] is True


def test_app_render_archives_the_exact_frame_it_showed(tmp_path, config_file, output_path):
    from eink_calendar.app import App

    app = App(load_config(config_file))
    app._render_current()

    staged = app._display._staged  # the RGB image App handed to set_image()
    assert staged is not None
    assert output_path.read_bytes() == _png_bytes(staged)


def test_cache_backed_app_render_is_reproducible(tmp_path, config_file, cache_path, output_path):
    from eink_calendar.app import App
    from eink_calendar.calendar_source.cache import CacheContents, save_cache
    from eink_calendar.calendar_source.models import Event

    day = datetime(2026, 9, 10, tzinfo=timezone.utc)
    events = [
        Event(
            id="e1",
            summary="Planning sync",
            start=day.replace(hour=9),
            end=day.replace(hour=10),
            all_day=False,
            calendar_id="primary",
            color="red",
        )
    ]
    save_cache(cache_path, CacheContents(fetched_at=day, events=events))

    App(load_config(config_file))._render_current()
    first = output_path.read_bytes()
    App(load_config(config_file))._render_current()
    assert output_path.read_bytes() == first
