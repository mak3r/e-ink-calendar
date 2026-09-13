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
from eink_calendar.weather_source.cache import (
    CachedWeather,
    load_weather_cache,
    save_weather_cache,
)
from eink_calendar.weather_source.fetch import compute_solar_lunar, fetch_weather
from eink_calendar.weather_source.models import WeatherReading, WeatherSnapshot

__all__ = ["App", "main"]

log = logging.getLogger("eink_calendar")


class App:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._tz = ZoneInfo(config.refresh.timezone)
        self._view = ViewMode.from_name(config.view.default)
        self._cache = load_cache(config.cache.path)
        self._calendar_labels = {
            calendar.color: calendar.label
            for account in config.accounts
            for calendar in account.calendars
        }

        self._weather_cache_path = config.cache.path.parent / "weather_cache.json"
        self._weather_cache = (
            load_weather_cache(self._weather_cache_path) if config.weather else CachedWeather()
        )
        self._weather_snapshot: WeatherSnapshot | None = None
        if config.weather:
            sunrise, sunset, moon_phase = compute_solar_lunar(
                self._today(), config.weather.lat, config.weather.lon, config.refresh.timezone
            )
            self._weather_snapshot = WeatherSnapshot(
                weather=self._weather_cache.reading,
                sunrise=sunrise,
                sunset=sunset,
                moon_phase=moon_phase,
            )

        self._display = create_display(
            config.display.driver,
            archive_path=config.display.output_path,
            data_dir=config.display.output_path.parent,
            auto_open=config.display.mock_auto_open,
        )
        log.info("archiving each frame to %s", config.display.output_path)
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
        """Fetch every calendar and refresh weather; on calendar-fetch
        success replace the cache and re-render.

        Weather refreshes on this same cadence as an independent,
        always-attempted step: a weather failure or a calendar failure never
        blocks or blanks the other, matching the "a failed fetch must never
        blank the panel" rule for each data source individually.
        """
        self._refresh_weather()

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

    def _refresh_weather(self) -> None:
        """Fetch a fresh weather reading; on failure fall back to the last
        cached one. Solar/lunar is recomputed fresh every call regardless —
        it's local and deterministic, so it never needs the cache and can
        never be the reason a refresh fails.
        """
        weather_config = self._config.weather
        if weather_config is None:
            return

        reading: WeatherReading | None
        try:
            reading = fetch_weather(weather_config.lat, weather_config.lon)
        except Exception:  # a bad weather fetch must never blank the widget
            log.warning("weather refresh failed; keeping last good reading", exc_info=True)
            reading = self._weather_cache.reading
        else:
            self._weather_cache = CachedWeather(
                fetched_at=datetime.now(tz=self._tz), reading=reading
            )
            save_weather_cache(self._weather_cache_path, self._weather_cache)

        sunrise, sunset, moon_phase = compute_solar_lunar(
            self._today(), weather_config.lat, weather_config.lon, self._config.refresh.timezone
        )
        with self._lock:
            self._weather_snapshot = WeatherSnapshot(
                weather=reading, sunrise=sunrise, sunset=sunset, moon_phase=moon_phase
            )

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
            weather = self._weather_snapshot
        image = render(
            view,
            events,
            when=self._today(),
            resolution=self._config.display.resolution,
            week_starts_on=self._config.view.week_starts_on,
            calendar_labels=self._calendar_labels,
            day_max_entries=self._config.view.day_max_entries,
            weather=weather,
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
