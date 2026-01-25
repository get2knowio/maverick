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

| Category         | Technology              | Notes                                    |
| ---------------- | ----------------------- | ---------------------------------------- |
| Language         | Python 3.10+            | Use `from __future__ import annotations` |
| Package Manager  | uv                      | Fast, reproducible builds via `uv.lock`  |
| Build System     | Make                    | AI-friendly commands with minimal output |
| AI/Agents        | Claude Agent SDK        | `claude-agent-sdk` package               |
| TUI              | Textual                 | `textual` package                        |
| CLI              | Click                   | `click` package                          |
| Validation       | Pydantic                | For configuration and data models        |
| Testing          | pytest + pytest-asyncio | All tests async-compatible               |
| Linting          | Ruff                    | Fast, comprehensive Python linter        |
| Type Checking    | MyPy                    | Strict mode recommended                  |
| Git Operations   | GitPython               | `maverick.git` wraps GitPython           |
| GitHub API       | PyGithub                | `maverick.utils.github_client`           |
| Logging          | structlog               | `maverick.logging.get_logger()`          |
| Retry Logic      | tenacity                | `@retry` decorator or `AsyncRetrying`    |
| Secret Detection | detect-secrets          | `maverick.utils.secrets`                 |

## Third-Party Library Standards

These libraries are the canonical choices for their domains. Do NOT introduce alternatives or custom implementations.

### GitPython (`maverick.git`)

**Use for**: All git operations (commits, branches, diffs, status, push/pull)

```python
from maverick.git import AsyncGitRepository

repo = AsyncGitRepository(path)
await repo.create_branch("feature/new")
await repo.commit("feat: add feature")
await repo.push()
```

**Do NOT**: Use `subprocess.run("git ...")` or create new git wrappers

### PyGithub (`maverick.utils.github_client`)

**Use for**: All GitHub API operations (issues, PRs, labels, comments)

```python
from maverick.utils.github_client import GitHubClient

client = GitHubClient()
issues = await client.list_issues(repo_name, labels=["bug"])
await client.create_pr(repo_name, title, body, head, base)
```

**Do NOT**: Use `subprocess.run("gh ...")` for operations that PyGithub supports

### structlog (`maverick.logging`)

**Use for**: All logging throughout the codebase

```python
from maverick.logging import get_logger

logger = get_logger(__name__)
logger.info("processing_started", item_id=item_id, count=10)
logger.error("operation_failed", error=str(e), context="validation")
```

**Do NOT**: Use `import logging; logging.getLogger(__name__)`

### tenacity

**Use for**: All retry logic with exponential backoff

```python
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

async for attempt in AsyncRetrying(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
):
    with attempt:
        return await risky_operation()
```

**Do NOT**: Write manual `for attempt in range(retries):` loops

### detect-secrets (`maverick.utils.secrets`)

**Use for**: Detecting secrets/credentials in content before commits

```python
from maverick.utils.secrets import detect_secrets

findings = detect_secrets(file_content)
if findings:
    raise SecurityError(f"Potential secrets found: {findings}")
```

**Do NOT**: Write custom regex patterns for secret detection

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
  - **Streaming-First Design**: The TUI follows a streaming-first philosophy where the primary content area is a unified, scrolling event stream (inspired by Claude Code's interface).
  - Single-column streaming output as the main focus
  - Minimal chrome, maximum content—every pixel should convey information
  - All workflow step types contribute via `StepOutput` or type-specific events like `AgentStreamChunk`
- **Tools**: Wrap external systems (GitHub CLI, git, notifications). Delegate execution to runners.

## Workflow Architecture

Maverick uses YAML-based workflows exclusively. The Python decorator DSL (`@workflow`) was deprecated and removed as of December 2025.

### WorkflowFile (YAML/JSON Serialization)

**Location**: `maverick.dsl.serialization.schema`

Workflows are defined in YAML/JSON and executed by `WorkflowFileExecutor`:

- Declarative workflow definitions shared across projects
- User-editable workflows without Python knowledge
- Built-in workflow library with multi-location discovery
- Supports all step types: python, agent, generate, validate, branch, loop, subworkflow, checkpoint

```python
from maverick.dsl.serialization.schema import WorkflowFile
from maverick.dsl.serialization.executor import WorkflowFileExecutor
from maverick.dsl.serialization.registry import ComponentRegistry

# Load from YAML
workflow = WorkflowFile.from_yaml(yaml_content)

# Execute with registry
registry = ComponentRegistry()
executor = WorkflowFileExecutor(registry=registry)
async for event in executor.execute(workflow, inputs={"branch": "main"}):
    print(event)
```

**Key methods**: `to_dict()`, `to_yaml()`, `from_dict()`, `from_yaml()`

### Example YAML Workflow

```yaml
version: "1.0"
name: hello-world
description: A simple example workflow

inputs:
  name:
    type: string
    required: true

steps:
  - name: format_greeting
    type: python
    action: format_greeting
    args:
      - ${{ inputs.name }}

  - name: uppercase
    type: python
    action: str.upper
    args:
      - ${{ steps.format_greeting.output }}

outputs:
  greeting: ${{ steps.format_greeting.output }}
  uppercase: ${{ steps.uppercase.output }}
```

### Migration from Decorator DSL

If you have existing Python decorator workflows, see `docs/migrating-from-decorator-dsl.md` for migration guidance. The decorator DSL was removed in favor of the more maintainable and user-friendly YAML approach.

### Workflow Discovery Locations

Workflows are discovered from three locations (in override order):

1. **Project**: `.maverick/workflows/` (highest priority)
2. **User**: `~/.config/maverick/workflows/`
3. **Built-in**: Packaged with Maverick (lowest priority)

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

1. **TUI is display-only**: `src/maverick/tui/**` MUST NOT execute subprocesses or make network calls. TUI code delegates to runners/services and only updates reactive state + renders results.

2. **No blocking on the event loop**: Never call `subprocess.run` from `async def`. Use `CommandRunner`. DSL `PythonStep` callables MUST be async or offloaded via `asyncio.to_thread`.

3. **Deterministic ops in workflows/runners**: Agents provide judgment only. Workflows own git commits, validation, retries, checkpointing, and error recovery policies.

4. **Single typed contract for actions**: Use frozen dataclasses with `to_dict()` or `TypedDict` with validation. Keep action outputs stable across versions; treat them as public interfaces.

5. **One canonical wrapper per external system**: Don't duplicate `git`/`gh`/validation wrappers. Use `src/maverick/runners/**` for execution and have tools/context builders delegate.

6. **Tool server factories must be async-safe**: No `asyncio.run()` inside factories. Use lazy verification. Return concrete types; avoid `Any` on public APIs.

7. **Resilience features must be real**: Retry/fix loops must actually invoke fixers and re-run validation (no "simulated" recovery).

8. **Use canonical third-party libraries**: Do NOT introduce alternatives to established libraries (see Third-Party Library Standards section). This includes:
   - Git: `maverick.git`, NOT `subprocess.run("git ...")`
   - GitHub: `maverick.utils.github_client`, NOT `subprocess.run("gh ...")`
   - Logging: `maverick.logging.get_logger()`, NOT stdlib `logging.getLogger()`
   - Retry: `tenacity`, NOT manual `for attempt in range()` loops
   - Secrets: `maverick.utils.secrets`, NOT custom regex patterns

9. **TUI streaming follows the unified event pattern**: All workflow step types MUST contribute to the unified stream via standardized events:
   - Agent steps: Use `AgentStreamChunk` for streaming output and thinking
   - Python/deterministic steps: Use `StepOutput` for progress and status messages
   - All steps: Emit `StepStarted`/`StepCompleted` for lifecycle tracking
   - FIFO buffer management (100KB limit) prevents memory exhaustion
   - 50ms debounced updates prevent UI flickering during rapid event bursts

10. **Branch names MUST match the target repository**: When working with multiple repositories, branch names MUST use the appropriate prefix for the target repository. Never push sample project branches to maverick core (and vice versa). Verify `git remote -v` before pushing.

## Modularization Guidelines

Long, multi-responsibility modules are a primary driver of slow iteration, merge conflicts, and accumulated technical debt. Treat file growth as a design smell.

- **Soft limit**: Aim for modules < ~500 LOC and test modules < ~400–600 LOC
- **Refactor trigger**: If a module exceeds ~800 LOC or has many unrelated top-level definitions, split it as part of the change (or create a `tech debt` issue scoped to the split)
- **Hard stop**: Avoid adding new features to modules > ~1000 LOC without first carving out a focused submodule/package
- **Single responsibility**: Each module/package MUST have one "reason to change"—one domain, one layer, one cohesive feature area

### Backwards-Compatible Refactors

When splitting a public module, preserve import stability:

- Prefer creating a package and re-exporting the current public surface from `__init__.py`
- If external consumers import from the old module path, keep a small shim module that imports/re-exports from the new package for a migration period
- Maintain `__all__` (or equivalent explicit exports) so the public API stays intentional and discoverable

### Preferred Split Patterns

Use these repository-specific patterns to prevent common "god file" failures:

- **CLI**: Keep `src/maverick/main.py` as a thin entrypoint; put each Click command in `src/maverick/cli/commands/<command>.py`; keep shared Click options/error handling in `src/maverick/cli/common.py`
- **Workflows**: Use a package-per-workflow (`src/maverick/workflows/<name>/`) and split into `models.py`, `events.py`, `dsl.py`/`constants.py`, and `workflow.py`
- **TUI models**: Split `src/maverick/tui/models.py` into a `src/maverick/tui/models/` package grouped by domain (enums, dialogs, widget state, screen state, theme)
- **Tools (MCP servers)**: Split into a package with `runner.py` (subprocess), `errors.py`, `responses.py`, `prereqs.py`, `server.py`, and per-resource tool modules
- **DSL execution**: Isolate per-step-type execution logic into handler modules; keep the executor/coordinator readable and small
- **Tests**: Split by unit-under-test and scenario group; move shared fixtures/factories into a local `conftest.py` (directory-scoped) instead of copy/paste

## Hardening Requirements

All external calls MUST have:

- Explicit timeouts (no infinite waits)
- Retry logic with exponential backoff for network operations
- Specific exception handling (no bare `except Exception`)

## Operating Standard

The default stance is **full ownership** of the repository state. "That's not my problem" is not an acceptable response.

- **Do what you're asked, then keep going**: Complete changes end-to-end, then address collateral failures and obvious correctness issues you encountered along the way
- **Fix what you find**: Broken tests, lint failures, type errors, flaky behavior, or obvious bugs—fix them even if they predate your changes
- **Keep the tree green**: Don't rationalize failures as "unrelated" or "not introduced by me." If the repo is failing, the task is not done yet
- **No artificial scope minimization**: We are not operating under time pressure. Prefer complete solutions over narrow patches
- **No deferral by difficulty**: "Too hard" or "too far-reaching" is a signal to decompose the work, not to stop. Break the problem down and make real progress now
- **Only defer when truly blocked**: Defer work only when it is impossible in the current context (missing requirements, missing access, non-reproducible failures). Document exactly what's blocked and the next concrete step

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
- Maintain `__all__` (or equivalent explicit exports) so the public API stays intentional and discoverable

## Multi-Repository Development

Maverick development involves two distinct repositories. **Never confuse them.**

| Repository                  | Purpose                  | Remote URL                               |
| --------------------------- | ------------------------ | ---------------------------------------- |
| **maverick**                | Core CLI/TUI application | `get2knowio/maverick.git`                |
| **sample-maverick-project** | E2E test project         | `get2knowio/sample-maverick-project.git` |

### Branch Naming Conventions

- **Maverick branches**: `###-feature-name` where `###` >= 020 (e.g., `030-tui-streaming`)
- **Sample project branches**: `###-feature-name` where `###` starts at 001 (e.g., `001-greet-cli`)

**CRITICAL**: Before pushing any branch, verify you're in the correct repository:

```bash
git remote -v  # Check remote URL
pwd            # Check working directory
```

**Do NOT push sample project branches (001-xxx) to the maverick repository.** This causes confusion and requires cleanup. See `.specify/memory/constitution.md` Appendix D for full conventions and recovery procedures.

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
