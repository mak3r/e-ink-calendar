# Layout / design-iteration workflow

How to iterate on the calendar's **visual design** — the Day / Week / Month
layouts, spacing, typography, and the six-colour palette mapping. This page ties
together the mock render loop, the real-Pi preview, and the handoff to the
product-designer persona.

It does **not** cover installing or operating the device (see
[`runbook.md`](runbook.md)) or the MVP pass/fail bar (see
[`acceptance-criteria.md`](acceptance-criteria.md)). It is about the design
feedback loop only.

---

## The two ways to see a frame

| | Mock render (`render_once.py`) | Real-Pi preview (`pull_preview.sh`) |
|---|---|---|
| Where it runs | Any Mac / Linux box, no GPIO | Fetches a frame the Pi already drew |
| Speed | Seconds; edit → re-run | As slow as a real daily refresh + a panel repaint |
| Colour fidelity | RGB PNG at `config.display.resolution` — the palette tuples, **not** the panel's actual output | The Spectra 6 quantisation, ghosting, and viewing-angle contrast as they really look on the wall |
| Use it for | Layout, alignment, text fitting, date maths, edge-case calendars, 90% of design work | Final colour/contrast sign-off, "does this actually read from across the kitchen" |

Do the bulk of the work against the mock loop. Only reach for the Pi preview
when a decision depends on how the physical panel renders.

---

## 1. Mock loop — `scripts/render_once.py`

Renders one frame through the mock display driver
(`eink_calendar/display/mock_driver.py`) to `data/last_render.png`, at
`config.display.resolution`. No Pi, no GPIO, and — with `--use-cache` — no
network.

```bash
# render the current cache as-is, open the PNG; no network call at all
python scripts/render_once.py --use-cache --open

# fetch from Google first, then render
python scripts/render_once.py --open
```

| Flag | Effect |
|---|---|
| `--use-cache` | Render from `cache.json` only; skip the network call entirely |
| `--view {day,week,month}` | Override `config.view.default` for this render |
| `--open` | Open the resulting PNG in the default viewer |
| `--config <path>` | Use a specific config file instead of the default search path |

### Capturing a full set of frames

For a design review you usually want all three views from the same event data,
plus any edge cases. `--use-cache` guarantees every frame is rendered from the
identical `cache.json`:

```bash
mkdir -p design-review/2026-09-10
for v in day week month; do
  python scripts/render_once.py --use-cache --view "$v"
  cp data/last_render.png "design-review/2026-09-10/$v.png"
done
```

### Edge-case calendars

The layouts are most likely to break on data extremes. Build a few
`cache.json` fixtures (or point `--config` at configs with different calendar
sets) and capture a frame of each:

- an empty day / empty week
- a day with 10+ overlapping events
- very long event titles and long location strings
- all-day events stacked with timed events
- events in four different calendar colours at once
- a month with events on nearly every cell

Keep the fixtures you reuse under `data/fixtures/` (gitignored) and note in the
review folder which fixture produced which PNG.

---

## 2. Real-Pi preview — `scripts/pull_preview.sh`

Pulls the frame the Pi most recently drew. The Pi runs nothing but `sshd`; the
render (`data/last_render.png`, mode `0600` under the `eink-calendar` service
user) is fetched via `sudo` on the Pi — `rsync --rsync-path="sudo rsync"` with a
`sudo cat` fallback — so the login user needs passwordless sudo and must **not**
be the `eink-calendar` service user.

```bash
scripts/pull_preview.sh <pi-host>          # or  user@pi-host
```

Saves to `./data/last_render.png` and opens it. Environment overrides (all
optional):

| Variable | Default | Purpose |
|---|---|---|
| `EINK_REMOTE_DIR` | `/home/eink-calendar/app` | App directory on the Pi |
| `EINK_REMOTE_RENDER` | `$EINK_REMOTE_DIR/data/last_render.png` | Full path to the render, overrides `EINK_REMOTE_DIR` |
| `EINK_SSH_USER` | from `user@host`, else the host default | Sudo-capable login user (not `eink-calendar`) |
| `EINK_PREVIEW_OUT` | `./data/last_render.png` | Local output path |

To force a fresh frame before pulling, press button B on the device (force
refresh) or restart the service, then wait for the repaint to finish.

> This is the same command the runbook documents for operators
> ([`runbook.md`](runbook.md) §10). It is repeated here only for the design
> context; the runbook remains the source of truth for the Pi-side setup it
> depends on.

---

## 3. Staging renders for the product-designer persona

The product-designer persona works from its own worktree at
`~/projects/e-ink-calendar-worktrees/product-designer/` (branch
`persona/product-designer`) and owns `.claude/plans/**` and
`docs/architecture.md` (jointly with docs). It does **not** run the app or edit
source — so it needs the frames handed to it as image files.

Recommended staging convention:

1. Put the frame set in a dated folder **inside the product-designer worktree**
   so that Claude session can read it directly:
   ```
   ~/projects/e-ink-calendar-worktrees/product-designer/design-review/<YYYY-MM-DD>-<topic>/
     day.png  week.png  month.png  <edge-case>.png
     NOTES.md   ← what changed, what to look at, which fixture produced each PNG
   ```
   `design-review/` is not owned by any persona and is gitignored — it is a
   scratch drop zone, not a committed artefact.
2. In `NOTES.md` record: the commit SHA the renders were built from, the config
   / fixture used, and the specific questions for the designer ("is the week
   header too heavy?", "does yellow-on-white read?").
3. Start (or message) a product-designer Claude session pointed at that folder.

If a real-panel opinion is needed, include both the mock PNG and the
`pull_preview.sh` PNG side by side and say which is which.

---

## 4. Feeding decisions back into plans and issues

The product-designer persona turns a review into one of:

- **An update to `.claude/plans/`** — for a design *direction* or a constraint
  (e.g. "Week view always shows 7 columns even when empty"). This is the
  authoritative record; `docs/architecture.md` §"Color palette" and the view
  descriptions are transcribed from it.
- **A `persona/developer` + `type/task` issue** — for a concrete rendering
  change, labelled `phase/2-core-logic` (it lives under `render/**`). Link the
  review folder or attach the frames in the issue body.
- **A `persona/product-designer` + `type/task` issue** — if the review opens a
  larger design question that needs its own plan entry first.

Once the plan changes, the docs persona brings `docs/architecture.md` back in
sync (that is a separate docs issue, per the handoff rules in `CLAUDE.md`).

---

## At a glance

```
edit render/*  ──►  render_once.py --use-cache --view {day,week,month}
                          │
                          ▼
              design-review/<date>-<topic>/*.png  +  NOTES.md
                 (staged in the product-designer worktree)
                          │
                          ▼
        product-designer Claude session reviews the frames
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
   .claude/plans/   developer issue   product-designer issue
   (direction)      (render/** fix)   (new design question)
          │
          ▼
   docs updates docs/architecture.md to match (separate docs issue)
```
