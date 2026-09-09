# Quality Specs

This directory contains the quality gate plugin system.

## How it works

CI calls `make quality`, which runs `quality-specs/checks.sh` if present.
`checks.sh` exits 0 on success and non-zero on failure. The merge-manager
treats a non-zero exit as a blocker.

## Setting up quality checks for your project

1. Copy the example for your language:
   ```bash
   cp quality-specs/examples/go.sh quality-specs/checks.sh
   chmod +x quality-specs/checks.sh
   ```

2. Customize `checks.sh` for your project's specific rules.

3. Update `.claude/quality.md` to describe what the checks do, in plain English
   for agent consumption.

## What goes in checks.sh

Project-specific quality rules that are not covered by `make lint` or `make test`.
Examples:
- Verify no TODO comments remain in non-test files
- Check that API response types have serialization annotations
- Verify config file schema compliance
- Check that all exported symbols have documentation
- Run security-specific static analysis (gosec, bandit, semgrep)

## Examples

See `quality-specs/examples/` for language-specific starter scripts.
Each example includes common checks for that language and documents
what each check does and how to customize it.

## Agent context

Agents read `.claude/quality.md` (not this directory) to understand
what quality means for the project. Keep `.claude/quality.md` updated
when you change `checks.sh`.
