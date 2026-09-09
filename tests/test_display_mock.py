"""MockDisplay + ``create_display("mock", ...)`` — the Mac render path.

Regression coverage for #51: the mock driver module was missing, so every
non-hardware entry point crashed on import.
"""

from __future__ import annotations

import sys

import pytest
from PIL import Image

from eink_calendar.display.factory import create_display
from eink_calendar.display.mock_driver import MockDisplay


def _frame(size: tuple[int, int] = (800, 480)) -> Image.Image:
    return Image.new("RGB", size, "white")


def test_factory_returns_mock_instance(tmp_path):
    display = create_display("mock", archive_path=tmp_path / "out.png")
    assert isinstance(display, MockDisplay)


def test_factory_rejects_unknown_driver(tmp_path):
    with pytest.raises(ValueError, match="unknown display driver"):
        create_display("plasma", archive_path=tmp_path / "out.png")


def test_show_archives_staged_frame_at_configured_resolution(tmp_path):
    archive = tmp_path / "nested" / "last_render.png"
    display = create_display("mock", archive_path=archive)

    display.set_image(_frame((800, 480)))
    display.show()

    assert archive.is_file()
    with Image.open(archive) as written:
        assert written.size == (800, 480)


def test_show_without_a_staged_frame_is_a_noop(tmp_path):
    archive = tmp_path / "last_render.png"
    create_display("mock", archive_path=archive).show()
    assert not archive.exists()


def test_show_refreshes_the_same_path_each_time(tmp_path):
    archive = tmp_path / "last_render.png"
    display = create_display("mock", archive_path=archive)

    display.set_image(_frame())
    display.show()
    first = archive.read_bytes()

    display.set_image(Image.new("RGB", (800, 480), "red"))
    display.show()

    assert archive.read_bytes() != first


def test_auto_open_opens_the_archived_file(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(
        "eink_calendar.display.mock_driver._open_in_viewer", opened.append
    )
    display = create_display(
        "mock", archive_path=tmp_path / "o.png", auto_open=True
    )

    display.set_image(_frame((10, 10)))
    display.show()

    assert opened == [tmp_path / "o.png"]


def test_auto_open_disabled_never_opens_a_viewer(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(
        "eink_calendar.display.mock_driver._open_in_viewer", opened.append
    )
    display = create_display(
        "mock", archive_path=tmp_path / "o.png", auto_open=False
    )

    display.set_image(_frame((10, 10)))
    display.show()

    assert opened == []


def test_mock_path_imports_no_hardware_module(tmp_path):
    create_display("mock", archive_path=tmp_path / "o.png")
    assert "inky" not in sys.modules
