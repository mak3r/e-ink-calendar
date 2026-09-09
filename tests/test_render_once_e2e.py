"""End-to-end: ``scripts/render_once.py --use-cache`` on a populated cache.

Runs the script as its own process (the way the dev loop and AC-25 do) and
asserts it renders through the mock driver to ``data/last_render.png`` at the
configured resolution. The config's credential files do not exist, so a reached
fetch would crash — a clean exit proves no network call was made.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from eink_calendar.calendar_source.cache import CacheContents, save_cache
from eink_calendar.calendar_source.models import Event

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "render_once.py"


def _sample_events() -> list[Event]:
    day = datetime(2026, 9, 9, tzinfo=timezone.utc)
    timed = Event(
        id="evt-timed",
        summary="Timed meeting",
        start=day.replace(hour=14, minute=30),
        end=day.replace(hour=15, minute=30),
        all_day=False,
        calendar_id="primary",
        color="red",
    )
    all_day = Event(
        id="evt-allday",
        summary="All-day trip",
        start=day,
        end=day + timedelta(days=1),
        all_day=True,
        calendar_id="primary",
        color="blue",
    )
    return [timed, all_day]


def test_render_once_use_cache_writes_last_render(tmp_path, cache_path, config_file):
    save_cache(
        cache_path,
        CacheContents(fetched_at=datetime.now(timezone.utc), events=_sample_events()),
    )

    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--use-cache", "--config", str(config_file)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    rendered = tmp_path / "data" / "last_render.png"
    assert rendered.is_file()
    with Image.open(rendered) as image:
        assert image.size == (800, 480)


def test_render_once_use_cache_errors_on_empty_cache(tmp_path, config_file):
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--use-cache", "--config", str(config_file)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode != 0
    assert "cache" in result.stderr.lower()
