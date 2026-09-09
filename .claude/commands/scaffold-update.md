# /scaffold-update

Propose a change to this scaffolding template. Because this template is consumed by other projects, changes follow a stricter process than ordinary feature work.

**This command is for changes to the scaffolding itself** — CLAUDE.md, slash commands, workflows, quality-spec examples, scripts. For changes to a derived project's application code, use the normal persona workflow.

---

## Step 1 — Interview

Ask the user:

1. **What do you want to change?** (Which file(s) and what specifically)
2. **Why?** (What problem does this solve or improve?)
3. **Have you tested this change in a derived project?** (If yes, which one)

Do not proceed until you have clear answers to all three.

---

## Step 2 — Impact Analysis

Determine whether the change is:

**Additive** (safe — existing projects are unaffected):
- Adding a new file or section that didn't exist before
- Adding a new slash command
- Adding a new quality-spec example
- Adding new optional configuration

**Breaking** (requires a migration note):
- Changing the behavior of an existing slash command
- Renaming or removing a file that existing derived projects already have
- Changing the branch naming convention or worktree structure
- Changing required Makefile targets or their expected exit codes
- Changing CLAUDE.md sections that personas rely on

Print the classification and rationale before proceeding.

---

## Step 3 — Route to the Correct Persona

| Change type | Persona |
|---|---|
| `.github/workflows/**`, `scripts/**`, `Makefile` | gitops-manager |
| `CLAUDE.md`, `.claude/commands/**` | docs |
| `quality-specs/examples/**`, `quality-specs/checks.sh` | developer |
| `.gitleaks.toml`, `.gitignore`, security-related workflows | security |
| `docs/**`, `README.md` | docs |
| New `.claude/quality.md` structure or `.claude/scaffold-source.md` | docs |

Print the routed persona and confirm with the user before proceeding.

---

## Step 4 — Draft the Change

Make the proposed change and present a diff. For breaking changes, draft a migration note to include in the PR body explaining what derived projects must do to update.

**Migration note format:**
```
## Migration Note

This change affects: <which file/behavior>

Derived projects that were created from an earlier version of this template
must take the following action:
  1. <specific step>
  2. <specific step>
```

---

## Step 5 — Human Confirmation Gate

Print:
> "Here is the proposed change. Summary:
> - Files changed: <list>
> - Impact: <additive / breaking with migration note>
> - Routed to: persona/<name>
>
> Reply **'proceed'** to open a PR, or **'cancel'** to abort."

Do not open any PR or commit anything until the user explicitly says 'proceed'.

---

## Step 6 — Open a PR

Commit the change on the appropriate persona branch and open a PR targeting `develop`:

```bash
git checkout persona/<name>
git pull origin persona/<name>
# make the edit
git add <files>
git commit -m "docs(scaffold): <one-line description>

<migration note if breaking>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
gh pr create --repo "$REPO" --base develop \
  --title "<title>" \
  --body "<body including migration note if breaking>"
```

---

## Step 7 — Report

Print:
```
Scaffold update proposed.
PR: <url>
Persona: <name>
Impact: <additive / breaking>
<migration note if applicable>

To merge: /watch-work merge-manager
```
