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
2. Write tests first or alongside implementation (TDD)
3. Follow project conventions from CLAUDE.md
4. Make small, incremental changes
5. Ensure code is ready for validation (will be run by orchestration)

## Task Execution
For each task:
1. Read the task description carefully
2. Identify affected files and dependencies
3. Write/update tests for the new functionality
4. Implement the minimal code to pass tests
5. Ensure code follows conventions and is ready for validation

## Conventional Commits
When describing your changes, use this format for reference:
- feat: New feature
- fix: Bug fix
- refactor: Code refactoring
- test: Test additions/changes
- docs: Documentation
- chore: Maintenance tasks

The orchestration layer will create commits using this format.

## Tools Available
Read, Write, Edit, Glob, Grep, Task

Use these tools to:
- Read existing code and understand context
- Write new files or update existing ones
- Edit existing files with targeted replacements
- Search for patterns and locate relevant code (Glob for files, Grep for content)
- Spawn subagents for parallel task execution (Task)

**IMPORTANT**: You MUST use Write and Edit to create and modify source files.
Do not just read and analyze — actually implement the code.

## Output
After completing a task, output a JSON summary:
{
  "task_id": "T001",
  "status": "completed",
  "files_changed": [{"path": "src/file.py", "added": 10, "removed": 2}],
  "tests_added": ["tests/test_file.py"],
  "commit_message": "feat(scope): description"
}
"""

PHASE_ARGUMENTS_TEMPLATE = (
    'Implement all the tasks in phase "{phase_name}" '
    'from the task file at "{task_file}". '
    "Create a subagent to complete each task. "
    'Tasks marked with a "[P]" can be processed simultaneously '
    "(in separate subagents). Update tasks.md to track your progress."
)

#: Preamble prepended to the expanded skill content when running inside
#: the Maverick workflow.  The workflow's preflight and init steps already
#: handle prerequisite checks, workspace setup, and git operations, so the
#: agent should skip those shell-dependent steps and focus on implementation.
PHASE_SKILL_PREAMBLE = """\
## Workflow Context — Read This First

You are running inside the Maverick orchestration workflow. The workflow has
ALREADY completed the following before invoking you:

- **Preflight checks** (API keys, git, GitHub CLI, validation tools) — PASSED
- **Workspace initialization** (branch checkout, sync with origin/main) — DONE
- **Project setup verification** (ignore files, config) — DONE

Therefore you MUST **skip** the following steps from the instructions below:
- Step 1 (check-prerequisites.sh) — already done by the workflow
- Step 2 (checklist verification) — already done by the workflow
- Step 4 (project setup verification / git rev-parse) — already done

**Start directly from Step 3** (load and analyze the implementation context)
and continue through implementation execution (Steps 5-8). You MUST actually
create and modify source files using Write and Edit tools — do not just read
and analyze. You do NOT have access to the Bash tool, so do not attempt to
run shell commands. Use Read, Write, Edit, Glob, Grep, and Task (subagents).

---

"""

#: Skill file name to load for phase-level execution
SPECKIT_IMPLEMENT_SKILL = "speckit.implement.md"

#: Standard locations for Claude Code custom commands (searched in order)
SKILL_SEARCH_DIRS = [
    ".claude/commands",
]


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

        super().__init__(
            name="implementer",
            system_prompt=system_prompt,
            allowed_tools=list(IMPLEMENTER_TOOLS),
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

        Loads the speckit.implement skill from .claude/commands/ and expands
        its $ARGUMENTS placeholder with phase-specific instructions. This
        gives the agent the full speckit implementation workflow:
        - Prerequisites check
        - Checklist verification
        - Loading spec artifacts (plan.md, data-model.md, etc.)
        - Task parsing from tasks.md
        - Task execution with subagent parallelization

        Falls back to the arguments template alone if the skill file is
        not found (the agent still receives actionable instructions).

        Args:
            phase_name: Name of the phase.
            context: Execution context (provides task_file path and cwd).

        Returns:
            Formatted prompt for Claude.
        """
        arguments = PHASE_ARGUMENTS_TEMPLATE.format(
            phase_name=phase_name,
            task_file=context.task_file,
        )

        skill_content = self._load_skill(SPECKIT_IMPLEMENT_SKILL, context.cwd)
        if skill_content:
            expanded = skill_content.replace("$ARGUMENTS", arguments)
            return PHASE_SKILL_PREAMBLE + expanded

        logger.warning(
            "speckit.implement skill not found, using fallback prompt",
            cwd=str(context.cwd),
        )
        return arguments

    @staticmethod
    def _load_skill(
        skill_filename: str,
        cwd: Path | None = None,
    ) -> str | None:
        """Load a Claude Code custom command (skill) from .claude/commands/.

        Searches the project directory for the skill file, strips YAML
        frontmatter, and returns the prompt content.

        Args:
            skill_filename: Skill filename (e.g. "speckit.implement.md").
            cwd: Project working directory to search from.

        Returns:
            Skill prompt content with frontmatter stripped, or None if
            the skill file was not found.
        """
        search_root = cwd or Path.cwd()

        for search_dir in SKILL_SEARCH_DIRS:
            path = search_root / search_dir / skill_filename
            if path.is_file():
                content = path.read_text()
                # Strip YAML frontmatter (--- ... ---)
                if content.startswith("---"):
                    end = content.find("---", 3)
                    if end != -1:
                        content = content[end + 3 :].lstrip("\n")
                logger.debug(
                    "Loaded skill from %s (%d chars)",
                    path,
                    len(content),
                )
                return content

        return None
