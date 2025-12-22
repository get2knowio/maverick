<!--
Sync Impact Report
==================
Version change: 1.1.0 → 1.2.0
Modified principles:
  - V. Test-First → Enhanced with anti-deferral rules from debt analysis
  - VI. Type Safety → Enhanced with Protocol usage and no magic numbers
  - VII. Simplicity → Enhanced with DRY and hardening requirements
Added sections:
  - IX. Debt Prevention (new principle based on analysis of issues #61-#152)
Removed sections: None
Templates requiring updates:
  - .specify/templates/plan-template.md: ✅ Compatible (Constitution Check section exists)
  - .specify/templates/spec-template.md: ✅ Compatible (no constitution-specific references)
  - .specify/templates/tasks-template.md: ✅ Compatible (checkpoint guidance aligns with resilience principle)
Propagation:
  - CLAUDE.md: ✅ Updated with Debt Prevention Guidelines section
Follow-up TODOs: None
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

**Rationale**: The TUI requires responsive updates during long-running agent operations.
Async generators enable real-time progress reporting without blocking the event loop.

### II. Separation of Concerns

Components have distinct, non-overlapping responsibilities:

- **Agents**: Know HOW to do a task (system prompts, tool selection, Claude SDK interaction)
- **Workflows**: Know WHAT to do and WHEN (orchestration, state management, sequencing)
- **TUI**: Presents state and captures input (no business logic, display only)
- **Tools**: Wrap external systems (GitHub CLI, git, notifications)

Business logic MUST NOT leak into TUI components. Agents MUST NOT orchestrate themselves.

**Rationale**: Clear boundaries enable independent testing, easier debugging, and prevent
the coupling that makes systems brittle.

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

**Rationale**: Parallel agent execution means partial success is valuable. Users should
get results from successful operations even when some fail. Unattended operation requires
the system to recover from transient failures without human intervention.

### V. Test-First (Anti-Deferral)

Every public class and function MUST have tests. Testing is mandatory, not optional.
No PR shall be merged without tests covering new functionality.

- Use pytest fixtures for common setup
- Mock external dependencies (Claude API, GitHub CLI, filesystem)
- TUI tests use Textual's `pilot` fixture
- Async tests use `pytest.mark.asyncio`
- Tests are written BEFORE implementation (Red-Green-Refactor)
- Do NOT comment out or skip failing tests; fix them immediately
- For async components (Agents/Workflows), testing MUST verify concurrency and error states,
  not just happy paths

**Rationale**: TDD catches design problems early. Comprehensive tests enable confident
refactoring and serve as executable documentation. Deferring tests creates debt that
compounds over time (learned from issues #61-#152).

### VI. Type Safety & Constants

Complete type hints are required throughout the codebase. No magic numbers or strings.

- All public functions MUST have complete type annotations
- Use `TypeAlias` for complex types to improve readability
- Prefer `@dataclass` or Pydantic `BaseModel` over plain dicts for structured data
- Use `Protocol` for interfaces when duck typing is needed (avoids circular dependencies)
- Use `@dataclass(frozen=True)` for immutable value objects
- Use `@dataclass(slots=True)` for frequently instantiated objects
- No magic numbers or string literals in logic code; extract to named constants or config
- Use `Protocol` (structural typing) to define interfaces between components
  (e.g., between DSL and Agents) to avoid circular dependencies and tight coupling

**Rationale**: Static typing catches errors at development time, improves IDE support,
and serves as inline documentation. Named constants prevent "magic value" bugs and
enable centralized configuration changes.

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
- Validate at system boundaries (user input, external APIs) but trust internal code
- Documentation examples MUST be treated as code—add tests that validate code snippets
  in `README.md` or `docs/quickstart.md` to ensure they remain executable

**Rationale**: Transient failures are inevitable in distributed systems. Proper hardening
prevents cascading failures and makes debugging easier. Bare exception handlers hide bugs.
(Learned from network reliability issues in #61-#152.)

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
├── workflows/           # Workflow orchestration
├── tools/               # MCP tool definitions
├── hooks/               # Safety and logging hooks
├── tui/                 # Textual application
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

**Version**: 1.2.0 | **Ratified**: 2025-12-12 | **Last Amended**: 2025-12-22
