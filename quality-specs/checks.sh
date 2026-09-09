#!/usr/bin/env bash
# quality-specs/examples/python.sh — Python quality checks
# Copy to quality-specs/checks.sh and customize.
set -euo pipefail

FAILED=0

# Check for TODO comments in non-test files
echo "Checking for TODO comments in source files..."
if find . -name "*.py" -not -name "test_*" -not -path "*/tests/*" -not -path "*/.venv/*" \
    -exec grep -ln "TODO" {} + 2>/dev/null | grep -q .; then
  echo "FAIL: TODO comments found:"
  find . -name "*.py" -not -name "test_*" -not -path "*/tests/*" -not -path "*/.venv/*" \
    -exec grep -n "TODO" {} + 2>/dev/null
  FAILED=1
else
  echo "PASS: No TODO comments"
fi

# Run bandit security scanner if available
if command -v bandit > /dev/null 2>&1; then
  echo "Running bandit security scan..."
  if ! bandit -r . -x '.venv,tests,test_*' -ll -q 2>/dev/null; then
    echo "FAIL: bandit found security issues"
    FAILED=1
  else
    echo "PASS: bandit clean"
  fi
else
  echo "SKIP: bandit not installed (install with: pip install bandit)"
fi

# Check for missing type annotations on public functions (requires mypy)
if command -v mypy > /dev/null 2>&1; then
  echo "Running mypy type check..."
  if ! mypy . --ignore-missing-imports --no-error-summary 2>/dev/null; then
    echo "FAIL: mypy type errors found"
    FAILED=1
  else
    echo "PASS: mypy clean"
  fi
else
  echo "SKIP: mypy not installed (install with: pip install mypy)"
fi

exit $FAILED
