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
know or care about the broader workflow context. The orchestration layer handles:
- Git operations (commits are created after you complete your work)
- Validation execution (format, lint, test pipelines run after implementation)
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
6. Ensure code is ready for validation (will be run by orchestration)

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

# DEPRECATED: Phase mode is speckit-era code. The bead-driven fly workflow
# exclusively uses _execute_task_mode with single-task ImplementerContext
# (task_description set from bead description). Phase mode may still be used
# by `refuel speckit` invocations. Do not invest in this template.
PHASE_PROMPT_TEMPLATE = """\
## Phase Execution: {phase_name}

You are implementing a single phase from the task file at `{task_file}`.

### Step 1: Load Context

Read and internalize the following spec artifacts before writing any code:
- **REQUIRED**: Read `{task_file}` for the complete task list
- **REQUIRED**: Read the spec directory for `plan.md` (tech stack, architecture,
  directory structure, key design decisions)
- **REQUIRED**: Read `CLAUDE.md` (if it exists) for project conventions, coding
  standards, and development patterns you must follow
- **IF EXISTS**: Read `data-model.md` for schema definitions and entity relationships
- **IF EXISTS**: Read files in `contracts/` for API contracts and interface definitions
- **IF EXISTS**: Read `research.md` for technology choices, trade-offs, and decisions
- **IF EXISTS**: Read `quickstart.md` for setup patterns and project entry points

Internalize the tech stack, directory layout, naming conventions, and testing
patterns from these artifacts. All code you write must align with them.

### Step 2: Project Setup Verification

Before implementing features, verify that the project has appropriate ignore
files (`.gitignore`, etc.) for its tech stack. If `plan.md` specifies a tech
stack and no ignore files exist yet, create them with standard patterns for
that technology.

Common patterns by technology:
- **Python**: `__pycache__/`, `*.pyc`, `.venv/`, `dist/`, `*.egg-info/`,
  `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`
- **Node.js**: `node_modules/`, `dist/`, `.next/`, `.nuxt/`, `coverage/`
- **Rust**: `target/`, `Cargo.lock` (for libraries)
- **Go**: `vendor/` (if vendoring), binary outputs
- **General**: `.env`, `.env.local`, `*.log`, `.DS_Store`, `*.swp`

### Step 3: Identify Tasks

From `{task_file}`, find ALL tasks listed under the **"{phase_name}"** section.

Parse the task structure carefully:
- Extract task IDs (e.g., `T001`, `T002`) and their full descriptions
- Identify dependency markers — tasks that reference other task IDs as
  prerequisites must wait until those complete
- Identify **[P]** parallel markers — these tasks have no inter-dependencies
  and can execute simultaneously
- Determine execution flow: sequential tasks first, then parallel batches,
  then any sequential tasks that depend on the parallel batch

These are the tasks you MUST implement in this session.

### Step 4: Execute Tasks

Implement tasks using a TDD (Test-Driven Development) approach:

**For each task:**
1. **Read** existing files that will be affected (use Read tool)
2. **Write tests first** — create or update test files that define the expected
   behavior. Test files must cover the public API of any new module.
3. **Implement the source code** — use Write (new files) or Edit (existing files)
   to create the minimal implementation that satisfies the tests
4. **Verify consistency** — re-read modified files to confirm edits applied
   correctly and the code is syntactically valid

**Parallel task execution ([P] markers):**
- Tasks marked with **[P]** can be executed simultaneously by spawning
  separate subagents via the Task tool
- Launch all [P] tasks in a single response with multiple Task tool calls
- Each subagent prompt must include: the task description, relevant file paths,
  project conventions from CLAUDE.md, and the tech stack context
- Sequential tasks must be completed in order before moving to the next

**Phase ordering:**
- Complete all tasks in a phase before the orchestration layer advances to
  the next phase. You only handle the current phase.

### Step 5: Progress Tracking

After completing each task:
- Mark it as done in `{task_file}` by changing `- [ ]` to `- [x]` for that
  task line using the Edit tool
- If a task fails or cannot be completed, leave it unchecked and continue
  with the next task — do not let one failure block the entire phase
- If a parallel [P] subagent fails, continue with remaining tasks and report
  the failure

### Step 6: Completion Validation

After all tasks in the phase are attempted:
- Re-read `{task_file}` to verify all tasks in **"{phase_name}"** are marked
  `[x]` (or documented as failed with a reason)
- Verify that the implemented features match what the task descriptions
  specified — do not leave partial implementations
- Confirm that every new source file has a corresponding test file
- Run the project's validation commands via Bash (sync dependencies if you
  modified dependency files, then format, lint, test). Fix any issues found
  before completing.

### Rules

- You MUST use Write and Edit to create and modify actual source files.
  Reading and analyzing is NOT enough — you must produce working code.
- You MUST create test files for every source module you create. If you
  create `src/foo/bar.py`, also create `tests/test_bar.py`. Do not skip
  tests or defer them to a later phase.
- Use Bash to run validation commands (sync deps, format, lint, test)
  before completing. The orchestration workflow handles git commits after
  you finish.
- Do NOT include commit messages in your output — the workflow generates
  them automatically.
- Follow the project's conventions from CLAUDE.md if it exists.
- Read files before editing them. Do not guess at file contents.
- Prefer Edit over Write for existing files to make targeted changes.
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

        if context.is_phase_mode and context.phase_name:
            return self._build_phase_prompt(context.phase_name, context)

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
        return f"""Execute the following task:

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

After completion, provide a summary of changes made.
"""

    def _build_phase_prompt(
        self,
        phase_name: str,
        context: ImplementerContext,
    ) -> str:
        """Build prompt for phase-level execution.

        Creates a focused prompt that tells the agent exactly what to do
        for a single phase: read spec artifacts, find the phase's tasks,
        and implement them by writing code with Write/Edit tools.

        Args:
            phase_name: Name of the phase to implement.
            context: Execution context (provides task_file path and cwd).

        Returns:
            Formatted prompt for Claude.
        """
        return PHASE_PROMPT_TEMPLATE.format(
            phase_name=phase_name,
            task_file=context.task_file,
        )
