# GitHub Copilot Instructions for Maverick

This file provides guidance to GitHub Copilot when working with code in this repository.

## Project Overview

**Maverick** is a Python CLI/TUI application that automates AI-powered development workflows using the Claude Agent SDK and Textual. It orchestrates multi-phase workflows: feature implementation from task lists, parallel code review, convention updates, and PR management.

- **Primary Language:** Python 3.10+ (Async-first)
- **Key Libraries:** `claude-agent-sdk`, `textual` (TUI), `click` (CLI), `pydantic` (Data Models), `anyio`/`asyncio`
- **Architecture:** Layered (CLI/TUI → Workflows → Agents → Tools)
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

## Technology Stack

| Category        | Technology              | Notes                                    |
| --------------- | ----------------------- | ---------------------------------------- |
| Language        | Python 3.10+            | Use `from __future__ import annotations` |
| Package Manager | uv                      | Fast, reproducible builds via `uv.lock`  |
| Build System    | Make                    | AI-friendly commands with minimal output |
| AI/Agents       | Claude Agent SDK        | `claude-agent-sdk` package               |
| TUI             | Textual                 | `textual` package                        |
| CLI             | Click                   | `click` package                          |
| Validation      | Pydantic                | For configuration and data models        |
| Testing         | pytest + pytest-asyncio | All tests async-compatible               |
| Linting         | Ruff                    | Fast, comprehensive Python linter        |
| Type Checking   | MyPy                    | Strict mode recommended                  |

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

## Workflow Architecture: Two Workflow Types

Maverick supports two distinct workflow representations, each serving different use cases:

### WorkflowFile (YAML/JSON Serialization)

**Location**: `maverick.dsl.serialization.schema`

Used for file-based workflows defined in YAML/JSON. Best for:

- Declarative workflow definitions shared across projects
- User-editable workflows without Python knowledge
- Built-in workflow library (discovery, CI integration)

```python
from maverick.dsl.serialization.schema import WorkflowFile

# Load from YAML
workflow = WorkflowFile.from_yaml(yaml_content)

# Convert to YAML
yaml_str = workflow.to_yaml()
```

**Key methods**: `to_dict()`, `to_yaml()`, `from_dict()`, `from_yaml()`

### WorkflowDefinition (Python Decorator)

**Location**: `maverick.dsl.decorator`

Used for code-based workflows defined with the `@workflow` decorator. Best for:

- Complex logic requiring Python control flow
- Workflows needing dynamic step generation
- Integration tests and programmatic workflows

```python
from maverick.dsl import workflow, step, WorkflowEngine

@workflow(name="my-workflow", description="A code-based workflow")
def my_workflow(input_data: str):
    result = yield step("process").python(action=transform, args=(input_data,))
    return {"result": result}

# Execute with engine
engine = WorkflowEngine()
async for event in engine.execute(my_workflow, input_data="test"):
    print(event)
```

**Note**: `WorkflowDefinition` does NOT support serialization to YAML. This is by design—Python generator workflows with arbitrary lambdas cannot be reliably serialized.

### When to Use Which

| Use Case                     | Recommended Type              |
| ---------------------------- | ----------------------------- |
| Shareable workflow templates | `WorkflowFile` (YAML)         |
| CI/CD pipeline definitions   | `WorkflowFile` (YAML)         |
| Complex conditional logic    | `WorkflowDefinition` (Python) |
| Dynamic step generation      | `WorkflowDefinition` (Python) |
| Built-in workflow library    | `WorkflowFile` (YAML)         |
| Unit/integration tests       | `WorkflowDefinition` (Python) |

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

## Claude Agent SDK Patterns

- Always specify `allowed_tools` explicitly (principle of least privilege)
- Use `ClaudeSDKClient` for stateful/multi-turn interactions
- Use `query()` for one-shot, stateless interactions
- Custom tools use the `@tool` decorator and `create_sdk_mcp_server()`
- Hooks are async functions matching the SDK's hook signature
- Extract and structure agent outputs; do not return raw text

## Architectural Guardrails

These rules are required to maintain layer boundaries. If a change would violate any item, stop and refactor.

1. **TUI is display-only**: `src/maverick/tui/**` MUST NOT execute subprocesses or make network calls.

2. **No blocking on the event loop**: Never call `subprocess.run` from `async def`. Use `CommandRunner`.

3. **Deterministic ops in workflows/runners**: Agents provide judgment only. Workflows own git commits, validation, retries.

4. **Single typed contract for actions**: Use frozen dataclasses with `to_dict()` or `TypedDict` with validation.

5. **One canonical wrapper per external system**: Don't duplicate `git`/`gh`/validation wrappers. Use `src/maverick/runners/**`.

6. **Tool server factories must be async-safe**: No `asyncio.run()` inside factories. Use lazy verification.

7. **Resilience features must be real**: Retry/fix loops must actually invoke fixers and re-run validation (no "simulated" recovery).

## Modularization Guidelines

Treat file growth as a design smell.

- **Soft limit**: Modules < ~500 LOC, test modules < ~400–600 LOC
- **Refactor trigger**: Modules > ~800 LOC should be split
- **Hard stop**: Don't add features to modules > ~1000 LOC without splitting first
- **Single responsibility**: Each module should have one "reason to change"

### Preferred Split Patterns

- **CLI**: Keep `main.py` thin; commands in `src/maverick/cli/commands/`
- **Workflows**: Package-per-workflow with `models.py`, `events.py`, `dsl.py`/`constants.py`, `workflow.py`
- **TUI models**: Split into `src/maverick/tui/models/` by domain (enums, dialogs, state models, theme)
- **Tools (MCP servers)**: Split into `runner.py`, `errors.py`, `responses.py`, `prereqs.py`, `server.py`
- **DSL execution**: Step-type handlers in separate modules; keep executor/coordinator small
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

## Debt Prevention Guidelines

Analysis of past technical debt (#61-#152) reveals recurring patterns. Strict adherence to these rules prevents debt accumulation.

### 1. Testing is Not Optional (Anti-Deferral)

- No PR shall be merged without passing **new** tests covering added functionality
- Do not comment out or skip failing tests; fix them immediately
- For async components (Agents/Workflows), test concurrency and error states, not just happy paths

### 2. Zero-Tolerance for Duplication (DRY)

- If logic (Git operations, Validation, GitHub API calls) is needed in a second location, **refactor to a shared utility immediately**—do not wait for "cleanup"
- Use Mixins or Composition over inheritance for shared agent capabilities

### 3. Hardening by Default (Anti-Assumption)

- All external calls (GitHub API, Git subprocesses) **MUST** have:
  - Explicit timeouts
  - Retry logic with exponential backoff for network operations
  - Specific exception handling (no bare `except Exception`)

### 4. Type Safety & Constants

- No magic numbers or string literals in logic code; extract to named constants or configuration
- Use `Protocol` (structural typing) to define interfaces between components to avoid circular dependencies

### 5. Documentation Integrity

- Treat documentation examples as code—where possible, add tests that validate code snippets in `README.md` or `docs/quickstart.md`

### 6. Backwards-Compatible Refactors

- Preserve import stability by re-exporting from package `__init__.py`
- Keep a small shim module that imports/re-exports from new locations during migration

## Development Commands

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

## Key Files

- `.specify/memory/constitution.md`: Core architectural principles (authoritative reference)
- `CLAUDE.md`: Detailed coding guidelines for AI assistants
- `GEMINI.md`: Condensed project context
- `CONTRIBUTING.md`: Developer setup and contribution guide
- `pyproject.toml`: Build configuration and dependencies
