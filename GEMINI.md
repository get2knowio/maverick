# Maverick Project Context for Gemini

## Project Overview

**Maverick** is a Python CLI/TUI application designed to orchestrate autonomous AI-powered development workflows. It leverages the **Claude Agent SDK** to manage the complete development lifecycle, including task implementation, code review, validation, and pull request management.

*   **Primary Language:** Python 3.10+ (Async-first)
*   **Key Libraries:** `claude-agent-sdk`, `textual` (TUI), `click` (CLI), `pydantic` (Data Models), `anyio`/`asyncio`.
*   **Architecture:** Layered (CLI/TUI -> Workflows -> Agents -> Tools).
*   **License:** MIT

## Environment & Setup

### Prerequisites
*   **Python 3.10+**
*   **GitHub CLI (`gh`)**: Required for PR/Issue management.
*   **Claude API Key**: `ANTHROPIC_API_KEY` environment variable.
*   **uv** (Recommended): For fast dependency management.

### Installation
```bash
# Clone and install in editable mode with dev dependencies
uv pip install -e ".[dev]"
# OR
pip install -e ".[dev]"
```

## Development Workflow & Commands

### Building & Running
*   **CLI Entry Point**: `maverick` (via `src/maverick/main.py`)
*   **Run Development Version**: `python -m maverick` or `maverick` (after install).
*   **Configuration**: `maverick.yaml` (project) or `~/.config/maverick/config.yaml` (user).

### Testing & Validation
The project adheres to strict quality standards.

*   **Test Runner**: `pytest`
    *   Run all tests: `pytest`
    *   Run with coverage: `pytest --cov=maverick`
*   **Linting**: `ruff`
    *   Check: `ruff check .`
    *   Fix: `ruff check --fix .`
*   **Formatting**: `ruff format`
    *   Format all: `ruff format .`
*   **Type Checking**: `mypy`
    *   Strict check: `mypy src/maverick`

### Architecture & Key Directories

*   **`src/maverick/`**: Main package source.
    *   **`agents/`**: Autonomous agents (e.g., `CodeReviewerAgent`, `ImplementerAgent`). Logic for *HOW* to do tasks.
    *   **`workflows/`**: Workflow orchestration (e.g., `FlyWorkflow`, `RefuelWorkflow`). Logic for *WHAT* and *WHEN*.
    *   **`dsl/`**: Domain-Specific Language for defining workflows.
    *   **`tools/`**: MCP (Model Context Protocol) tool definitions (Git, GitHub, Validation).
    *   **`tui/`**: Textual-based terminal user interface components.
    *   **`models/`**: Pydantic data models for structured IO.
*   **`tests/`**: Comprehensive test suite (Unit, Integration, TUI).
*   **`specs/`**: Documentation and design specifications (Spec-Driven Development).
*   **`plugins/maverick/`**: **Legacy** Claude Code plugin (deprecated/migration source).

## coding Conventions

*   **Async-First**: All I/O bound operations must be `async`/`await`.
*   **Type Hints**: Mandatory for all public APIs. Use `from __future__ import annotations`.
*   **Docstrings**: Google-style docstrings required for public classes and functions.
*   **Pydantic**: Use `BaseModel` for all configuration and complex data structures.
*   **Separation of Concerns**:
    *   **Agents**: Stateless decision makers.
    *   **Workflows**: Stateful orchestrators.
    *   **Tools**: Safe interfaces to external systems.

## Key Files
*   `CLAUDE.md`: Detailed coding guidelines and context for AI assistants.
*   `CONTRIBUTING.md`: Developer setup and contribution guide.
*   `pyproject.toml`: Build configuration and dependencies.
*   `.specify/memory/constitution.md`: Core architectural principles.

## Debt Prevention Guidelines

Analysis of past technical debt (#61-#152) reveals recurring patterns. Strict adherence to these rules is required to prevent accumulation of new debt.

### 1. Testing is Not Optional (Anti-Deferral)
*   **Root Cause:** Deferring integration tests or ignoring pre-existing failures.
*   **Rule:** No PR shall be merged without passing **new** tests covering the added functionality.
*   **Rule:** Do not comment out or skip failing tests; fix them immediately.
*   **Rule:** For async components (Agents/Workflows), testing must verify concurrency and error states, not just happy paths.

### 2. Zero-Tolerance for Duplication (DRY)
*   **Root Cause:** Copy-pasting logic between Agents (e.g., `ImplementerAgent` vs `IssueFixerAgent`) or Workflows (`Fly` vs `Refuel`).
*   **Rule:** If logic regarding Git operations, Validation, or GitHub API calls is needed in a second location, **refactor to a shared utility immediately**. Do not wait for a "cleanup" phase.
*   **Rule:** Use Mixins or Composition over inheritance for shared agent capabilities.

### 3. Hardening by Default (Anti-Assumption)
*   **Root Cause:** Assuming reliable networks or infinite resources.
*   **Rule:** All external calls (GitHub API, Git subprocesses) **must** have:
    *   Explicit timeouts.
    *   Retry logic with exponential backoff for network operations.
    *   Specific exception handling (no bare `except Exception`).

### 4. Type Safety & Constants
*   **Root Cause:** "Magic" numbers/strings and loose coupling.
*   **Rule:** No magic numbers or string literals in logic code; extract to named constants or configuration.
*   **Rule:** Use `Protocol` (structural typing) to define interfaces between components (e.g., between DSL and Agents) to avoid circular dependencies and tight coupling.

### 5. Documentation Integrity
*   **Root Cause:** Code evolving faster than docs.
*   **Rule:** Treat documentation examples as code. Where possible, add tests that validate the code snippets in `README.md` or `quickstart.md` to ensure they remain executable.
