# Day view widget column: post-deploy fixes (timezone bug, icons, layout)

Status: **approved** — ready for `persona/developer`. Follow-up to
[[day-view-widget-column]] (`.claude/plans/day-view-widget-column.md`,
implemented in #166/#167) — corrects a real bug found on the device plus a
round of visual refinement to the weather widget, both from direct feedback
on the shipped render.

Mockups iterated live against a real device screenshot:
https://claude.ai/code/artifact/9ec445cb-77a5-4c26-b4fb-d705762f9724

---

## 1. Bug: sunrise/sunset times are wrong

Reported from an actual device render: sunrise showed an evening time,
sunset a morning time. Root cause, found in the shipped code:
`weather_source/fetch.py::compute_solar_lunar()` builds astral's
`LocationInfo(latitude=lat, longitude=lon)` with **no timezone**, which
defaults to UTC. `astral.sun()` therefore returns `sunrise`/`sunset` as
UTC-aware datetimes, and `render/day_view.py::_draw_dawn_dusk_widget()`
formats them directly (`weather.sunrise.strftime("%-I:%M %p")`) with no
conversion to the household's configured local timezone
(`refresh.timezone`, e.g. `"America/New_York"`). The displayed times are in
UTC, not local time.

**Fix:** pass the configured timezone into `LocationInfo` (or convert the
returned datetimes to `refresh.timezone` before they leave
`compute_solar_lunar()`) so `weather.sunrise`/`weather.sunset` are correct
in local time before formatting ever happens.

## 2. Task: 24-hour time everywhere

Sunrise/sunset currently format with `%-I:%M %p` (12-hour, AM/PM). Switch to
`%H:%M`, matching the event list's existing 24-hour times (`%H:%M` is
already used for event start times in `day_view.py`).

## 3. Bug: moon phase text overflows its widget

`_draw_moon_widget()` draws `weather.moon_phase` as a single unwrapped
`draw_text()` call — a two-word phase name like "Waxing Crescent" runs past
the widget's border. **Fix:** wrap the phase name onto two lines using the
existing `wrap_text()` helper (`layout_common.py`), sized to the widget's
content width, the same pattern already used for event summaries.

## 4. Task: dawn/dusk icon needs an actual sun, and clearer sunrise/sunset differentiation

The current icon draws a horizon line and an arrow but no sun shape at all
— confirmed against the real device render, which shows no dome. Iterated
through several rounds directly against rendered mocks to land on:

- A half-circle "dome" (filled yellow, black outline) clipped so only its
  top half shows, sitting on the horizon line — the standard sunrise/sunset
  glyph convention.
- **Both** the sunrise and sunset arrows sit in the same unclipped band
  directly below the horizon line — not one above and one below — and are
  differentiated purely by direction: pointing up (rising) for sunrise,
  pointing down (setting) for sunset. An earlier above/below split looked
  asymmetric once rendered (arrows at uneven distances from the dome); a
  shared band reads more consistently.
- Arrows are drawn triangles (three points), not a text/Unicode glyph —
  consistent with the project's existing "no icon fonts" rule for anything
  on the physical panel.

## 5. Task: weather widget — remove the ambiguous top icon, restructure the forecast rows

- **Remove** the current top-of-widget icon + temperature + condition text
  entirely — a single icon/temp with no time period attached is ambiguous
  (is it now? this morning? unclear).
- **H/L moves to the top** of the widget in its place, at a larger size:
  bigger value font plus a small bold "H:" / "L:" label (previously tiny
  plain text below the icon).
- The same-day forecast (`ForecastPoint` list) renders as **stacked rows**,
  not three narrow side-by-side columns. Each row: the period label
  ("Morning" / "This Afternoon" / "Tonight") on its own line, then a second
  line with a **condition icon** and a **larger temperature** side by side.
  Freeing the label from sharing a row with the icon/temp is what allows
  both to grow (icon ~26px → 40px, temperature ~20px → 32px in the mock).
- Each period gets **its own condition icon** reflecting that period's
  actual forecast — not one generic icon reused for all three (which is
  what made the removed top icon ambiguous in the first place).

## 6. Task: widen the condition vocabulary (needed for §5's per-period icons)

`weather_source/fetch.py`'s `_condition_name()` collapses Open-Meteo's WMO
codes 1 ("mainly clear"), 2 ("partly cloudy"), and 3 ("overcast") into one
`_CLOUDY` bucket — throwing away exactly the granularity §5 needs. Per the
device owner's request to "assume a northeast (of North America)
perspective," widen the mapping to a six-value vocabulary: **sunny, partly
sunny, partly cloudy, cloudy, rain, snow** (storm and fog remain in the
underlying WMO-code buckets but fall back to the closest of these six for
icon purposes — e.g. storm → rain, fog → cloudy — rather than getting
dedicated icons, since they're less common in this use case).

Icon set for the six conditions (flat shapes, six-color palette, no gray,
matching the mockup):
- **Sunny** — sun only.
- **Partly Sunny** — small sun mostly visible, small cloud at its base.
- **Partly Cloudy** — small cloud dominant, small sun peeking from behind.
- **Cloudy** — cloud only, no sun.
- **Rain** — cloud with a few blue raindrop marks below it.
- **Snow** — cloud with a few blue dot/flake marks below it.

## 7. Task: rename "Now" to "Morning"

`ForecastPoint(label="Now", ...)` mislabels a reading taken at last refresh
as if it were live — this device doesn't have live data any more than the
clock idea did (see `day-view-widget-column.md` §1). Rename the literal
label to **"Morning"**, matching "This Afternoon"/"Tonight" as the three
parts of the day. This is the simpler of two options discussed: it doesn't
require a new field, but is only accurate if the scheduled refresh actually
happens in the morning (per `refresh.daily_time`) — a manual force-refresh
at a different hour would still show "Morning" for whatever was just
fetched. The fuller fix (show the literal refresh timestamp instead, via a
new `fetched_at` field on the cached reading) was considered and explicitly
deferred — revisit if the mislabeling in practice turns out to bother
anyone.

## 8. Out of scope

- The `fetched_at`-timestamp alternative to "Morning" (see §7).
- Dedicated icons for storm/fog (see §6).
- Any change to week/month views, the event list, or the calendar key.

## 9. Cross-Persona Completeness Check

- **Docs**: yes — the six-condition vocabulary and the timezone-correction
  behavior aren't yet reflected in `docs/architecture.md`'s weather_source
  section (added in #170 before this vocabulary existed) → `persona/docs`
  companion.
- **Test coverage**: yes — the timezone fix, 24-hour formatting, text
  wrapping, and the widened condition mapping are all new/changed behavior
  → `persona/test-engineer` companion.
- **Security**: no new untrusted-input surface — this reuses the same
  Open-Meteo response already covered by #168's review, just maps more of
  its existing fields.
- **QA / acceptance criteria**: not affected.
- **CI/build/deploy**: no new dependency.
