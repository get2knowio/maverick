"""ImplementerAgent for executing structured task files.

This module provides the ImplementerAgent that executes tasks from tasks.md
files or direct descriptions using TDD approach and conventional commits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.common import (
    CODE_QUALITY_PRINCIPLES,
    FRAMEWORK_CONVENTIONS,
    TOOL_USAGE_BASH,
    TOOL_USAGE_EDIT,
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
    TOOL_USAGE_TASK,
    TOOL_USAGE_WRITE,
)
from maverick.agents.skill_prompts import render_prompt
from maverick.agents.tools import IMPLEMENTER_TOOLS
from maverick.logging import get_logger
from maverick.models.implementation import (
    ImplementationResult,
    ImplementerContext,
    Task,
    TaskStatus,
)

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE = f"""You are an expert software engineer.
You focus on methodical, test-driven implementation within an orchestrated workflow.

$skill_guidance

## Your Role
You implement beads — units of work that may be feature tasks, validation fixes,
or review findings. The bead description tells you what to do; you do not need to
know or care about the broader workflow context.

You are responsible for:
- Writing code to implement the bead's requirements
- Running validation (format, lint, typecheck, test) via Bash and fixing failures
- Iterating until validation passes or you determine the issue is unfixable
- Syncing dependencies if you modify dependency files (pyproject.toml, etc.)

The orchestration layer handles:
- Git operations (commits are created after you complete your work)
- Branch management and PR creation
- Bead lifecycle (selection, closing, creating follow-up beads)

You focus on:
- Understanding the bead's requirements and writing code
- Following TDD approach (write tests alongside implementation)
- Adhering to project conventions (see Project Conventions section below)
- Reading existing code before modifying it

## Core Approach
1. Read CLAUDE.md (if present) for project-specific conventions
2. Read relevant existing code before writing anything new
3. Understand the task fully before writing code
4. Write tests for every source file you create or modify — this is
   mandatory, not optional
5. Make small, incremental changes
6. Sync dependencies if you changed dependency files
7. Run validation commands via Bash (format, lint, typecheck, test)
8. Fix any validation failures and re-run until clean
9. Clean up after yourself: remove dead code, unused imports, stale
   comments, and orphaned files created by your changes
10. If you cannot resolve a failure after genuine effort, stop and report what you tried

## Completeness Standard

Your work is NOT done until:
- All acceptance criteria are satisfied (not partially — fully)
- All validation commands pass (format, lint, typecheck, test)
- No dead code remains from your changes (unused functions, imports,
  variables, or files that your refactoring made obsolete)
- No TODO/FIXME/HACK comments are left behind — resolve them now or
  remove the code they reference
- No deferred work — if a change requires a follow-up (e.g., updating
  callers, removing a shim, migrating tests), do it in this session.
  There is no "later" — this bead must be complete and self-contained

## Task Execution
For each task:
1. Read the task description carefully
2. Identify affected files and dependencies — read them first
3. Create test files for all new source modules (e.g., `tests/test_<module>.py`)
4. Implement the minimal code to pass tests
5. Ensure code follows conventions and is ready for validation

**IMPORTANT**: Every source file you create MUST have a corresponding test file.
If you create `src/foo/bar.py`, you must also create `tests/test_bar.py` (or
the equivalent path for the project's test layout). Do not defer test creation
to a later phase — write tests in the same session as the implementation.

## Tool Usage Guidelines

You have access to: **Read, Write, Edit, Glob, Grep, Task, Bash**

### Read
{TOOL_USAGE_READ}
- Read CLAUDE.md and existing source files to understand context and conventions
  before writing new code.

### Write
{TOOL_USAGE_WRITE}

### Edit
{TOOL_USAGE_EDIT}

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

### Task (Subagents)
{TOOL_USAGE_TASK}
- When tasks are marked **[P]** (parallel), launch them simultaneously via
  multiple Task tool calls in a single response. This maximizes throughput.

### Bash
{TOOL_USAGE_BASH}
$validation_commands

**CRITICAL**: You MUST use Write and Edit to create and modify source files.
Reading and analyzing is NOT enough — actually implement the code.

{CODE_QUALITY_PRINCIPLES}

{FRAMEWORK_CONVENTIONS}

$project_conventions
"""

# =============================================================================
# Helpers
# =============================================================================

#: Mapping from ValidationConfig field names to human-readable labels.
_VALIDATION_LABELS: dict[str, str] = {
    "sync_cmd": "Sync dependencies",
    "format_cmd": "Format",
    "lint_cmd": "Lint",
    "typecheck_cmd": "Type check",
    "test_cmd": "Test",
}


def _format_validation_commands(
    commands: dict[str, list[str]] | None,
) -> str:
    """Format validation commands dict into a prompt-friendly string.

    Args:
        commands: Mapping of command type to argv list (e.g.
            ``{"test_cmd": ["pytest", "-x", "--tb=short"]}``).

    Returns:
        Markdown snippet listing each command, or empty string if none.
    """
    if not commands:
        return ""
    lines = ["\n#### Project Commands (from maverick.yaml)"]
    for key, argv in commands.items():
        label = _VALIDATION_LABELS.get(key, key)
        lines.append(f"- **{label}**: `{' '.join(argv)}`")
    return "\n".join(lines)


# =============================================================================
# Context coercion
# =============================================================================


def _coerce_implementer_context(data: dict[str, Any]) -> ImplementerContext:
    """Coerce a dict prompt to ImplementerContext.

    Python workflows pass dicts via ClaudeStepExecutor; this converts them
    to the typed model the agent expects.
    """
    task_file_str = data.get("task_file")
    task_file = Path(task_file_str) if task_file_str else None
    cwd_str = data.get("cwd")
    cwd = Path(cwd_str) if cwd_str else Path.cwd()

    return ImplementerContext(
        task_file=task_file,
        task_description=data.get("task_description"),
        phase_name=data.get("phase_name"),
        branch=data.get("branch") or data.get("branch_name") or "main",
        cwd=cwd,
        skip_validation=data.get("skip_validation", False),
        dry_run=data.get("dry_run", False),
        briefing_context=data.get("briefing_context"),
        previous_failures=data.get("previous_failures"),
        runway_context=data.get("runway_context"),
    )


# =============================================================================
# ImplementerAgent
# =============================================================================


class ImplementerAgent(MaverickAgent[ImplementerContext, ImplementationResult]):
    """Agent for executing structured task files.

    Implements methodical, test-driven task execution from tasks.md files
    or direct task descriptions.

    Type Parameters:
        Context: ImplementerContext - task source and execution options
        Result: ImplementationResult - aggregated task outcomes and file changes

    Example:
        >>> agent = ImplementerAgent()
        >>> context = ImplementerContext(
        ...     task_file=Path("specs/004/tasks.md"),
        ...     branch="feature/implement"
        ... )
        >>> result = await agent.execute(context)
        >>> result.success
        True
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        project_type: str | None = None,
        validation_commands: dict[str, list[str]] | None = None,
    ) -> None:
        """Initialize ImplementerAgent.

        Args:
            model: Claude model ID (defaults to claude-sonnet-4-5-20250929).
            mcp_servers: Optional MCP server configurations.
            max_tokens: Optional maximum output tokens (SDK default used if None).
            temperature: Optional sampling temperature 0.0-1.0 (SDK default).
            project_type: Project type for skill guidance (auto-detected if None).
            validation_commands: Optional dict of validation type to command list,
                loaded from maverick.yaml. Injected into the system prompt as guidance.
        """
        # Format validation commands for prompt injection
        validation_section = _format_validation_commands(validation_commands)

        # Render prompt with skill guidance for this project type
        rendered_instructions = render_prompt(
            IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE,
            project_type=project_type,
            extra_context={"validation_commands": validation_section},
        )

        super().__init__(
            name="implementer",
            instructions=rendered_instructions,
            allowed_tools=list(IMPLEMENTER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def build_prompt(self, context: ImplementerContext | dict[str, Any]) -> str:
        """Construct the prompt string from context (FR-017).

        Delegates to internal prompt builders based on context mode.
        For phase mode, uses the phase prompt template. For task mode,
        uses the task description as the prompt.

        Args:
            context: Execution context with task source and options.
                Can be an ImplementerContext or a dict (auto-coerced).

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        if isinstance(context, dict):
            context = _coerce_implementer_context(context)

        if context.is_single_task and context.task_description:
            synthetic_task = Task(
                id="T000",
                description=context.task_description,
                status=TaskStatus.PENDING,
                parallel=False,
            )
            return self._build_task_prompt(synthetic_task, context)

        # Fallback: task_file description
        return f"Implement tasks from: {context.task_file}"

    def _build_task_prompt(self, task: Task, context: ImplementerContext) -> str:
        """Build the prompt for executing a bead/task.

        Creates a focused prompt with the bead description and instructions
        to read existing code and CLAUDE.md before implementing.

        Args:
            task: Task (bead) to execute.
            context: Execution context.

        Returns:
            Formatted prompt for Claude.
        """
        base = f"""Execute the following task:

**Task ID**: {task.id}
**Description**: {task.description}

## Before You Start
1. Read `CLAUDE.md` (if present at the repo root) for project conventions
2. Read existing source files that will be affected by this change
3. Understand the codebase patterns before introducing new code

## Implementation Approach (TDD)
1. Understand exactly what the task description requires
2. Write or update tests that define the expected behavior
3. Implement the minimal code to satisfy the tests
4. Verify your changes follow project conventions

## After Implementation
1. If you modified dependency files, sync dependencies via Bash
2. Run all validation commands (see Project Commands in your system prompt)
3. Fix any failures and re-run until clean
4. Report completion only when all validation passes (or explain what's stuck)
"""

        sections = [base]
        if context.runway_context:
            sections.append(f"## Historical Context\n{context.runway_context}")
        if context.briefing_context:
            sections.append(f"## Project Briefing\n{context.briefing_context}")
        if context.previous_failures:
            sections.append(f"## Previous Failures\n{context.previous_failures}")
        return "\n\n".join(sections)
