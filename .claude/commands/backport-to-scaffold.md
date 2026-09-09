# /backport-to-scaffold

Propose an improvement from this derived project back to the upstream `mak3r/claude-scaffolding` template. Use this when you've made a generic improvement (to a slash command, workflow, or other scaffolding file) that should benefit all projects derived from the template.

**Human confirmation required** before any PR is opened in the scaffold repo.

---

## Step 1 — Read the Scaffold Source

```bash
cat .claude/scaffold-source.md
```

Extract:
- `scaffold-repo` — the upstream template repo (e.g., `mak3r/claude-scaffolding`)
- `scaffold-version` — the SHA this project was based on

If `scaffold-source.md` does not exist or `scaffold-repo` is not set, print:
```
Cannot backport: .claude/scaffold-source.md is missing or incomplete.
This file is created by /create-project. If you created this project manually,
add the following to .claude/scaffold-source.md:
  scaffold-repo: mak3r/claude-scaffolding
  scaffold-version: <sha of scaffold at creation time>
```
Then stop.

---

## Step 2 — Identify the File to Contribute

Ask the user:
> "Which file do you want to contribute back to the scaffold? (e.g., `.claude/commands/watch-work.md`, `.github/workflows/ci.yml`)"

Alternatively, if no specific file is named, show files that have diverged from the scaffold version:
```bash
SCAFFOLD_REPO=$(grep 'scaffold-repo:' .claude/scaffold-source.md | awk '{print $2}')
SCAFFOLD_SHA=$(grep 'scaffold-version:' .claude/scaffold-source.md | awk '{print $2}')

# For each scaffolding file in common locations, show if it differs
for f in CLAUDE.md .claude/commands/*.md .github/workflows/*.yml Makefile .gitleaks.toml; do
  [ -f "$f" ] || continue
  scaffold_content=$(gh api "repos/$SCAFFOLD_REPO/contents/$f" --jq '.content' 2>/dev/null | base64 -d)
  if [ -n "$scaffold_content" ] && ! diff -q <(echo "$scaffold_content") "$f" > /dev/null 2>&1; then
    echo "DIVERGED: $f"
  fi
done
```

---

## Step 3 — Check for Project-Specific Content

Read the file the user wants to contribute and scan for content that would not make sense in a generic template:

- Repo-specific names (this project's repo name, owner)
- Language-specific commands hard-coded (not via Makefile targets)
- Absolute file paths specific to this project's directory structure
- Project-specific API keys, URLs, or credentials (even placeholders)
- Phase Determination table rows that reference this project's specific components

Print a list of any found items:
```
⚠️  Project-specific content detected in <file>:
  Line <n>: "<text>" — this references this project's <repo name / language / path>
```

Ask the user to confirm whether these items should be:
- Removed (replaced with generic placeholders)
- Kept as-is (user believes they are generic enough)

---

## Step 4 — Prepare the Generic Version

Create a version of the file with project-specific content replaced by generic placeholders.
Present it as a diff and ask for user approval.

---

## Step 5 — Human Confirmation Gate

Print:
> "Here is what I'll contribute to `<scaffold-repo>`:
> - File: `<path>`
> - Change: <summary of what's different from the current scaffold version>
> - Project-specific content: <removed/kept as-is>
>
> This will open a PR in `<scaffold-repo>`. Reply **'contribute'** to proceed, or **'cancel'** to abort."

Do not open any PR until the user says 'contribute'.

---

## Step 6 — Open a PR in the Scaffold Repo

```bash
SCAFFOLD_REPO=$(grep 'scaffold-repo:' .claude/scaffold-source.md | awk '{print $2}')
THIS_REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')

# Create a branch in the scaffold repo and open a PR
BRANCH="backport/$(date +%Y%m%d)-<file-slug>"
gh api --method POST "repos/$SCAFFOLD_REPO/git/refs" \
  --field ref="refs/heads/$BRANCH" \
  --field sha="$(gh api repos/$SCAFFOLD_REPO/git/ref/heads/main --jq '.object.sha')"

# Use gh to update the file content in that branch
# (requires the file content to be base64-encoded)
CONTENT=$(base64 < <prepared-generic-file>)
SHA=$(gh api "repos/$SCAFFOLD_REPO/contents/<path>" --jq '.sha')
gh api --method PUT "repos/$SCAFFOLD_REPO/contents/<path>" \
  --field message="<commit message>" \
  --field content="$CONTENT" \
  --field branch="$BRANCH" \
  --field sha="$SHA"

gh pr create --repo "$SCAFFOLD_REPO" --base main --head "$BRANCH" \
  --title "<title>" \
  --body "Backport from $THIS_REPO.

## What changed
<description of the improvement>

## Why this is generic
<why this improvement belongs in the template, not just in $THIS_REPO>

## Testing
Tested in $THIS_REPO. The improvement was validated by <what was validated>."
```

---

## Step 7 — Report

```
Backport PR opened: <url>

The improvement to <file> has been proposed to <scaffold-repo>.
Once merged, future projects created from the template will include this improvement.

To update this project when the scaffold is updated, re-run /create-project
or manually copy the updated file from the scaffold repo.
```
