# Maverick Project Context for Gemini

## Project Overview

**Maverick** is a Python CLI/TUI application designed to orchestrate autonomous AI-powered development workflows. It leverages the **Claude Agent SDK** to manage the complete development lifecycle, including task implementation, code review, validation, and pull request management.

- **Primary Language:** Python 3.10+ (Async-first)
- **Key Libraries:** `claude-agent-sdk`, `textual` (TUI), `click` (CLI), `pydantic` (Data Models), `anyio`/`asyncio`.
- **Architecture:** Layered (CLI/TUI -> Workflows -> Agents -> Tools).
- **License:** MIT

## Environment & Setup

### Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** (Recommended): For fast dependency management and reproducible builds.
- **GitHub CLI (`gh`)**: Required for PR/Issue management.
- **Claude API Key**: `ANTHROPIC_API_KEY` environment variable.

### Installation

```bash
# Using uv (recommended) - uses uv.lock for reproducibility
uv sync

# Run maverick
uv run maverick --help

# OR using pip
pip install -e ".[dev]"
```

## Development Workflow & Commands

### Building & Running

- **CLI Entry Point**: `maverick` (via `src/maverick/main.py`)
- **Run Development Version**: `uv run maverick` or `uv run python -m maverick`
- **Configuration**: `maverick.yaml` (project) or `~/.config/maverick/config.yaml` (user).

### Testing & Validation

**IMPORTANT**: Always use `make` commands instead of `uv run` directly. The Makefile provides AI-agent-friendly output with minimal noise.

| Command               | Purpose                                |
| --------------------- | -------------------------------------- |
| `make test`           | Run tests (errors only)                |
| `make lint`           | Run ruff linter (errors only)          |
| `make typecheck`      | Run mypy (errors only)                 |
| `make format`         | Check formatting (diff if needed)      |
| `make format-fix`     | Apply formatting fixes                 |
| `make check`          | Run all checks (lint, typecheck, test) |
| `make ci`             | CI mode: fail fast on any error        |
| `make clean`          | Remove build artifacts and caches      |
| `make VERBOSE=1 test` | Full output for debugging              |

### Architecture & Key Directories

- **`src/maverick/`**: Main package source.
  - **`agents/`**: Autonomous agents (e.g., `CodeReviewerAgent`, `ImplementerAgent`). Logic for _HOW_ to do tasks.
  - **`workflows/`**: Workflow orchestration (e.g., `FlyWorkflow`, `RefuelWorkflow`). Logic for _WHAT_ and _WHEN_.
  - **`dsl/`**: Domain-Specific Language for defining workflows.
  - **`tools/`**: MCP (Model Context Protocol) tool definitions (Git, GitHub, Validation).
  - **`tui/`**: Textual-based terminal user interface components.
  - **`models/`**: Pydantic data models for structured IO.
- **`tests/`**: Comprehensive test suite (Unit, Integration, TUI).
- **`specs/`**: Documentation and design specifications (Spec-Driven Development).
- **`plugins/maverick/`**: **Legacy** Claude Code plugin (deprecated/migration source).

## coding Conventions

- **Async-First**: All I/O bound operations must be `async`/`await`.
- **Type Hints**: Mandatory for all public APIs. Use `from __future__ import annotations`.
- **Docstrings**: Google-style docstrings required for public classes and functions.
- **Pydantic**: Use `BaseModel` for all configuration and complex data structures.
- **Separation of Concerns**:
  - **Agents**: Stateless decision makers.
  - **Workflows**: Stateful orchestrators.
  - **Tools**: Safe interfaces to external systems.

## Architectural Guardrails (Non-Negotiables)

These truisms are required to maintain the clarity/segmentation described in `.specify/memory/constitution.md` and the Slidev training content.

1. **TUI is display-only**: `src/maverick/tui/**` must not execute subprocesses or make network calls. Delegate to runners/services and only render/update state.
2. **Async-first means no blocking on the event loop**: never use `subprocess.run` in an `async def` path. Prefer `CommandRunner` (`src/maverick/runners/command.py`). DSL `PythonStep` callables must be async or offloaded (e.g., `asyncio.to_thread`).
3. **Deterministic ops belong to workflows/runners, not agents**: agents provide judgment; workflows own git/validation execution, retries, checkpointing, and recovery policy.
4. **Actions must have a single typed contract**: avoid ad-hoc `dict[str, Any]` outputs; prefer frozen dataclasses (with `to_dict()` for serialization) or `TypedDict` + boundary validation.
5. **Resilience features must be real**: retry/fix loops must actually invoke fixers and re-run validation (no “simulated” recovery).
6. **One canonical wrapper per external system**: don’t duplicate `git`/`gh`/validation wrappers; prefer `src/maverick/runners/**` and have tools/context builders delegate.
7. **Tool server factories must be async-safe**: avoid `asyncio.run` inside factories; prefer lazy verification or explicit async verify APIs; keep public return types concrete (avoid `Any`).

## Key Files

- `CLAUDE.md`: Detailed coding guidelines and context for AI assistants.
- `CONTRIBUTING.md`: Developer setup and contribution guide.
- `pyproject.toml`: Build configuration and dependencies.
- `.specify/memory/constitution.md`: Core architectural principles.

## Operating Standard (Ownership & Follow-Through)

The default stance is full ownership of the repository state while you work. “That’s not my problem” is not an acceptable response.

- **Do what you’re asked, then keep going:** Complete the requested change end-to-end, then address collateral failures and obvious correctness issues you encountered along the way.
- **Fix what you find:** If you encounter broken tests, lint failures, type errors, flaky behavior, or obvious bugs while working, attempt to fix them—even if they predate your changes.
- **Keep the tree green:** Don’t rationalize failures as “unrelated” or “not introduced by me.” If the repo is failing, the task is not done yet.
- **No artificial scope minimization:** We are not operating under time pressure. Unless explicitly instructed otherwise, prefer a complete, robust solution over a narrowly-scoped patch.
- **No deferral by difficulty:** “Too hard” or “too far-reaching” is a signal to decompose the work, not to stop. Break the problem down and make real progress now.
- **Only defer when truly blocked:** Defer work only when it is impossible in the current context (missing requirements, missing access, non-reproducible failures). If you must defer, document exactly what’s blocked and what the next concrete step is.

## Debt Prevention Guidelines

Analysis of past technical debt (#61-#152) reveals recurring patterns. Strict adherence to these rules is required to prevent accumulation of new debt.

### 1. Testing is Not Optional (Anti-Deferral)

- **Root Cause:** Deferring integration tests or ignoring pre-existing failures.
- **Rule:** No PR shall be merged without passing **new** tests covering the added functionality.
- **Rule:** Do not comment out or skip failing tests; fix them immediately.
- **Rule:** For async components (Agents/Workflows), testing must verify concurrency and error states, not just happy paths.

### 2. Zero-Tolerance for Duplication (DRY)

- **Root Cause:** Copy-pasting logic between Agents (e.g., `ImplementerAgent` vs `IssueFixerAgent`) or Workflows (`Fly` vs `Refuel`).
- **Rule:** If logic regarding Git operations, Validation, or GitHub API calls is needed in a second location, **refactor to a shared utility immediately**. Do not wait for a "cleanup" phase.
- **Rule:** Use Mixins or Composition over inheritance for shared agent capabilities.

### 3. Hardening by Default (Anti-Assumption)

- **Root Cause:** Assuming reliable networks or infinite resources.
- **Rule:** All external calls (GitHub API, Git subprocesses) **must** have:
  - Explicit timeouts.
  - Retry logic with exponential backoff for network operations.
  - Specific exception handling (no bare `except Exception`).

### 4. Type Safety & Constants

- **Root Cause:** "Magic" numbers/strings and loose coupling.
- **Rule:** No magic numbers or string literals in logic code; extract to named constants or configuration.
- **Rule:** Use `Protocol` (structural typing) to define interfaces between components (e.g., between DSL and Agents) to avoid circular dependencies and tight coupling.

### 5. Documentation Integrity

- **Root Cause:** Code evolving faster than docs.
- **Rule:** Treat documentation examples as code. Where possible, add tests that validate the code snippets in `README.md` or `quickstart.md` to ensure they remain executable.

### 6. Modularize Early (Keep Files Small)

- **Root Cause:** “God modules” that accumulate multiple responsibilities, slow navigation, and increase merge conflicts.
- **Rules:**
  - **Soft limit:** keep modules < ~500 LOC and test modules < ~400–600 LOC.
  - **Refactor trigger:** if a module exceeds ~800 LOC or becomes multi-domain, split it as part of the change (or open a `tech debt` issue scoped to the split).
  - **Hard stop:** avoid adding new features to modules > ~1000 LOC without carving out a focused submodule/package first.
  - **Single responsibility:** each module/package should have one clear reason to change.

### 7. Preferred Split Patterns (Repo Conventions)

- **CLI:** `src/maverick/main.py` stays thin; put commands under `src/maverick/cli/commands/`; shared Click glue in `src/maverick/cli/common.py`.
- **Workflows:** package-per-workflow under `src/maverick/workflows/<name>/` with `models.py`, `events.py`, `dsl.py`/`constants.py`, `workflow.py`.
- **TUI models:** split into `src/maverick/tui/models/` grouped by domain (enums, dialogs, state models, theme).
- **Tools (MCP servers):** split into `runner.py`, `errors.py`, `responses.py`, `prereqs.py`, `server.py`, and per-resource tool modules.
- **DSL execution:** step-type handlers in separate modules; keep the executor/coordinator small and readable.
- **Tests:** split by unit-under-test and scenario; use local `conftest.py` for shared fixtures/factories.

### 8. Backwards-Compatible Refactors

- Preserve import stability by re-exporting from package `__init__.py` and/or keeping a small shim module that imports/re-exports from the new location during migration.
