<!--
Sync Impact Report
==================
Version change: N/A (initial) → 1.0.0
Added sections:
  - Core Principles (7 principles)
  - Technology Stack
  - Code Style & Conventions
  - Claude Agent SDK Patterns
  - File Organization
  - Governance
Removed sections: None (initial creation)
Templates requiring updates:
  - .specify/templates/plan-template.md: ✅ Compatible (Constitution Check section exists)
  - .specify/templates/spec-template.md: ✅ Compatible (no constitution-specific references)
  - .specify/templates/tasks-template.md: ✅ Compatible (test-first guidance aligns with principles)
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

### IV. Fail Gracefully

One agent or issue failing MUST NOT crash the entire workflow.

- Always capture and report errors with context before re-raising or wrapping
- Provide actionable error messages that help users understand what went wrong
- Use structured error types from the exception hierarchy
- Log errors with sufficient context for debugging

**Rationale**: Parallel agent execution means partial success is valuable. Users should
get results from successful operations even when some fail.

### V. Test-First

Every public class and function MUST have tests. Testing is mandatory, not optional.

- Use pytest fixtures for common setup
- Mock external dependencies (Claude API, GitHub CLI, filesystem)
- TUI tests use Textual's `pilot` fixture
- Async tests use `pytest.mark.asyncio`
- Tests are written BEFORE implementation (Red-Green-Refactor)

**Rationale**: TDD catches design problems early. Comprehensive tests enable confident
refactoring and serve as executable documentation.

### VI. Type Safety

Complete type hints are required throughout the codebase.

- All public functions MUST have complete type annotations
- Use `TypeAlias` for complex types to improve readability
- Prefer `@dataclass` or Pydantic `BaseModel` over plain dicts for structured data
- Use `Protocol` for interfaces when duck typing is needed
- Use `@dataclass(frozen=True)` for immutable value objects
- Use `@dataclass(slots=True)` for frequently instantiated objects

**Rationale**: Static typing catches errors at development time, improves IDE support,
and serves as inline documentation.

### VII. Simplicity

Avoid over-engineering. Start simple and add complexity only when justified.

- No global mutable state
- No massive god-classes; prefer composition over inheritance
- No hardcoded paths; use pathlib and configuration
- No premature abstractions; three similar lines are better than a premature helper
- No `shell=True` in subprocess calls without explicit security justification
- No `print()` for output; use logging or TUI updates

**Rationale**: YAGNI (You Aren't Gonna Need It). Simple code is easier to understand,
test, and maintain.

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

**Version**: 1.0.0 | **Ratified**: 2025-12-12 | **Last Amended**: 2025-12-12
