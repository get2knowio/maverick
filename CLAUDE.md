# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Maverick is a Python CLI/TUI application that automates AI-powered development workflows using the Claude Agent SDK and Textual. It orchestrates multi-phase workflows: feature implementation from task lists, parallel code review, convention updates, and PR management.

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
| Git Operations  | GitPython               | `maverick.git` wraps GitPython           |
| GitHub API      | PyGithub                | `maverick.utils.github_client`           |
| Logging         | structlog               | `maverick.logging.get_logger()`          |
| Retry Logic     | tenacity                | `@retry` decorator or `AsyncRetrying`    |
| Secret Detection| detect-secrets          | `maverick.utils.secrets`                 |

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
├── agents/              # Agent implementations
│   ├── base.py          # MaverickAgent abstract base class
│   └── *.py             # Concrete agents (CodeReviewerAgent, etc.)
├── workflows/           # Workflow orchestration
│   ├── fly.py           # FlyWorkflow - full spec-based workflow
│   └── refuel.py        # RefuelWorkflow - tech-debt resolution
├── tools/               # MCP tool definitions
├── hooks/               # Safety and logging hooks
├── tui/                 # Textual application
│   ├── app.py           # Main Textual App
│   ├── screens/         # Screen components
│   └── widgets/         # Reusable widgets
└── utils/               # Shared utilities
```

### Separation of Concerns

- **Agents**: Know HOW to do a task (system prompts, tool selection, Claude SDK interaction)
- **Workflows**: Know WHAT to do and WHEN (orchestration, state management, sequencing)
- **TUI**: Presents state and captures input (no business logic)
- **Tools**: Wrap external systems (GitHub CLI, git, notifications)

## Workflow Architecture: YAML-Based DSL

**As of December 2025**: Maverick uses a unified YAML-based workflow DSL for all workflow authoring. The previous Python decorator DSL has been deprecated and removed.

### WorkflowFile (YAML/JSON Serialization)

**Location**: `maverick.dsl.serialization.schema`

All workflows are defined in YAML/JSON format. This provides:

- **Declarative syntax**: Clear, readable workflow definitions
- **Discoverability**: Automatic discovery from project, user, and built-in locations
- **Shareability**: Version-controlled workflow definitions across teams
- **Validation**: Schema validation and error reporting at load time
- **Visualization**: Automatic ASCII/Mermaid diagram generation
- **No Python required**: Non-developers can author and modify workflows

```python
from maverick.dsl.serialization.schema import WorkflowFile

# Load from YAML
workflow = WorkflowFile.from_yaml(yaml_content)

# Convert to YAML
yaml_str = workflow.to_yaml()
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

### Workflow Discovery Locations

Workflows are discovered in precedence order (higher overrides lower):

1. **Project**: `.maverick/workflows/` - Project-specific customizations
2. **User**: `~/.config/maverick/workflows/` - User-wide customizations
3. **Built-in**: Packaged with Maverick - Default implementations

### Migration from Decorator DSL

If you have existing Python decorator workflows, see `docs/migrating-from-decorator-dsl.md` for migration guidance. The decorator DSL was removed in favor of the more maintainable and user-friendly YAML approach.

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

## Core Principles

See `.specify/memory/constitution.md` for the authoritative reference.

1. **Async-First**: All agent interactions and workflows MUST be async. Use `asyncio` patterns; no threading for I/O. Workflows yield progress updates as async generators for TUI consumption.

2. **Dependency Injection**: Agents and workflows receive configuration and dependencies, not global state. MCP tool servers are passed in, not created internally.

3. **Fail Gracefully**: One agent/issue failing MUST NOT crash the entire workflow. Capture and report errors with context.

4. **Test-First**: Every public class and function MUST have tests. TDD with Red-Green-Refactor.

5. **Type Safety**: Complete type hints required. Use `@dataclass` or Pydantic `BaseModel` over plain dicts.

6. **Simplicity**: No global mutable state, no god-classes, no premature abstractions.

## Operating Standard (Ownership & Follow-Through)

The default stance is full ownership of the repository state while you work. “That’s not my problem” is not an acceptable response.

- **Do what you’re asked, then keep going**: Complete the requested change end-to-end, then address collateral failures and obvious correctness issues you encountered along the way.
- **Fix what you find**: If you encounter broken tests, lint failures, type errors, flaky behavior, or obvious bugs while working, attempt to fix them—even if they predate your changes.
- **Keep the tree green**: Don’t rationalize failures as “unrelated” or “not introduced by me.” If the repo is failing, the task is not done yet.
- **No artificial scope minimization**: We are not operating under time pressure. Unless explicitly instructed otherwise, prefer a complete, robust solution over a narrowly-scoped patch.
- **No deferral by difficulty**: “Too hard” or “too far-reaching” is a signal to decompose the work, not to stop. Break the problem down and make real progress now.
- **Only defer when truly blocked**: Defer work only when it is impossible in the current context (missing requirements, missing access, non-reproducible failures). If you must defer, document exactly what’s blocked and what the next concrete step is.

## Claude Agent SDK Patterns

- Always specify `allowed_tools` explicitly (principle of least privilege)
- Use `ClaudeSDKClient` for stateful/multi-turn interactions
- Use `query()` for one-shot, stateless interactions
- Custom tools use the `@tool` decorator and `create_sdk_mcp_server()`
- Hooks are async functions matching the SDK's hook signature
- Extract and structure agent outputs; do not return raw text

## Code Style

| Element   | Convention           | Example                            |
| --------- | -------------------- | ---------------------------------- |
| Classes   | PascalCase           | `CodeReviewerAgent`, `FlyWorkflow` |
| Functions | snake_case           | `execute_review`, `create_pr`      |
| Constants | SCREAMING_SNAKE_CASE | `MAX_RETRIES`, `DEFAULT_TIMEOUT`   |
| Private   | Leading underscore   | `_build_prompt`, `_validate_input` |

- Docstrings: Google-style format with Args, Returns, Raises sections
- Exceptions: Hierarchy from `MaverickError` → `AgentError`, `WorkflowError`, `ConfigError`
- No `print()` for output; use logging or TUI updates
- No `shell=True` in subprocess calls without explicit security justification

## Debt Prevention Guidelines

Analysis of past technical debt (#61-#152) reveals recurring patterns. Strict adherence to these rules prevents debt accumulation.

### 1. Testing is Not Optional (Anti-Deferral)

- No PR shall be merged without passing **new** tests covering added functionality
- Do not comment out or skip failing tests; fix them immediately (including failures that predate your change)
- For async components (Agents/Workflows), test concurrency and error states, not just happy paths

### 2. Modularize Early (Keep Files Small)

Long, multi-responsibility modules are a primary driver of slow iteration and merge conflicts. Treat file growth as a design smell.

- **Soft limit**: aim for modules < ~500 LOC and test modules < ~400–600 LOC.
- **Refactor trigger**: if a module exceeds ~800 LOC or has many unrelated top-level definitions, split it as part of the change (or create a `tech debt` issue scoped to the split).
- **Hard stop**: avoid adding new features to modules > ~1000 LOC without first carving out a focused submodule/package.
- **Single responsibility**: each module/package should have one “reason to change” (one domain, one layer, one cohesive feature area).

### 3. Preferred Split Patterns (Repository-Specific)

Use these patterns to prevent the common “god file” failures seen in this repo:

- **CLI**: keep `src/maverick/main.py` as a thin entrypoint; put each Click command in `src/maverick/cli/commands/<command>.py`; keep shared Click options/error handling in `src/maverick/cli/common.py`.
- **Workflows**: use a package-per-workflow (`src/maverick/workflows/<name>/`) and split into `models.py`, `events.py`, `dsl.py`/`constants.py`, and `workflow.py`.
- **TUI models**: split `src/maverick/tui/models.py` into a `src/maverick/tui/models/` package grouped by domain (enums, dialogs, widget state, screen state, theme).
- **Tools (MCP servers)**: split into a package with `runner.py` (subprocess), `errors.py`, `responses.py`, `prereqs.py`, `server.py`, and per-resource tool modules.
- **DSL execution**: isolate per-step-type execution logic into handler modules; keep the executor/coordinator readable and small.
- **Tests**: split by unit-under-test and scenario group; move shared fixtures/factories into a local `conftest.py` (directory-scoped) instead of copy/paste.

### 4. Backwards-Compatible Refactors

When splitting a public module, preserve import stability:

- Prefer creating a package and re-exporting the current public surface from `__init__.py`.
- If external consumers import from the old module path, keep a small shim module that imports/re-exports from the new package for a migration period.
- Maintain `__all__` (or equivalent explicit exports) so the public API stays intentional and discoverable.

### 5. Zero-Tolerance for Duplication (DRY)

- If logic (Git operations, Validation, GitHub API calls) is needed in a second location, **refactor to a shared utility immediately**—do not wait for "cleanup"
- Use Mixins or Composition over inheritance for shared agent capabilities

### 6. Hardening by Default (Anti-Assumption)

- All external calls (GitHub API, Git subprocesses) **MUST** have:
  - Explicit timeouts
  - Retry logic with exponential backoff for network operations
  - Specific exception handling (no bare `except Exception`)

### 7. Type Safety & Constants

- No magic numbers or string literals in logic code; extract to named constants or configuration
- Use `Protocol` (structural typing) to define interfaces between components to avoid circular dependencies

### 8. Documentation Integrity

- Treat documentation examples as code—where possible, add tests that validate code snippets in `README.md` or `docs/quickstart.md`

## Architectural Guardrails (Non-Negotiables)

These “truisms” are required to preserve the clarity and layer boundaries described in `.specify/memory/constitution.md` and the Slidev training. If a change would violate any item below, stop and refactor the design before proceeding.

### 1. TUI is display-only

- `src/maverick/tui/**` MUST NOT execute subprocesses (`subprocess.run`, `asyncio.create_subprocess_exec`) or make network calls.
- TUI code MUST delegate external interactions to runners/services and only update reactive state + render results.

### 2. Async-first means “no blocking on the event loop”

- Never call `subprocess.run` from an `async def` path.
- Prefer `CommandRunner` (`src/maverick/runners/command.py`) for subprocess execution with timeouts.
- DSL `PythonStep` callables MUST be async, or must be run off-thread (e.g., `asyncio.to_thread`) to avoid freezing the TUI/workflows.

### 3. Deterministic ops belong to workflows/runners, not agents

- Agents provide judgment (implementation/review/fix suggestions). They MUST NOT own deterministic side effects like git commits/pushes or running validation.
- Workflows (or DSL steps/actions) own deterministic execution, retries, checkpointing, and error recovery policies.

### 4. Actions must have a single, typed contract

- Workflow actions MUST not return ad-hoc `dict[str, Any]` blobs.
- Use one canonical contract:
  - preferred: frozen dataclasses (with `to_dict()` for DSL serialization), or
  - acceptable: `TypedDict` + validation at boundaries.
- Keep action outputs stable across versions; treat them as public interfaces.

### 5. Resilience features must be real, not stubs

- “Retry/fix loops” and “recovery” must actually invoke the fixer/retry validation or be removed.
- If the DSL/workflow definition is the right place for retry logic, implement it there rather than simulating it in a Python action.

### 6. One canonical wrapper per external system

- Do not create new `git`/`gh`/validation subprocess wrappers in random modules.
- Prefer:
  - `src/maverick/runners/**` for deterministic execution + parsing
  - `src/maverick/tools/**` for MCP surfaces (delegate to runners/utilities)
  - `src/maverick/dsl/context_builders.py` for context composition (delegate; no subprocess re-implementation)

### 7. Tool server factories must be async-safe and consistent

- Factory functions MUST NOT call `asyncio.run()` internally.
- Prefer lazy prerequisite verification on first tool use, or provide an explicit async `verify_prerequisites()` API callers can `await`.
- Return concrete, correct types (avoid `Any` on public APIs).

## Workflows

### FlyWorkflow

Full spec-based development workflow:

1. **Setup**: Sync branch with origin/main, validate spec directory
2. **Implementation**: Parse tasks.md, execute tasks (parallel for "P:" marked)
3. **Code Review**: Parallel CodeRabbit + architecture review
4. **Validation**: Format/lint/build/test with iterative fixes
5. **Convention Update**: Update CLAUDE.md if significant learnings
6. **PR Management**: Generate PR body, create/update via GitHub CLI

### RefuelWorkflow

Tech-debt resolution workflow:

1. **Discovery**: List open issues with target label
2. **Selection**: Analyze and select up to 3 non-conflicting issues
3. **Implementation**: Execute fixes in parallel
4. **Review & Validation**: Same as FlyWorkflow
5. **Finalize**: Mark PR ready, close issues

### Review-and-Fix with Registry Fragment

Accountability-tracked code review workflow fragment (`src/maverick/library/fragments/review-and-fix-with-registry.yaml`):

1. **Gather Context**: Collect PR diff, changed files, and spec files
2. **Parallel Reviews**: Run spec and technical reviewers concurrently
3. **Create Registry**: Merge findings into IssueRegistry with deduplication
4. **Detect Deleted Files**: Auto-block findings for deleted files
5. **Fix Loop**: Iterate until all actionable items resolved or max iterations:
   - Prepare fixer input with attempt history
   - Run ReviewFixerAgent with accountability
   - Update registry with outcomes
   - Check exit conditions
6. **Create Tech Debt Issues**: GitHub issues for blocked/deferred findings

Key accountability features:
- Fixer must report on EVERY issue (no silent skipping)
- Deferred items with invalid justifications are re-sent
- Blocked items require valid technical justification
- Full attempt history preserved for debugging
- Unresolved items become GitHub tech-debt issues

## Dependencies

- [uv](https://docs.astral.sh/uv/) for dependency management (`uv sync`)
- [Make](https://www.gnu.org/software/make/) for development commands (see Development Commands section)
- [GitHub CLI](https://cli.github.com/) (`gh`) for PR and issue management
- Optional: [CodeRabbit CLI](https://coderabbit.ai/) for enhanced code review
- Optional: [ntfy](https://ntfy.sh) for push notifications

## Legacy Plugin Reference

The `plugins/maverick/` directory contains the legacy Claude Code plugin implementation being migrated. Reference for workflow logic:

- `plugins/maverick/commands/` - Slash command definitions
- `plugins/maverick/scripts/` - Shell scripts (sync, validation, PR management)

## Active Technologies
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Click, Pydantic, PyYAML, GitPython (028-maverick-init)
- YAML files (`maverick.yaml`, `~/.config/maverick/config.yaml`) (028-maverick-init)
- Python 3.10+ (with `from __future__ import annotations`) + Textual 0.40+, Claude Agent SDK (`claude-agent-sdk`), Click, Pydantic, PyYAML (030-tui-execution-visibility)
- N/A (in-memory state during workflow execution; streaming buffer with 100KB FIFO limit) (030-tui-execution-visibility)

- Python 3.10+ (with `from __future__ import annotations`) + claude-agent-sdk, textual, click, pyyaml, pydantic (001-maverick-foundation)
- YAML config files (project: `maverick.yaml`, user: `~/.config/maverick/config.yaml`) (001-maverick-foundation)
- Claude Agent SDK (`claude-agent-sdk`), Pydantic for MaverickAgent base class (002-base-agent)
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Pydantic, Git CLI (003-code-reviewer-agent)
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Pydantic, Git CLI, GitHub CLI (`gh`) (004-implementer-issue-fixer-agents)
- N/A (file system for task files, Git for commits) (004-implementer-issue-fixer-agents)
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), GitHub CLI (`gh`) (005-github-mcp-tools)
- N/A (tools interact with GitHub API via CLI) (005-github-mcp-tools)
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Pydantic, Git CLI, ntfy.sh (HTTP API) (006-utility-mcp-tools)
- N/A (tools interact with external systems: git, ntfy.sh, validation commands) (006-utility-mcp-tools)
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Pydantic (for configuration models) (007-safety-hooks)
- N/A (metrics in-memory with rolling window; logs via standard Python logging) (007-safety-hooks)
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Pydantic, asyncio (008-validation-workflow)
- N/A (in-memory state during workflow execution) (008-validation-workflow)
- Python 3.10+ (with `from __future__ import annotations`) + Pydantic (BaseModel), dataclasses (frozen/slots), asyncio (009-fly-workflow)
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Pydantic (BaseModel), dataclasses (frozen/slots), asyncio (010-refuel-workflow)
- N/A (no persistence; in-memory state during workflow execution) (010-refuel-workflow)
- Python 3.10+ (with `from __future__ import annotations`) + Textual 0.40+, Click (CLI entry point), Pydantic (for configuration models) (011-tui-layout-theming)
- N/A (in-memory state; workflows provide state via async generators) (011-tui-layout-theming)
- Python 3.10+ (with `from __future__ import annotations`) + Textual 0.40+, Rich (syntax highlighting via Textual's built-in support) (012-workflow-widgets)
- N/A (in-memory state; widgets receive immutable snapshots) (012-workflow-widgets)
- Python 3.10+ (with `from __future__ import annotations`) + Textual 0.40+, Click (CLI), Pydantic (configuration models) (013-tui-interactive-screens)
- JSON file at `~/.config/maverick/history.json` for workflow history (013-tui-interactive-screens)
- Python 3.10+ (with `from __future__ import annotations`) + Click (CLI), Textual (TUI), Pydantic (config validation), existing workflows (FlyWorkflow, RefuelWorkflow) (014-cli-entry-point)
- Python 3.10+ (with `from __future__ import annotations`) + pytest>=7.0.0, pytest-asyncio>=0.21.0, pytest-cov>=4.0.0, ruff, mypy, textual (for pilot testing), click (for CliRunner) (015-testing-infrastructure)
- N/A (no persistent storage; in-memory state during test execution) (015-testing-infrastructure)
- Python 3.10+ (with `from __future__ import annotations`) + subprocess (stdlib), dataclasses (stdlib), pathlib (stdlib) (016-git-operations)
- N/A (operates on git repositories) (016-git-operations)
- Python 3.10+ with `from __future__ import annotations` + asyncio (stdlib), dataclasses (stdlib), pathlib (stdlib), signal (stdlib) (017-subprocess-runners)
- N/A (in-memory state during execution) (017-subprocess-runners)
- Python 3.10+ (with `from __future__ import annotations`) + pathlib (stdlib), logging (stdlib), re (stdlib), existing GitOperations utility (018-context-builder)
- N/A (read-only file access, no persistence) (018-context-builder)
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Pydantic (for input models), standard logging (019-generator-agents)
- N/A (stateless text generation, no persistence) (019-generator-agents)
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Pydantic, Click, asyncio (020-workflow-refactor)
- N/A (in-memory state during workflow execution; git for persistence) (020-workflow-refactor)
- N/A (no persistence changes) (021-agent-tool-permissions)
- Python 3.10+ (with `from __future__ import annotations`) + Pydantic (BaseModel for configuration/results), dataclasses (frozen/slots for events), asyncio (async workflow execution), Claude Agent SDK (for agent/generate steps) (022-workflow-dsl)
- N/A (in-memory state during workflow execution; results are returned to caller) (022-workflow-dsl)
- Python 3.10+ (with `from __future__ import annotations`) + claude-agent-sdk, pydantic, asyncio (stdlib), pathlib (stdlib), hashlib (stdlib), json (stdlib) (023-dsl-flow-control)
- JSON files under `.maverick/checkpoints/` for checkpoint persistence (023-dsl-flow-control)
- Python 3.10+ (with `from __future__ import annotations`) + claude-agent-sdk, Textual 0.40+, Click, Pydantic, PyYAML (for YAML parsing) (024-workflow-serialization-viz)
- N/A (workflow files are user-managed; no Maverick-owned persistence) (024-workflow-serialization-viz)
- Python 3.10+ (with `from __future__ import annotations`) + claude-agent-sdk, Pydantic, PyYAML, Click, Textual, pathlib (stdlib) (025-builtin-workflow-library)
- N/A (workflow files are user-managed YAML/Python; no Maverick-owned persistence) (025-builtin-workflow-library)
- Python 3.10+ (with `from __future__ import annotations`) + claude-agent-sdk, Pydantic, PyYAML, asyncio (stdlib), subprocess (stdlib), shutil (stdlib) for workflow actions; DSL-based workflow definitions with YAML serialization (026-dsl-builtin-workflows)
- N/A for persistence; in-memory state during workflow execution; optional JSON checkpoints under `.maverick/checkpoints/` (026-dsl-builtin-workflows)

## Recent Changes

- 003-code-reviewer-agent: Added Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK (`claude-agent-sdk`), Pydantic, Git CLI
- 002-base-agent: Added MaverickAgent abstract base class with Claude Agent SDK integration
- 001-maverick-foundation: Added Python 3.10+ (with `from __future__ import annotations`) + claude-agent-sdk, textual, click, pyyaml, pydantic
