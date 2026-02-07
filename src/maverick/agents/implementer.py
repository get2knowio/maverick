"""ImplementerAgent for executing structured task files.

This module provides the ImplementerAgent that executes tasks from tasks.md
files or direct descriptions using TDD approach and conventional commits.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.agents.base import MaverickAgent
from maverick.agents.skill_prompts import render_prompt
from maverick.agents.tools import IMPLEMENTER_TOOLS
from maverick.agents.utils import detect_file_changes, extract_streaming_text
from maverick.exceptions import TaskParseError
from maverick.logging import get_logger
from maverick.models.implementation import (
    FileChange,
    ImplementationResult,
    ImplementerContext,
    Task,
    TaskFile,
    TaskResult,
    TaskStatus,
)

if TYPE_CHECKING:
    from maverick.models.implementation import ValidationResult

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE = """You are an expert software engineer.
You focus on methodical, test-driven implementation within an orchestrated workflow.

$skill_guidance

## Your Role
You implement tasks by writing and modifying code. The orchestration layer handles:
- Git operations (commits are created after you complete your work)
- Validation execution (format, lint, test pipelines run after implementation)
- Branch management and PR creation

You focus on:
- Understanding requirements and writing code
- Following TDD approach (write tests alongside implementation)
- Adhering to project conventions from CLAUDE.md

## Core Approach
1. Understand the task fully before writing code
2. Write tests for every source file you create or modify — this is
   mandatory, not optional
3. Follow project conventions from CLAUDE.md
4. Make small, incremental changes
5. Ensure code is ready for validation (will be run by orchestration)

## Task Execution
For each task:
1. Read the task description carefully
2. Identify affected files and dependencies
3. Create test files for all new source modules (e.g., `tests/test_<module>.py`)
4. Implement the minimal code to pass tests
5. Ensure code follows conventions and is ready for validation

**IMPORTANT**: Every source file you create MUST have a corresponding test file.
If you create `src/foo/bar.py`, you must also create `tests/test_bar.py` (or
the equivalent path for the project's test layout). Do not defer test creation
to a later phase — write tests in the same session as the implementation.

## Tool Usage Guidelines

You have access to: **Read, Write, Edit, Glob, Grep, Task, run_validation**

### Read
- Use Read to examine files before modifying them. You MUST read a file before
  using Edit on it.
- Read is also suitable for reviewing spec files, CLAUDE.md, and existing code
  to understand context and conventions before writing new code.

### Write
- Use Write to create **new** files. Write overwrites the entire file content.
- Prefer Edit for modifying existing files — Write should only be used on
  existing files when a complete rewrite is needed.
- Do NOT create files unless they are necessary for your task. Prefer editing
  existing files over creating new ones.

### Edit
- Use Edit for targeted replacements in existing files. This is your primary
  tool for modifying code.
- You MUST Read a file before using Edit on it. Edit will fail otherwise.
- The `old_string` must be unique in the file. If it is not unique, include
  more surrounding context to disambiguate.
- Preserve exact indentation (tabs/spaces) from the file content.

### Glob
- Use Glob to find files by name or pattern (e.g., `**/*.py`, `src/**/test_*.py`).
- Use Glob instead of guessing file paths. When you need to find where a module,
  class, or file lives, search for it first.

### Grep
- Use Grep to search file contents by regex pattern.
- Use Grep to find function definitions, class usages, import locations, and
  string references across the codebase.
- Prefer Grep over reading many files manually when searching for specific
  patterns.

### Task (Subagents)
- Use Task to spawn subagents for parallel work. Each subagent operates
  independently with its own context.
- When tasks are marked **[P]** (parallel), launch them simultaneously via
  multiple Task tool calls in a single response. This maximizes throughput.
- Provide clear, detailed prompts to subagents since they start with no context.
  Include file paths, requirements, and conventions they need to follow.

### run_validation
- You do NOT have Bash access. To run commands use run_validation instead.
- Call with types: ["sync"] to install or update dependencies. Always do
  this after modifying pyproject.toml, package.json, or similar files.
- Call with types: ["test"] to run tests after implementing code.
- Call with types: ["lint"] or ["format"] to check for style issues.
- Call with types: ["format", "lint", "test"] to run multiple checks at once.
- Use this to verify your code works BEFORE completing the phase.
- Do NOT rely solely on the orchestration layer to catch errors — take
  ownership of delivering working code.

**CRITICAL**: You MUST use Write and Edit to create and modify source files.
Reading and analyzing is NOT enough — actually implement the code.

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
  patterns. Match the style and conventions of surrounding code.
"""

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
- Run run_validation with types: ["sync"] (if you modified dependency
  files), then ["format", "lint", "test"]. Fix any issues found before
  completing.

### Rules

- You MUST use Write and Edit to create and modify actual source files.
  Reading and analyzing is NOT enough — you must produce working code.
- You MUST create test files for every source module you create. If you
  create `src/foo/bar.py`, also create `tests/test_bar.py`. Do not skip
  tests or defer them to a later phase.
- You do NOT have Bash access. Use run_validation for all commands.
- The orchestration workflow handles git commits after you finish.
- Use run_validation to run tests, lint, and format checks before
  completing. If you modified dependency files, run sync first.
- Do NOT include commit messages in your output — the workflow generates
  them automatically.
- Follow the project's conventions from CLAUDE.md if it exists.
- Read files before editing them. Do not guess at file contents.
- Prefer Edit over Write for existing files to make targeted changes.
"""


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
    ) -> None:
        """Initialize ImplementerAgent.

        Args:
            model: Claude model ID (defaults to claude-sonnet-4-5-20250929).
            mcp_servers: Optional MCP server configurations.
            max_tokens: Optional maximum output tokens (SDK default used if None).
            temperature: Optional sampling temperature 0.0-1.0 (SDK default).
            project_type: Project type for skill guidance (auto-detected if None).
        """
        # Render prompt with skill guidance for this project type
        system_prompt = render_prompt(
            IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE,
            project_type=project_type,
        )

        # Build allowed tools list, adding validation MCP tool if server is present
        tools = list(IMPLEMENTER_TOOLS)
        if mcp_servers and "validation-tools" in mcp_servers:
            tools.append("mcp__validation-tools__run_validation")

        super().__init__(
            name="implementer",
            system_prompt=system_prompt,
            allowed_tools=tools,
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def execute(self, context: ImplementerContext) -> ImplementationResult:
        """Execute tasks from file or description.

        Args:
            context: Execution context with task source and options.

        Returns:
            ImplementationResult with task outcomes and file changes.

        Raises:
            TaskParseError: If task file has invalid format.
            AgentError: On unrecoverable execution errors.
        """
        # Route to phase mode if phase_name is specified
        if context.is_phase_mode:
            return await self._execute_phase_mode(context)

        # Otherwise use task-by-task mode (original behavior)
        return await self._execute_task_mode(context)

    async def _execute_task_mode(
        self, context: ImplementerContext
    ) -> ImplementationResult:
        """Execute tasks one by one with Maverick-managed parallelization.

        This is the original execution mode where Maverick handles parallel
        batching via asyncio.gather().

        Args:
            context: Execution context with task source and options.

        Returns:
            ImplementationResult with task outcomes and file changes.
        """
        start_time = time.monotonic()
        task_results: list[TaskResult] = []
        commits: list[str] = []
        all_files_changed: list[FileChange] = []
        errors: list[str] = []

        try:
            # Parse tasks
            if context.is_single_task:
                # Create synthetic single-task TaskFile
                tasks = [
                    Task(
                        id="T000",
                        description=context.task_description or "",
                        status=TaskStatus.PENDING,
                        parallel=False,
                    )
                ]
                task_file = TaskFile(path=Path("direct-task"), tasks=tasks, phases={})
            else:
                if not context.task_file or not context.task_file.exists():
                    raise TaskParseError(
                        f"Task file not found: {context.task_file}",
                    )
                task_file = TaskFile.parse(context.task_file)

            logger.info(
                "Starting implementation: %d tasks from %s",
                len(task_file.pending_tasks),
                task_file.path,
            )

            # Execute tasks - parallel batches where marked, sequential otherwise
            remaining_tasks = list(task_file.pending_tasks)
            while remaining_tasks:
                # Check if next batch is parallelizable
                parallel_batch = self._get_parallel_batch(remaining_tasks)

                if parallel_batch:
                    # Execute parallel batch concurrently
                    batch_results = await self._execute_parallel_batch(
                        parallel_batch, context
                    )
                    task_results.extend(batch_results)

                    for task_result in batch_results:
                        if task_result.succeeded:
                            all_files_changed.extend(task_result.files_changed)
                            if task_result.commit_sha:
                                commits.append(task_result.commit_sha)
                        else:
                            error_msg = (
                                task_result.error
                                or f"Task {task_result.task_id} failed"
                            )
                            errors.append(error_msg)

                    # Remove executed tasks from remaining
                    executed_ids = {t.id for t in parallel_batch}
                    remaining_tasks = [
                        t for t in remaining_tasks if t.id not in executed_ids
                    ]
                else:
                    # Execute single sequential task
                    task = remaining_tasks.pop(0)
                    task_result = await self._execute_single_task(task, context)
                    task_results.append(task_result)

                    if task_result.succeeded:
                        all_files_changed.extend(task_result.files_changed)
                        if task_result.commit_sha:
                            commits.append(task_result.commit_sha)
                    else:
                        errors.append(task_result.error or f"Task {task.id} failed")
                        # Continue with next task per Constitution IV

            # Compute summary
            tasks_completed = sum(1 for r in task_results if r.succeeded)
            tasks_failed = sum(1 for r in task_results if r.status == TaskStatus.FAILED)
            tasks_skipped = sum(
                1 for r in task_results if r.status == TaskStatus.SKIPPED
            )

            return ImplementationResult(
                success=tasks_failed == 0,
                tasks_completed=tasks_completed,
                tasks_failed=tasks_failed,
                tasks_skipped=tasks_skipped,
                task_results=task_results,
                files_changed=all_files_changed,
                commits=commits,
                validation_passed=all(
                    all(v.success for v in r.validation)
                    for r in task_results
                    if r.validation
                ),
                metadata={
                    "branch": context.branch,
                    "duration_ms": int((time.monotonic() - start_time) * 1000),
                    "dry_run": context.dry_run,
                },
                errors=errors,
            )

        except Exception as e:
            if isinstance(e, TaskParseError):
                raise
            logger.exception("Implementation failed: %s", e)
            completed = sum(1 for r in task_results if r.succeeded)
            return ImplementationResult(
                success=False,
                tasks_completed=completed,
                tasks_failed=len(task_results) - completed,
                tasks_skipped=0,
                task_results=task_results,
                files_changed=all_files_changed,
                commits=commits,
                validation_passed=False,
                errors=[str(e)],
            )

    async def _execute_single_task(
        self,
        task: Task,
        context: ImplementerContext,
    ) -> TaskResult:
        """Execute a single task using Claude SDK.

        Args:
            task: Task to execute.
            context: Execution context.

        Returns:
            TaskResult with execution outcome.
        """
        start_time = time.monotonic()

        try:
            logger.info("Executing task %s: %s", task.id, task.description[:50])

            # Build prompt for Claude
            prompt = self._build_task_prompt(task, context)

            # Execute via Claude SDK with streaming
            messages = []
            async for msg in self.query(prompt, cwd=context.cwd):
                messages.append(msg)
                # Stream text to TUI if callback is set
                if self.stream_callback:
                    text = extract_streaming_text(msg)
                    if text:
                        await self.stream_callback(text)

            # Parse result from output (simplified - full parsing in enhancement phase)
            files_changed = await detect_file_changes(context.cwd)

            # Validation and commits are handled by the workflow layer
            # Agent returns file changes; orchestration runs validation/commits
            validation_results: list[ValidationResult] = []
            commit_sha = None

            duration_ms = int((time.monotonic() - start_time) * 1000)

            return TaskResult(
                task_id=task.id,
                status=TaskStatus.COMPLETED,
                files_changed=files_changed,
                tests_added=[
                    f.file_path for f in files_changed if "test" in f.file_path.lower()
                ],
                commit_sha=commit_sha,
                duration_ms=duration_ms,
                validation=validation_results,
            )

        except Exception as e:
            logger.error("Task %s failed: %s", task.id, e)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )

    def _build_task_prompt(self, task: Task, context: ImplementerContext) -> str:
        """Build the prompt for executing a task."""
        return f"""Execute the following task:

**Task ID**: {task.id}
**Description**: {task.description}
**Branch**: {context.branch}

Follow the TDD approach:
1. First, understand what needs to be done
2. Write tests if applicable
3. Implement the solution
4. Ensure code passes validation

After completion, provide a summary of changes made.
"""

    def _get_parallel_batch(self, tasks: list[Task]) -> list[Task]:
        """Get consecutive parallelizable tasks from the front of the list.

        Args:
            tasks: List of tasks to check.

        Returns:
            List of tasks that can be executed in parallel, or empty list
            if the first task is not parallelizable.
        """
        batch: list[Task] = []
        for task in tasks:
            if task.parallel and not task.dependencies:
                batch.append(task)
            elif batch:
                # Stop at first non-parallel task after collecting some parallel tasks
                break
            else:
                # First task is not parallel, return empty batch
                break
        return batch

    async def _execute_parallel_batch(
        self,
        tasks: list[Task],
        context: ImplementerContext,
    ) -> list[TaskResult]:
        """Execute a batch of tasks in parallel.

        Args:
            tasks: List of tasks to execute concurrently.
            context: Execution context.

        Returns:
            List of TaskResults in the same order as input tasks.
        """
        logger.info(
            "Executing %d tasks in parallel: %s",
            len(tasks),
            [t.id for t in tasks],
        )

        # Create coroutines for all tasks
        coros = [self._execute_single_task(task, context) for task in tasks]

        # Execute concurrently with gather
        results = await asyncio.gather(*coros, return_exceptions=True)

        # Convert any exceptions to failed TaskResults
        task_results: list[TaskResult] = []
        for task, result in zip(tasks, results, strict=True):
            if isinstance(result, Exception):
                logger.error(
                    "Parallel task %s failed with exception: %s", task.id, result
                )
                task_results.append(
                    TaskResult(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error=str(result),
                    )
                )
            else:
                assert isinstance(result, TaskResult)
                task_results.append(result)

        return task_results

    async def _execute_phase_mode(
        self, context: ImplementerContext
    ) -> ImplementationResult:
        """Execute all tasks in a phase via /speckit.implement.

        In phase mode, the prompt invokes /speckit.implement which handles
        task parsing, prerequisite checks, and execution. Claude decides how
        to parallelize [P] marked tasks using the Task tool (subagents).

        The agent does NOT pre-parse tasks — Claude reads tasks.md directly
        and determines which tasks belong to the requested phase.

        Args:
            context: Execution context with phase_name and task_file.

        Returns:
            ImplementationResult with phase execution outcome.
        """
        start_time = time.monotonic()

        assert context.task_file is not None
        assert context.phase_name is not None

        try:
            # Verify task file exists (Claude can't read a nonexistent file)
            if not context.task_file.exists():
                raise TaskParseError(f"Task file not found: {context.task_file}")

            logger.info(
                "Executing phase '%s' from %s",
                context.phase_name,
                context.task_file,
            )

            # Build phase prompt — Claude/speckit handles task parsing
            prompt = self._build_phase_prompt(context.phase_name, context)

            # Execute via Claude SDK with streaming
            # Claude handles task parsing and parallelization within the phase
            messages = []
            async for msg in self.query(prompt, cwd=context.cwd):
                messages.append(msg)
                # Stream text to TUI if callback is set
                if self.stream_callback:
                    text = extract_streaming_text(msg)
                    if text:
                        await self.stream_callback(text)

            # Detect file changes after phase execution
            files_changed = await detect_file_changes(context.cwd)

            duration_ms = int((time.monotonic() - start_time) * 1000)

            return ImplementationResult(
                success=True,
                tasks_completed=0,
                tasks_failed=0,
                tasks_skipped=0,
                task_results=[],
                files_changed=files_changed,
                commits=[],
                validation_passed=True,
                metadata={
                    "branch": context.branch,
                    "phase": context.phase_name,
                    "duration_ms": duration_ms,
                    "dry_run": context.dry_run,
                    "execution_mode": "phase",
                },
            )

        except Exception as e:
            if isinstance(e, TaskParseError):
                raise
            logger.exception("Phase execution failed: %s", e)
            return ImplementationResult(
                success=False,
                tasks_completed=0,
                tasks_failed=0,
                tasks_skipped=0,
                task_results=[],
                files_changed=[],
                commits=[],
                validation_passed=False,
                errors=[str(e)],
                metadata={
                    "branch": context.branch,
                    "phase": context.phase_name,
                    "execution_mode": "phase",
                },
            )

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
