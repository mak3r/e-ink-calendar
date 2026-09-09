# Agent Workflow

This document describes the branch strategy, persona model, and PR lifecycle for projects built on the claude-scaffolding template.

## Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Stable releases only. Never commit directly. Protected by CI. |
| `develop` | Integration branch. All persona PRs target develop. |
| `feature/developer/<name>` | Short-lived feature branches owned by developer + test-engineer. |
| `persona/<name>` | Long-lived branches for security, gitops-manager, docs, qa, product-designer. |

## Persona Model

Nine distinct personas each own a slice of the codebase and operate from an isolated git worktree:

| Persona | Worktree | Branch |
|---|---|---|
| developer | `development/` | `feature/developer/*` |
| test-engineer | `development/` | `feature/developer/*` (same as developer) |
| security | `security/` | `persona/security` |
| qa | `qa/` | `persona/qa` |
| gitops-manager | `gitops-manager/` | `persona/gitops-manager` |
| docs | `docs/` | `persona/docs` |
| product-designer | `product-designer/` | `persona/product-designer` |
| merge-manager | *(main clone)* | *(no commits)* |
| triage | *(main clone)* | *(no commits)* |

Full rules for each persona are in CLAUDE.md.

## PR Lifecycle

1. **Product designer** creates issues via `/triage` or directly, with `persona/*`, `phase/*`, `type/*` labels
2. **Developer** picks up issues via `/watch-work developer`, creates a feature branch, implements, opens PR to `develop`
3. **Test engineer** works the same feature branch, adds tests, pushes to the same PR
4. **Merge manager** reviews the PR via `/watch-work merge-manager`: runs `make test`, checks for security issues, merges to `develop`
5. **Other personas** (security, qa, gitops-manager, docs) work their queues independently on long-lived branches
6. **Merge manager** periodically creates a PR from `develop` to `main` for releases

## Handoff Protocol

When a persona completes work that unblocks another persona, they MUST:

1. Post a `HANDOFF → persona/<next>` comment on the issue (see format in CLAUDE.md)
2. Re-label the issue OR create a new issue for the next persona
3. The next persona's `/watch-work` queue picks it up automatically

Work is not complete until the handoff is posted.

## Issue Labels

Every issue must have exactly one label from each group:
- `persona/*` — which persona owns it
- `phase/*` — which project phase it belongs to
- `type/*` — bug, task, or security

Optional: `status/blocked`, `type/freeze`.

## Autonomous Operations

- `/triage` — interactive intake; creates issues with human confirmation
- `/watch-work <persona>` — works through the issue queue autonomously
- `/watch-work <persona> <minutes>` — watch mode, polls for new work
- `/work-summary` — shows the full queue grouped by persona
- `/persona-setup` — initialize any persona session
