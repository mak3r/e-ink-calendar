# Project Manager Guide

This guide covers how to set up a new project derived from claude-scaffolding and manage the day-to-day persona workflow.

## Initial Setup (one-time)

After creating a project from this template:

```bash
# 1. Clone the new repo
git clone https://github.com/<owner>/<repo-name>
cd <repo-name>

# 2. Run setup (creates worktrees, branches, labels, branch protection)
bash scripts/setup.sh --repo <owner>/<repo-name>

# 3. Customize the four required files:
#    - CLAUDE.md (Project Purpose + file ownership table)
#    - Makefile (replace stub targets with real build/test/lint commands)
#    - quality-specs/checks.sh (copy from quality-specs/examples/<language>.sh)
#    - .claude/quality.md (describe what quality means for this project)
```

After setup, your directory structure will look like:

```
~/projects/
├── <repo-name>/                    ← main clone (merge-manager, triage)
└── <repo-name>-worktrees/
    ├── security/                   ← persona/security
    ├── gitops-manager/             ← persona/gitops-manager
    ├── docs/                       ← persona/docs
    ├── qa/                         ← persona/qa
    ├── product-designer/           ← persona/product-designer
    └── development/                ← developer + test-engineer
```

## Starting a Persona Session

1. Open a terminal in the persona's worktree directory
2. Start Claude Code: `claude`
3. Run `/persona-setup` to initialize the session

The persona-setup command verifies your branch, reviews your file scope, and fetches open issues.

## Starting Work

To have an agent work through the issue queue autonomously:

```bash
# From the persona's worktree:
claude
# Then run:
/watch-work <persona-name>
# Or for continuous watch mode (60 minutes):
/watch-work <persona-name> 60
```

## Seeing the Full Queue

From any directory:
```bash
claude
/work-summary
```

This shows all open issues grouped by persona (ready, blocked, frozen) and a recommended execution order.

## Filing a New Issue

```bash
# From the main clone:
claude
/triage
```

The triage agent conducts an intake interview, scans affected source files, and drafts issues for your review before creating them.

## Proposing a Change to the Scaffolding

When you improve a slash command, workflow, or other generic scaffolding file:

```bash
# From the main clone of the scaffolding project:
claude
/scaffold-update
```

To contribute the improvement back to the upstream template:

```bash
# From any derived project:
claude
/backport-to-scaffold
```

## Release Process

1. Merge manager creates a PR from `develop` to `main` when develop is stable
2. Tag the release: `git tag v<version> && git push origin v<version>`
3. Add your release pipeline to `.github/workflows/` via the gitops-manager persona

## Worktree Maintenance

Worktrees are persistent — do not delete them after a PR merges. The developer worktree switches branches within the same session.

To recreate a lost worktree:
```bash
git worktree add ../<repo-name>-worktrees/<persona> persona/<persona>
```

To list all worktrees:
```bash
git worktree list
```
