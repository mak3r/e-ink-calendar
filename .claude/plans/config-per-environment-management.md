# Per-environment config management (dev mock vs Pi inky)

Status: **approved** — follow-up design for issue #110. Supersedes the
main plan's §4 only on the question of *how the dev and Pi `config.yaml`
differ*; the schema, dataclass model, and validation rules in
`.claude/plans/i-just-received-a-dynamic-candy.md` §4 are unchanged.

Last reconciled against `origin/develop` on 2026-09-10 (`config.py` has
`display.output_path`; no overlay or env-key-override mechanism exists).

---

## 1. Problem

`config.yaml` must differ between the dev Mac and the Pi for a handful of
keys, but the project had no stated model for that split:

- **Environment-specific** (legitimately different per machine):
  `display.driver` (`mock` / `inky`), `display.resolution`,
  `display.output_path`, `display.mock_auto_open`, `buttons.pin_map`.
- **Shared** (must stay identical, or the two machines render different
  calendars): `accounts`, `refresh`, `view`, `buttons.bindings`,
  `cache.path`.

Two concrete failures motivated the decision:

- `deploy.sh secrets` mirrors the *entire* `~/.config/eink-calendar/`
  including `config.yaml`, so it overwrites the Pi's `inky` config with
  the Mac's `mock` config (#109).
- Nothing tells the operator which keys are *supposed* to differ, so the
  shared keys drift silently (add a calendar on the Mac, forget the Pi).

## 2. Options weighed

| Option | Verdict |
|---|---|
| **A. Pi-authored config, formalized** — each machine keeps its own `config.yaml`; `deploy.sh` never touches it; the split is documented and the example file is annotated. | **Chosen.** |
| B. Deploy-time overlay / `--set key=value` in `deploy.sh` | Rejected — makes the Pi's running config a derived artifact nobody can read directly; needs a YAML editor (`yq`/fragile `sed`) on the deploy path. |
| C. Committed base + environment overlay file, merged in `config.py` at load | Rejected as premature — adds a merge codepath, a second file, and validation-ordering complexity to `config.py` for a **two-environment, single-operator** project. Revisit only if a real fleet appears. |
| D. Env-var overrides for the environment-specific keys | Rejected — scatters config across the systemd unit and the YAML, and `resolution` / `pin_map` are awkward as env vars. The unit already sets `EINK_CALENDAR_CONFIG`; that is the right amount of env. |

## 3. Decision

**The Pi's `config.yaml` is authored on the Pi and is the single source of
truth for that device.** `deploy.sh` never reads, writes, or deletes it.

Drift on the *shared* keys is controlled by documentation and tooling, not
by a merge mechanism:

1. **`deploy.sh secrets` syncs an explicit allowlist** — credential and
   token files only (`*_credentials.json`, `*_token.json`), never
   `config.yaml`, and `--delete` is scoped so it cannot remove Pi-only
   files (render dir, `cache.json`). This is #109's fix; this design
   ratifies it as the permanent base behavior regardless of anything
   layered on later.
2. **`config.example.yaml` is annotated** with an inline
   `# ENV-SPECIFIC` / `# SHARED — keep dev and Pi identical` marker on
   every key, so both machines' configs are derived from one template and
   the operator can see the split at the point of editing.
3. **The split is documented** in `docs/architecture.md` (Configuration
   section) and `docs/runbook.md` (§6 authoring, §10/§13 deploy notes).
4. **Optional, not required:** a read-only `deploy.sh check-config
   <pi-host>` that fetches the Pi's `config.yaml` and diffs the shared
   keys against the local one, reporting drift. No writes. Filed as a
   gitops follow-up; ship only if the doc-only approach proves
   insufficient in practice.

## 4. Consistency with #105 / #107

`display.output_path` is environment-specific and appears in the table
above. Under Pi-authored config the Pi either sets it explicitly or relies
on the working-dir-anchored default from #107
(`data/last_render.png` → `~/app/data/last_render.png` under systemd's
`WorkingDirectory`). Developer still owns that default. No conflict —
#107's `config.example.yaml` change (fixing `../data/...` →
`data/last_render.png`) lands first; the annotation pass in §3.2 builds on
the corrected file.

## 5. Follow-up issues

| # | Persona | Work |
|---|---|---|
| #109 (existing) | gitops-manager | secrets allowlist — credential/token files only, never `config.yaml`. Commented with this decision. |
| new | developer | Annotate `config.example.yaml` with `ENV-SPECIFIC` / `SHARED` markers. No `config.py` change. Coordinate with #107 (same file). |
| new | gitops-manager | Optional read-only `deploy.sh check-config <pi-host>` shared-key drift check. |
| new | qa | Runbook: "`config.yaml` is Pi-authored, never synced by `deploy.sh`" note in §6/§10/§13 + the shared-vs-env-specific key list. |

## 6. Revisit trigger

If the project ever runs more than one Pi, or more than one operator
authors config, reopen this with Option C (committed base + per-host
overlay merged in `config.py`).
