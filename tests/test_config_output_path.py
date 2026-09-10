"""``display.output_path`` resolution rules (#91 / #92).

The stale-archive bug was a CWD-relative archive path resolved against the
symlinked systemd ``WorkingDirectory``. These tests pin the fix: the resolved
path depends only on the config file's location, never on ``os.getcwd()``, and a
symlinked config dir is kept in the path verbatim (not dereferenced) so it stays
stable across deploys.
"""

from __future__ import annotations

import os
from pathlib import Path

from eink_calendar.config import load_config

_CONFIG = """\
display:
  driver: mock
  resolution: [800, 480]
{output_line}
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
    credentials_file: "/nonexistent/creds.json"
    token_file: "/nonexistent/token.json"
    calendars:
      - {{id: primary, label: Example, color: red}}
cache:
  path: "cache.json"
"""


def _write_config(directory: Path, *, output: str | None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    line = f'  output_path: "{output}"' if output is not None else ""
    path = directory / "config.yaml"
    path.write_text(_CONFIG.format(output_line=line), encoding="utf-8")
    return path


def test_relative_output_path_is_anchored_to_the_config_dir(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "etc" / "eink-calendar"
    cfg = _write_config(cfg_dir, output="data/last_render.png")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    resolved = load_config(cfg).display.output_path

    assert resolved == cfg_dir / "data" / "last_render.png"
    assert resolved.is_absolute()


def test_default_output_path_sits_beside_the_config(tmp_path):
    cfg = _write_config(tmp_path / "cfg", output=None)
    assert load_config(cfg).display.output_path == (
        tmp_path / "cfg" / "data" / "last_render.png"
    )


def test_absolute_output_path_is_used_verbatim(tmp_path):
    target = tmp_path / "var" / "spool" / "frame.png"
    cfg = _write_config(tmp_path / "cfg", output=str(target))
    assert load_config(cfg).display.output_path == target


def test_resolution_is_independent_of_cwd(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path / "cfg", output="data/last_render.png")
    (tmp_path / "cwd_a").mkdir()
    (tmp_path / "cwd_b").mkdir()

    monkeypatch.chdir(tmp_path / "cwd_a")
    from_a = load_config(cfg).display.output_path
    monkeypatch.chdir(tmp_path / "cwd_b")
    from_b = load_config(cfg).display.output_path

    assert from_a == from_b == tmp_path / "cfg" / "data" / "last_render.png"


def test_symlinked_config_dir_is_kept_in_the_path_not_dereferenced(tmp_path):
    real = tmp_path / "releases" / "0.2.0"
    _write_config(real, output="data/last_render.png")
    link = tmp_path / "app"
    link.symlink_to(real, target_is_directory=True)

    resolved = load_config(link / "config.yaml").display.output_path

    # The release symlink stays in the path (normpath, not resolve) so the
    # archived location is stable when `app` is repointed at a new release.
    assert resolved == link / "data" / "last_render.png"
    assert str(resolved).startswith(str(link) + os.sep)
    # ...and a write through it still lands in the real directory.
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_bytes(b"frame")
    assert (real / "data" / "last_render.png").read_bytes() == b"frame"


def test_dotdot_in_output_path_is_collapsed_without_resolving_symlinks(tmp_path):
    real = tmp_path / "releases" / "0.2.0"
    _write_config(real, output="../shared/last_render.png")
    link = tmp_path / "app"
    link.symlink_to(real, target_is_directory=True)

    resolved = load_config(link / "config.yaml").display.output_path
    # `link/..` is collapsed textually to `tmp_path` — the `app` symlink is NOT
    # resolved to `releases/0.2.0` first (that is the whole point of normpath).
    assert resolved == tmp_path / "shared" / "last_render.png"


def test_tilde_in_output_path_is_expanded(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    cfg = _write_config(tmp_path / "cfg", output="~/frame.png")
    assert load_config(cfg).display.output_path == home / "frame.png"


def test_legacy_mock_output_path_key_is_ignored(tmp_path):
    cfg_dir = tmp_path / "cfg"
    _write_config(cfg_dir, output=None)
    # inject the dead pre-0.3 key alongside the (absent) real one
    text = (cfg_dir / "config.yaml").read_text().replace(
        "  resolution: [800, 480]",
        '  mock_output_path: "./data/preview.png"\n  resolution: [800, 480]',
    )
    (cfg_dir / "config.yaml").write_text(text, encoding="utf-8")

    assert load_config(cfg_dir / "config.yaml").display.output_path == (
        cfg_dir / "data" / "last_render.png"
    )
