"""Common prompt fragments shared across Maverick agents.

These constants provide reusable text blocks for agent system prompts.
Each fragment covers a single tool or principle section. Agents compose
their system prompts by importing and interpolating the fragments they
need.

Usage:
    from maverick.agents.prompts.common import (
        TOOL_USAGE_READ,
        TOOL_USAGE_EDIT,
        CODE_QUALITY_PRINCIPLES,
        PROJECT_CONVENTIONS,
    )

    AGENT_PROMPT = f\"\"\"You are an agent...

    ### Read
    {TOOL_USAGE_READ}

    ### Edit
    {TOOL_USAGE_EDIT}

    {CODE_QUALITY_PRINCIPLES}

    {PROJECT_CONVENTIONS}
    \"\"\"
"""

from __future__ import annotations

# =============================================================================
# Tool Usage Fragments
# =============================================================================

TOOL_USAGE_READ = """\
- Use Read to examine files before modifying them. You MUST read a file before
  using Edit on it."""

TOOL_USAGE_EDIT = """\
- Use Edit for targeted replacements in existing files. This is your primary
  tool for modifying code.
- You MUST Read a file before using Edit on it. Edit will fail otherwise.
- The `old_string` must be unique in the file. If it is not unique, include
  more surrounding context to disambiguate.
- Preserve exact indentation (tabs/spaces) from the file content."""

TOOL_USAGE_WRITE = """\
- Use Write to create **new** files. Write overwrites the entire file content.
- Prefer Edit for modifying existing files — Write should only be used on
  existing files when a complete rewrite is needed.
- Do NOT create files unless they are necessary. Prefer editing existing files
  over creating new ones."""

TOOL_USAGE_GLOB = """\
- Use Glob to find files by name or pattern (e.g., `**/*.py`, `tests/test_*.py`).
- Use Glob instead of guessing file paths. When you need to find where a module,
  class, or file lives, search for it first."""

TOOL_USAGE_GREP = """\
- Use Grep to search file contents by regex pattern.
- Use Grep to find function definitions, class usages, import locations, and
  string references across the codebase.
- Prefer Grep over reading many files manually when searching for specific
  patterns."""

TOOL_USAGE_TASK = """\
- Use Task to spawn subagents for parallel work. Each subagent operates
  independently with its own context.
- Provide clear, detailed prompts to subagents since they start with no context.
  Include file paths, requirements, and conventions they need to follow."""

# =============================================================================
# Code Quality Principles
# =============================================================================

CODE_QUALITY_PRINCIPLES = """\
## Code Quality Principles

- **Avoid over-engineering**: Only make changes directly required by the task.
  Do not add features, refactor code, or make improvements beyond what is asked.
- **Keep it simple**: The right amount of complexity is the minimum needed for
  the current task. Three similar lines of code is better than a premature
  abstraction.
- **Security awareness**: Do not introduce command injection, XSS, SQL injection,
  or other vulnerabilities. Validate at system boundaries.
- **No magic values**: Extract magic numbers and string literals into named
  constants.
- **Read before writing**: Always understand existing code before modifying it.
  Do not propose changes to code you have not read.
- **Minimize file creation**: Prefer editing existing files over creating new
  ones. Only create files that are truly necessary.
- **Clean boundaries**: Ensure new code integrates cleanly with existing
  patterns. Match the style and conventions of surrounding code."""

# =============================================================================
# Project Conventions (injected into agent prompts at runtime)
# =============================================================================

PROJECT_CONVENTIONS = """\
## Project Conventions

These are the canonical standards for this project. Follow them strictly.

### Canonical Third-Party Libraries

Use ONLY these libraries for their domains. Do NOT introduce alternatives or
write custom implementations for what they already provide.

- **VCS writes** (commit, push, branch): `maverick.library.actions.jj` (Jujutsu).
  Do NOT shell out to raw VCS CLIs for write operations.
- **VCS reads** (diff, status, log): `maverick.git` (GitPython). Read-only.
- **GitHub operations**: `maverick.utils.github_client` (PyGithub). Do NOT use
  `subprocess.run("gh ...")` for operations PyGithub supports.
- **Logging**: `maverick.logging.get_logger()` (structlog). Do NOT use
  `import logging; logging.getLogger()`.
- **Retry logic**: `tenacity` (`@retry`, `AsyncRetrying`). Do NOT write manual
  `for attempt in range(retries):` loops.
- **Secret detection**: `maverick.utils.secrets.detect_secrets`. Do NOT write
  custom regex for secret detection.
- **Validation**: Pydantic `BaseModel` for configuration and data models.
- **CLI**: Click for commands, Rich for terminal output.

### Async-First

- All agent interactions and workflows MUST be async.
- Never call `subprocess.run` from an `async def` path — use `CommandRunner`.
- Use `asyncio` patterns; no threading for I/O.

### Type Safety & Typed Contracts

- Complete type hints on all public functions and classes.
- Use `@dataclass` or Pydantic `BaseModel` over plain dicts.
- Action outputs must use frozen dataclasses or TypedDict — no ad-hoc
  `dict[str, Any]` blobs.
- Use `from __future__ import annotations` in every module.

### Code Style

- Classes: PascalCase. Functions: snake_case. Constants: SCREAMING_SNAKE_CASE.
- Private members: leading underscore.
- Docstrings: Google-style with Args, Returns, Raises sections.
- No `print()` — use logging or Rich Console.
- No `shell=True` in subprocess calls without security justification.
- No magic numbers or string literals in logic — extract to named constants.

### Separation of Concerns

- Agents provide judgment (implementation, review, fix suggestions).
- Workflows own deterministic side effects (commits, validation, retries).
- Agents MUST NOT create commits, push code, or run validation directly.

### Hardening by Default

- All external calls (network APIs, subprocesses) MUST have explicit timeouts.
- Network operations MUST use retry with exponential backoff (tenacity).
- No bare `except Exception` — use specific exception handling.
- Custom exceptions inherit from `MaverickError`.

### Testing Requirements

- Every public class and function MUST have tests.
- TDD: Red-Green-Refactor. Write tests alongside implementation.
- Test concurrency and error states for async components, not just happy paths.

### Modularization

- Aim for modules < ~500 LOC. Refactor at ~800 LOC.
- Single responsibility per module.
- Prefer composition over inheritance for shared agent capabilities."""
