#!/usr/bin/env bash
# quality-specs/examples/node.sh — Node.js quality checks
# Copy to quality-specs/checks.sh and customize.
set -euo pipefail

FAILED=0

# Check for TODO comments in non-test source files
echo "Checking for TODO comments in source files..."
if find . \( -name "*.ts" -o -name "*.js" -o -name "*.mts" \) \
    -not -name "*.test.*" -not -name "*.spec.*" \
    -not -path "*/node_modules/*" -not -path "*/dist/*" -not -path "*/.next/*" \
    -exec grep -ln "TODO" {} + 2>/dev/null | grep -q .; then
  echo "FAIL: TODO comments found"
  find . \( -name "*.ts" -o -name "*.js" \) \
    -not -name "*.test.*" -not -path "*/node_modules/*" \
    -exec grep -n "TODO" {} + 2>/dev/null
  FAILED=1
else
  echo "PASS: No TODO comments"
fi

# Check package.json for missing required fields
echo "Checking package.json required fields..."
for field in name version description license; do
  if ! node -e "const p = require('./package.json'); if (!p.$field) process.exit(1)" 2>/dev/null; then
    echo "FAIL: package.json missing required field: $field"
    FAILED=1
  fi
done

# Run npm audit for security vulnerabilities (high and critical only)
echo "Checking for known vulnerabilities..."
if ! npm audit --audit-level=high 2>/dev/null; then
  echo "FAIL: npm audit found high/critical vulnerabilities"
  FAILED=1
else
  echo "PASS: npm audit clean"
fi

exit $FAILED
