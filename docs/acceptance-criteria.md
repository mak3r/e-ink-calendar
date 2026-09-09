# Acceptance Criteria

MVP acceptance criteria for the e-ink calendar, derived from the Confirmed
Decisions in the approved plan (`.claude/plans/i-just-received-a-dynamic-candy.md`)
and the per-module issues #2–#16.

Each criterion is written so `qa` can turn it into an E2E test under
`test/e2e/**` later. "Test" names the intended verification: an E2E scenario,
a unit-test area owned by developer/test-engineer, or a manual step on the Pi
during hardware bring-up.

## Format

```
AC-<n>: <one-line description>
  Given: <precondition>
  When:  <action>
  Then:  <expected outcome>
  Test:  <how to verify — command, test file, or manual step>
```

## Criteria

### View cycling (button A)

AC-1: Button A cycles Day → Week → Month → Day
  Given: The app is running against the mock display and buttons with a populated cache
  When:  Button A is pressed four times
  Then:  The rendered view advances Day → Week → Month → Day, returning to the start
  Test:  E2E — drive mock_buttons A repeatedly, assert the view mode in each resulting render

AC-2: View cycling never performs a network call
  Given: The app is running with a populated cache and network access blocked
  When:  Button A is pressed to move through all three views
  Then:  Every view renders from cached events with no Google Calendar API request attempted
  Test:  E2E — patch the fetch layer to fail loudly if called; cycle all views; assert it was never invoked

AC-3: Day and Week views are filtered from the cached month
  Given: A cache containing a full month of events fetched in one call per calendar
  When:  The Day and Week views render
  Then:  Each shows only the events in its date range, filtered client-side from the same cache — no additional fetch
  Test:  unit (render/*) + E2E — assert Day/Week contents are a subset of the cached month

### Force refresh (button B)

AC-4: Button B triggers a fetch-and-render
  Given: The app is running against mock display/buttons
  When:  Button B is pressed
  Then:  `refresh_and_render()` runs: events are fetched for every configured account/calendar and the current view is re-rendered
  Test:  E2E — spy on the fetch layer; press B; assert a fetch occurred and last_render.png was rewritten

AC-5: A failed refresh never blanks the display
  Given: A successful render is currently on screen and a valid cache exists
  When:  Button B is pressed and the fetch fails (network error, auth error, API error)
  Then:  The cache and the on-screen render are both left unchanged; the last good image stays displayed
  Test:  E2E — populate cache, force fetch to raise; press B; assert last_render.png byte-identical and cache.json unchanged

### Daily automatic refresh

AC-6: Auto-refresh fires once per day at the configured local time
  Given: `refresh.daily_time` and `refresh.timezone` are set in config
  When:  The scheduler reaches that wall-clock time in that timezone
  Then:  Exactly one `refresh_and_render()` runs, and the next wake is scheduled for the same time the following day
  Test:  unit (scheduler: seconds-until-next-time math, DST-aware) + E2E with a near-future daily_time and a compressed wait

AC-7: A failed automatic refresh is non-fatal
  Given: The scheduler triggers a refresh and the fetch fails
  Then:  The last good render remains on screen, the process keeps running, and the next day's refresh is still scheduled
  Test:  E2E — same as AC-5 but via the scheduler path

### Buttons C and D

AC-8: Buttons C and D are registered but inert
  Given: The app is running
  When:  Button C or D is pressed
  Then:  A registered callback runs that does nothing — no crash, no error log, no render, no fetch (C/D reserved for a future settings menu)
  Test:  unit (buttons/*) — assert C/D callbacks exist and are genuine no-ops; E2E — press C/D, assert no state change

### Unattended operation / zero end-user authentication

AC-9: The runtime never attempts interactive authentication
  Given: The app or `render_once.py` runs on the Pi or Mac
  When:  Credentials are loaded or refreshed
  Then:  No code path calls `InstalledAppFlow.run_local_server()` or otherwise tries to open a browser; only silent token refresh via google-auth is used
  Test:  static — grep the runtime package for `run_local_server` (must appear only in `scripts/setup_oauth.py`); unit — auth.py refresh path uses a mocked credential

AC-10: Expired credentials refresh silently and are re-persisted
  Given: A `token.json` with an expired access token but a valid refresh token, stored outside the repo checkout
  When:  A fetch runs
  Then:  The credential is refreshed automatically, the refreshed token is written back to the same file, and the fetch succeeds — with no human interaction
  Test:  unit (auth.py) with a mock expired credential; manual on Pi over a multi-day run

AC-11: The service starts unattended after a reboot
  Given: The systemd unit is installed and OAuth was completed once via `setup_oauth.py`
  When:  The Pi reboots
  Then:  `eink-calendar.service` starts on its own (After=network-online.target), loads the cache, and renders without any prompt
  Test:  manual on Pi — reboot, confirm the panel updates with no console interaction

### Cache behaviour

AC-12: Startup renders from cache without requiring an immediate fetch
  Given: A valid `data/cache.json` exists at startup
  When:  The app starts
  Then:  It renders the default view from the cache first; it does not block startup on a network fetch
  Test:  E2E — start with a prepared cache and network blocked; assert a render is produced

AC-13: A missing or corrupt cache degrades gracefully
  Given: `data/cache.json` is absent or contains invalid JSON
  When:  The app starts
  Then:  It starts in an empty-event state (renders an empty calendar) rather than crashing
  Test:  unit (cache.py) — missing file and malformed file both yield empty state; E2E — start with no cache, assert no crash

AC-14: The cache round-trips events and the fetch timestamp
  Given: A list of timed and all-day events plus a fetch timestamp
  When:  The cache is written and re-read
  Then:  The reloaded data equals the original (event fields and timestamp preserved)
  Test:  unit (cache.py)

### Rendering and palette

AC-15: All three views render to an image from a sample event list
  Given: A sample event list containing both timed (`start.dateTime`) and all-day (`start.date`) events
  When:  Each of Day, Week, Month is rendered
  Then:  Each produces a `PIL.Image` at the configured resolution with no exception, and both event shapes appear correctly placed
  Test:  unit (render/*) + E2E snapshot of last_render.png dimensions

AC-16: No colour outside the six-key palette appears in a render
  Given: The Spectra-6 palette (black, white, red, yellow, blue, green)
  When:  Any view is rendered
  Then:  Every pixel of the composited RGB image is one of the six palette colours; body text and gridlines are black-on-white and the four accents are used only for event colour-coding blocks
  Test:  unit (render/*) — assert the set of distinct colours in the output ⊆ PALETTE

AC-17: Rendering is deterministic
  Given: The same event list and view mode
  When:  Rendered twice
  Then:  The two output images are byte-identical
  Test:  unit (render/*) — render twice, compare bytes

AC-18: Every render is persisted to disk before hitting the panel
  Given: Either the real Inky driver or the mock driver
  When:  A view is shown
  Then:  The composited RGB image is written to `data/last_render.png` (identical format/path for both drivers) before the driver's platform-specific step runs
  Test:  unit (display/*) — both drivers write last_render.png; E2E — assert the file updates on every render

### Configuration

AC-19: The example config loads into typed config objects
  Given: `config/config.example.yaml`
  When:  `config.py` loads it
  Then:  It populates the full dataclass tree (AppConfig / DisplayConfig / RefreshConfig / ViewConfig / ButtonConfig / AccountConfig / CalendarSpec / CacheConfig) with no error
  Test:  unit (test_config.py)

AC-20: Invalid config values are rejected with a clear error
  Given: A config with (a) a calendar `color` not in the palette, (b) a malformed `refresh.daily_time`, or (c) an unknown `display.driver`
  When:  `config.py` loads it
  Then:  Loading fails with a message that names the offending field and the allowed values
  Test:  unit (test_config.py) — one case per invalid field

AC-21: Accounts are always a list
  Given: Config with two entries under `accounts`
  When:  Loaded
  Then:  Both accounts (each with its own credentials/token files and calendars) are represented; adding a second Google account is a config-only change
  Test:  unit (test_config.py)

AC-22: Secrets live outside the repo checkout
  Given: A deployed install
  When:  Config, credentials, and tokens are resolved
  Then:  They are read from `~/.config/eink-calendar/` (or another path outside the working tree); nothing under the repo is required to hold a secret, and `config.yaml`/token/credential paths are gitignored
  Test:  static — review `.gitignore` against `SECURITY.md`; manual — confirm deployed paths

### Platform portability

AC-23: The package imports with no hardware libraries installed
  Given: A machine with no `inky` and no `gpiozero`
  When:  `import eink_calendar` and its submodules run
  Then:  Import succeeds; `inky_driver` / `gpio_buttons` are only imported when config selects the real driver
  Test:  unit — import the package in the CI environment (which has no GPIO libs)

AC-24: The app runs identically against mock and real implementations
  Given: `display.driver` / button bindings selected via config
  When:  The app wires displays and buttons
  Then:  It builds against the `base.py` ABCs, so switching mock ↔ real is a config change with no code change
  Test:  E2E against mock; manual on Pi against real hardware

### Developer loop

AC-25: `render_once.py --use-cache` renders with no network call
  Given: A populated cache
  When:  `python scripts/render_once.py --use-cache` runs on a Mac
  Then:  The configured view renders through the mock driver to `data/last_render.png` at the configured resolution, with no fetch attempted
  Test:  E2E on the dev machine

## Hardware bring-up checklist (manual, on the Pi)

These cannot run in CI — verify once during Pi setup and record results in
`docs/runbook.md`:

- `inky.auto()` detects the panel; `resolution` matches `display.resolution` in config
- Actual panel refresh shows the composited image (colours acceptable after the inky library's quantization)
- Button pin map and pull-up direction match Pimoroni's current pinout docs
- Buttons A/B produce the expected actions; C/D do nothing
- A multi-day unattended run refreshes daily at `daily_time` and survives a token expiry
- `scripts/pull_preview.sh <pi-host>` retrieves `data/last_render.png` with nothing running on the Pi but `sshd`
