<!--
Sync Impact Report
==================
Version change: 1.10.0 to 1.11.0
Modified principles: None
Removed sections: None
Updated sections:
  - Appendix E: Replaced the stale "fly hidden workspace" narrative (that model was
    retired when the single-repo CWD model, Guardrail 0, became the default) with a
    pointer to Guardrail 0 as the default model plus the spec-chain's hidden jj
    workspace as the one documented, scoped exception (spec 050-headless-spec-chain).
Templates requiring updates: None
Source: Feature 050-headless-spec-chain -- maverick spec introduces the first
hidden-workspace exception to Guardrail 0 since the single-repo model was adopted;
Appendix E's prior content predated that model and no longer matched any running code.
-->

# Maverick Constitution

## Core Principles

### I. Async-First

All agent interactions and workflows MUST be async. This is non-negotiable for maintaining
responsiveness and enabling concurrent operations.

- Use `asyncio` patterns consistently; no threading for I/O operations
- Workflows MUST yield progress updates as async generators for TUI consumption
- All Claude Agent SDK interactions are inherently async and MUST remain so
- Blocking I/O in async contexts is prohibited
- **Never call `subprocess.run` from an `async def` path**—use `CommandRunner` or
  `asyncio.create_subprocess_exec` with proper timeouts
- Python step callables MUST be async, or MUST be offloaded via `asyncio.to_thread`
  to avoid freezing the TUI/workflows

**Rationale**: The TUI requires responsive updates during long-running agent operations.
Async generators enable real-time progress reporting without blocking the event loop.
Blocking calls in async contexts cause UI freezes and deadlocks.

### II. Separation of Concerns

Components have distinct, non-overlapping responsibilities:

- **Agents**: Know HOW to do a task (system prompts, tool selection, Claude SDK interaction).
  Agents provide judgment (implementation/review/fix suggestions). They MUST NOT own
  deterministic side effects like git commits/pushes or running validation.
- **Workflows**: Know WHAT to do and WHEN (orchestration, state management, sequencing).
  Workflows (or DSL steps/actions) own deterministic execution, retries, checkpointing,
  and error recovery policies.
- **TUI**: Presents state and captures input. **Display-only—no business logic.**
  `src/maverick/tui/**` MUST NOT execute subprocesses (`subprocess.run`,
  `asyncio.create_subprocess_exec`) or make network calls. TUI code MUST delegate
  external interactions to runners/services and only update reactive state + render results.

  **Streaming-First Design**: The TUI follows a streaming-first philosophy where the
  primary content area is a unified, scrolling event stream. This pattern prioritizes:
  - Single-column streaming output as the main focus (inspired by Claude Code's interface)
  - Minimal chrome, maximum content—every pixel should convey information
  - Subtle status indicators that inform without distracting
  - Chronological workflow events (step starts, agent outputs, tool calls, completions)

  All workflow step types contribute to this unified stream through the `StepOutput` event
  or type-specific events like `AgentStreamChunk`. See Appendix C for architecture details.
- **Tools**: Wrap external systems (GitHub CLI, git, notifications). Delegate execution
  to runners/utilities; do not re-implement subprocess logic.

Business logic MUST NOT leak into TUI components. Agents MUST NOT orchestrate themselves.

**Rationale**: Clear boundaries enable independent testing, easier debugging, and prevent
the coupling that makes systems brittle. The TUI display-only rule prevents UI code from
accumulating I/O responsibilities that belong in the service layer.

### III. Dependency Injection

Agents and workflows MUST receive configuration and dependencies, not access global state.

- MCP tool servers are passed in, not created internally
- Configuration objects are injected at construction time
- External service clients (GitHub, git) are injectable for testing
- No module-level mutable state

**Rationale**: Dependency injection enables testing with mocks and makes dependencies
explicit rather than hidden.

### IV. Fail Gracefully, Recover Aggressively

One agent or issue failing MUST NOT crash the entire workflow. The system MUST prioritize
forward progress over early termination.

- Always capture and report errors with context before attempting recovery
- Retry failed operations with exponential backoff (default: 3 attempts)
- Provide actionable error messages that help diagnose what went wrong
- Use structured error types from the exception hierarchy
- Log errors with sufficient context for debugging
- Continue processing remaining work items even when some fail
- Aggregate partial results rather than discarding successful work
- **Resilience features MUST be real, not stubs**: "Retry/fix loops" and "recovery" MUST
  actually invoke the fixer/retry validation. If the workflow definition is the right
  place for retry logic, implement it there rather than simulating it in a Python action.

**Rationale**: Parallel agent execution means partial success is valuable. Users should
get results from successful operations even when some fail. Unattended operation requires
the system to recover from transient failures without human intervention. Stub resilience
creates false confidence and hides real failure modes.

### V. Test-First (Anti-Deferral)

Every public class and function MUST have tests. Testing is mandatory, not optional.
No PR shall be merged without tests covering new functionality.

- Use pytest fixtures for common setup
- Mock external dependencies (Claude API, GitHub CLI, filesystem)
- TUI tests use Textual's `pilot` fixture
- Async tests use `pytest.mark.asyncio`
- Tests are written BEFORE implementation (Red-Green-Refactor)
- Do NOT comment out or skip failing tests; fix them immediately (including failures
  that predate your change)
- For async components (Agents/Workflows), testing MUST verify concurrency and error states,
  not just happy paths

**Rationale**: TDD catches design problems early. Comprehensive tests enable confident
refactoring and serve as executable documentation. Deferring tests creates debt that
compounds over time (learned from issues #61-#152).

### VI. Type Safety & Typed Contracts

Complete type hints are required throughout the codebase. No magic numbers or strings.
All workflow actions MUST have a single, typed contract.

- All public functions MUST have complete type annotations
- Use `TypeAlias` for complex types to improve readability
- Prefer `@dataclass` or Pydantic `BaseModel` over plain dicts for structured data
- Use `Protocol` for interfaces when duck typing is needed (avoids circular dependencies)
- Use `@dataclass(frozen=True)` for immutable value objects
- Use `@dataclass(slots=True)` for frequently instantiated objects
- No magic numbers or string literals in logic code; extract to named constants or config
- Use `Protocol` (structural typing) to define interfaces between components
  (e.g., between DSL and Agents) to avoid circular dependencies and tight coupling
- **Workflow actions MUST NOT return ad-hoc `dict[str, Any]` blobs.** Use one canonical
  contract: preferred is frozen dataclasses (with `to_dict()` for DSL serialization),
  or acceptable is `TypedDict` + validation at boundaries.
- **Keep action outputs stable across versions**; treat them as public interfaces.
- **Pydantic Field descriptions**: All required `Field(...)` declarations in Pydantic
  models SHOULD include a `description` parameter for API documentation. This enables
  auto-generated schemas and improves developer experience.

**Rationale**: Static typing catches errors at development time, improves IDE support,
and serves as inline documentation. Named constants prevent "magic value" bugs and
enable centralized configuration changes. Typed contracts prevent runtime surprises
and make refactoring safe.

### VII. Simplicity & DRY

Avoid over-engineering. Start simple and add complexity only when justified.
Zero tolerance for duplication.

- No global mutable state
- No massive god-classes; prefer composition over inheritance
- No hardcoded paths; use pathlib and configuration
- No premature abstractions; three similar lines are better than a premature helper
- No `shell=True` in subprocess calls without explicit security justification
- No `print()` for output; use logging or TUI updates
- If logic regarding Git operations, Validation, or GitHub API calls is needed in a
  second location, refactor to a shared utility IMMEDIATELY—do not wait for "cleanup"
- Use Mixins or Composition over inheritance for shared agent capabilities

**Rationale**: YAGNI (You Aren't Gonna Need It). Simple code is easier to understand,
test, and maintain. Copy-paste creates maintenance nightmares and inconsistent behavior
(learned from `ImplementerAgent` vs `IssueFixerAgent` duplication in issues #61-#152).

### VIII. Relentless Progress

The system MUST make forward progress at all costs during unattended operation. This is
the paramount principle for autonomous agent orchestration.

- **Never give up silently**: Exhaust all recovery options before failing a task
- **Checkpoint state**: Persist progress after each significant operation to enable resumption
- **Degrade gracefully**: When optimal paths fail, fall back to slower but reliable alternatives
- **Isolate failures**: One task's failure MUST NOT block unrelated tasks from proceeding
- **Auto-recover external dependencies**: Retry with backoff for GitHub API, git operations,
  and other external services (default: 3 attempts with exponential backoff)
- **Preserve partial work**: Commit completed work before attempting risky operations
- **Log for resumption**: Record sufficient state to allow manual or automatic retry

Recovery hierarchy (in order of preference):
1. Retry the exact operation with backoff
2. Try an alternative approach to achieve the same goal
3. Skip the failing component and continue with remaining work
4. Checkpoint state and surface actionable error for user intervention

**Rationale**: Maverick operates unattended for extended periods. Human intervention is
expensive and slow. The system must be resilient to transient failures, network issues,
API rate limits, and unexpected errors. Forward progress is more valuable than early
termination with a clean error message.

### IX. Hardening by Default

All external interactions MUST assume unreliable networks and resources.
Never assume external calls will succeed on the first attempt.

- All external calls (GitHub API, Git subprocesses) MUST have:
  - Explicit timeouts (no infinite waits)
  - Retry logic with exponential backoff for network operations
  - Specific exception handling (no bare `except Exception`)
- **Retry logic MUST use tenacity**: Use `@retry` decorator or `AsyncRetrying` for all
  retry logic. Do NOT write manual `for attempt in range(retries):` loops. Tenacity
  provides proper exponential backoff, retry statistics, and consistent behavior.
- Validate at system boundaries (user input, external APIs) but trust internal code
- Documentation examples MUST be treated as code—add tests that validate code snippets
  in `README.md` or `docs/quickstart.md` to ensure they remain executable

**Rationale**: Transient failures are inevitable in distributed systems. Proper hardening
prevents cascading failures and makes debugging easier. Bare exception handlers hide bugs.
(Learned from network reliability issues in #61-#152.)

### X. Architectural Guardrails

These concrete rules operationalize the abstract principles above. Violations MUST be
caught in code review. If a change would violate any item below, stop and refactor
the design before proceeding.

1. **TUI is display-only**: `src/maverick/tui/**` MUST NOT execute subprocesses or make
   network calls. TUI code delegates to runners/services and only updates reactive
   state + renders results. (Enforces Principle II)

2. **Async-first means no blocking on the event loop**: Never call `subprocess.run` from
   an `async def` path. Prefer `CommandRunner` (`src/maverick/runners/command.py`) for
   subprocess execution with timeouts. Python step callables MUST be async or offloaded
   via `asyncio.to_thread`. (Enforces Principle I)

3. **Deterministic ops belong to workflows/runners, not agents**: Agents provide judgment.
   They MUST NOT own deterministic side effects like git commits/pushes or running
   validation. Workflows own execution, retries, checkpointing, and recovery. (Enforces
   Principle II)

4. **Actions MUST have a single typed contract**: Workflow actions MUST NOT return ad-hoc
   `dict[str, Any]` blobs. Use frozen dataclasses with `to_dict()` or `TypedDict` with
   boundary validation. Keep outputs stable across versions. (Enforces Principle VI)

5. **Resilience features MUST be real, not stubs**: Retry/fix loops MUST actually invoke
   fixers and re-run validation. If the workflow definition is the right place for retry
   logic, implement it there. (Enforces Principle IV)

6. **One canonical wrapper per external system**: Do not duplicate `git`/`gh`/validation
   wrappers. Prefer `src/maverick/runners/**` for execution and have tools/context
   builders delegate. (Enforces Principle VII)

7. **Tool server factories MUST be async-safe**: Factory functions MUST NOT call
   `asyncio.run()` internally. Prefer lazy prerequisite verification on first tool use,
   or provide an explicit async `verify_prerequisites()` API. Return concrete types;
   avoid `Any` on public APIs. (Enforces Principles I and VI)

8. **Use canonical third-party libraries**: Do NOT introduce alternatives to the
   established libraries. Specifically:
   - **Git operations**: Use `maverick.git.GitRepository` or `AsyncGitRepository`,
     NOT `subprocess.run("git ...")`
   - **GitHub API**: Use `maverick.utils.github_client.GitHubClient`, NOT subprocess
     calls to `gh` CLI (except for auth token retrieval)
   - **Logging**: Use `maverick.logging.get_logger()`, NOT stdlib `logging.getLogger()`
   - **Retry logic**: Use `tenacity`, NOT manual `for attempt in range()` loops
   - **Secret detection**: Use `maverick.utils.secrets.detect_secrets`, NOT custom regex
   (Enforces Principles VII and IX. See Appendix B for complete library list.)

9. **TUI streaming follows the unified event pattern**: All workflow step types MUST
   contribute to the unified stream via standardized events:
   - **Agent steps**: Use `AgentStreamChunk` for streaming output and thinking
   - **Python/deterministic steps**: Use `StepOutput` for progress and status messages
   - **All steps**: Emit `StepStarted`/`StepCompleted` for lifecycle tracking
   - The `UnifiedStreamWidget` is the canonical display component for workflow execution
   - FIFO buffer management (100KB limit) prevents memory exhaustion
   - 50ms debounced updates prevent UI flickering during rapid event bursts
   (Enforces Principle II streaming-first design. See Appendix C for architecture.)

10. **Branch names MUST match the target repository**: When working with multiple
    repositories (e.g., maverick core vs. sample-maverick-project), branch names MUST
    use the appropriate prefix for the target repository:
    - **Maverick core**: Use `###-feature-name` format (e.g., `030-tui-streaming`) where
      `###` corresponds to a maverick feature spec number
    - **Sample project**: Use `###-feature-name` format (e.g., `001-greet-cli`) where
      `###` corresponds to a sample project feature spec number
    - **Never push sample project branches to maverick core** (and vice versa)
    - Verify `git remote -v` before pushing to ensure you're targeting the correct repo
    (Enforces repository isolation. See Appendix D for multi-repo workflow.)

**Rationale**: Abstract principles are necessary but insufficient. Concrete, reviewable
rules prevent principle drift and make code review objective. Each guardrail traces to
the principle it operationalizes.

### XI. Modularize Early

Long, multi-responsibility modules are a primary driver of slow iteration, merge
conflicts, and accumulated technical debt. Treat file growth as a design smell.

**Line-of-Code Thresholds**:

- **Soft limit**: Aim for modules < ~500 LOC and test modules < ~400–600 LOC
- **Refactor trigger**: If a module exceeds ~800 LOC or has many unrelated top-level
  definitions, split it as part of the change (or create a `tech debt` issue scoped
  to the split)
- **Hard stop**: Avoid adding new features to modules > ~1000 LOC without first carving
  out a focused submodule/package

**Single Responsibility**: Each module/package MUST have one "reason to change"—one
domain, one layer, one cohesive feature area.

**Backwards-Compatible Refactors**: When splitting a public module, preserve import
stability:

- Prefer creating a package and re-exporting the current public surface from `__init__.py`
- If external consumers import from the old module path, keep a small shim module that
  imports/re-exports from the new package for a migration period
- Maintain `__all__` (or equivalent explicit exports) so the public API stays intentional
  and discoverable

**Rationale**: "God modules" accumulate multiple responsibilities, slow navigation,
increase merge conflicts, and make testing brittle. Proactive modularization prevents
the debt spiral observed in issues #61-#152. Small, focused modules are easier to
understand, test, and refactor independently.

### XII. Ownership & Follow-Through

The default stance is full ownership of the repository state while working. "That's not
my problem" is not an acceptable response.

- **Do what you're asked, then keep going**: Complete the requested change end-to-end,
  then address collateral failures and obvious correctness issues encountered along the way
- **Fix what you find**: If you encounter broken tests, lint failures, type errors, flaky
  behavior, or obvious bugs while working, attempt to fix them—even if they predate your
  changes
- **Keep the tree green**: Do not rationalize failures as "unrelated" or "not introduced
  by me." If the repo is failing, the task is not done yet
- **No artificial scope minimization**: We are not operating under time pressure. Unless
  explicitly instructed otherwise, prefer a complete, robust solution over a narrowly-scoped
  patch
- **No deferral by difficulty**: "Too hard" or "too far-reaching" is a signal to decompose
  the work, not to stop. Break the problem down and make real progress now
- **Only defer when truly blocked**: Defer work only when it is impossible in the current
  context (missing requirements, missing access, non-reproducible failures). If you must
  defer, document exactly what's blocked and what the next concrete step is

**Rationale**: Autonomous agents and human contributors alike must leave the codebase
better than they found it. Partial fixes that "work for my change" accumulate into
systemic rot. Full ownership prevents the tragedy of the commons where everyone assumes
someone else will clean up.

## Appendix A: Preferred Split Patterns

Use these repository-specific patterns to prevent common "god file" failures:

| Component | Pattern |
|-----------|---------|
| **CLI** | Keep `src/maverick/main.py` as a thin entrypoint; put each Click command in `src/maverick/cli/commands/<command>.py`; keep shared Click options/error handling in `src/maverick/cli/common.py` |
| **Workflows** | Use a package-per-workflow (`src/maverick/workflows/<name>/`) and split into `models.py`, `events.py`, `dsl.py`/`constants.py`, and `workflow.py` |
| **TUI models** | Split `src/maverick/tui/models.py` into a `src/maverick/tui/models/` package grouped by domain (enums, dialogs, widget state, screen state, theme) |
| **Tools (MCP servers)** | Split into a package with `runner.py` (subprocess), `errors.py`, `responses.py`, `prereqs.py`, `server.py`, and per-resource tool modules |
| **Tests** | Split by unit-under-test and scenario group; move shared fixtures/factories into a local `conftest.py` (directory-scoped) instead of copy/paste |

## Technology Stack

These technology choices are non-negotiable constraints for all Maverick development:

| Category | Technology | Notes |
|----------|------------|-------|
| Language | Python 3.10+ | Use `from __future__ import annotations` |
| AI/Agents | Claude Agent SDK | `claude-agent-sdk` package |
| TUI | Textual | `textual` package |
| CLI | Click | `click` package |
| Validation | Pydantic | For configuration and data models |
| Testing | pytest + pytest-asyncio | All tests async-compatible |
| Linting | Ruff | Fast, comprehensive Python linter |
| Type Checking | MyPy | Strict mode recommended |
| VCS (writes) | Jujutsu (jj) | `maverick.jj.client.JjClient` for all jj ops |
| VCS (reads) | GitPython | `maverick.git` wraps GitPython (read-only) |
| VCS (protocol) | VcsRepository | `maverick.vcs` abstracts git/jj for reads |
| Workspaces | WorkspaceManager | `maverick.workspace` — hidden jj clones |

## Code Style & Conventions

### Naming

| Element | Convention | Example |
|---------|------------|---------|
| Classes | PascalCase | `CodeReviewerAgent`, `FlyWorkflow` |
| Functions/Methods | snake_case | `execute_review`, `create_pr` |
| Constants | SCREAMING_SNAKE_CASE | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| Private | Leading underscore | `_build_prompt`, `_validate_input` |

### Docstrings

All public classes and functions MUST have docstrings using Google-style format:

```python
def execute_task(task_id: str, config: TaskConfig) -> TaskResult:
    """Execute a single task with the given configuration.

    Args:
        task_id: Unique identifier for the task to execute.
        config: Configuration object containing execution parameters.

    Returns:
        TaskResult containing execution status and any outputs.

    Raises:
        TaskNotFoundError: If the task_id does not exist.
        ExecutionError: If the task fails during execution.
    """
```

### Error Handling

- Define custom exceptions in a dedicated `exceptions.py` module
- Exception hierarchy: `MaverickError` → `AgentError`, `WorkflowError`, `ConfigError`, etc.
- Never catch bare `Exception` except at top-level boundaries
- Log errors with context before re-raising or wrapping

## Claude Agent SDK Patterns

When working with the Claude Agent SDK, follow these patterns:

- Always specify `allowed_tools` explicitly (principle of least privilege)
- Use `ClaudeSDKClient` for stateful/multi-turn interactions
- Use `query()` for one-shot, stateless interactions
- Custom tools use the `@tool` decorator and `create_sdk_mcp_server()`
- Hooks are async functions matching the SDK's hook signature
- Extract and structure agent outputs; do not return raw text to callers

## File Organization

```
src/maverick/
├── __init__.py          # Version, public API exports
├── main.py              # CLI entry point (Click commands)
├── config.py            # Pydantic configuration models
├── exceptions.py        # Custom exception hierarchy
├── agents/              # Agent implementations
│   ├── base.py          # MaverickAgent abstract base class
│   └── *.py             # Concrete agent implementations
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
├── runners/             # Deterministic command execution (git, gh, validation)
├── tools/               # MCP tool definitions (delegate to runners)
├── hooks/               # Safety and logging hooks
├── tui/                 # Textual application (display-only)
│   ├── app.py           # Main Textual App
│   ├── screens/         # Screen components
│   └── widgets/         # Reusable widgets
└── utils/               # Shared utilities
```

## Governance

This constitution supersedes all other practices and conventions. All code contributions
MUST comply with these principles.

### Amendment Process

1. Amendments require documentation of the change rationale
2. Breaking changes to principles require migration plans for existing code
3. Version increments follow semantic versioning:
   - MAJOR: Backward-incompatible principle changes
   - MINOR: New principles or material expansions
   - PATCH: Clarifications, wording improvements

### Compliance Review

- All PRs MUST be reviewed for constitution compliance
- Complexity deviations MUST be justified in PR descriptions
- Use `.specify/memory/constitution.md` as the authoritative reference
- Architectural guardrails (Principle X) MUST be checked in code review
- Canonical library usage (Guardrail #8, Appendix B) MUST be verified in code review
- TUI streaming patterns (Guardrail #9, Appendix C) MUST be verified in TUI changes
- Module size thresholds (Principle XI) MUST be checked before merging large files
- Ownership expectations (Principle XII) apply to all contributors including AI agents
- Branch naming conventions (Guardrail #10, Appendix D) MUST be verified before pushing
- Workspace cwd threading (Appendix E) MUST be verified for all new workflow steps

**Version**: 1.11.0 | **Ratified**: 2025-12-12 | **Last Amended**: 2026-07-24

## Appendix B: Canonical Third-Party Libraries

These libraries are the canonical choices for their domains. Do NOT introduce alternatives
or custom implementations. Violations found in code review MUST be refactored.

| Domain | Library | Maverick Wrapper | Do NOT Use |
|--------|---------|------------------|------------|
| VCS Writes | Jujutsu (jj) | `maverick.jj.client.JjClient`, `maverick.library.actions.jj` | `subprocess.run("git commit/push ...")` |
| VCS Reads | GitPython | `maverick.git.GitRepository`, `AsyncGitRepository` | `subprocess.run("git ...")` for reads |
| VCS Abstraction | VcsRepository | `maverick.vcs.factory.create_vcs_repository()` | Direct git/jj calls for portable reads |
| Workspaces | WorkspaceManager | `maverick.workspace.manager.WorkspaceManager` | Manual `jj git clone` or `git clone` |
| GitHub API | PyGithub | `maverick.utils.github_client.GitHubClient` | `subprocess.run("gh ...")` except auth |
| Logging | structlog | `maverick.logging.get_logger()` | stdlib `logging.getLogger()` |
| Retry Logic | tenacity | `@retry`, `AsyncRetrying` | Manual `for attempt in range()` |
| Secret Detection | detect-secrets | `maverick.utils.secrets.detect_secrets` | Custom regex patterns |

**Usage Examples**:

```python
# VCS write operations (jj) - CORRECT
from maverick.library.actions.jj import git_commit, git_push
result = await git_commit("feat: add feature", cwd=workspace_path)
await git_push(cwd=workspace_path)

# VCS read operations (GitPython) - CORRECT
from maverick.git import GitRepository, AsyncGitRepository
repo = GitRepository(path)
branch = repo.current_branch()

# Workspace lifecycle - CORRECT
from maverick.workspace.manager import WorkspaceManager
manager = WorkspaceManager(project_root, project_name)
info = await manager.create()  # returns WorkspaceInfo with .path

# Logging - CORRECT
from maverick.logging import get_logger
logger = get_logger(__name__)
logger.info("operation_started", item_id=item_id)

# Retry logic - CORRECT
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential
async for attempt in AsyncRetrying(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
):
    with attempt:
        result = await risky_operation()
```

**Rationale**: Canonical libraries ensure consistent behavior, centralized configuration,
proper error handling, and easier testing. Multiple implementations of the same capability
lead to subtle bugs and maintenance burden (learned from code review 2026-01-12).

## Appendix C: TUI Streaming Architecture

The TUI uses a streaming-first design where the primary content area is a unified, scrolling
event stream. This pattern prioritizes workflow output visibility over complex layouts.

### Core Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `UnifiedStreamWidget` | `src/maverick/tui/widgets/unified_stream.py` | Main stream display widget |
| `UnifiedStreamEntry` | `src/maverick/tui/models/widget_state.py` | Single stream entry model |
| `UnifiedStreamState` | `src/maverick/tui/models/widget_state.py` | Stream state management |
| `StreamEntryType` | `src/maverick/tui/models/enums.py` | Entry type enumeration |

### Event Types for Stream Contribution

All workflow step types contribute to the unified stream through these event patterns:

| Step Type | Event | Description |
|-----------|-------|-------------|
| All steps | `StepStarted` | Emitted when step begins execution |
| All steps | `StepCompleted` | Emitted when step completes (success or failure) |
| Agent steps | `AgentStreamChunk` | Streaming output, thinking, or errors from agents |
| Python/deterministic | `StepOutput` | Progress messages, status updates, warnings |
| Loop steps | `LoopIterationStarted/Completed` | Loop iteration lifecycle |

### StepOutput Event Pattern

The `StepOutput` event is the generic mechanism for any workflow step to contribute
informational output to the unified stream:

```python
from maverick.events import StepOutput

# In a Python action or workflow step:
if event_callback:
    await event_callback(StepOutput(
        step_name="fetch_pr",
        message=f"Fetching PR #{pr_number}...",
        level="info",  # "info", "success", "warning", "error"
        source="github",  # Optional source identifier
    ))
```

### Stream Entry Styling

Entries are styled by type for visual differentiation:

| Entry Type | Badge | Color |
|------------|-------|-------|
| `STEP_START` | `[STEP]` | Primary (cyan) |
| `STEP_COMPLETE` | `[OK]` | Success (green) |
| `STEP_FAILED` | `[FAIL]` | Error (red) |
| `STEP_OUTPUT` | `[source]` | Level-based (info/success/warning/error) |
| `AGENT_OUTPUT` | `[agent]` | Text |
| `AGENT_THINKING` | `[thinking]` | Muted italic |
| `TOOL_CALL` | `[TOOL]` | Secondary (blue) |

### Buffer Management

The stream uses FIFO buffer management to prevent memory exhaustion:

- **Max size**: 100KB default (configurable via `UnifiedStreamState.max_size_bytes`)
- **Eviction**: Oldest entries are removed when buffer exceeds limit
- **Size tracking**: Entries track `size_bytes` for efficient buffer management

### UI Update Debouncing

To prevent flickering during rapid event bursts:

- **Debounce interval**: 50ms between UI refreshes
- **Batch mounting**: Multiple entries mounted in single refresh cycle
- **Auto-scroll**: Maintains scroll position unless user manually scrolls

**Rationale**: Streaming-first design follows the proven pattern from Claude Code's terminal
interface. Single-column output maximizes content visibility and reduces cognitive load.
Standardized event types ensure all step types can contribute without custom UI code.

## Appendix D: Repository and Branch Naming Conventions

Maverick development involves two distinct repositories with different purposes. Confusing
them causes branch pollution, incorrect commits, and wasted cleanup effort.

### Repository Overview

| Repository | Purpose | Location | Branch Prefix Examples |
|------------|---------|----------|------------------------|
| **maverick** | Core Maverick CLI/TUI application | `/workspaces/maverick` | `030-tui-streaming`, `028-maverick-init` |
| **sample-maverick-project** | Test project for E2E testing and demos | `/workspaces/sample-maverick-project` | `001-greet-cli`, `002-todo-app` |

### Branch Naming Rules

**Maverick Core Repository** (`get2knowio/maverick`):
- Branch format: `###-descriptive-name` where `###` is a maverick feature spec number
- Examples: `030-tui-execution-visibility`, `028-maverick-init`, `recursing-archimedes`
- Spec location: `/workspaces/maverick/specs/###-feature-name/`
- NEVER use low numbers (001-010) for maverick branches—these are reserved for sample projects

**Sample Project Repository** (`get2knowio/sample-maverick-project`):
- Branch format: `###-descriptive-name` where `###` starts from `001`
- Examples: `001-greet-cli`, `002-todo-app`, `003-calculator`
- Spec location: `/workspaces/sample-maverick-project/specs/###-feature-name/`
- Used for testing maverick workflows against a real project

### Pre-Push Verification Checklist

Before pushing any branch, verify:

```bash
# 1. Check which repository you're in
pwd
git remote -v

# 2. Verify branch name matches repository
git branch --show-current

# 3. Check that your commits belong to this repo
git log --oneline -5
```

### Common Mistakes to Avoid

| Mistake | How It Happens | Prevention |
|---------|----------------|------------|
| Sample branch in maverick | Working in wrong terminal/directory | Always check `git remote -v` before push |
| Maverick branch in sample | Copy/paste branch name from wrong context | Verify spec directory exists in current repo |
| Commits to wrong repo | Multiple terminals with similar prompts | Use distinct terminal titles or prompts per repo |

### Recovery Procedure

If you accidentally push a branch to the wrong repository:

1. **Do NOT force-push or rewrite history** on shared branches
2. Delete the incorrect remote branch: `git push origin --delete <branch-name>`
3. If commits need preservation, cherry-pick to correct repo
4. Document the incident to prevent recurrence

**Rationale**: The 001-greet-cli incident (2026-01-21) demonstrated how easily branch
confusion can occur when working across multiple repositories. Clear naming conventions
and verification procedures prevent wasted effort and repository pollution.

## Appendix E: Workspace Isolation Architecture

**Default: single-repo CWD model (Guardrail 0).** `fly`, `refuel`, `land`, and every
other long-running command operate directly in the user's checkout under `Path.cwd()`
(resolved once at the CLI boundary and threaded explicitly through every layer beneath
it — see Guardrail 0 and Guardrail 7 in CLAUDE.md). There is no hidden workspace, no
clone bridge, and no `WorkspaceManager` for these commands. Two implementations of a
general-purpose hidden-workspace model were tried and retired before this model was
adopted (`jj git clone` — drifted on bd state, gone in `cf11db4`; `jj workspace add` —
bd's gitignored `embeddeddolt/` didn't travel into the workspace, gone in the slice that
introduced the single-repo model). See CLAUDE.md Guardrail 0 for the full history and
the CWD contract every command in this model follows: CLI resolves `cwd`, passes it
explicitly to the workflow, which threads it to every action/agent step — no
`Path.cwd()` defaults inside `src/maverick/workflows/` or `src/maverick/actors/`.

### The scoped exception: spec-chain's hidden jj workspace

`maverick spec` (spec 050-headless-spec-chain) is a **documented exception** to the
single-repo model. Each chain step (specify → clarify → plan → tasks → analyze) mutates
`specs/`, `.specify/feature.json`, and agent scratch state over a multi-minute model
call; the user's checkout must stay untouched until each step's artifacts are verified
complete, and only completed-step artifacts may land. Running steps directly in the
user's checkout would expose half-written spec artifacts mid-run and make atomic landing
impossible without ad-hoc staging.

The historic reason general-purpose workspaces were retired — bd's gitignored
`embeddeddolt/` not traveling into `jj workspace add` — does **not** apply here: the
spec chain never runs `bd` inside the workspace. All bead/ledger writes (assumption
ledger entries from clarify, remediation beads from analyze) happen in the user's
checkout via the workflow (`src/maverick/workflows/spec_chain/workflow.py`), never the
agent and never the workspace. This keeps Guardrail X.3 (agents never own deterministic
side effects) and Guardrail X.8 (canonical wrappers) intact even inside the exception.

**Mechanism** (`src/maverick/workspace/spec_chain.py`, `research.md` R3):

- Location: `~/.maverick/workspaces/<project-slug>/spec-chain/<feature>/` — per-feature,
  so two features' chains never share (and one can never destroy the other's resumable
  state).
- Creation: `JjClient.workspace_add`, from the user's colocated checkout — the shared
  backing store materializes committed files (`.claude/commands/speckit.*.md`,
  `.specify/**`, existing `specs/**`) into the workspace. The PRD file (often untracked)
  is copied in explicitly.
- Reuse & cleanup: a resumable chain (`status` `halted`/`running`) reuses its workspace
  on resume; a fresh or completed chain forgets + recreates it, so runs start clean.
- Landing: after each step succeeds (verified against the filesystem, never the agent's
  self-report — research.md R9), `src/maverick/workflows/spec_chain/landing.py` syncs
  `specs/<feature-dir>/**` from the workspace into the user's checkout via an atomic
  staged copy (temp sibling + rename). This is what makes "only completed artifacts
  land" and "resume never regenerates a landed step" both hold.

### CWD contract inside the exception

Within the spec-chain workflow itself, the ordinary Guardrail 7 rules still apply one
level down: `SpecChainWorkflow._run()` resolves the workspace path once (via
`prepare_workspace`) and threads it explicitly to every step (`build_step_prompt`,
`verify_step_artifacts`, `land_step_artifacts`) and to `SpecChainSquadron` — no step
re-derives or defaults it. The one deliberate deviation is `SpecChainAgent.run_step`,
which binds the OS process working directory via a locked `os.chdir()`/restore pair for
the duration of a single airframe `execute()` call — a workaround for airframe 0.9.0rc1
exposing no `cwd`/`working_directory` parameter on the `claude` provider's runtime
(research.md R1; the field exists on `CopilotOptions`/`KimiOptions`/
`OpenCodeServerOptions` but not `ClaudeOptions`, an adapter gap worth upstreaming later).
Because chain steps run strictly sequentially and one Maverick CLI invocation runs one
workflow per process, the exposure window is a single in-process critical section, not
cross-workflow concurrency.

**Rationale**: The workspace isolation debugging session (2026-02-20) that originally
motivated this appendix revealed that an implementer agent can silently write to the
wrong directory when no step passes `cwd` explicitly — the bug is invisible until
downstream steps find nothing to work with. That lesson generalizes to both models
above: whether the working directory is the user's checkout (the default) or a hidden
workspace (this scoped exception), every step must receive it explicitly, and nothing
in `workflows/` or `actors/` may default to `Path.cwd()`.
