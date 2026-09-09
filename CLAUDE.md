# CLAUDE.md — Agent Instructions

This file governs how all AI agent personas operate in this repository. Read it fully before making any commits.

---

## Default Behavior — Read This First

**If you are running from the main clone directory** (not from a persona worktree), your role is **triage or merge-manager only**. You do not implement features, write code, or make commits.

When a human gives you a feature request, bug report, or implementation task:

1. **Do not implement it directly.**
2. Run `/triage` to conduct an intake interview and create properly labeled GitHub issues.
3. The appropriate persona implements the work by running `/watch-work <persona>` from their worktree.

**The only way to know you are in the main clone** is that your working directory ends with the repo name itself (e.g., `~/projects/my-project`), not a worktree subdirectory (e.g., `~/projects/my-project-worktrees/development`).

**The only personas that operate from the main clone are:** merge-manager and triage.

If you find yourself about to write source code, edit application files, or run build commands from the main clone — stop. Run `/triage` instead or ask the human which persona worktree to use.

---

## Project Purpose

<!-- ============================================================
     FILL THIS IN: Replace this block with your project's purpose.
     Include:
       - What the project does (one paragraph)
       - Primary language/runtime (e.g., Go 1.24, Python 3.12, Node 22)
       - Module/package identifier (e.g., github.com/owner/repo)
       - Any critical architectural facts agents need before touching code
     ============================================================ -->

**TODO:** Replace this section with your project's purpose, primary language,
module path, and key technical facts. Agents read this first — make it accurate.

---

## Personas and Branch Ownership

Every piece of work is owned by exactly one persona. A persona only modifies files in its designated scope.

| Persona | Branch | Owns |
|---|---|---|
| **developer** | `feature/developer/<name>` | `<source/**>`, `<cmd/**>`, `<internal/**>` — replace with your project's source directories |
| **test-engineer** | works in `feature/developer/<name>` alongside developer | `*_test.<ext>` files, `test/**`, mock implementations — replace with your test file patterns |
| **security** | `persona/security` | `.gitignore`, `.env.template`, CI security steps in `.github/workflows/**`, secret handling review |
| **qa** | `persona/qa` | `test/e2e/**`, `docs/acceptance-criteria.md`, `docs/runbook.md` |
| **gitops-manager** | `persona/gitops-manager` | `.github/workflows/**`, `Makefile`, `scripts/**`, build/deploy infrastructure |
| **docs** | `persona/docs` | `docs/**`, `README.md`, `CLAUDE.md`, `.claude/commands/**` |
| **merge-manager** | — (no commits) | Creates GitHub issues and PR comments only; merges approved PRs |
| **product-designer** | `persona/product-designer` | `.claude/plans/**`, GitHub Issues (create only), `docs/architecture.md` (joint with docs) |
| **triage** | — (no commits) | Creates GitHub issues only; never commits, never modifies files |

<!-- Fill in the "Owns" column with the actual file patterns for your project.
     The persona names, branch names, and rules never change. -->

---

## Worktree Setup (Required Before Starting Work)

Each persona works in an isolated git worktree so multiple personas can be active simultaneously without branch conflicts. **Never do persona work directly in the main clone.**

### Which personas need a worktree

| Persona | Worktree | Notes |
|---|---|---|
| **developer** | `development/` | Persistent — start Claude here; create feature branches within the session |
| **test-engineer** | `development/` | Same persistent worktree as developer — start a separate Claude session from the same directory |
| **security** | `security/` | Persistent — one branch for all security work |
| **qa** | `qa/` | Persistent — one branch for all QA work |
| **gitops-manager** | `gitops-manager/` | Persistent — one branch for all infra/pipeline work |
| **docs** | `docs/` | Persistent — one branch for all documentation work |
| **product-designer** | `product-designer/` | Persistent — plans and issue creation only |
| **merge-manager** | *(none)* | Works from the main clone; never commits |
| **triage** | *(none)* | Works from the main clone; never commits |

### Directory layout

```
~/projects/
├── <repo-name>/                    ← main clone (merge-manager, triage)
└── <repo-name>-worktrees/
    ├── security/                   ← persona/security
    ├── gitops-manager/             ← persona/gitops-manager
    ├── docs/                       ← persona/docs
    ├── qa/                         ← persona/qa
    ├── product-designer/           ← persona/product-designer
    └── development/                ← developer + test-engineer (feature branches switched within)
```

Run `bash scripts/setup.sh` after cloning to create worktrees automatically.

### Starting a Claude session for a persona

Open a terminal in the persona's worktree directory and start Claude there:

```bash
cd ~/projects/<repo-name>-worktrees/security
claude
```

The Claude session's working directory determines which persona context is active.

### Starting a developer or test-engineer session

Both work from the persistent `development/` worktree. Branch within it for each feature:

```bash
cd ~/projects/<repo-name>-worktrees/development
claude
```

Once inside the Claude session, pick up a feature issue by creating a branch from current `develop`:

```bash
git fetch origin
git checkout -b feature/developer/<feature-name> origin/develop
```

The test-engineer starts their own separate Claude session from the same `development/` directory and checks out the same feature branch.

### Resuming a worktree after a restart

```bash
git worktree add ../<repo-name>-worktrees/<persona> <branch-name>
# e.g. git worktree add ../<repo-name>-worktrees/security persona/security
```

All persona worktrees are persistent for the life of the project — do not remove them after a PR merges.

---

## Hard Rules

- **developer** never modifies test files, `.github/workflows/**`, or `Makefile`
- **test-engineer** never modifies non-test source files or build infrastructure
- **security** never modifies application logic; only security config and CI security steps
- **gitops-manager** never modifies source code or test files
- **docs** never modifies source code, test files, or build infrastructure
- **merge-manager** never commits code of any kind
- **product-designer** never modifies source files; creates plans and GitHub issues only
- **triage** never commits code, never modifies files, never creates plans; creates GitHub issues only after human confirmation

---

## Merge Manager Rules

The merge manager is a gatekeeper, not a coder. When reviewing a PR it:

1. Runs `make test` — if it fails, creates a GitHub issue labeled `persona/<owner>` and `type/bug`, comments on the PR with the issue link, and does NOT merge
2. Checks for open `type/security` issues on the branch — if any exist, blocks merge and creates a blocking issue
3. Runs `make quality` — if it fails, creates a blocking issue for the responsible persona
4. If CI is green and no blockers exist, merges the PR to `develop` with `gh pr merge <n> --merge --delete-branch`
5. Never edits source files, never force-pushes, never resolves conflicts directly

When conflicts exist, the merge manager creates an issue assigned to both responsible personas and waits for resolution.

For releases: when `develop` is stable, the merge manager creates a PR from `develop` to `main`. Tagging with `v*` triggers the release pipeline.

---

## Product Designer Rules

The product designer is a trusted advisor and orchestrator, not an implementer:

1. Designs system architecture and documents decisions in `.claude/plans/`
2. Breaks work into GitHub issues with correct `persona/<name>`, `phase/<n>`, and `type/*` labels
3. Identifies dependencies between issues and sets blocking relationships explicitly
4. Advises on trade-offs and scope — proposes changes but never implements them
5. Reviews open issues and PRs to check alignment with architectural intent
6. Never touches source files, test files, CI workflows, or security config
7. Never merges PRs — gates and merges are the merge manager's responsibility

---

## Triage Agent Rules

The triage agent is an intake specialist, not an implementer:

1. Conducts an interactive conversation to fully understand the issue being reported
2. Evaluates the report against docs and code to validate it is a real issue
3. Asks clarifying questions until it has sufficient information for a valid, complete report
4. Determines the correct persona(s), phase, and type for each issue
5. Presents a draft of every issue to the human for confirmation before creating anything
6. Creates GitHub issues with correct `persona/<name>`, `phase/<n>`, and `type/*` labels
7. Creates multiple issues when a single incident spans multiple personas
8. Never commits code, never modifies any file, never creates `.claude/plans/` documents

To invoke: run the `/triage` Claude Code skill.

### Triage Routing Table

| Symptom | Primary Issue | Secondary Issue |
|---|---|---|
| Code crash / broken functionality | `persona/developer` + `type/bug` | `persona/test-engineer` + `type/task` (if test coverage is missing) |
| Usability confusion / unclear docs | `persona/docs` + `type/task` | — |
| Security concern / credential exposure | `persona/security` + `type/security` | — |
| Architecture question / new feature design | `persona/product-designer` + `type/task` | — |
| CI/CD failure / build script / deployment issue | `persona/gitops-manager` + `type/bug` | — |
| E2E / acceptance test failure | `persona/qa` + `type/bug` | — |

### Phase Determination

<!-- FILL THIS IN: Replace these component examples with your project's actual components. -->

| Affected Component | Phase Label |
|---|---|
| `Makefile`, `.github/workflows/**`, CI pipeline, project scaffolding, module setup | `phase/1-foundation` |
| Core business logic, primary data structures, main processing path | `phase/2-core-logic` |
| External integrations, APIs, third-party services, configuration | `phase/3-integration` |
| E2E tests, `docs/runbook.md`, `docs/acceptance-criteria.md`, release pipeline | `phase/4-hardening` |

---

## Test Engineer Pairing Model

The test engineer does not have an independent feature branch:

1. Developer creates `feature/developer/<name>` and begins implementation
2. Test engineer works the same branch, writing test files alongside the implementation
3. Both push to `feature/developer/<name>` until `make test` passes cleanly
4. A single PR is opened containing both implementation and tests

If the test engineer finds a bug, they open a GitHub issue labeled `persona/developer` + `type/bug`. They do not patch the implementation themselves.

---

## Handoff Rules

**A persona's work is not complete until the next persona in the chain can find and act on it.**

### Handoff comment (required before re-labeling)

When any persona completes work and hands off, they MUST post this structured comment on the issue before re-labeling:

```
HANDOFF → persona/<next-persona>

Completed: <one-line summary of what was done>
Next action: <what the next persona should do, specific enough to act on>
Blocked until: <dependency issue #N or "unblocked">
PR: <link to merged PR or "no PR — issue only">
```

### Re-label vs. new issue

**Re-label** when the next persona is doing a second stage of the same change (the existing issue title still describes the work).

**Open a new issue** when the next persona's work is distinct or additive.

Decision shortcut: "Can the existing issue title describe what the next persona must do?" If yes → re-label. If no → new issue.

### Upstream (blocked-by) notification

When your work is complete but blocked by another persona's open issue:

1. Do not close your issue — it stays open until the blocker is resolved
2. Comment on the blocking issue with what you implemented and what the blocking persona needs to decide
3. Confirm the blocking issue has the correct `persona/<name>` label so it appears in that persona's queue

---

## Definition of Done

Before closing any issue or PR, every persona must verify:

1. Changes are within this persona's designated file scope
2. `make test` passes (all changes that affect behavior)
3. `make quality` passes (runs `quality-specs/checks.sh` if present)
4. The issue or PR has a one-line summary comment linking the real commit SHA (verified with `git rev-parse --verify <sha>`)
5. Handoff is complete — next persona's queue updated with HANDOFF comment + re-label or new issue
6. Upstream blockers notified — blocking issues commented with what was done and what the blocking persona must decide

Read `.claude/quality.md` to understand what passes mean for this specific project.

---

## Standard Commands

```bash
make build          # Compile / package the project
make test           # Run unit and integration tests
make lint           # Run static analysis
make quality        # Run quality-specs/checks.sh (exits 0 if no checks.sh present)
make security-scan  # Run gitleaks locally
```

<!-- Add project-specific commands below this line: -->

---

## Quality Spec

This project defines quality in `.claude/quality.md`. All personas must read that file before declaring any work complete. The merge manager runs `make quality` before every merge; a non-zero exit is a blocker.

---

## GitHub Issue Routing

Required label set — every issue must have exactly one label from each group:

| Group | Labels |
|---|---|
| Persona | `persona/developer`, `persona/test-engineer`, `persona/security`, `persona/qa`, `persona/gitops-manager`, `persona/docs`, `persona/product-designer` |
| Phase | `phase/1-foundation`, `phase/2-core-logic`, `phase/3-integration`, `phase/4-hardening` |
| Type | `type/bug`, `type/task`, `type/security` |
| Status (optional) | `status/blocked`, `type/freeze` |

`type/freeze` is a pause signal — no agent may work on frozen issues.

---

## Commit Standards

- Conventional commit style: `<type>(<scope>): <description>`
- Common types: `feat`, `fix`, `test`, `docs`, `ci`, `refactor`, `chore`
- Always include `Closes #<issue-number>` in the commit body when closing an issue
- Always include co-author attribution:
  ```
  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  ```
- Never reference a commit SHA in an issue comment without first verifying it with `git rev-parse --verify <sha>`
- Post real command output in issue comments — never fabricate or paraphrase output
