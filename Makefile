# Makefile - AI-agent-friendly development commands
# All targets minimize output by default. Use VERBOSE=1 for full output.
#
# Usage:
#   make test          # Run tests, only show failures
#   make lint          # Run ruff, only show errors
#   make typecheck     # Run mypy, only show errors
#   make format        # Check formatting, show diff if needed
#   make check         # Run all checks
#   make install       # Sync dependencies
#   make VERBOSE=1 test  # Full pytest output

.PHONY: help install sync test test-fast test-cov test-integration lint typecheck \
       format format-fix check clean ci ci-coverage \
       test-tui test-tui-unit test-tui-widgets test-tui-screens test-tui-e2e \
       test-tui-visual test-tui-perf test-tui-a11y update-snapshots

# Default: show help
.DEFAULT_GOAL := help

# Quiet by default, override with VERBOSE=1
VERBOSE ?= 0

ifeq ($(VERBOSE),1)
  Q :=
  PYTEST_ARGS := -v --tb=short
  RUFF_ARGS :=
  MYPY_ARGS :=
else
  Q := @
  PYTEST_ARGS := -q --no-header --tb=line -x
  RUFF_ARGS := --quiet
  MYPY_ARGS := --no-error-summary
endif

help: ## Show this help
	$(Q)echo "Usage: make [target] [VERBOSE=1]"
	$(Q)echo ""
	$(Q)grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Install/sync all dependencies
	$(Q)uv sync --quiet 2>&1 | grep -v "^Resolved\|^Prepared\|^Installed\|^Audited" || true

sync: install ## Alias for install

test: ## Run tests (errors only, parallel)
	$(Q)uv run pytest $(PYTEST_ARGS) -n auto --dist loadscope tests/ 2>&1 | grep -v "^===\|^---\|^platform\|^rootdir\|^plugins\|^collected\|passed\|warnings summary" | grep -v "^$$" || true

test-fast: ## Run unit tests only (fastest feedback loop)
	$(Q)uv run pytest $(PYTEST_ARGS) -n auto --dist loadscope -m "not slow" tests/unit/

test-cov: ## Run tests with coverage report
	$(Q)uv run pytest $(PYTEST_ARGS) --cov=maverick --cov-report=term-missing tests/

test-integration: ## Run integration tests only
	$(Q)uv run pytest $(PYTEST_ARGS) tests/integration/

lint: ## Run ruff linter (errors only)
	$(Q)uv run ruff check $(RUFF_ARGS) src/ tests/ 2>&1 || true

typecheck: ## Run mypy type checker (errors only)
	$(Q)uv run mypy $(MYPY_ARGS) src/ 2>&1 | grep -v "^Success\|^Found 0 errors" || true

format: ## Check formatting (shows diff if changes needed)
	$(Q)uv run ruff format --check --diff src/ tests/ 2>&1 | head -50 || echo "[format] Files need formatting. Run: make format-fix"

format-fix: ## Apply formatting fixes
	$(Q)uv run ruff format src/ tests/ --quiet
	$(Q)echo "[format] Done"

check: lint typecheck test ## Run all checks (lint, typecheck, test)
	$(Q)echo "[check] All checks passed" || echo "[check] Some checks failed"

ci: ## CI mode: fail fast on any error
	$(Q)uv run ruff check src/ tests/ || exit 1
	$(Q)uv run ruff format --check src/ tests/ || exit 1
	$(Q)uv run mypy src/ || exit 1
	$(Q)uv run pytest -n auto --dist loadscope -x --tb=short tests/ || exit 1

ci-coverage: ## CI mode with coverage (for GitHub Actions)
	$(Q)uv run ruff check src/ tests/ || exit 1
	$(Q)uv run ruff format --check src/ tests/ || exit 1
	$(Q)uv run mypy src/ || exit 1
	$(Q)uv run pytest --cov=maverick --cov-report=term-missing --cov-report=xml --cov-fail-under=76 --junit-xml=results.xml --timeout=30 -v tests/ || exit 1

clean: ## Remove build artifacts and caches
	$(Q)rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__ .coverage htmlcov dist build *.egg-info
	$(Q)find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	$(Q)echo "[clean] Done"

# =============================================================================
# TUI Testing Commands
# =============================================================================

test-tui: ## Run all TUI tests (widget, screen, integration)
	$(Q)uv run pytest $(PYTEST_ARGS) tests/tui tests/unit/tui -v --tb=short -m "tui"

test-tui-unit: ## Run TUI widget and screen unit tests only
	$(Q)uv run pytest $(PYTEST_ARGS) tests/unit/tui/widgets tests/unit/tui/screens tests/unit/tui/models -v --tb=short

test-tui-widgets: ## Run TUI widget tests only
	$(Q)uv run pytest $(PYTEST_ARGS) tests/tui/widgets tests/unit/tui/widgets -v --tb=short

test-tui-screens: ## Run TUI screen tests only
	$(Q)uv run pytest $(PYTEST_ARGS) tests/tui/screens tests/unit/tui/screens -v --tb=short

test-tui-e2e: ## Run E2E tests with MCP TUI driver (slow)
	$(Q)uv run pytest $(PYTEST_ARGS) tests/tui/e2e -v -m "e2e" --timeout=120

test-tui-visual: ## Run visual regression tests
	$(Q)uv run pytest $(PYTEST_ARGS) tests/tui/visual -v -m "visual"

test-tui-perf: ## Run performance benchmark tests
	$(Q)uv run pytest $(PYTEST_ARGS) tests/tui/performance -v -m "performance"

test-tui-a11y: ## Run accessibility tests
	$(Q)uv run pytest $(PYTEST_ARGS) tests/tui -v -m "accessibility"

update-snapshots: ## Update visual regression snapshots
	$(Q)uv run pytest tests/tui/visual --snapshot-update -v
