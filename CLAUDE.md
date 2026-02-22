# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Maverick is a Python CLI application that automates AI-powered development workflows using the Claude Agent SDK. It orchestrates multi-phase workflows: feature implementation from task lists, parallel code review, convention updates, and PR management.

## Technology Stack

| Category        | Technology              | Notes                                    |
| --------------- | ----------------------- | ---------------------------------------- |
| Language        | Python 3.10+            | Use `from __future__ import annotations` |
| Package Manager | uv                      | Fast, reproducible builds via `uv.lock`  |
| Build System    | Make                    | AI-friendly commands with minimal output |
| AI/Agents       | Claude Agent SDK        | `claude-agent-sdk` package               |
| CLI             | Click                   | `click` package                          |
| CLI Output      | Rich                    | `rich` package (auto TTY detection)      |
| Validation      | Pydantic                | For configuration and data models        |
| Testing         | pytest + pytest-asyncio | Parallel via xdist (`-n auto`)           |
| Linting         | Ruff                    | Fast, comprehensive Python linter        |
| Type Checking   | MyPy                    | Strict mode recommended                  |
| VCS (writes)    | Jujutsu (jj)            | `maverick.jj.client.JjClient` for all jj ops |
| VCS (reads)     | GitPython               | `maverick.git` wraps GitPython (read-only) |
| VCS (protocol)  | VcsRepository           | `maverick.vcs` abstracts git/jj for reads  |
| Workspaces      | WorkspaceManager        | `maverick.workspace` — hidden jj clones    |
| GitHub API      | PyGithub                | `maverick.utils.github_client`           |
| Logging         | structlog               | `maverick.logging.get_logger()`          |
| Retry Logic     | tenacity                | `@retry` decorator or `AsyncRetrying`    |
| Secret Detection| detect-secrets          | `maverick.utils.secrets`                 |

## Third-Party Library Standards

These libraries are the canonical choices for their domains. Do NOT introduce alternatives or custom implementations.

### Jujutsu / jj (`maverick.library.actions.jj`)

**Use for**: All write-path VCS operations (commit, push, merge, branch).
Requires colocated mode (`jj git init --colocate`) so `.git` is shared.

```python
from maverick.library.actions.jj import git_commit, git_push

result = await git_commit("feat: add feature")
await git_push()
```

**Do NOT**: Shell out to `git` for write operations. Use `jj` actions instead.

### GitPython (`maverick.git`)

**Use for**: Read-only git operations (diffs, status, log, blame). Works
unchanged in colocated mode because jj and git share the `.git` directory.

```python
from maverick.git import AsyncGitRepository

repo = AsyncGitRepository(path)
diff = await repo.diff("main")
```

**Do NOT**: Use GitPython for write operations (commits, pushes). Use jj actions.

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
├── jj/                  # JjClient — typed jj (Jujutsu) wrapper
│   ├── client.py        # JjClient (CommandRunner-based, async)
│   ├── models.py        # Frozen dataclass result types
│   ├── errors.py        # JjError hierarchy under MaverickError
│   └── repository.py    # JjRepository (VcsRepository protocol impl)
├── vcs/                 # VCS abstraction layer
│   ├── protocol.py      # VcsRepository runtime-checkable protocol
│   └── factory.py       # create_vcs_repository() auto-detection
├── workspace/           # Hidden workspace lifecycle management
│   ├── manager.py       # WorkspaceManager (create/bootstrap/teardown)
│   ├── models.py        # WorkspaceInfo, WorkspaceState, result types
│   └── errors.py        # WorkspaceError hierarchy
├── workflows/           # Workflow orchestration
│   ├── fly.py           # FlyWorkflow - full spec-based workflow
│   └── refuel.py        # RefuelWorkflow - tech-debt resolution
├── tools/               # MCP tool definitions
├── hooks/               # Safety and logging hooks
└── utils/               # Shared utilities
```

### Separation of Concerns

- **Agents**: Know HOW to do a task (system prompts, tool selection, Claude SDK interaction)
- **Workflows**: Know WHAT to do and WHEN (orchestration, state management, sequencing)
- **Tools**: Wrap external systems (GitHub CLI, git, notifications)
- **JjClient**: Typed wrapper around `jj` CLI with retries, timeouts, and error hierarchy
- **WorkspaceManager**: Lifecycle for hidden jj workspaces (`~/.maverick/workspaces/`)
- **VcsRepository**: Protocol abstracting git vs jj for read operations

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

| Command               | Purpose                                     |
| --------------------- | ------------------------------------------- |
| `make test`           | Run all tests in parallel (errors only)     |
| `make test-fast`      | Unit tests only, no slow tests (fastest)    |
| `make test-cov`       | Run tests with coverage report              |
| `make test-integration` | Run integration tests only                |
| `make lint`           | Run ruff linter (errors only)               |
| `make typecheck`      | Run mypy (errors only)                      |
| `make format`         | Check formatting (diff if needed)           |
| `make format-fix`     | Apply formatting fixes                      |
| `make check`          | Run all checks (lint, typecheck, test)      |
| `make ci`             | CI mode: fail fast on any error             |
| `make clean`          | Remove build artifacts and caches           |
| `make VERBOSE=1 test` | Full output for debugging                   |

## Core Principles

See `.specify/memory/constitution.md` for the authoritative reference.

1. **Async-First**: All agent interactions and workflows MUST be async. Use `asyncio` patterns; no threading for I/O. Workflows yield progress updates as async generators for CLI consumption.

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
- No `print()` for output; use logging or Rich Console
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

### 1. Async-first means "no blocking on the event loop"

- Never call `subprocess.run` from an `async def` path.
- Prefer `CommandRunner` (`src/maverick/runners/command.py`) for subprocess execution with timeouts.
- DSL `PythonStep` callables MUST be async, or must be run off-thread (e.g., `asyncio.to_thread`) to avoid blocking workflows.

### 2. Deterministic ops belong to workflows/runners, not agents

- Agents provide judgment (implementation/review/fix suggestions). They MUST NOT own deterministic side effects like git commits/pushes or running validation.
- Workflows (or DSL steps/actions) own deterministic execution, retries, checkpointing, and error recovery policies.

### 3. Actions must have a single, typed contract

- Workflow actions MUST not return ad-hoc `dict[str, Any]` blobs.
- Use one canonical contract:
  - preferred: frozen dataclasses (with `to_dict()` for DSL serialization), or
  - acceptable: `TypedDict` + validation at boundaries.
- Keep action outputs stable across versions; treat them as public interfaces.

### 4. Resilience features must be real, not stubs

- “Retry/fix loops” and “recovery” must actually invoke the fixer/retry validation or be removed.
- If the DSL/workflow definition is the right place for retry logic, implement it there rather than simulating it in a Python action.

### 5. One canonical wrapper per external system

- Do not create new `git`/`gh`/validation subprocess wrappers in random modules.
- Prefer:
  - `src/maverick/runners/**` for deterministic execution + parsing
  - `src/maverick/tools/**` for MCP surfaces (delegate to runners/utilities)
  - `src/maverick/dsl/context_builders.py` for context composition (delegate; no subprocess re-implementation)

### 6. Tool server factories must be async-safe and consistent

- Factory functions MUST NOT call `asyncio.run()` internally.
- Prefer lazy prerequisite verification on first tool use, or provide an explicit async `verify_prerequisites()` API callers can `await`.
- Return concrete, correct types (avoid `Any` on public APIs).

### 7. Workspace isolation requires explicit cwd threading

All DSL steps that operate inside a hidden workspace MUST receive `cwd` pointing to the
workspace path. Without it, agents and validators silently operate on the user's working
directory instead.

- Agent steps: pass `cwd` in the step's `context` dict
- Validate steps: pass `cwd` via the workflow/fragment `inputs` (not `kwargs` — ValidateStepRecord doesn't support kwargs)
- Review actions: pass `cwd` to `gather_local_review_context()` and `run_review_fix_loop()`
- jj actions: pass `cwd` (accepts `str | Path | None`); `_make_client` coerces with `Path(cwd)`

See `.specify/memory/constitution.md` Appendix E for the full architecture.

### 8. DSL expressions resolve to strings — coerce at boundaries

All `${{ }}` expressions resolve to JSON-serializable types (strings). Action handlers MUST
coerce to native Python types:

```python
# Path coercion — DSL passes string, code needs Path
cwd = Path(input_cwd) if input_cwd else Path.cwd()

# Integer coercion — YAML int fields cannot accept ${{ }} expressions
# Use hardcoded values or pass through inputs with explicit int() conversion
```

Violations cause `AttributeError: 'str' object has no attribute 'is_dir'` or similar.

## Workflows

Maverick uses a beads-only workflow model. All development is driven by beads (units of work managed by the `bd` CLI tool).

### CLI Commands

| Command | Purpose |
|---------|---------|
| `maverick fly [options]` | Pick next ready bead(s) and iterate (bead execution) |
| `maverick land [options]` | Curate history and push (finalize fly work) |
| `maverick refuel speckit <spec_dir>` | Create beads from a SpecKit specification |
| `maverick workspace status` | Show workspace state for current project |
| `maverick workspace clean` | Remove workspace for current project |
| `maverick init` | Initialize a new Maverick project |
| `maverick uninstall` | Remove Maverick configuration |

### fly (Bead-Driven Development)

Iterates over ready beads until done. Runs the `fly-beads` DSL workflow:

1. **Preflight**: Check API, git, jj, and bd prerequisites
2. **Create workspace**: Clone user repo into `~/.maverick/workspaces/<project>/` via `jj git clone`
3. **Bead Loop**: Select next ready bead, implement, validate, review, commit (via jj), close

All fly work happens in the hidden workspace — the user's working directory is untouched. Run `maverick land` after `fly` to curate and push. Preflight MUST use `check_validation_tools: false` because the workspace `.venv` doesn't exist until bootstrap; rely on `sync_deps` step to install tools before validation.

Options: `--epic` (optional, filter by epic), `--max-beads` (default 30), `--dry-run`, `--skip-review`, `--list-steps`, `--session-log`

### land (Curate and Push)

Finalizes work from `fly` by reorganizing commits into clean history and pushing. Three modes:

- **Approve** (default): curate → interactive prompt → `jj git push` → teardown workspace
- **Eject** (`--eject`): curate → push preview branch → keep workspace
- **Finalize** (`--finalize`): create PR from preview branch → teardown

Uses an AI agent (CuratorAgent) for intelligent reorganization, with user approval. Falls back to git push when no workspace exists.

Options: `--no-curate`, `--dry-run`, `--yes`/`-y`, `--base` (default "main"), `--heuristic-only`, `--eject`, `--finalize`, `--branch`

### refuel speckit (Bead Creation)

Creates beads from a SpecKit specification directory containing `tasks.md`:

1. **Parse**: Extract phases and tasks from tasks.md
2. **Create**: Generate epic and work beads via `bd`
3. **Wire**: Set up dependencies between beads

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

## Multi-Repository Development

Maverick development involves two distinct repositories. **Never confuse them.**

| Repository | Purpose | Remote URL |
|------------|---------|------------|
| **maverick** | Core CLI application | `get2knowio/maverick.git` |
| **sample-maverick-project** | E2E test project | `get2knowio/sample-maverick-project.git` |

### Branch Naming Conventions

- **Maverick branches**: `###-feature-name` where `###` >= 020 (e.g., `030-tui-streaming`)
- **Sample project branches**: `###-feature-name` where `###` starts at 001 (e.g., `001-greet-cli`)

**CRITICAL**: Before pushing any branch, verify you're in the correct repository:

```bash
git remote -v  # Check remote URL
pwd            # Check working directory
```

**Do NOT push sample project branches (001-xxx) to the maverick repository.** This causes
confusion and requires cleanup. See `.specify/memory/constitution.md` Appendix D for full
conventions and recovery procedures.

## Legacy Plugin Reference

The `plugins/maverick/` directory contains the legacy Claude Code plugin implementation being migrated. Reference for workflow logic:

- `plugins/maverick/commands/` - Slash command definitions
- `plugins/maverick/scripts/` - Shell scripts (sync, validation, PR management)

## Active Technologies
- Python 3.10+ (with `from __future__ import annotations`) + Claude Agent SDK v0.1.18 (`claude-agent-sdk`, `output_format` structured output), Click, Rich, Pydantic, PyYAML, GitPython
- YAML files (`maverick.yaml`, `~/.config/maverick/config.yaml`)
- JSON files under `.maverick/checkpoints/` for checkpoint persistence
- DSL-based workflow definitions with YAML serialization

## Recent Changes
- 030-typed-output-contracts: Added Pydantic-based typed output contracts for agents using Claude Agent SDK `output_format` structured output
