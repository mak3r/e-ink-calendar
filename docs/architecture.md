# Architecture

This document describes the system design of the e-ink calendar display for
contributors and operators. It is adapted from the approved architecture plan in
`.claude/plans/i-just-received-a-dynamic-candy.md`; where the two disagree, that
plan is authoritative until a follow-up plan supersedes it.

## Overview

A household calendar display: a Raspberry Pi drives a Pimoroni Inky Impression
7.3" (Spectra 6, six-color e-paper) panel showing Day / Week / Month views of one
or more Google Calendars. Two physical buttons cycle the view and force a
refresh; otherwise the panel repaints once per day on a schedule.

The real end users are non-technical family members. Once deployed, the device
must run unattended indefinitely with **no re-authentication** ever required from
them.

Target runtime is Python 3.11 (the system Python on Raspberry Pi OS Bookworm).
The package identifier is `eink_calendar`, run as `python -m eink_calendar.app`.

### Hard constraints

Five non-negotiable constraints shape every decision below:

1. **The package must import and run on a Mac with no GPIO hardware.**
   Hardware-only imports (`inky`, `gpiozero`) are confined to
   `eink_calendar/display/inky_driver.py` and
   `eink_calendar/buttons/gpio_buttons.py`, loaded lazily by their `factory.py`
   only when config selects the real driver. Mac-based development is the primary
   dev loop; the Pi is used only for final hardware validation.
2. **Secrets live entirely outside the repo checkout** — in
   `~/.config/eink-calendar/` (config, OAuth client secrets, tokens). No code
   path reads or writes a repo-relative secret.
3. **The runtime never runs an interactive OAuth flow.** Silent refresh only.
   Consent happens once, ahead of deployment, via `scripts/setup_oauth.py`.
4. **Six colors, from one palette.** Every color used in `render/` comes from
   `render/palette.py::PALETTE`; arbitrary hex/RGB is forbidden.
5. **A failed fetch must never blank the panel.** The last good render stays up
   and the cache is left intact.

## Components

```
eink_calendar/
  __init__.py
  app.py                    main loop: scheduler thread + buttons + display
  config.py                 YAML -> frozen dataclasses, all validation
  view_state.py             ViewMode enum + cycle(); pure state, no I/O

  calendar_source/
    models.py               Event dataclass; Calendar API + cache normalization
    auth.py                 per-account silent credential load/refresh only
    fetch.py                one events.list call per calendar, whole-month window
    cache.py                JSON cache of last-fetched events (0600 file)
    local_files.py          write_private_text() / ensure_private_dir() helpers
    __init__.py

  render/
    palette.py              PALETTE dict - the single source of truth for color
    renderer.py             dispatch (view_mode, events) -> PIL.Image
    day_view.py             day layout
    week_view.py            week layout
    month_view.py           month grid layout
    layout_common.py        shared layout/text helpers
    __init__.py

  display/
    base.py                 Display ABC: set_image(img), show()
    factory.py              create_display(driver, ...) - lazy-imports inky_driver
    inky_driver.py          REAL panel - imports `inky` (Pi only, lazy)
    mock_driver.py          writes data/last_render.png, optionally opens it
    __init__.py

  buttons/
    base.py                 Buttons ABC: on_view_cycle(cb), on_refresh(cb), start(), stop()
    factory.py              create_buttons(driver, ...) - lazy-imports gpio_buttons
    gpio_buttons.py         REAL buttons - imports `gpiozero` (Pi only, lazy)
    mock_buttons.py         stdin-driven buttons for Mac dev
    __init__.py

scripts/
  render_once.py            Mac dev loop: fetch-or-cache -> render -> mock display
  setup_oauth.py            one-time interactive OAuth consent
  deploy.sh                 release-tarball deploy + secrets sync over SSH
  pull_preview.sh           scp the Pi's last_render.png locally and open it
  setup.sh                  create the persona worktrees after clone

systemd/
  eink-calendar.service     runs the app as a dedicated --system user

config/
  config.example.yaml       template; real config.yaml is gitignored / lives in ~/.config

requirements-base.txt       runtime deps that install everywhere (Mac + Pi)
requirements-pi.txt         adds inky, gpiozero, RPi.GPIO - Pi only
requirements-dev.txt        pytest, ruff, mypy, bandit
```

### Ownership boundary

Enforced by `CLAUDE.md`: `developer` owns `eink_calendar/**` except `*_test.py`
and the two mock drivers (`display/mock_driver.py`, `buttons/mock_buttons.py`),
which `test-engineer` owns alongside `tests/**`.

### Dependency direction

`app.py` depends on `config`, `view_state`, `calendar_source.*`,
`render.renderer`, `display.factory`, `buttons.factory` — and on **no concrete
driver class**. `render/*` depends only on `calendar_source.models` and
`render.palette`. `calendar_source/*` has no dependency on `render`, `display`,
or `buttons`. `view_state` depends on nothing. This keeps the whole non-hardware
core a pure function of (config, cached events, today's date).

## Data Flow

```
                 +--------------------------- scheduler thread --------------+
                 |  sleep until next refresh.daily_time (configured tz)      |
                 v                                                           |
config.yaml -> load_config() -> AppConfig (frozen dataclasses)               |
                 |                                                           |
   +-------------+--------------+                                            |
   v                            v                                           |
button events            refresh_and_render():                               |
  A: cycle view            for account in accounts:                          |
     -> render FROM CACHE      load_credentials(token_file)  -- silent refresh|
  B: force refresh           build_service(creds)                            |
     -> refresh_and_render     for calendar in account.calendars:            |
  C/D: no-op                    fetch_calendar_events(...)  -- 1 API call/cal |
                                    |                                        |
                                    v                                        |
                          list[Event]  -->  save_cache(cache.json, 0600)     |
                                    |                                        |
                                    v                                        |
                   render(view, events, when=today, resolution, week_start)  |
                                    |                                        |
                                    v                                        |
                        PIL.Image  -->  display.set_image() ; display.show()  |
                                    |                                        |
                                    +-->  archive to data/last_render.png ----+
```

On startup `app.py` renders immediately from `cache.json` if present — no fetch
is needed to show something. On any fetch exception, `refresh_and_render()` logs
and returns; cache and screen are untouched.

## Configuration

One YAML file. In normal use it lives at
`~/.config/eink-calendar/config.yaml` (or the path in `$EINK_CALENDAR_CONFIG`);
`config/config.yaml` is a dev-only fallback and is gitignored. `config.py` loads
it into **frozen dataclasses** — no raw dicts cross the config boundary — and
every validation failure raises `ConfigError` naming the offending key/value, so
a misconfigured display fails loudly at startup instead of rendering nothing.

**Resolution order for the config path** (`load_config(path=None)`):
explicit arg -> `$EINK_CALENDAR_CONFIG` -> `~/.config/eink-calendar/config.yaml`
-> `config/config.yaml` (cwd-relative).

```yaml
display:
  driver: mock                 # "inky" | "mock"
  mock_output_path: "./data/preview.png"
  mock_auto_open: true          # open the PNG after each render (dev convenience)
  resolution: [800, 480]        # two positive ints; confirm vs inky.auto().resolution at bring-up

refresh:
  daily_time: "05:30"           # 24-hour HH:MM, validated by regex
  timezone: "America/New_York"  # any zoneinfo key; non-empty

view:
  default: day                  # "day" | "week" | "month"
  week_starts_on: monday        # "monday" | "sunday" (default monday)

buttons:
  pin_map: {A: 5, B: 6, C: 16, D: 24}          # label -> int GPIO pin; confirm vs Pimoroni pinout
  bindings: {A: cycle_view, B: force_refresh, C: noop, D: noop}
                                                # actions: cycle_view | force_refresh | noop
                                                # D reserved for a future settings menu

accounts:                       # non-empty list; a single account is a 1-element list
  - name: personal
    credentials_file: "~/.config/eink-calendar/personal_credentials.json"
    token_file: "~/.config/eink-calendar/personal_token.json"
    calendars:                  # non-empty list
      - {id: "primary", label: "Example", color: red}
      # add a 2nd `accounts:` entry to add a 2nd Google account - no code change

cache:
  path: "data/cache.json"
```

**Dataclasses** (`config.py`): `AppConfig` -> `DisplayConfig`, `RefreshConfig`,
`ViewConfig`, `ButtonConfig`, `list[AccountConfig]` (each ->
`list[CalendarSpec]`), `CacheConfig`. `AppConfig.source_path` records where the
config was loaded from.

**Validation rules that matter:**

- `display.driver` is one of {inky, mock}; `display.resolution` is exactly two
  positive ints.
- `refresh.daily_time` matches `^([01]\d|2[0-3]):[0-5]\d$`.
- `view.default` is one of {day, week, month}; `week_starts_on` is one of
  {monday, sunday}.
- `buttons.pin_map` is str->int; `buttons.bindings` values are one of
  {cycle_view, force_refresh, noop}.
- `accounts` is non-empty; each `calendars` is non-empty.
- **`calendars[].color` is one of {black, white, red, green, blue, yellow}** —
  the six panel colors. `config.PALETTE_COLORS` is kept in sync with
  `render/palette.py::PALETTE` by convention (both keyed by the same names).
- All file paths are `.expanduser()`-ed at load.

### OAuth setup flow

Google Calendar API, **read-only** scope
(`https://www.googleapis.com/auth/calendar.readonly`).

1. **One-time, by a human with a browser**, before or at deployment:
   `python -m scripts.setup_oauth --account <name>`. This is the **only** place
   `InstalledAppFlow.run_local_server()` is ever called. It reads that account's
   `credentials_file` (the OAuth *client secret* downloaded from Google Cloud)
   and `token_file` from the config, runs consent, and writes a fresh token JSON
   via `write_private_text()` (0600) to the configured `token_file` — outside the
   repo.
2. The script prints a pre-authorization checklist it cannot enforce:
   - **The OAuth consent screen must be "Production", not "Testing"** —
     testing-mode refresh tokens expire after 7 days and the family would
     re-authorize forever.
   - The account should not be enrolled in Google's Advanced Protection Program
     (it blocks the installed-app flow).
3. **Runtime** (`calendar_source/auth.py::load_credentials`): loads the token
   file; if `creds.valid` it returns them; if `creds.expired and
   creds.refresh_token` it does a **silent** `creds.refresh(Request())` and
   re-writes the token 0600; otherwise it raises `CalendarAuthError` telling the
   operator to re-run `setup_oauth.py`. It **never** opens a browser.

Adding a second Google account is a second `accounts:` entry plus one more
`setup_oauth.py` run. No code change.

## Main loop and scheduling

`app.py::App` — one class, wired entirely against the `Display` and `Buttons`
ABCs. Identical code on Pi and Mac; only `config.display.driver` differs.

**Threads:** the main thread blocks on a stop event; one daemon
`refresh-scheduler` thread handles timed refreshes; button callbacks fire on
whatever thread the button driver uses. A single `threading.Lock` guards
`self._view` and `self._cache`; `self._stop` is a `threading.Event`.

**Startup:** register button callbacks -> `buttons.start()` -> `_render_current()`
straight from `cache.json` (no fetch) -> start the scheduler thread -> block.

**Scheduler loop:** compute seconds until the next `refresh.daily_time` in the
configured timezone (`_seconds_until_next_refresh`: today's target, or tomorrow's
if already past) -> `self._stop.wait(timeout=...)` -> if not stopped,
`refresh_and_render()` -> repeat.

**`refresh_and_render()`:** `_fetch_all()` (per account: `load_credentials` ->
`build_service` -> per calendar `fetch_calendar_events`). On **any** exception:
`log.warning(..., exc_info=True)` and return — cache and screen unchanged. On
success: build `CacheContents(fetched_at=now, events=...)`, `save_cache(...)`,
swap `self._cache` under the lock, `_render_current()`.

**Button semantics:**

| Button | Binding | Effect |
|---|---|---|
| A | `cycle_view` | `self._view = cycle(self._view)`; `_render_current()` — **cache only, never a network call** |
| B | `force_refresh` | `refresh_and_render()` — fetch + repaint |
| C, D | `noop` | nothing (D reserved for a future settings menu) |

**`_render_current()`:** under the lock, snapshot `(view, events)`, then
`render(view, events, when=today, resolution, week_starts_on)` ->
`display.set_image(img)` -> `display.show()`. The mock display also archives to
`data/last_render.png`; `pull_preview.sh` fetches that file from the Pi.

**Fetch window (design -> `fetch.py`):** each refresh pulls the **whole month,
padded to whole weeks** (`month_window()`), one `events().list` call per calendar
with `singleEvents=True, orderBy="startTime"`. Day and Week views filter that
cached month client-side, so cycling with button A is always offline.

**Timezone:** all "today"/"now" decisions use
`ZoneInfo(config.refresh.timezone)`, never naive local time.

## View state

`view_state.py` — pure, no I/O, no imports from the rest of the package.
`ViewMode(str, Enum)` with values `"day" | "week" | "month"` (compares equal to
the config string). `ViewMode.from_name()` parses a config string;
`ViewMode.next()` / `cycle()` advance Day -> Week -> Month -> Day.

## Color palette

`render/palette.py::PALETTE` — `dict[str, tuple[int,int,int]]`, the **single
source of truth** for color:

```
black (0,0,0)      white (255,255,255)   red (220,40,40)
green (40,150,70)  blue (40,80,190)      yellow (240,200,40)
```

- `ACCENT_COLORS = {red, green, blue, yellow}` — the values allowed for a
  calendar's `color:` field.
- **Convention:** body text and gridlines are `black` on `white`. The four
  accents are reserved for per-calendar event color-coding only.
- `color(name)` returns the RGB tuple or raises `KeyError` listing valid names.
- The renderer composites in RGB using only these tuples and a
  **non-anti-aliased** font, so the image is already palette-pure; the `inky`
  library does the final quantization with no manual dithering. `mypy`/`ruff`
  plus review enforce "no hex literals in `render/`" — there is no automated lint
  rule for it yet (candidate follow-up).

`renderer.render(view_mode, events, *, when=None, resolution=DEFAULT_RESOLUTION,
week_starts_on="monday")` accepts a `str` or `ViewMode`, sorts events by
`(start, end, id)`, and dispatches to `day_view` / `week_view` / `month_view`.
`DEFAULT_RESOLUTION = (800, 480)`.

## Viewing a render without a panel (Mac and Pi)

Two ways to see a render without a physical panel:

1. **Mac dev loop — `scripts/render_once.py`:** the recommended iteration loop
   for layout/color/font work.
   `python scripts/render_once.py --use-cache --open` renders `cache.json` as-is
   with zero network calls; without `--use-cache` it does one fetch per calendar
   first. `--view {day,week,month}` overrides `config.view.default`. Output always
   goes through the **mock** display driver to `data/last_render.png`.
2. **Pi preview — `scripts/pull_preview.sh <pi-host>`:** `rsync`/`scp` the Pi's
   `~/app/data/last_render.png` to the local machine and open it. Requires
   nothing on the Pi but `sshd` — no web server, no network listener. Env
   overrides: `EINK_REMOTE_DIR`, `EINK_REMOTE_RENDER`, `EINK_SSH_USER`,
   `EINK_PREVIEW_OUT`.

The mock display driver (`display/mock_driver.py`, owned by test-engineer) writes
the PNG and optionally opens it with the platform opener.

For the full design-iteration loop — capturing a Day/Week/Month frame set,
edge-case calendar fixtures, staging renders for the product-designer persona,
and feeding decisions back into `.claude/plans/` and rendering issues — see
[`design-workflow.md`](design-workflow.md).

## Deploy, systemd, and releases

### Service user

A dedicated `--system` user (default `eink-calendar`), no login shell
(`/usr/sbin/nologin`), in the `spi` and `gpio` groups. It owns only its checkout
at `~/app` (a **symlink to the currently-deployed release directory**) and
`~/.config/eink-calendar/`. Full setup steps are in `docs/runbook.md` §4.

### systemd unit (`systemd/eink-calendar.service`)

`Type=simple`, `After/Wants=network-online.target`,
`WorkingDirectory=/home/eink-calendar/app`,
`Environment=EINK_CALENDAR_CONFIG=/home/eink-calendar/.config/eink-calendar/config.yaml`,
`ExecStart=/home/eink-calendar/app/.venv/bin/python -m eink_calendar.app`,
`Restart=on-failure`, `RestartSec=5`.

Hardening: `UMask=0077` (the compensating control cited by `local_files.py` —
files the service writes outside `write_private_text()`, e.g.
`data/last_render.png`, must not be world-readable), `NoNewPrivileges=true`,
`ProtectSystem=strict`, `ProtectHome=read-only`,
`ReadWritePaths=-/home/eink-calendar/app/data /home/eink-calendar/.config/eink-calendar`,
`PrivateTmp=true`, plus the usual `ProtectKernel*` / `Restrict*` /
`LockPersonality`. `DevicePolicy` is left at default pending hardware bring-up
(#15) — tightening to `DevicePolicy=closed` + explicit `DeviceAllow` needs
verification against the real panel.

### Deploy (`scripts/deploy.sh`)

**Canonical install method: the tagged release tarball (decided, #47).** An
early sketch had `deploy.sh` do a git clone/pull on the Pi; the team moved to
release tarballs (PR #52) and that is now the one canonical method. Rationale:
the Pi needs no git, no build toolchain, and no repo checkout; "always deploy a
tagged release, never `main` HEAD" is enforced structurally rather than by
convention; and a device maintained by non-technical family should have the
smallest possible on-device surface. `deploy.sh` and `docs/runbook.md`
§5/§9/§10 agree on this model.

Release-tarball based, over SSH — a Pi set up from the runbook can be updated with
this script and nothing else (**no git checkout on the Pi**):

- `deploy.sh code <pi-host> [VERSION]` — download the GitHub tag archive
  (`.../archive/refs/tags/<VERSION>.tar.gz`, default: newest local tag via
  `git describe --tags --abbrev=0`), extract into the service user's home,
  repoint `~/app`, `pip install -r requirements-pi.txt` in `~/app/.venv`,
  `systemctl restart`.
- `deploy.sh secrets <pi-host>` — `rsync` local `~/.config/eink-calendar/` to the
  Pi (`--chmod=D700,F600`, then `chown` to the service user). **Secrets are never
  in git and never in the code path.**
- `deploy.sh all <pi-host> [VERSION]` — secrets, then code.

> **#47 (resolved):** canonical install method = release tarball. `deploy.sh`
> and `docs/runbook.md` §5 agree; the git-clone/pull approach is dropped.

### Releases

`develop` is the integration branch. When it is stable, `merge-manager` opens a
PR `develop -> main`. Pushing a `v*` tag on `main` triggers the release pipeline
(gitops-manager owns `.github/workflows/**`). Always deploy a tagged release,
never `main` HEAD.

## Key technical decisions

- **Hardware imports are lazy and quarantined** so the entire non-hardware core
  runs on a Mac. Without this, development would require the Pi in the loop for
  every change — the constraint is what makes the primary dev loop possible at
  all, not a style preference.
- **Secrets live outside the checkout** (`~/.config/eink-calendar/`) rather than
  in a gitignored repo path, so an accidental `git add -A` or a repo archive can
  never leak a token or client secret. `.gitignore` still carries a
  defense-in-depth backstop.
- **Silent-refresh-only at runtime** with a separate one-time `setup_oauth.py`
  keeps the device unattended: the family never sees a browser consent prompt.
  The consent-screen "Production" requirement is the corollary — Testing-mode
  refresh tokens expire in 7 days.
- **A failed fetch is a no-op**, not an error screen: the last good render and
  the cache stay intact, so the panel degrades to stale-but-readable, never to
  blank or a stack trace.
- **Whole-month fetch window** means Day and Week views are pure client-side
  filters of the cache, so cycling views with button A never touches the
  network.
- **One palette, six colors, no dithering** — the renderer composites only
  `PALETTE` tuples with a non-anti-aliased font, so the image is already
  palette-pure before `inky` quantizes it.

## Security considerations

1. **Secrets never touch the repo.** `config.yaml`, OAuth client secrets, and
   token JSON live only in `~/.config/eink-calendar/`. `.gitignore` carries a
   defense-in-depth backstop (`*credentials*.json`, `*_token.json`,
   `config/config.yaml`, `data/`, ...) in case one ever lands repo-relative.
2. **File permissions.** `calendar_source/local_files.py` writes every
   personal-data / credential file (`token.json`, `cache.json`) as a **0600**
   file inside a **0700** directory via `write_private_text()` — `O_CREAT` at
   `0600` so it is never briefly world-readable, atomic `os.replace`. The systemd
   `UMask=0077` covers everything else the service writes.
3. **Read-only Google scope.** `calendar.readonly` only — the device can never
   modify or delete calendar data even if compromised.
4. **No interactive auth at runtime, no inbound network.** The runtime only does
   silent token refresh and outbound HTTPS to Google. `pull_preview.sh` uses the
   operator's own SSH; the device runs no listener.
5. **`cache.json` and `last_render.png` are personal data** (event
   titles/times/locations; a picture of the family's week). Both are kept
   non-world-readable by the mechanisms in (2).
6. **Fail-safe rendering.** A corrupt/missing cache returns empty contents rather
   than crashing; a failed fetch keeps the last good screen.
7. **Revoke/rotate procedure** lives in `docs/runbook.md` (joint security + qa
   ownership): revoke the token in the Google account, delete the token file,
   re-run `setup_oauth.py`.

## External dependencies

- **Google Calendar API** — read-only scope; one `events().list` call per
  calendar per refresh. The only external service the runtime contacts.
- **Python packages that install everywhere** (`requirements-base.txt`):
  `google-api-python-client`, `google-auth`, `google-auth-oauthlib`, `Pillow`,
  `PyYAML`.
- **Pi-only packages** (`requirements-pi.txt`): `inky`, `gpiozero`, `RPi.GPIO`.
- **Dev-only packages** (`requirements-dev.txt`): `pytest`, `ruff`, `mypy`,
  `bandit`.
- **Hardware:** Raspberry Pi (SPI + GPIO enabled), Pimoroni Inky Impression 7.3"
  Spectra 6 panel, two momentary push buttons.

## Development phases

| Phase | Scope |
|---|---|
| `phase/1-foundation` | `Makefile`, `.github/workflows/**`, package skeleton, `requirements-*.txt`, `config.py`, `view_state.py` |
| `phase/2-core-logic` | `render/**`, `calendar_source/cache.py`, `app.py` main loop/scheduling |
| `phase/3-integration` | `calendar_source/auth.py` + `fetch.py` (Google API + OAuth), `display/**`, `buttons/**` (real + mock) |
| `phase/4-hardening` | `systemd/**`, `scripts/deploy.sh`, `scripts/pull_preview.sh`, `docs/runbook.md`, release pipeline, physical Pi bring-up |

## Known open design questions

- ~~**#47** — canonical install method~~ **resolved: release tarball** (see the
  Deploy section above).
- **#15** — `DevicePolicy`/`DeviceAllow` tightening for SPI/GPIO, pending real
  hardware; also the first-boot hardware bring-up checklist (`docs/runbook.md`
  §11).
- Automated lint rule for "no hex/RGB literals outside `render/palette.py`" —
  currently review-enforced only.
