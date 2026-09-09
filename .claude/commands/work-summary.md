# /work-summary

Print a human-readable execution queue showing all open issues grouped by persona, blocked vs. unblocked status, and the recommended work order.

**Read-only**: this command never creates issues, commits code, or modifies anything.

---

## Step 1 — Fetch all open issues

```bash
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
gh issue list \
  --repo "$REPO" \
  --state open \
  --json number,title,labels,updatedAt \
  --limit 100 \
  --jq '.[] | {
    number: .number,
    title: .title,
    labels: [.labels[].name],
    updated: .updatedAt[:10]
  }'
```

## Step 2 — Fetch open PRs needing review

```bash
gh pr list \
  --repo "$REPO" \
  --state open \
  --json number,title,headRefName,reviewDecision,statusCheckRollup \
  --limit 30 \
  --jq '.[] | {
    number: .number,
    title: .title,
    branch: .headRefName,
    review: (.reviewDecision // "PENDING"),
    ci: (if (.statusCheckRollup // [] | length) == 0 then "unknown"
         elif (.statusCheckRollup | all(.[]; .state == "SUCCESS")) then "green"
         else "failing" end)
  }'
```

## Step 3 — Render the queue

Group and print in this format:

```
═══════════════════════════════════════════════════════════
WORK SUMMARY — <repo-name>
<date>
═══════════════════════════════════════════════════════════

NEEDS HUMAN (merge-manager action required):
  PR #<n>  <title>  [ci:green, review:PENDING → merge-manager must review]
  PR #<n>  <title>  [ci:green, review:APPROVED → ready to merge]

READY TO WORK (unblocked, no status/blocked label):
  persona/developer      #<n>  <title>    phase/<n>  type/<t>
  persona/gitops-manager #<n>  <title>    phase/<n>  type/<t>
  ...

BLOCKED (has status/blocked label):
  persona/security  #<n>  <title>    blocked by <issue text if available>
  ...

FROZEN (has type/freeze label — no agent may touch these):
  #<n>  <title>

NO OPEN WORK:
  persona/qa             — no open issues
  persona/product-designer — no open issues
  ...
═══════════════════════════════════════════════════════════
RECOMMENDED EXECUTION ORDER (unblocked items only):

  1. /watch-work <persona>   ← <reason: phase/1 bug, oldest, etc.>
  2. /watch-work <persona>
  ...
═══════════════════════════════════════════════════════════
```

**Sorting within READY TO WORK:**
- `type/bug` before `type/task`
- `phase/1` before `phase/2` before `phase/3` before `phase/4`
- Oldest `updatedAt` first within the same priority

**Recommended execution order** lists each persona once, ordered by the priority of their highest-priority unblocked issue. This is the sequence a human project manager would use to unblock the most work.

## Step 4 — HANDOFF scan (bonus)

After the main table, scan the 10 most recently updated issues for issues that have been re-labeled (e.g., now assigned to `persona/developer`) but whose last comment does not contain a `HANDOFF →` block. Flag these:

```
HANDOFF AUDIT:
  #<n>  <title> — labeled persona/developer but last comment has no HANDOFF block (check manually)
```

This catches issues that were re-labeled without the required handoff comment.
