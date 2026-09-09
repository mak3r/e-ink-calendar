# Quality Spec for <Project Name>

<!-- Replace "<Project Name>" with your project's name. -->
<!-- This file is read by all agent personas before declaring work complete. -->
<!-- Fill in each section to define what quality means for this specific project. -->

## What "make test" means

<!-- Describe what tests exist, what coverage is expected, and what passing means.
Example: "Runs all unit tests. Integration tests require a running database.
Coverage must stay above 80% on internal/ packages." -->

TODO: describe your test suite here.

## What "make lint" means

<!-- Describe which linting rules matter and why.
Example: "Runs golangci-lint with errcheck, govet, staticcheck enabled.
All exported functions must have godoc comments." -->

TODO: describe your lint rules here.

## What "make quality" checks

<!-- Describe what quality-specs/checks.sh verifies and what the thresholds are.
Example: "Checks that no TODO comments remain in non-test files.
Verifies that API response structs have json tags on all fields." -->

TODO: copy quality-specs/examples/<language>.sh to quality-specs/checks.sh and describe it here.

## Language and framework conventions

<!-- Describe idioms, naming conventions, error handling patterns, and any
framework-specific rules agents must follow when writing or reviewing code.
Example: "Use structured logging (slog) not fmt.Println.
All errors must be wrapped with %w before returning." -->

TODO: describe your project's coding conventions here.

## Definition of done additions

<!-- Any additions to the generic Definition of Done in CLAUDE.md.
Example: "All public API endpoints must have an OpenAPI spec entry."
Leave blank if the generic DoD is sufficient. -->

None — the generic Definition of Done in CLAUDE.md applies.
