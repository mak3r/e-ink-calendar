# Standard targets required by CI. Replace stub bodies with real implementations.
# All targets must exit 0 on success and non-zero on failure.
# The 'quality' and 'security-scan' targets work out of the box with no changes.

.PHONY: build test lint quality security-scan

build:
	@echo "ERROR: 'make build' is not configured for this project."
	@echo "Replace this stub in Makefile with your real build command."
	@echo "Examples: go build ./...  |  npm run build  |  cargo build  |  python -m build"
	@exit 1

test:
	@echo "ERROR: 'make test' is not configured for this project."
	@echo "Replace this stub in Makefile with your real test command."
	@echo "Examples: go test ./...  |  npm test  |  pytest  |  cargo test"
	@exit 1

lint:
	@echo "ERROR: 'make lint' is not configured for this project."
	@echo "Replace this stub in Makefile with your real lint command."
	@echo "Examples: golangci-lint run  |  npm run lint  |  flake8  |  cargo clippy"
	@exit 1

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
