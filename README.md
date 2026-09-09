# claude-scaffolding

A language-agnostic GitHub template repository for multi-agent Claude Code development. Use this as the foundation for new projects that leverage Claude's multi-persona agent system.

Licensed under the [Apache 2.0 License](LICENSE).

---

## What you get

- **9 agent personas** with clear file ownership and behavioral rules, each operating from an isolated git worktree
- **Branch protection** — direct commits to `main` are blocked; all work flows through PRs with CI gates
- **Language-agnostic CI** — calls `make build`, `make test`, `make lint`, `make quality`; you wire in the language-specific commands
- **Quality spec plugin system** — drop `quality-specs/checks.sh` to add project-specific quality gates without changing workflows
- **Secret scanning** — gitleaks on every branch, every push
- **External contributor protection** — non-collaborator PRs and issues are auto-closed and locked
- **Interaction limits** — GitHub collaboration set to collaborators-only, renewed automatically every 5 months
- **7 slash commands** — persona-setup, triage, watch-work, work-summary, scaffold-update, create-project, backport-to-scaffold

### The 9 Personas

| Persona | Role |
|---|---|
| developer | Implements features and fixes |
| test-engineer | Writes and maintains tests alongside developer |
| security | Owns security config, secret handling, CI security steps |
| qa | Writes E2E tests and acceptance criteria |
| gitops-manager | Owns CI/CD, Makefile, build scripts, infrastructure |
| docs | Owns documentation, README, CLAUDE.md |
| product-designer | Creates architectural plans and GitHub issues |
| merge-manager | Reviews PRs, enforces quality gates, merges to develop |
| triage | Conducts issue intake interviews, creates issues with human confirmation |

---

## Quick start

### Creating a new project from this template

In any Claude Code session, run:
```
/create-project
```

Claude will ask for your project name, GitHub owner, description, and stack, then bootstrap the full repo.

### Manual setup

1. Click **"Use this template"** on GitHub to create a new repo
2. Clone the new repo and run setup:
   ```bash
   bash scripts/setup.sh --repo <owner>/<repo-name>
   ```
3. Fill in the four required files:
   - **`CLAUDE.md`** — Project Purpose section + file ownership table
   - **`Makefile`** — Replace stub targets with your build/test/lint commands
   - **`quality-specs/checks.sh`** — Copy from `quality-specs/examples/<language>.sh`
   - **`.claude/quality.md`** — Describe what quality means for your project

---

## How it works

### Persona isolation via git worktrees

Each persona operates in a separate git worktree, preventing merge conflicts during parallel work:

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

Start a persona session:
```bash
cd ~/projects/<repo-name>-worktrees/security
claude
/persona-setup
```

### Autonomous issue queue processing

```bash
# Work through all issues for a persona once:
/watch-work developer

# Watch mode — continuously poll for new work for 60 minutes:
/watch-work gitops-manager 60

# See the full queue:
/work-summary
```

### Issue intake

```bash
# From the main clone:
/triage
```

The triage agent interviews you, reads the relevant source files, and drafts GitHub issues with correct persona/phase/type labels for your review before creating anything.

---

## Customizing for your language/stack

### Quality spec (make quality)

The `make quality` target calls `quality-specs/checks.sh` if present, exits 0 if not.

```bash
# Copy the example for your language:
cp quality-specs/examples/go.sh quality-specs/checks.sh
# or: python.sh, node.sh, rust.sh

chmod +x quality-specs/checks.sh
# Customize it for your project's rules
```

Update `.claude/quality.md` to describe the checks in plain English so agents understand what they mean.

### Build/test/lint (Makefile)

The Makefile stubs exit 1 by default to force you to wire them up:

```makefile
build:
    go build ./...       # or: npm run build, cargo build, etc.

test:
    go test ./...        # or: pytest, npm test, cargo test, etc.

lint:
    golangci-lint run    # or: flake8, eslint, cargo clippy, etc.
```

### Language-specific CI setup

If your build/test/lint commands require a language runtime, add the appropriate setup step to `ci.yml`:

```yaml
# In .github/workflows/ci.yml, before the make call:
- uses: actions/setup-go@v5
  with:
    go-version-file: go.mod
```

---

## Files you keep vs. files you change

| File | Action |
|---|---|
| `CLAUDE.md` | Fill in Project Purpose + file ownership (keep structure) |
| `Makefile` | Replace stub targets with real commands |
| `quality-specs/checks.sh` | Copy from examples and customize |
| `.claude/quality.md` | Write from scratch for your project |
| `.github/workflows/ci.yml` | Add language setup steps if needed |
| `docs/*.md` | Replace placeholders with real content |
| `.gitleaks.toml` | Add project-specific secret patterns |
| `.gitignore` | Add language-specific patterns below the marker |
| All other files | Keep as-is — they are language-agnostic |

---

## Updating the scaffolding

To propose a change to this template:
```
/scaffold-update
```

To contribute an improvement from a derived project back to this template:
```
/backport-to-scaffold
```

---

## License

Copyright 2024-present Mark Abrams. Licensed under the [Apache 2.0 License](LICENSE).
