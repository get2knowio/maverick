# GitHub Copilot Instructions for Maverick

This file provides guidance to GitHub Copilot when working with code in this repository.

## Project Overview

**Maverick** is a Python CLI/TUI application that automates AI-powered development workflows using the Claude Agent SDK and Textual. It orchestrates multi-phase workflows: feature implementation from task lists, parallel code review, convention updates, and PR management.

- **Primary Language:** Python 3.10+ (Async-first)
- **Key Libraries:** `claude-agent-sdk`, `textual` (TUI), `click` (CLI), `pydantic` (Data Models), `anyio`/`asyncio`
- **Architecture:** Layered (CLI/TUI → Workflows → Agents → Tools)
- **License:** MIT

## Technology Stack

| Category      | Technology              | Notes                                    |
| ------------- | ----------------------- | ---------------------------------------- |
| Language      | Python 3.10+            | Use `from __future__ import annotations` |
| AI/Agents     | Claude Agent SDK        | `claude-agent-sdk` package               |
| TUI           | Textual                 | `textual` package                        |
| CLI           | Click                   | `click` package                          |
| Validation    | Pydantic                | For configuration and data models        |
| Testing       | pytest + pytest-asyncio | All tests async-compatible               |
| Linting       | Ruff                    | Fast, comprehensive Python linter        |
| Type Checking | MyPy                    | Strict mode recommended                  |

## Architecture

```
src/maverick/
├── __init__.py          # Version, public API exports
├── main.py              # CLI entry point (Click commands)
├── config.py            # Pydantic configuration models
├── exceptions.py        # Custom exception hierarchy (MaverickError base)
├── agents/              # Agent implementations (HOW to do tasks)
├── workflows/           # Workflow orchestration (WHAT and WHEN)
├── dsl/                 # Domain-Specific Language for workflows
├── tools/               # MCP tool definitions (Git, GitHub, Validation)
├── hooks/               # Safety and logging hooks
├── tui/                 # Textual application (display-only)
└── utils/               # Shared utilities
```

### Separation of Concerns

- **Agents**: Know HOW to do a task (system prompts, tool selection, Claude SDK interaction). Provide judgment only—no deterministic side effects.
- **Workflows**: Know WHAT to do and WHEN (orchestration, state management, sequencing). Own git/validation execution, retries, checkpointing.
- **TUI**: Presents state and captures input. **Display-only—no business logic, no subprocesses.**
- **Tools**: Wrap external systems (GitHub CLI, git, notifications). Delegate execution to runners.

## Core Principles (Non-Negotiable)

### 1. Async-First

All agent interactions and workflows MUST be async.

- Use `asyncio` patterns consistently; no threading for I/O operations
- Never call `subprocess.run` from an `async def` path—use `CommandRunner` or `asyncio.create_subprocess_exec`
- DSL `PythonStep` callables MUST be async or offloaded via `asyncio.to_thread`

### 2. Dependency Injection

Agents and workflows receive configuration and dependencies, not global state.

- MCP tool servers are passed in, not created internally
- Configuration objects are injected at construction time
- No module-level mutable state

### 3. Fail Gracefully, Recover Aggressively

One agent/issue failing MUST NOT crash the entire workflow.

- Capture and report errors with context before recovery
- Retry with exponential backoff (default: 3 attempts)
- Continue processing remaining work items even when some fail
- Resilience features MUST be real, not stubs

### 4. Test-First (Anti-Deferral)

Every public class and function MUST have tests.

- Use pytest fixtures for common setup
- Mock external dependencies (Claude API, GitHub CLI, filesystem)
- Do NOT comment out or skip failing tests; fix them immediately
- For async components, test concurrency and error states, not just happy paths

### 5. Type Safety & Typed Contracts

Complete type hints required throughout.

- All public functions MUST have complete type annotations
- Use `@dataclass` or Pydantic `BaseModel` over plain dicts
- No magic numbers or string literals; extract to named constants
- Workflow actions MUST NOT return ad-hoc `dict[str, Any]` blobs

### 6. Simplicity & DRY

Avoid over-engineering. Zero tolerance for duplication.

- No global mutable state or god-classes
- No hardcoded paths; use pathlib and configuration
- If logic is needed in a second location, refactor to shared utility IMMEDIATELY

## Code Style

| Element   | Convention           | Example                            |
| --------- | -------------------- | ---------------------------------- |
| Classes   | PascalCase           | `CodeReviewerAgent`, `FlyWorkflow` |
| Functions | snake_case           | `execute_review`, `create_pr`      |
| Constants | SCREAMING_SNAKE_CASE | `MAX_RETRIES`, `DEFAULT_TIMEOUT`   |
| Private   | Leading underscore   | `_build_prompt`, `_validate_input` |

- **Docstrings**: Google-style format with Args, Returns, Raises sections
- **Exceptions**: Hierarchy from `MaverickError` → `AgentError`, `WorkflowError`, `ConfigError`
- **No `print()`**: Use logging or TUI updates
- **No `shell=True`**: In subprocess calls without explicit security justification

## Architectural Guardrails

These rules are required to maintain layer boundaries. If a change would violate any item, stop and refactor.

1. **TUI is display-only**: `src/maverick/tui/**` MUST NOT execute subprocesses or make network calls.

2. **No blocking on the event loop**: Never call `subprocess.run` from `async def`. Use `CommandRunner`.

3. **Deterministic ops in workflows/runners**: Agents provide judgment only. Workflows own git commits, validation, retries.

4. **Single typed contract for actions**: Use frozen dataclasses with `to_dict()` or `TypedDict` with validation.

5. **One canonical wrapper per external system**: Don't duplicate `git`/`gh`/validation wrappers. Use `src/maverick/runners/**`.

6. **Tool server factories must be async-safe**: No `asyncio.run()` inside factories. Use lazy verification.

## Modularization Guidelines

Treat file growth as a design smell.

- **Soft limit**: Modules < ~500 LOC, test modules < ~400–600 LOC
- **Refactor trigger**: Modules > ~800 LOC should be split
- **Hard stop**: Don't add features to modules > ~1000 LOC without splitting first
- **Single responsibility**: Each module should have one "reason to change"

### Preferred Split Patterns

- **CLI**: Keep `main.py` thin; commands in `src/maverick/cli/commands/`
- **Workflows**: Package-per-workflow with `models.py`, `events.py`, `workflow.py`
- **TUI models**: Split into `src/maverick/tui/models/` by domain
- **Tools**: Split into `runner.py`, `errors.py`, `responses.py`, `server.py`
- **Tests**: Split by unit-under-test; shared fixtures in local `conftest.py`

## Hardening Requirements

All external calls MUST have:

- Explicit timeouts (no infinite waits)
- Retry logic with exponential backoff for network operations
- Specific exception handling (no bare `except Exception`)

## Operating Standard

The default stance is **full ownership** of the repository state.

- **Do what you're asked, then keep going**: Complete changes end-to-end, then address collateral failures
- **Fix what you find**: Broken tests, lint failures, type errors—fix them even if they predate your changes
- **Keep the tree green**: Don't rationalize failures as "unrelated"
- **No artificial scope minimization**: Prefer complete solutions over narrow patches
- **Only defer when truly blocked**: Document exactly what's blocked and the next concrete step

## Development Commands

```bash
# Testing
pytest                          # Run all tests
pytest --cov=maverick           # With coverage

# Linting & Formatting
ruff check .                    # Check linting
ruff check --fix .              # Auto-fix
ruff format .                   # Format code

# Type Checking
mypy src/maverick               # Strict type check
```

## Key Files

- `.specify/memory/constitution.md`: Core architectural principles (authoritative reference)
- `CLAUDE.md`: Detailed coding guidelines for AI assistants
- `GEMINI.md`: Condensed project context
- `CONTRIBUTING.md`: Developer setup and contribution guide
- `pyproject.toml`: Build configuration and dependencies
