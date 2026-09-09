"""Main loop: scheduler + buttons + display, wired against the driver ABCs.

The same code runs on the Pi (real Inky panel + GPIO buttons) and on a Mac
(mock display + stdin buttons) — the only difference is which concrete drivers
``config.display.driver`` selects. Nothing here imports a concrete driver class.

Behavior (design §5):

* A scheduler thread sleeps until the next ``refresh.daily_time`` in the
  configured timezone, then fetches + re-renders.
* Button A cycles Day/Week/Month and re-renders **from cache only** — never a
  network call. Button B forces a fetch + re-render. C/D are no-ops.
* A failed fetch is logged and swallowed: the last good render stays on screen
  and the cache is left untouched.
* Startup renders immediately from ``cache.json`` if it exists — no fetch is
  required to show something.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from eink_calendar.buttons.factory import create_buttons
from eink_calendar.calendar_source.auth import load_credentials
from eink_calendar.calendar_source.cache import CacheContents, load_cache, save_cache
from eink_calendar.calendar_source.fetch import build_service, fetch_calendar_events
from eink_calendar.calendar_source.models import Event
from eink_calendar.config import AppConfig, load_config
from eink_calendar.display.factory import create_display
from eink_calendar.render.renderer import render
from eink_calendar.view_state import ViewMode, cycle

__all__ = ["App", "main"]

log = logging.getLogger("eink_calendar")

_ARCHIVE_PATH = "data/last_render.png"


class App:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._tz = ZoneInfo(config.refresh.timezone)
        self._view = ViewMode.from_name(config.view.default)
        self._cache = load_cache(config.cache.path)

        self._display = create_display(
            config.display.driver,
            archive_path=_ARCHIVE_PATH,
            auto_open=config.display.mock_auto_open,
        )
        self._buttons = create_buttons(
            config.display.driver,
            pin_map=config.buttons.pin_map,
            bindings=config.buttons.bindings,
        )

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._scheduler: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------

    def run_forever(self) -> None:
        """Wire everything up and block until interrupted."""
        self._buttons.on_view_cycle(self._on_view_cycle)
        self._buttons.on_refresh(self._on_refresh)
        self._buttons.start()

        self._render_current()  # show cached state immediately, no fetch

        self._scheduler = threading.Thread(
            target=self._scheduler_loop, name="refresh-scheduler", daemon=True
        )
        self._scheduler.start()

        try:
            while not self._stop.wait(timeout=1.0):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self._stop.set()
            self._buttons.stop()

    def stop(self) -> None:
        self._stop.set()

    # -- button handlers -------------------------------------------------

    def _on_view_cycle(self) -> None:
        with self._lock:
            self._view = cycle(self._view)
        log.info("view cycled to %s", self._view.value)
        self._render_current()  # cache only — never fetches

    def _on_refresh(self) -> None:
        log.info("manual refresh requested")
        self.refresh_and_render()

    # -- core ------------------------------------------------------------

    def refresh_and_render(self) -> None:
        """Fetch every calendar; on success replace the cache and re-render.

        On any failure the cache and the on-screen render are left as they were.
        """
        try:
            events = self._fetch_all()
        except Exception:  # a bad fetch must never blank the panel
            log.warning("refresh failed; keeping last good render", exc_info=True)
            return

        fresh = CacheContents(fetched_at=datetime.now(tz=self._tz), events=events)
        save_cache(self._config.cache.path, fresh)
        with self._lock:
            self._cache = fresh
        log.info("refreshed %d events", len(events))
        self._render_current()

    def _fetch_all(self) -> list[Event]:
        today = self._today()
        events: list[Event] = []
        for account in self._config.accounts:
            creds = load_credentials(account.token_file)
            service = build_service(creds)
            for calendar in account.calendars:
                events.extend(
                    fetch_calendar_events(
                        service, calendar.id, color=calendar.color, when=today
                    )
                )
        return events

    def _render_current(self) -> None:
        with self._lock:
            view = self._view
            events = list(self._cache.events)
        image = render(
            view,
            events,
            when=self._today(),
            resolution=self._config.display.resolution,
            week_starts_on=self._config.view.week_starts_on,
        )
        self._display.set_image(image)
        self._display.show()

    # -- scheduling ----------------------------------------------------

    def _scheduler_loop(self) -> None:
        while not self._stop.is_set():
            wait_seconds = self._seconds_until_next_refresh()
            log.info("next scheduled refresh in %.0f s", wait_seconds)
            if self._stop.wait(timeout=wait_seconds):
                return
            self.refresh_and_render()

    def _seconds_until_next_refresh(self, *, now: datetime | None = None) -> float:
        current = now or datetime.now(tz=self._tz)
        hour, minute = (int(part) for part in self._config.refresh.daily_time.split(":"))
        target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= current:
            target += timedelta(days=1)
        return (target - current).total_seconds()

    def _today(self) -> date:
        return datetime.now(tz=self._tz).date()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(argv[0] if argv else None)
    App(config).run_forever()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
