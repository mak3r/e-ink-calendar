#!/usr/bin/env bash
# quality-specs/examples/go.sh — Go quality checks
# Copy to quality-specs/checks.sh and customize.
set -euo pipefail

FAILED=0

# Check for TODO comments in non-test files
echo "Checking for TODO comments in source files..."
if grep -rn "TODO" --include="*.go" --exclude="*_test.go" . 2>/dev/null | grep -v "^Binary" | grep -q .; then
  echo "FAIL: TODO comments found in source files:"
  grep -rn "TODO" --include="*.go" --exclude="*_test.go" . | grep -v "^Binary"
  FAILED=1
else
  echo "PASS: No TODO comments in source files"
fi

# Check that all exported functions have godoc comments
echo "Checking for missing godoc comments on exported functions..."
# Uses go vet with the 'commentedoutcode' or a simple grep heuristic
MISSING=$(grep -rn "^func [A-Z]" --include="*.go" --exclude="*_test.go" . 2>/dev/null | \
  while IFS=: read -r file line rest; do
    prev_line=$(sed -n "$((line-1))p" "$file" 2>/dev/null)
    if ! echo "$prev_line" | grep -q "^//"; then
      echo "$file:$line: exported function missing godoc comment: $rest"
    fi
  done)
if [ -n "$MISSING" ]; then
  echo "FAIL: Missing godoc comments:"
  echo "$MISSING"
  FAILED=1
else
  echo "PASS: All exported functions have godoc comments"
fi

# Run gosec security scanner if available
if command -v gosec > /dev/null 2>&1; then
  echo "Running gosec security scan..."
  if ! gosec -quiet ./... 2>/dev/null; then
    echo "FAIL: gosec found security issues"
    FAILED=1
  else
    echo "PASS: gosec clean"
  fi
else
  echo "SKIP: gosec not installed (install with: go install github.com/securego/gosec/v2/cmd/gosec@latest)"
fi

# Check that go.mod and go.sum are in sync
echo "Checking go.mod/go.sum sync..."
if ! go mod verify > /dev/null 2>&1; then
  echo "FAIL: go mod verify failed — run 'go mod tidy'"
  FAILED=1
else
  echo "PASS: go.mod/go.sum in sync"
fi

exit $FAILED
