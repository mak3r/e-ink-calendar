"""YAML configuration loading and validation.

The on-disk config is a single YAML file that lives *outside* the repo checkout
in normal use (``~/.config/eink-calendar/config.yaml``); ``config/config.yaml``
is only a convenience fallback for local development. This module loads that file
into frozen dataclasses so the rest of the package never handles raw dicts past
the config-loading boundary.

All validation errors raise :class:`ConfigError` with a message that names the
offending key and value, so a misconfigured household display fails loudly at
startup instead of rendering nothing.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("eink_calendar")

__all__ = [
    "PALETTE_COLORS",
    "AccountConfig",
    "AppConfig",
    "ButtonConfig",
    "CacheConfig",
    "CalendarSpec",
    "ConfigError",
    "DisplayConfig",
    "RefreshConfig",
    "ViewConfig",
    "load_config",
]


class ConfigError(Exception):
    """Raised when the config file is missing, malformed, or fails validation."""


# The Inky Impression 7.3" Spectra 6 panel can only show these six colors.
# render/palette.py's PALETTE dict is keyed by these same names — keep in sync.
PALETTE_COLORS: frozenset[str] = frozenset(
    {"black", "white", "red", "green", "blue", "yellow"}
)

_VALID_DRIVERS: frozenset[str] = frozenset({"inky", "mock"})
_VALID_VIEWS: frozenset[str] = frozenset({"day", "week", "month"})
_VALID_WEEK_START: frozenset[str] = frozenset({"monday", "sunday"})
_VALID_BINDINGS: frozenset[str] = frozenset({"cycle_view", "force_refresh", "noop"})
_DAY_MAX_ENTRIES_RANGE: tuple[int, int] = (5, 9)
_DAY_MAX_ENTRIES_DEFAULT = 9

_DAILY_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# Search order when load_config() is called with no explicit path.
_ENV_VAR = "EINK_CALENDAR_CONFIG"
_DEFAULT_PATHS: tuple[Path, ...] = (
    Path("~/.config/eink-calendar/config.yaml"),
    Path("config/config.yaml"),
)


@dataclass(frozen=True)
class DisplayConfig:
    driver: str
    output_path: Path
    mock_auto_open: bool
    resolution: tuple[int, int]


@dataclass(frozen=True)
class RefreshConfig:
    daily_time: str
    timezone: str


@dataclass(frozen=True)
class ViewConfig:
    default: str
    week_starts_on: str
    day_max_entries: int


@dataclass(frozen=True)
class ButtonConfig:
    pin_map: dict[str, int]
    bindings: dict[str, str]


@dataclass(frozen=True)
class CalendarSpec:
    id: str
    label: str
    color: str


@dataclass(frozen=True)
class AccountConfig:
    name: str
    credentials_file: Path
    token_file: Path
    calendars: list[CalendarSpec]


@dataclass(frozen=True)
class CacheConfig:
    path: Path


@dataclass(frozen=True)
class AppConfig:
    display: DisplayConfig
    refresh: RefreshConfig
    view: ViewConfig
    buttons: ButtonConfig
    accounts: list[AccountConfig]
    cache: CacheConfig
    source_path: Path = field(default=Path("<unknown>"))


def load_config(path: str | os.PathLike[str] | None = None) -> AppConfig:
    """Load and validate the config file.

    If ``path`` is None, the ``EINK_CALENDAR_CONFIG`` environment variable is
    consulted first, then ``~/.config/eink-calendar/config.yaml``, then
    ``config/config.yaml`` (relative to the current working directory).
    """
    resolved = _resolve_path(path)
    try:
        raw_text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config file {resolved}: {exc}") from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"config file {resolved} is not valid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"config file {resolved} must contain a top-level mapping")

    return _build_app_config(data, resolved)


def _resolve_path(path: str | os.PathLike[str] | None) -> Path:
    if path is not None:
        return Path(path).expanduser()

    env_value = os.environ.get(_ENV_VAR)
    if env_value:
        return Path(env_value).expanduser()

    for candidate in _DEFAULT_PATHS:
        expanded = candidate.expanduser()
        if expanded.is_file():
            return expanded

    searched = ", ".join(str(p) for p in (_ENV_VAR, *_DEFAULT_PATHS))
    raise ConfigError(f"no config file found (looked at: {searched})")


def _build_app_config(data: dict[str, Any], source: Path) -> AppConfig:
    return AppConfig(
        display=_build_display(_section(data, "display", source)),
        refresh=_build_refresh(_section(data, "refresh", source)),
        view=_build_view(_section(data, "view", source)),
        buttons=_build_buttons(_section(data, "buttons", source)),
        accounts=_build_accounts(data.get("accounts")),
        cache=_build_cache(_section(data, "cache", source)),
        source_path=source,
    )


def _section(data: dict[str, Any], key: str, source: Path) -> dict[str, Any]:
    value = data.get(key)
    if value is None:
        raise ConfigError(f"config file {source} is missing required section '{key}'")
    if not isinstance(value, dict):
        raise ConfigError(f"config section '{key}' must be a mapping")
    return value


def _require(section: dict[str, Any], key: str, section_name: str) -> Any:
    if key not in section or section[key] is None:
        raise ConfigError(f"'{section_name}.{key}' is required")
    return section[key]


def _build_display(section: dict[str, Any]) -> DisplayConfig:
    driver = _require(section, "driver", "display")
    if driver not in _VALID_DRIVERS:
        raise ConfigError(
            f"display.driver must be one of {sorted(_VALID_DRIVERS)}, got {driver!r}"
        )

    resolution_raw = _require(section, "resolution", "display")
    if (
        not isinstance(resolution_raw, (list, tuple))
        or len(resolution_raw) != 2
        or not all(isinstance(n, int) and n > 0 for n in resolution_raw)
    ):
        raise ConfigError(
            f"display.resolution must be two positive integers, got {resolution_raw!r}"
        )

    return DisplayConfig(
        driver=driver,
        output_path=_resolve_output_path(section),
        mock_auto_open=bool(section.get("mock_auto_open", False)),
        resolution=(int(resolution_raw[0]), int(resolution_raw[1])),
    )


def _resolve_output_path(section: dict[str, Any]) -> Path:
    """Absolute path where both drivers archive the last composited frame.

    ``display.output_path`` may be absolute (used as-is) or relative, in which
    case it is anchored to the **working directory**. That is what makes the
    default (``data/last_render.png``) land in the right place everywhere:
    under systemd ``WorkingDirectory`` is the ``~/app`` checkout, so it becomes
    ``~/app/data/last_render.png`` — the path ``scripts/pull_preview.sh``, the
    systemd unit's ``ReadWritePaths`` and ``docs/runbook.md`` all already
    assume — and in the Mac dev loop, run from the repo root, it is
    ``<repo>/data/last_render.png``.

    The pre-0.3 ``mock_output_path`` key is obsolete; if it is present without
    ``output_path`` we warn with a migration hint rather than silently ignoring
    it (issue #105).
    """
    raw = section.get("output_path")
    if raw is None and section.get("mock_output_path") is not None:
        log.warning(
            "config: 'display.mock_output_path' is obsolete (removed in v0.3) — "
            "rename it to 'display.output_path'. Ignoring it; archiving to the "
            "default 'data/last_render.png' instead."
        )

    candidate = Path(str(raw) if raw else "data/last_render.png").expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    # normpath (not resolve): collapse '..' without dereferencing the ~/app
    # release symlink, so the archived path stays stable across deploys.
    return Path(os.path.normpath(candidate))


def _build_refresh(section: dict[str, Any]) -> RefreshConfig:
    daily_time = _require(section, "daily_time", "refresh")
    if not isinstance(daily_time, str) or not _DAILY_TIME_RE.match(daily_time):
        raise ConfigError(
            f"refresh.daily_time must be a 24-hour HH:MM string, got {daily_time!r}"
        )
    timezone = _require(section, "timezone", "refresh")
    if not isinstance(timezone, str) or not timezone.strip():
        raise ConfigError("refresh.timezone must be a non-empty string")
    return RefreshConfig(daily_time=daily_time, timezone=timezone)


def _build_view(section: dict[str, Any]) -> ViewConfig:
    default = _require(section, "default", "view")
    if default not in _VALID_VIEWS:
        raise ConfigError(
            f"view.default must be one of {sorted(_VALID_VIEWS)}, got {default!r}"
        )
    week_starts_on = section.get("week_starts_on", "monday")
    if week_starts_on not in _VALID_WEEK_START:
        raise ConfigError(
            f"view.week_starts_on must be one of {sorted(_VALID_WEEK_START)}, "
            f"got {week_starts_on!r}"
        )

    day_max_entries = section.get("day_max_entries", _DAY_MAX_ENTRIES_DEFAULT)
    lo, hi = _DAY_MAX_ENTRIES_RANGE
    if (
        not isinstance(day_max_entries, int)
        or isinstance(day_max_entries, bool)
        or not (lo <= day_max_entries <= hi)
    ):
        raise ConfigError(
            f"view.day_max_entries must be an integer between {lo} and {hi}, "
            f"got {day_max_entries!r}"
        )

    return ViewConfig(
        default=default, week_starts_on=week_starts_on, day_max_entries=day_max_entries
    )


def _build_buttons(section: dict[str, Any]) -> ButtonConfig:
    pin_map_raw = _require(section, "pin_map", "buttons")
    if not isinstance(pin_map_raw, dict) or not all(
        isinstance(k, str) and isinstance(v, int) for k, v in pin_map_raw.items()
    ):
        raise ConfigError("buttons.pin_map must map button labels to integer GPIO pins")

    bindings_raw = _require(section, "bindings", "buttons")
    if not isinstance(bindings_raw, dict):
        raise ConfigError("buttons.bindings must be a mapping of button labels to actions")
    for label, action in bindings_raw.items():
        if action not in _VALID_BINDINGS:
            raise ConfigError(
                f"buttons.bindings[{label!r}] must be one of {sorted(_VALID_BINDINGS)}, "
                f"got {action!r}"
            )

    return ButtonConfig(
        pin_map={str(k): int(v) for k, v in pin_map_raw.items()},
        bindings={str(k): str(v) for k, v in bindings_raw.items()},
    )


def _build_accounts(accounts_raw: Any) -> list[AccountConfig]:
    if not isinstance(accounts_raw, list) or not accounts_raw:
        raise ConfigError(
            "'accounts' must be a non-empty list (a single account is still a "
            "one-element list, so adding a second Google account stays a config change)"
        )

    accounts: list[AccountConfig] = []
    for index, entry in enumerate(accounts_raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"accounts[{index}] must be a mapping")
        name = _require(entry, "name", f"accounts[{index}]")
        credentials_file = _require(entry, "credentials_file", f"accounts[{index}]")
        token_file = _require(entry, "token_file", f"accounts[{index}]")
        calendars = _build_calendars(entry.get("calendars"), index)
        accounts.append(
            AccountConfig(
                name=str(name),
                credentials_file=Path(str(credentials_file)).expanduser(),
                token_file=Path(str(token_file)).expanduser(),
                calendars=calendars,
            )
        )
    return accounts


def _build_calendars(calendars_raw: Any, account_index: int) -> list[CalendarSpec]:
    if not isinstance(calendars_raw, list) or not calendars_raw:
        raise ConfigError(
            f"accounts[{account_index}].calendars must be a non-empty list"
        )

    calendars: list[CalendarSpec] = []
    for cal_index, entry in enumerate(calendars_raw):
        where = f"accounts[{account_index}].calendars[{cal_index}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where} must be a mapping")
        color = _require(entry, "color", where)
        if color not in PALETTE_COLORS:
            raise ConfigError(
                f"{where}.color must be one of {sorted(PALETTE_COLORS)} "
                f"(the six panel colors), got {color!r}"
            )
        calendars.append(
            CalendarSpec(
                id=str(_require(entry, "id", where)),
                label=str(_require(entry, "label", where)),
                color=color,
            )
        )
    return calendars


def _build_cache(section: dict[str, Any]) -> CacheConfig:
    path = _require(section, "path", "cache")
    return CacheConfig(path=Path(str(path)).expanduser())
