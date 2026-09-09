# Quality Spec for e-ink-calendar

<!-- This file is read by all agent personas before declaring work complete. -->

## What "make test" means

Runs `pytest -q` over `tests/`. Tests must not import or exercise hardware-only
modules (`eink_calendar/display/inky_driver.py`, `eink_calendar/buttons/gpio_buttons.py`)
directly — those files import Pi-only packages (`inky`, `gpiozero`) and are never
imported unless `display.factory`/`buttons.factory` select the real driver, which
tests should not do. Everything else (`config`, `calendar_source`, `render`,
`view_state`, the mock display/button implementations) is fully testable in CI.

## What "make lint" means

Runs `ruff check eink_calendar tests`. Standard ruff defaults; no project-specific
rule overrides yet.

## What "make quality" checks

Runs `quality-specs/checks.sh` (copied from `quality-specs/examples/python.sh`,
unmodified): fails on TODO comments in non-test source files, runs `bandit` for
security issues, runs `mypy --ignore-missing-imports` for type errors.

## Language and framework conventions

- Python 3.11, matching Raspberry Pi OS Bookworm's system Python.
- Config is loaded into dataclasses (`eink_calendar/config.py`) — no passing raw
  dicts around past the config-loading boundary.
- Hardware-only imports (`inky`, `gpiozero`) must stay confined to
  `display/inky_driver.py` and `buttons/gpio_buttons.py`, imported lazily by their
  respective `factory.py` — the rest of the package must import cleanly on a Mac
  with no GPIO libraries installed. This is a hard architectural constraint, not
  a style preference: it's what makes Mac-based development possible at all.
- Secrets (OAuth tokens, credentials, `config.yaml`) are never read from or
  written to a path inside the repo checkout — see `docs/architecture.md` and
  the Security Considerations in `.claude/plans/` for the canonical location
  (`~/.config/eink-calendar/`).
- Colors used anywhere in `render/` must come from `render/palette.py`'s
  `PALETTE` dict — never arbitrary hex/RGB literals — since the display only
  supports six fixed colors.

## Definition of done additions

None — the generic Definition of Done in CLAUDE.md applies.
