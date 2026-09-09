#!/usr/bin/env bash
# scripts/setup.sh — post-clone setup for a claude-scaffolding derived project
#
# Creates worktrees, persona branches, GitHub labels, and branch protection.
# Idempotent: safe to run multiple times.
#
# Usage:
#   bash scripts/setup.sh [--repo owner/name] [--no-develop]
#
# Options:
#   --repo owner/name   GitHub repo (default: detected from git remote)
#   --no-develop        Skip creating the develop integration branch
#                       (use when merging directly to main)

set -euo pipefail

# ─── Parse args ──────────────────────────────────────────────────────────────
NO_DEVELOP=false
GITHUB_REPO=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --repo) GITHUB_REPO="$2"; shift 2 ;;
    --no-develop) NO_DEVELOP=true; shift ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# ─── Detect repo name and GitHub slug ────────────────────────────────────────
REPO_NAME=$(basename "$(git rev-parse --show-toplevel)")
WORKTREES_DIR="../${REPO_NAME}-worktrees"

if [ -z "$GITHUB_REPO" ]; then
  ORIGIN=$(git remote get-url origin 2>/dev/null || echo "")
  if [ -z "$ORIGIN" ]; then
    echo "ERROR: No git remote 'origin' found and --repo was not provided."
    echo "Either push to GitHub first or run: bash scripts/setup.sh --repo owner/repo-name"
    exit 1
  fi
  GITHUB_REPO=$(echo "$ORIGIN" | sed 's|.*github.com[:/]||; s|\.git$||')
fi

echo "=== Claude Scaffolding Setup ==="
echo "Repo name:    $REPO_NAME"
echo "GitHub repo:  $GITHUB_REPO"
echo "Worktrees:    $WORKTREES_DIR"
echo "Develop:      $([ "$NO_DEVELOP" = true ] && echo "skipped" || echo "yes")"
echo ""

# ─── Phase 1: Local git setup ────────────────────────────────────────────────
echo "── Phase 1: Branch setup ──"

INTEGRATION_BRANCH="develop"
if [ "$NO_DEVELOP" = true ]; then
  INTEGRATION_BRANCH="main"
fi

if [ "$NO_DEVELOP" = false ]; then
  if ! git show-ref --verify refs/heads/develop > /dev/null 2>&1; then
    echo "Creating branch: develop"
    git checkout -b develop
  else
    echo "Branch exists: develop"
  fi
  git push -u origin develop 2>/dev/null && echo "Pushed: develop" || echo "develop already pushed"
fi

for persona in security gitops-manager docs qa product-designer; do
  branch="persona/$persona"
  if ! git show-ref --verify "refs/heads/$branch" > /dev/null 2>&1; then
    echo "Creating branch: $branch"
    git checkout -b "$branch" "$INTEGRATION_BRANCH"
    git checkout "$INTEGRATION_BRANCH"
  else
    echo "Branch exists: $branch"
  fi
  git push -u origin "$branch" 2>/dev/null && echo "Pushed: $branch" || echo "$branch already pushed"
done

# Return to main
git checkout main 2>/dev/null || true

echo ""

# ─── Phase 2: Worktrees ──────────────────────────────────────────────────────
echo "── Phase 2: Worktrees ──"

mkdir -p "$WORKTREES_DIR"

for persona in security gitops-manager docs qa product-designer; do
  target="$WORKTREES_DIR/$persona"
  if [ -d "$target" ]; then
    echo "Worktree exists: $target"
  else
    echo "Adding worktree: $target (persona/$persona)"
    git worktree add "$target" "persona/$persona"
  fi
done

DEVELOPMENT_WT="$WORKTREES_DIR/development"
if [ -d "$DEVELOPMENT_WT" ]; then
  echo "Worktree exists: $DEVELOPMENT_WT"
else
  echo "Adding worktree: $DEVELOPMENT_WT ($INTEGRATION_BRANCH)"
  git worktree add "$DEVELOPMENT_WT" "$INTEGRATION_BRANCH"
fi

echo ""

# ─── Phase 3: GitHub labels ──────────────────────────────────────────────────
echo "── Phase 3: GitHub labels ──"

create_label() {
  local name="$1" color="$2" desc="$3"
  gh label create "$name" --color "$color" --description "$desc" --repo "$GITHUB_REPO" --force 2>/dev/null \
    && echo "Label: $name" || echo "Label (skipped): $name"
}

# Persona labels (blue)
create_label "persona/developer"       "0075ca" "Owned by: developer"
create_label "persona/test-engineer"   "0075ca" "Owned by: test-engineer"
create_label "persona/security"        "0075ca" "Owned by: security"
create_label "persona/qa"             "0075ca" "Owned by: qa"
create_label "persona/gitops-manager"  "0075ca" "Owned by: gitops-manager"
create_label "persona/docs"           "0075ca" "Owned by: docs"
create_label "persona/product-designer" "0075ca" "Owned by: product-designer"

# Phase labels (shades of gray)
create_label "phase/1-foundation"    "636e7b" "Scaffolding, CI, build system"
create_label "phase/2-core-logic"    "7d8590" "Core business logic"
create_label "phase/3-integration"   "9ea7b1" "External integrations, APIs"
create_label "phase/4-hardening"     "bac0c6" "E2E tests, docs, release"

# Type labels
create_label "type/bug"      "d73a4a" "Something isn't working"
create_label "type/task"     "0e8a16" "Work to be done"
create_label "type/security" "b60205" "Security concern or finding"
create_label "type/freeze"   "6e40c9" "Pause signal — no agent may work on this"

# Status labels
create_label "status/blocked" "e4e669" "Blocked by another issue"

echo ""

# ─── Phase 4: Branch protection ──────────────────────────────────────────────
echo "── Phase 4: Branch protection ──"

# Protect main
# No PR review requirement — all personas share one GitHub account, making
# peer review impossible. The merge-manager enforces quality gates via CI.
echo "Setting branch protection on: main"
gh api --method PUT \
  "repos/$GITHUB_REPO/branches/main/protection" \
  --input - << 'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["build-and-test", "secret-scan"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
echo "Branch protection set: main"

# Protect develop (if used)
if [ "$NO_DEVELOP" = false ]; then
  echo "Setting branch protection on: develop"
  gh api --method PUT \
    "repos/$GITHUB_REPO/branches/develop/protection" \
    --input - << 'EOF'
{
  "required_status_checks": {
    "strict": false,
    "contexts": ["build-and-test", "secret-scan"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
  echo "Branch protection set: develop"
fi

echo ""

# ─── Phase 5: Repo security ──────────────────────────────────────────────────
echo "── Phase 5: Repo security ──"
echo "Triggering initialize-repo-security workflow..."
gh workflow run initialize-repo-security.yml --repo "$GITHUB_REPO" 2>/dev/null \
  && echo "Workflow triggered" || echo "Workflow trigger skipped (may need a push to main first)"

echo ""

# ─── Done ────────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════"
echo "Setup complete!"
echo ""
echo "Worktree layout:"
echo "  $REPO_NAME/                ← main clone (merge-manager, triage)"
echo "  ${REPO_NAME}-worktrees/"
echo "    security/                ← persona/security"
echo "    gitops-manager/          ← persona/gitops-manager"
echo "    docs/                    ← persona/docs"
echo "    qa/                      ← persona/qa"
echo "    product-designer/        ← persona/product-designer"
echo "    development/             ← developer + test-engineer"
echo ""
echo "Manual steps required:"
echo "  1. Fill in CLAUDE.md: Project Purpose section + file ownership table"
echo "  2. Replace stub targets in Makefile with real build/test/lint commands"
echo "  3. Copy quality-specs/examples/<language>.sh to quality-specs/checks.sh"
echo "  4. Write .claude/quality.md describing quality for this project"
echo "  5. In GitHub Settings > General: add a repository description"
echo "  6. In GitHub Settings > General: check 'Template repository' if this IS a template"
echo "     (leave unchecked if this is a derived project)"
echo "  7. Fill in docs/architecture.md, docs/acceptance-criteria.md, docs/runbook.md"
echo "  8. Create a PAT with Administration:write (fine-grained) or repo (classic) scope,"
echo "     then: gh secret set REPO_ADMIN_TOKEN --repo $GITHUB_REPO"
echo "     This is required for the initialize-repo-security workflow to set interaction limits."
echo "══════════════════════════════════════════════"
