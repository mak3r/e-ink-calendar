# /watch-work

Adopt the persona named in $ARGUMENTS and work through open issues and PRs until the session ends or no work remains.

**Autonomous operation**: Do not ask for confirmation at any point. Invoking this skill is authorization to do all the work. Never ask "want me to proceed?", "shall I work on this?", or any similar question. Scan → pick → act, without pausing.

## Argument Parsing

Parse `$ARGUMENTS` as one of:

| Form | Meaning |
|---|---|
| `<persona>` | Work through items once, then stop |
| `<persona> <minutes>` | Work continuously, polling every ~4.5 min for `<minutes>` minutes |
| `<persona> until:<iso_timestamp>` | Work continuously until absolute deadline |

Valid persona names: `developer`, `test-engineer`, `security`, `qa`, `gitops-manager`, `docs`, `merge-manager`, `product-designer`, `triage`

If the persona name is not in that list, stop immediately and print:
```
Unknown persona: "<name>". Valid personas: developer, test-engineer, security, qa, gitops-manager, docs, merge-manager, product-designer, triage
```

On first call with `<minutes>`, compute `end_time = now + <minutes> minutes` as ISO 8601 UTC. Subsequent self-scheduled wake-ups pass `until:<end_time>` to preserve the deadline.

If persona is `triage`: print "The triage persona is invoked via /triage, not /watch-work. Run /triage instead." and stop.

---

## Step 1 — Adopt the Persona

Read `CLAUDE.md` and `.claude/quality.md` now to confirm:
- Which files you are allowed to modify
- Which branch you operate on
- Any hard rules that apply to this persona
- What `make test` and `make quality` mean for this project

**Branch validation by persona:**

- **developer**: Valid starting states are `develop` or `feature/developer/*`. If on `develop`, create a feature branch in Step 4. If on `feature/developer/<name>`, continue work. If on any other branch, stop and tell the user.
- **test-engineer**: Valid starting states are `develop`, `feature/developer/*`, or `persona/test-engineer`. Select the correct branch in Step 2 based on available work. If on any other branch, stop and tell the user.
- **All other personas**: Current branch must match `persona/<name>` exactly. If not, tell the user which branch to switch to and stop.

---

## Step 2 — Scan for Work (token-efficient, one pass)

> **Always fresh.** Do not rely on any prior in-session memory of what was "already handled" — the queue changes between runs. Verify current state from GitHub, not from conversation history.

> **test-engineer only — branch selection before scanning:**
> Run the queries below first (without checking out anything), then:
> 1. If there are open `feature/developer/*` PRs or issues labeled `persona/test-engineer` + `type/task` for a feature branch: prioritize those; run `git fetch origin && git checkout feature/developer/<name>`
> 2. Otherwise if there are issues for test infrastructure work: `git checkout persona/test-engineer && git pull`
> 3. If both exist, choose feature work
> 4. If no work exists, go to Step 5

Determine the repo:
```bash
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
REPO_NAME=$(basename "$REPO")
```

**Open issues assigned to this persona:**
```bash
gh issue list \
  --repo "$REPO" \
  --state open \
  --label "persona/<persona-name>" \
  --json number,title,labels,updatedAt \
  --limit 25 \
  --jq '.[] | "#\(.number)  \(.title)  \([.labels[].name] | join(","))  [updated \(.updatedAt[:10])]"'
```

**Open PRs needing this persona's attention:**

If persona is `merge-manager`, fetch ALL open PRs targeting `develop`:
```bash
gh pr list \
  --repo "$REPO" \
  --state open \
  --base develop \
  --json number,title,headRefName,reviewDecision,statusCheckRollup,comments \
  --limit 30 \
  --jq '.[] | "#\(.number)  \(.title)  [\(.headRefName)]  review:\(.reviewDecision // "PENDING")  ci:\(if (.statusCheckRollup // [] | length) == 0 then "unknown" elif (.statusCheckRollup | all(.[]; .state == "SUCCESS")) then "green" else "failing" end)  comments:\(.comments | length)"'
```

All other personas, fetch PRs on their branch:
```bash
gh pr list \
  --repo "$REPO" \
  --state open \
  --json number,title,headRefName,reviewDecision,comments,reviewRequests \
  --limit 30 \
  --jq '[.[] | select(
      (.headRefName | startswith("feature/developer/")) or
      (.headRefName | startswith("persona/")) or
      (.reviewRequests | length > 0)
  )] | .[] | "#\(.number)  \(.title)  [\(.headRefName)]  review:\(.reviewDecision // "PENDING")  comments:\(.comments | length)"'
```

**Stranded persona commits (merge-manager only)** — check whether any persona worktree has commits not yet in `develop` and no open PR:
```bash
WORKTREES_DIR="../${REPO_NAME}-worktrees"
for name in security gitops-manager docs qa product-designer; do
  count=$(git -C "$WORKTREES_DIR/$name" rev-list --count origin/develop..HEAD 2>/dev/null || echo 0)
  if [ "$count" -gt 0 ]; then
    branch=$(git -C "$WORKTREES_DIR/$name" branch --show-current)
    open_pr=$(gh pr list --repo "$REPO" --state open --head "$branch" --json number --jq '.[0].number // ""')
    if [ -z "$open_pr" ]; then
      echo "STRANDED: $name ($branch) has $count commit(s) ahead of develop with no open PR"
      git -C "$WORKTREES_DIR/$name" log --oneline origin/develop..HEAD
    fi
  fi
done
```

For any stranded persona branch: open a PR (`gh pr create --repo "$REPO" --base develop --head <branch>`) and flag it with highest priority.

**Linked PRs for issues in your queue** — for each issue number found (up to 5):
```bash
gh issue view <n> --repo "$REPO"
```
If a linked PR appears, add it to the queue.

Print the combined issue + PR queue, then proceed to Step 3.

---

## Step 3 — Pick the Highest-Priority Item

**If persona is `merge-manager`**, use this priority order:

| Priority | Condition |
|---|---|
| 0 | Stranded persona branch detected — open a PR immediately |
| 1 | PR with `ci:green` and `review:APPROVED` — ready to merge |
| 2 | PR with `ci:failing` — create or update a blocking issue |
| 3 | PR with open `type/security` issues on its branch — comment that it is blocked |
| 4 | PR with `review:CHANGES_REQUESTED` — already handled by owning persona; add comment if stale |
| 5 | PR with `review:PENDING` and `ci:green` — leave a review |

**All other personas**, score every item (prefer oldest `updatedAt` in ties):

| Priority | Condition |
|---|---|
| 1 | PR on your branch with `review:CHANGES_REQUESTED` — blocking a merge |
| 2 | PR where you are a requested reviewer |
| 3 | Issue labeled `type/bug` + `phase/1` |
| 4 | Issue labeled `type/bug` + `phase/2` (or higher) |
| 5 | Issue labeled `type/task` + `phase/1` |
| 6 | Issue labeled `type/task` + `phase/2` (or higher) |
| 7 | Anything else, oldest first |

If the queue is empty, go to Step 5.

---

## Step 4 — Do the Work

Do not announce the item and wait. Fetch details and begin immediately.

1. **Fetch full details:**
   - Issue: `gh issue view <n> --repo "$REPO"` — check for a linked PR in the output
   - PR: `gh pr view <n> --repo "$REPO" --comments`

2. **Understand what's needed.** Read only the files required to complete the task — no broad codebase exploration.

3. **Make the changes** within your persona's designated file scope from CLAUDE.md.

   > **developer — branch lifecycle:**
   > - If on `develop`: create a branch slug from the issue title and number: `git checkout -b feature/developer/<n>-<slug> origin/develop`
   > - After the PR for this issue merges: `git checkout develop && git pull origin develop && git branch -d feature/developer/<slug>`

   > **test-engineer — branch cleanup:**
   > - After completing work on a feature branch: push, then `git checkout develop && git pull origin develop`
   > - After completing test-infra work on `persona/test-engineer`: push, then `git checkout develop && git pull origin develop`

4. **Validate:**
   - Read `.claude/quality.md` to determine the correct validation commands for this project
   - Always run `make test` if any source or test files were modified
   - Always run `make quality` before declaring work complete

5. **Commit** using conventional commit style:
   ```
   <type>(<scope>): <description>

   Closes #<issue-number>

   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
   ```

5b. **Verify the commit SHA exists:**
   ```bash
   git rev-parse --verify <sha>
   ```
   Do not reference a SHA in any issue comment unless this command returns successfully. If it fails, the commit did not happen — do not fabricate or guess a SHA.

5c. **Open a PR** (branch-owning personas only — all except `merge-manager` and `product-designer`): if no open PR already targets `develop` for this branch, open one now:
   ```bash
   gh pr create --repo "$REPO" --base develop --title "<title>" --body "<body>"
   ```
   **Work is not done until a PR is open.** A commit with no open PR is stranded work — it can never reach `develop`.

5d. **Post-merge sync (merge-manager only)** — immediately after a successful `gh pr merge`, identify the merged branch's persona and rebase that worktree:
   ```bash
   WORKTREES_DIR="../${REPO_NAME}-worktrees"
   # For persona/<name> branches:
   git -C "$WORKTREES_DIR/<name>" fetch origin
   git -C "$WORKTREES_DIR/<name>" rebase origin/develop
   git -C "$WORKTREES_DIR/<name>" push --force-with-lease origin persona/<name>
   ```
   Also scan all other persona worktrees and rebase any that are more than 5 commits behind `origin/develop`.

5e. **Post HANDOFF comment** before re-labeling:
   ```
   HANDOFF → persona/<next-persona>

   Completed: <one-line summary>
   Next action: <specific instructions for next persona>
   Blocked until: <dependency issue #N or "unblocked">
   PR: <url or "no PR — issue only">
   ```

6. **Update the issue/PR** — comment must include all of the following (real output, not paraphrased):
   - Output of `git log --oneline -1` (proves the commit exists)
   - PR URL
   - For file-level fixes: output of a `grep` or `head` command confirming the change is in the file

   If you cannot produce real output, the commit did not happen — do not close the issue.

---

## Step 5 — Loop or Schedule

After completing an item (or finding an empty queue):

**Single-check mode** (no duration): stop and print a summary of what was completed.

**Watch mode:**
- Is `now < end_time`?
  - **Yes and work was just completed**: immediately return to Step 2
  - **Yes and queue was empty**: call `ScheduleWakeup` with `delaySeconds: 270`, `reason: "Polling for new work for <persona>"`, `prompt: "/watch-work <persona> until:<end_time_iso>"`
  - **No**: print `Session complete for <persona>. Items completed this session: <N>.` and stop

---

## Token Efficiency Rules

1. `--json <field-list>` on every `gh` call — never omit the field list
2. `--jq` on every list call — only formatted strings reach context, not raw JSON
3. Read only files needed for the current task — no broad codebase exploration
4. Never quote issue or PR body verbatim unless directly relevant to a code decision
5. One issue-list call and one PR-list call per scan cycle, plus up to 5 `gh issue view` calls to discover linked PRs
