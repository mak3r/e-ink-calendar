# /persona-setup

Initializes a persona session for this project. Run this at the start of every persona session to verify your environment, review your scope, and pick up or start an issue.

## Step 1 — Identify your persona

Infer the persona from the current working directory:

| Current directory ends with... | Persona |
|---|---|
| `<repo-name>` (main clone) | merge-manager or triage |
| `<repo-name>-worktrees/security` | security |
| `<repo-name>-worktrees/gitops-manager` | gitops-manager |
| `<repo-name>-worktrees/docs` | docs |
| `<repo-name>-worktrees/qa` | qa |
| `<repo-name>-worktrees/product-designer` | product-designer |
| `<repo-name>-worktrees/development` | developer or test-engineer |

Determine `<repo-name>` by running `git remote get-url origin | sed 's|.*/||; s|\.git$||'`.

If the directory is `development`, ask the user which persona (developer or test-engineer) if not clear from context.

## Step 2 — Verify environment

Run the following checks and report any failures before proceeding:

```bash
# Confirm git branch matches expected persona branch
git branch --show-current

# Confirm working tree is clean
git status

# Confirm .claude/commands/ is present
ls .claude/commands/

# Read the quality spec so you understand what quality means for this project
cat .claude/quality.md
```

If the branch does not match the expected persona branch (e.g., you're in the `security/` worktree but not on `persona/security`), stop and instruct the user to run:
```bash
git checkout persona/<name>
```

## Step 3 — Review persona scope

Read the Personas and Branch Ownership table in CLAUDE.md to confirm:
- Which files you are allowed to modify
- Which branch you operate on
- Any hard rules that apply to this persona

Then read `.claude/quality.md` to understand what `make test` and `make quality` mean for this project.

## Step 4 — Find open issues for this persona

```bash
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
gh issue list --repo "$REPO" --label "persona/<name>" --state open \
  --json number,title,labels,updatedAt \
  --jq '.[] | "#\(.number)  \(.title)  \([.labels[].name] | join(","))  [updated \(.updatedAt[:10])]"'
```

Replace `<name>` with the detected persona name.

Present the list and suggest the lowest-numbered unblocked issue (no `status/blocked` label).

## Step 5 — Create the feature branch (developer and test-engineer only)

**All other personas:** worktrees already exist on a fixed branch — skip to Step 6.

**Developer and test-engineer:** after picking an issue, create a feature branch from `origin/develop`:

```bash
git fetch origin
git checkout -b feature/developer/<short-descriptor> origin/develop
git branch --show-current
```

The test-engineer opens their own separate Claude session from the same `development/` directory, then checks out the same branch. **Never create a new worktree directory per feature** — switch branches within `development/`.

## Step 6 — Confirm readiness

Print a confirmation block:

```
Persona:    <name>
Branch:     <current branch>
Directory:  <pwd>
Issue:      #<number> — <title>
Scope:      <files this persona owns>
Blockers:   <any status/blocked issues, or "none">
```

Then begin work or wait for the user to confirm which issue to take.

## Handoff reminder

When work is complete, always follow the handoff protocol in CLAUDE.md before closing any issue:
1. Post the HANDOFF comment on the issue
2. Commit and push
3. Open a PR targeting `develop`
4. Re-label or create a new issue for the next persona in the chain
5. Comment on any upstream blocking issues
