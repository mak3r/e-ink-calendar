#!/usr/bin/env bash
# quality-specs/examples/rust.sh — Rust quality checks
# Copy to quality-specs/checks.sh and customize.
set -euo pipefail

FAILED=0

# Check for TODO comments in non-test source files
echo "Checking for TODO comments in source files..."
if find src -name "*.rs" -not -name "*test*" -exec grep -ln "TODO" {} + 2>/dev/null | grep -q .; then
  echo "FAIL: TODO comments found:"
  find src -name "*.rs" -not -name "*test*" -exec grep -n "TODO" {} + 2>/dev/null
  FAILED=1
else
  echo "PASS: No TODO comments"
fi

# Run cargo audit for security vulnerabilities
if command -v cargo-audit > /dev/null 2>&1 || cargo audit --version > /dev/null 2>&1; then
  echo "Running cargo audit..."
  if ! cargo audit --quiet 2>/dev/null; then
    echo "FAIL: cargo audit found vulnerabilities"
    FAILED=1
  else
    echo "PASS: cargo audit clean"
  fi
else
  echo "SKIP: cargo-audit not installed (install with: cargo install cargo-audit)"
fi

# Check that all public items have documentation
echo "Checking for missing documentation on public items..."
if ! cargo doc --no-deps --quiet 2>/dev/null; then
  echo "FAIL: cargo doc failed — check for missing doc comments"
  FAILED=1
else
  echo "PASS: cargo doc succeeded"
fi

# Run clippy with pedantic lints (customize as needed)
echo "Running clippy..."
if ! cargo clippy -- -D warnings 2>/dev/null; then
  echo "FAIL: clippy warnings found"
  FAILED=1
else
  echo "PASS: clippy clean"
fi

exit $FAILED
