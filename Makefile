# Standard targets required by CI. Replace stub bodies with real implementations.
# All targets must exit 0 on success and non-zero on failure.
# The 'quality' and 'security-scan' targets work out of the box with no changes.

.PHONY: build test lint quality security-scan

build:
	python -m compileall -q eink_calendar

test:
	pytest -q

lint:
	ruff check eink_calendar tests

quality:
	@if [ -f quality-specs/checks.sh ]; then \
		bash quality-specs/checks.sh; \
	else \
		echo "No quality-specs/checks.sh found — skipping quality gate"; \
	fi

security-scan:
	@if command -v gitleaks > /dev/null 2>&1; then \
		gitleaks detect --no-banner --config .gitleaks.toml --redact; \
	else \
		echo "gitleaks not installed locally; run 'brew install gitleaks' or rely on CI secret-scan job"; \
	fi
