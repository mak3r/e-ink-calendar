"""``display.output_path`` resolution rules (#105 / #108).

v0.3 anchored a relative ``output_path`` (and the default) to the **config
file's** directory; on the Pi that put ``last_render.png`` inside the secrets
dir ``deploy.sh`` wipes. #107 re-anchors it to the **working directory** so the
default agrees with ``pull_preview.sh`` / the systemd unit / the runbook
(``~/app/data/last_render.png`` under systemd, ``<repo>/data/last_render.png``
in the dev loop). These tests pin that contract:

* relative values (and the default) resolve against ``os.getcwd()``;
* absolute values are used verbatim, independent of cwd;
* ``..`` is collapsed textually (``normpath``), symlinks are never dereferenced;
* the obsolete ``mock_output_path`` key is ignored *with a warning*.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from eink_calendar.config import load_config

_CONFIG = """\
display:
  driver: mock
  resolution: [800, 480]
{extra}
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


def _write_config(directory: Path, *, extra: str = "") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "config.yaml"
    path.write_text(_CONFIG.format(extra=extra), encoding="utf-8")
    return path


def _line(**keys: str) -> str:
    return "\n".join(f"  {k}: \"{v}\"" for k, v in keys.items())


def _resolved(cfg: Path) -> Path:
    return load_config(cfg).display.output_path


# -- relative / default: anchored to the working directory -------------------


def test_relative_output_path_is_anchored_to_the_cwd(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path / "etc", extra=_line(output_path="data/last_render.png"))
    workdir = tmp_path / "app"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    resolved = _resolved(cfg)

    assert resolved == workdir / "data" / "last_render.png"
    assert resolved.is_absolute()
    # ...and NOT beside the config file (the pre-0.3 behaviour)
    assert resolved != cfg.parent / "data" / "last_render.png"


def test_default_output_path_is_under_the_cwd(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path / "etc")  # no output_path key at all
    workdir = tmp_path / "app"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    assert _resolved(cfg) == workdir / "data" / "last_render.png"


def test_relative_output_path_follows_the_cwd(tmp_path, monkeypatch):
    cfg = _write_config(tmp_path / "etc", extra=_line(output_path="data/last_render.png"))
    (tmp_path / "run_a").mkdir()
    (tmp_path / "run_b").mkdir()

    monkeypatch.chdir(tmp_path / "run_a")
    from_a = _resolved(cfg)
    monkeypatch.chdir(tmp_path / "run_b")
    from_b = _resolved(cfg)

    assert from_a == tmp_path / "run_a" / "data" / "last_render.png"
    assert from_b == tmp_path / "run_b" / "data" / "last_render.png"
    assert from_a != from_b


def test_deploy_upgrade_layout_resolves_under_the_app_dir(tmp_path, monkeypatch, caplog):
    """Real upgrade shape: config in ``~/.config/eink-calendar`` carrying the
    obsolete ``mock_output_path`` and no ``output_path``; the service runs with
    cwd = ``~/app``. The archive must land in ``~/app/data``."""
    cfg = _write_config(
        tmp_path / ".config" / "eink-calendar",
        extra=_line(mock_output_path="./data/preview.png"),
    )
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    monkeypatch.chdir(app_dir)

    with caplog.at_level(logging.WARNING, logger="eink_calendar"):
        resolved = _resolved(cfg)

    assert resolved == app_dir / "data" / "last_render.png"
    assert "mock_output_path" in caplog.text


# -- absolute: verbatim, cwd-independent ------------------------------------


def test_absolute_output_path_is_used_verbatim(tmp_path):
    target = tmp_path / "var" / "spool" / "frame.png"
    cfg = _write_config(tmp_path / "etc", extra=_line(output_path=str(target)))
    assert _resolved(cfg) == target


def test_absolute_output_path_is_independent_of_cwd(tmp_path, monkeypatch):
    target = tmp_path / "srv" / "frame.png"
    cfg = _write_config(tmp_path / "etc", extra=_line(output_path=str(target)))
    (tmp_path / "cwd_a").mkdir()
    (tmp_path / "cwd_b").mkdir()

    monkeypatch.chdir(tmp_path / "cwd_a")
    from_a = _resolved(cfg)
    monkeypatch.chdir(tmp_path / "cwd_b")
    from_b = _resolved(cfg)

    assert from_a == from_b == target


def test_tilde_in_output_path_is_expanded(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    cfg = _write_config(tmp_path / "etc", extra=_line(output_path="~/frame.png"))
    assert _resolved(cfg) == home / "frame.png"


# -- normpath, not resolve: collapse '..' without following symlinks --------


def test_dotdot_in_absolute_output_path_is_collapsed_textually(tmp_path):
    real = tmp_path / "releases" / "0.3.0"
    real.mkdir(parents=True)
    link = tmp_path / "app"
    link.symlink_to(real, target_is_directory=True)

    cfg = _write_config(
        tmp_path / "etc",
        extra=_line(output_path=str(link / ".." / "shared" / "last_render.png")),
    )
    # `<tmp>/app/../shared/...` collapses to `<tmp>/shared/...` — the `app`
    # symlink is NOT resolved to `releases/0.3.0` first.
    assert _resolved(cfg) == tmp_path / "shared" / "last_render.png"


def test_symlinked_component_in_output_path_is_not_dereferenced(tmp_path):
    real = tmp_path / "releases" / "0.3.0"
    (real / "data").mkdir(parents=True)
    link = tmp_path / "app"
    link.symlink_to(real, target_is_directory=True)

    cfg = _write_config(
        tmp_path / "etc",
        extra=_line(output_path=str(link / "data" / "last_render.png")),
    )
    resolved = _resolved(cfg)

    # the `app` symlink stays in the path (stable across deploys)...
    assert resolved == link / "data" / "last_render.png"
    assert str(resolved).startswith(str(link) + os.sep)
    # ...though a write through it still lands in the real release dir
    resolved.write_bytes(b"frame")
    assert (real / "data" / "last_render.png").read_bytes() == b"frame"


# -- obsolete key -----------------------------------------------------------


def test_legacy_mock_output_path_key_is_ignored_with_a_warning(tmp_path, monkeypatch, caplog):
    cfg = _write_config(
        tmp_path / "etc", extra=_line(mock_output_path="./data/preview.png")
    )
    workdir = tmp_path / "app"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    with caplog.at_level(logging.WARNING, logger="eink_calendar"):
        resolved = _resolved(cfg)

    assert resolved == workdir / "data" / "last_render.png"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("mock_output_path" in r.getMessage() for r in warnings)
    assert any("output_path" in r.getMessage() for r in warnings)  # migration hint


def test_mock_output_path_alongside_output_path_does_not_warn(tmp_path, monkeypatch, caplog):
    target = tmp_path / "explicit" / "frame.png"
    cfg = _write_config(
        tmp_path / "etc",
        extra=_line(mock_output_path="./old.png", output_path=str(target)),
    )
    with caplog.at_level(logging.WARNING, logger="eink_calendar"):
        resolved = _resolved(cfg)

    assert resolved == target
    assert "mock_output_path" not in caplog.text
