#!/usr/bin/env python3
"""Fast Mac dev loop: fetch-or-cache → render → mock display. No Pi involved.

This is the recommended iteration loop for layout / color / font work:

    python scripts/render_once.py --use-cache --open

``--use-cache`` renders whatever is already in ``cache.json`` with no network
call at all; without it, one fetch per calendar refreshes the cache first. The
result always goes through the *mock* display driver, writing
``data/last_render.png`` (and optionally opening it).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eink_calendar.calendar_source.auth import load_credentials
from eink_calendar.calendar_source.cache import CacheContents, load_cache, save_cache
from eink_calendar.calendar_source.fetch import build_service, fetch_calendar_events
from eink_calendar.calendar_source.models import Event
from eink_calendar.config import AppConfig, ConfigError, load_config
from eink_calendar.display.factory import create_display
from eink_calendar.render.renderer import render


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="path to config.yaml")
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="render cache.json as-is; make no network call",
    )
    parser.add_argument(
        "--view",
        choices=("day", "week", "month"),
        default=None,
        help="override config.view.default for this render",
    )
    parser.add_argument(
        "--open",
        dest="auto_open",
        action="store_true",
        help="open the PNG in the default viewer afterwards",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        parser.error(str(exc))

    tz = ZoneInfo(config.refresh.timezone)
    today = datetime.now(tz=tz).date()

    if args.use_cache:
        contents = load_cache(config.cache.path)
        if contents.is_empty:
            parser.error(
                f"cache at {config.cache.path} is empty — "
                "run once without --use-cache first"
            )
    else:
        contents = CacheContents(fetched_at=datetime.now(tz=tz), events=_fetch(config, today))
        save_cache(config.cache.path, contents)

    view = args.view or config.view.default
    image = render(
        view,
        contents.events,
        when=today,
        resolution=config.display.resolution,
        week_starts_on=config.view.week_starts_on,
    )

    archive_path = config.display.output_path
    display = create_display(
        "mock",
        archive_path=archive_path,
        auto_open=args.auto_open or config.display.mock_auto_open,
    )
    display.set_image(image)
    display.show()

    print(
        f"rendered {view} view ({len(contents.events)} events) -> {archive_path}"
    )
    return 0


def _fetch(config: AppConfig, today: date) -> list[Event]:
    events: list[Event] = []
    for account in config.accounts:
        creds = load_credentials(account.token_file)
        service = build_service(creds)
        for calendar in account.calendars:
            events.extend(
                fetch_calendar_events(
                    service, calendar.id, color=calendar.color, when=today
                )
            )
    return events


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
