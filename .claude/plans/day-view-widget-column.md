# Day view: dedicated widget column (dawn/dusk, moon phase, weather)

Status: **approved** — ready for `persona/developer`. Extends
[[day-view-card-redesign]] (`.claude/plans/day-view-card-redesign.md`) §2.4,
which reserved the right quarter of the panel for "a future widget" without
specifying one. This plan is that follow-up: it fills the reserved column
and picks the data sources behind it.

Mockups the device owner and I iterated on directly (in order):
- Clock/weather layout exploration: https://claude.ai/code/artifact/2885c84f-0f9e-4325-81aa-21484f0c2e46
- Weather-only alternatives after the clock was ruled out: https://claude.ai/code/artifact/cc7374ec-3e98-45ea-b733-e9553f2e6b31
- Final widget-column layout (current state): https://claude.ai/code/artifact/af7a371b-7a39-41a5-8130-e5b79ead5349

---

## 1. Why there's no clock

The device owner's first idea was a 14-segment-style digital clock in this
column. Verified against Pimoroni's actual driver source before designing
around it: `inky_ac073tc1a.py` (the Spectra 6 driver) exposes only
`set_image()`/`show()` — no region or partial-update API — and Pimoroni's own
docs put a full-panel refresh at 12-35 seconds depending on panel revision,
with a visible color flash each time. A real-time clock would mean flashing
the *entire* panel (event list included) every minute, and meaningfully more
wear-cycles on hardware rated for occasional full refreshes, not continuous
ones. The device owner agreed to drop the clock concept entirely rather than
build a clock that's wrong most of the day or refresh far more aggressively
than the rest of the device's design assumes. Sunrise/sunset and moon phase
took its place — both are facts about the *whole day*, not the current
moment, so they're immune to the staleness problem a clock has.

## 2. Visual design

The right quarter (`_COLUMN_FRACTION = 0.75` boundary, per
`day-view-card-redesign.md`) becomes a dedicated widget column: three
independently bordered, rounded-rectangle widgets stacked top to bottom,
matching the event cards' visual language (solid black border, rounded
corners) rather than being bare floating text:

1. **Dawn & Dusk** — sunrise and sunset times, side by side.
2. **Moon phase** — icon + phase name (e.g. "Waxing Gibbous").
3. **Weather** — current conditions (icon, temperature, condition text,
   high/low) plus a short same-day mini-forecast strip (e.g. now / this
   afternoon / tonight). This widget fills whatever vertical space is left
   after the two smaller widgets above it.

Layout specifics, settled after two rounds of feedback on the rendered mock:

- The widget column runs the **full panel height** (top margin to bottom
  margin) — independent of where the header/rule fall in the calendar
  column. It is not vertically constrained to start below the rule the way
  the event list is.
- **No vertical divider line** between the calendar column and the widget
  column. The gap between them plus each widget's own border does the
  separating; an explicit rule line was tried and rejected as visual clutter
  once real bordered widgets are there to do that job.
- The horizontal rule under the date **stops at the widget column's left
  edge** instead of crossing all the way to the panel's right margin —
  it forms a clean corner, not a cross, against where the widgets begin.
- The **calendar color key relocates** from the panel's outer-right corner
  to sit on the date's row, right-aligned to where the widget column
  begins — it now reads as belonging to the calendar column's header (key
  for the list below it), not as something related to the widgets beside it.

Icons are simple flat shapes (circles, strokes) in the six palette colors —
no gray exists in the Spectra 6 palette, so a real implementation needs
hand-drawn PIL shapes, not emoji or anti-aliased icon fonts.

## 3. Data sources

Two different kinds of data, two different sourcing strategies:

### 3.1 Solar & lunar — computed locally, no network

Sunrise, sunset, and moon phase are deterministic given (date, latitude,
longitude) — there is no need to fetch them from anywhere. Use
**[astral](https://pypi.org/project/astral/)** ([GitHub](https://github.com/sffjunkie/astral)),
a small, pure-Python, actively-maintained library with no network dependency
of its own. This is a *better* reliability story than the Google Calendar
integration: there's no token to expire, no service to be down, and the
figures literally cannot be "stale" since they're computed fresh for
`when` (the day being rendered) on every render — no caching needed for this
half of the data.

### 3.2 Weather (current conditions + forecast) — Open-Meteo

**[Open-Meteo](https://open-meteo.com/)** ([pricing/terms](https://open-meteo.com/en/pricing)):
verified directly against their pricing page before recommending it —

- **No account, no API key, no signup at all** for the free tier — a plain
  HTTPS GET with `latitude`/`longitude` (and which variables you want)
  returns JSON.
- Free-tier limits: 600 calls/minute, 5,000/hour, 10,000/day,
  300,000/month. This device needs on the order of 1-10 calls/day (one per
  scheduled refresh, one per manual force-refresh), nowhere close to any of
  those ceilings.
- Explicitly **non-commercial use only**, and **no uptime guarantee** — both
  fine for a household device, but the second point means the weather half
  of this feature must degrade the same way the calendar side already does:
  on a failed fetch, keep the last cached weather snapshot rather than
  blanking the widget or crashing the render.
- Coverage: current conditions, hourly forecast, 16-day daily forecast —
  everything the weather widget's mockup content needs.

No general-purpose HTTP client dependency is needed for this — stdlib
`urllib.request` + `json` is sufficient for one GET call with query
parameters and a JSON response; there's no need to add `requests` or
similar just for this.

### 3.3 Where each source shows up in the architecture

A new `eink_calendar/weather_source/` package, structured like the existing
`calendar_source/` package:

```
weather_source/
  models.py   # WeatherSnapshot: temp, condition, hi/lo, hourly forecast
              #   points (from Open-Meteo) + sunrise/sunset/moon_phase
              #   (from astral) bundled into one object
  fetch.py    # fetch_weather(lat, lon) -> Open-Meteo JSON via urllib;
              #   solar/lunar computed via astral, not fetched
  cache.py    # JSON cache of the last-fetched *weather* half only (mirrors
              #   calendar_source/cache.py) — solar/lunar is never cached
              #   because it's cheaper to recompute than to go stale
```

`render/day_view.py` depends on `weather_source.models` the same way it
already depends on `calendar_source.models` — consistent with
`docs/architecture.md`'s existing dependency-direction rule ("render/*
depends only on calendar_source.models and render.palette"), just extended
to the new peer package.

Config gets a new section, following `config.py`'s existing
frozen-dataclass-plus-`ConfigError` pattern:

```yaml
weather:
  location: {lat: 40.7128, lon: -74.0060}   # household's fixed location
```

## 4. Out of scope

- Any weather condition beyond what Open-Meteo's free tier returns (no
  radar imagery, no severe weather alerts).
- Multi-day forecast display — the mini-forecast strip is same-day only
  (now / afternoon / tonight), matching the mockup.
- Week/month view changes — day view only.
- Exposing `weather.location` via anything other than the config file (no
  auto-geolocation).

## 5. Cross-Persona Completeness Check

- **User-facing/docs**: yes — new config section, new module, two new
  external-facing data sources → `persona/docs` companion to document the
  config schema *and* explicitly cite Open-Meteo and astral as the data
  sources (their terms, the non-commercial/no-uptime-guarantee caveat, and
  why solar/lunar needs no network) in `docs/architecture.md`.
- **New/changed behavior without test coverage**: yes → `persona/test-engineer`
  companion.
- **Credentials/tokens/untrusted-input parsing**: yes, partially — no
  credentials involved (Open-Meteo needs no key), but the weather fetch
  parses a third-party JSON response, which is untrusted input a malformed
  or unexpected response could crash on → `persona/security` companion to
  review that parsing path.
- **`docs/acceptance-criteria.md` / e2e**: not affected — no existing
  criterion covers the day view's widget column.
- **CI/build/deploy tooling**: yes — `astral` is a new runtime dependency →
  `persona/gitops-manager` companion for `requirements-base.txt`.
