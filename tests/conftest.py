"""Shared fixtures for the test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

_CONFIG_TEMPLATE = """\
display:
  driver: mock
  output_path: "{output}"
  mock_auto_open: false
  resolution: [800, 480]
refresh:
  daily_time: "05:30"
  timezone: "America/New_York"
view:
  default: day
  week_starts_on: monday
buttons:
  pin_map: {{A: 5, B: 6, C: 16, D: 24}}
  bindings: {{A: cycle_view, B: force_refresh, C: noop, D: noop}}
accounts:
  - name: personal
    credentials_file: "{creds}"
    token_file: "{token}"
    calendars:
      - {{id: "primary", label: "Example", color: red}}
cache:
  path: "{cache}"
"""


@pytest.fixture
def cache_path(tmp_path: Path) -> Path:
    """Where the fixture config points its event cache (file not created here)."""
    return tmp_path / "cache.json"


@pytest.fixture
def output_path(tmp_path: Path) -> Path:
    """Absolute archive path the fixture config points ``display.output_path`` at."""
    return tmp_path / "data" / "last_render.png"


@pytest.fixture
def config_file(tmp_path: Path, cache_path: Path, output_path: Path) -> Path:
    """A valid ``config.yaml`` selecting the mock driver.

    The referenced credential/token files are never created — anything that
    actually reaches a Google fetch will fail, which is what makes the
    ``--use-cache`` path's "no network" guarantee observable in a test.
    """
    path = tmp_path / "config.yaml"
    path.write_text(
        _CONFIG_TEMPLATE.format(
            creds=tmp_path / "creds.json",
            token=tmp_path / "token.json",
            cache=cache_path,
            output=output_path,
        ),
        encoding="utf-8",
    )
    return path
