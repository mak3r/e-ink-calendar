# /create-project

Bootstrap a new project derived from this scaffolding template. Run this command when a user says "create a new project using this scaffolding" or similar.

**Human confirmation required before any GitHub action.** Do not create a repo, push any code, or run setup without explicit user approval at Step 3.

---

## Step 1 — Gather Inputs

Ask the user for all of the following before taking any action:

1. **Repo name**: what should the new GitHub repository be called? (e.g., `my-new-project`)
2. **GitHub owner**: which GitHub user or org should own it? (default: detect from `gh api user --jq '.login'`)
3. **Description**: one sentence describing what the project does
4. **Language/stack**: primary programming language and any key frameworks (e.g., "Go 1.24 + Cobra CLI", "Python 3.12 + FastAPI", "Node 22 + Express")
5. **Integration branch**: use a `develop` branch as integration branch? (default: yes; say no to merge directly to `main`)
6. **Visibility**: public or private? (default: public)

Confirm all inputs before proceeding:
```
New repo:     <owner>/<name>
Description:  <description>
Stack:        <language/stack>
Develop:      <yes/no>
Visibility:   <public/private>

Proceed? (yes/no)
```

---

## Step 2 — Confirm

Only proceed when the user says 'yes' (or equivalent).

---

## Step 3 — Create GitHub Repo from Template

```bash
gh repo create <owner>/<name> \
  --template mak3r/claude-scaffolding \
  --description "<description>" \
  --<public|private> \
  --clone
```

This creates the new repo and clones it locally. The current working directory after clone is `<name>/`.

---

## Step 4 — Run Setup

```bash
cd <name>
bash scripts/setup.sh --repo <owner>/<name>
```

This creates worktrees, branches, GitHub labels, and branch protection.

If the user chose no `develop` branch, run:
```bash
bash scripts/setup.sh --repo <owner>/<name> --no-develop
```

---

## Step 5 — Customize CLAUDE.md

Edit the **Project Purpose** section in `CLAUDE.md`:
- Replace the TODO block with a paragraph describing what the project does
- Add the primary language/runtime
- Add the module/package identifier if known

Edit the **Personas and Branch Ownership** table:
- Fill in the "Owns" column for `developer` and `test-engineer` with the expected source directories (use generic placeholders if not yet decided: `src/**`, `lib/**`, `cmd/**`)
- Fill in the **Phase Determination** table with project-specific components

---

## Step 6 — Wire the Makefile

Ask the user for their build, test, and lint commands:

> "What commands should I use for:
> - `make build` (compile or package the project)
> - `make test` (run unit tests)
> - `make lint` (run static analysis)
>
> Leave any blank to keep the stub (exits 1 to force you to fill it in later)."

Replace the stub bodies in `Makefile` with the user's commands.

---

## Step 7 — Copy Quality Spec

Check if a matching example exists in `quality-specs/examples/`:
```bash
ls quality-specs/examples/
```

If a match exists for the project's language, copy it:
```bash
cp quality-specs/examples/<language>.sh quality-specs/checks.sh
chmod +x quality-specs/checks.sh
```

Tell the user: "Copied `quality-specs/examples/<language>.sh` to `quality-specs/checks.sh`. Review and customize it for your project."

If no match exists, create an empty stub:
```bash
cat > quality-specs/checks.sh << 'EOF'
#!/usr/bin/env bash
# Quality checks for <project name>
# Add project-specific checks here. Exit non-zero on failure.
echo "No quality checks configured yet."
exit 0
EOF
chmod +x quality-specs/checks.sh
```

---

## Step 8 — Draft .claude/quality.md

Update `.claude/quality.md` with what is known so far:
- Fill in the language/framework in the "Language and framework conventions" section
- Fill in what `make test` means based on the test command provided in Step 6
- Note that `quality-specs/checks.sh` is a stub if no example was found

---

## Step 9 — Record Scaffold Source

Fill in `.claude/scaffold-source.md`:
```bash
SCAFFOLD_SHA=$(gh api repos/mak3r/claude-scaffolding/git/ref/heads/main --jq '.object.sha' | cut -c1-8)
TODAY=$(date +%Y-%m-%d)
```

Edit the file to replace the placeholder values with the actual SHA and date.

---

## Step 10 — Commit and Push

```bash
git add CLAUDE.md Makefile quality-specs/checks.sh .claude/quality.md .claude/scaffold-source.md
git commit -m "chore: initial project customization from claude-scaffolding template

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin develop
```

Then open a PR from `develop` to `main`:
```bash
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
gh pr create --repo "$REPO" --base main --head develop \
  --title "chore: initial project setup" \
  --body "Initial customization of the claude-scaffolding template for this project.

## What was customized
- CLAUDE.md: Project Purpose and Phase Determination filled in
- Makefile: build/test/lint targets wired
- quality-specs/checks.sh: quality gate configured
- .claude/quality.md: quality definition drafted
- .claude/scaffold-source.md: scaffold origin recorded"
```

---

## Step 11 — Print Next Steps

```
Project created: https://github.com/<owner>/<name>

✅ Repo created from template
✅ Branches and worktrees set up
✅ GitHub labels created
✅ Branch protection enabled
✅ CLAUDE.md customized
✅ Makefile wired
✅ Quality spec initialized
✅ Initial PR open

Remaining manual steps:
  1. In GitHub Settings > General: confirm "Template repository" is NOT checked
     (this is a project, not a template — uncheck if auto-enabled)
  2. Review and customize quality-specs/checks.sh for your project
  3. Fill in docs/architecture.md with your system design
  4. Fill in docs/acceptance-criteria.md with acceptance criteria
  5. Merge the initial PR: /watch-work merge-manager

To start working: /persona-setup (from the appropriate worktree)
To see what needs to be done: /work-summary
```
