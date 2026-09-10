"""``App`` rewrites the archive on every render path, and survives a bad one (#92).

Covers AC-3 (an archive write failure / refused path is logged, never raised,
never blanks the staged panel frame) and AC-4 (both the button view-cycle and
the scheduled-refresh paths rewrite ``last_render.png``).
"""

from __future__ import annotations

import logging
import os
import stat

import pytest

from eink_calendar.app import App
from eink_calendar.config import load_config
from eink_calendar.display.base import archive_image


@pytest.fixture
def app(config_file):
    return App(load_config(config_file))


def _restore_perms(path):
    try:
        os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass


# -- AC-4: every render path rewrites the archive ----------------------------


def test_view_cycle_rewrites_the_archive(app, output_path):
    app._render_current()  # startup render (day)
    day_bytes = output_path.read_bytes()

    app._on_view_cycle()  # -> week, cache-only re-render

    assert output_path.read_bytes() != day_bytes


def test_scheduled_refresh_rewrites_the_archive(app, output_path, monkeypatch):
    app._render_current()
    output_path.unlink()

    monkeypatch.setattr(app, "_fetch_all", list)
    app.refresh_and_render()  # the path the scheduler thread runs

    assert output_path.is_file()
    staged = app._display._staged
    assert staged is not None


# -- AC-3: a failing archive is loud but harmless ---------------------------


def test_archive_write_failure_is_logged_and_not_raised(tmp_path, caplog):
    read_only = tmp_path / "ro"
    read_only.mkdir()
    os.chmod(read_only, stat.S_IREAD | stat.S_IEXEC)
    try:
        with caplog.at_level(logging.WARNING, logger="eink_calendar"):
            archive_image(_tiny(), read_only / "last_render.png", data_dir=read_only)
        assert "could not archive render" in caplog.text
    finally:
        _restore_perms(read_only)


def test_symlinked_archive_target_is_refused(tmp_path, caplog):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    outside = tmp_path / "outside.png"
    link = data_dir / "last_render.png"
    link.symlink_to(outside)

    with caplog.at_level(logging.WARNING, logger="eink_calendar"):
        archive_image(_tiny(), link, data_dir=data_dir)

    assert "resolves outside the data dir" in caplog.text or "refusing to archive" in caplog.text
    assert not outside.exists()


def test_view_cycle_survives_an_unwritable_archive(app, output_path, caplog):
    app._render_current()  # creates the data dir + first archive
    os.chmod(output_path.parent, stat.S_IREAD | stat.S_IEXEC)
    try:
        with caplog.at_level(logging.WARNING, logger="eink_calendar"):
            app._on_view_cycle()  # must not raise out of the button callback
        assert "could not archive render" in caplog.text
        # the panel frame was still updated even though the archive failed
        assert app._display._staged is not None
    finally:
        _restore_perms(output_path.parent)


def _tiny():
    from PIL import Image

    return Image.new("RGB", (4, 4), (0, 0, 0))
