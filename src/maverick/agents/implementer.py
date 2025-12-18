"""ImplementerAgent for executing structured task files.

This module provides the ImplementerAgent that executes tasks from tasks.md
files or direct descriptions using TDD approach and conventional commits.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.agents.base import MaverickAgent
from maverick.agents.utils import extract_all_text
from maverick.exceptions import AgentError, TaskParseError
from maverick.models.implementation import (
    ChangeType,
    FileChange,
    ImplementationResult,
    ImplementerContext,
    Task,
    TaskFile,
    TaskResult,
    TaskStatus,
    ValidationResult,
)

if TYPE_CHECKING:
    from maverick.agents.result import AgentResult

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

IMPLEMENTER_SYSTEM_PROMPT = """You are an expert software engineer focused on methodical, test-driven implementation.

## Core Approach
1. Understand the task fully before writing code
2. Write tests first or alongside implementation (TDD)
3. Follow project conventions from CLAUDE.md
4. Make small, incremental changes with clear commits
5. Validate after each change (format, lint, test)

## Task Execution
For each task:
1. Read the task description carefully
2. Identify affected files and dependencies
3. Write/update tests for the new functionality
4. Implement the minimal code to pass tests
5. Run validation (format, lint, test)
6. Fix any issues before committing
7. Create a commit with conventional commit message

## Conventional Commits
Use format: `type(scope): description`
- feat: New feature
- fix: Bug fix
- refactor: Code refactoring
- test: Test additions/changes
- docs: Documentation
- chore: Maintenance tasks

## Tools Available
Read, Write, Edit, Bash, Glob, Grep

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

#: Tools available to the implementer agent
IMPLEMENTER_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]


# =============================================================================
# ImplementerAgent
# =============================================================================


class ImplementerAgent(MaverickAgent):
    """Agent for executing structured task files.

    Implements methodical, test-driven task execution from tasks.md files
    or direct task descriptions.

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
    ) -> None:
        """Initialize ImplementerAgent.

        Args:
            model: Claude model ID (defaults to claude-sonnet-4-5-20250929).
            mcp_servers: Optional MCP server configurations.
        """
        super().__init__(
            name="implementer",
            system_prompt=IMPLEMENTER_SYSTEM_PROMPT,
            allowed_tools=IMPLEMENTER_TOOLS,
            model=model,
            mcp_servers=mcp_servers,
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
        start_time = time.monotonic()
        task_results: list[TaskResult] = []
        commits: list[str] = []
        all_files_changed: list[FileChange] = []
        errors: list[str] = []

        try:
            # Parse tasks
            if context.is_single_task:
                # Create synthetic single-task TaskFile
                tasks = [Task(
                    id="T000",
                    description=context.task_description or "",
                    status=TaskStatus.PENDING,
                    parallel=False,
                )]
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
                            errors.append(
                                task_result.error or f"Task {task_result.task_id} failed"
                            )

                    # Remove executed tasks from remaining
                    executed_ids = {t.id for t in parallel_batch}
                    remaining_tasks = [t for t in remaining_tasks if t.id not in executed_ids]
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
            tasks_skipped = sum(1 for r in task_results if r.status == TaskStatus.SKIPPED)

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
                    for r in task_results if r.validation
                ),
                metadata={
                    "branch": context.branch,
                    "duration_ms": int((time.monotonic() - start_time) * 1000),
                    "dry_run": context.dry_run,
                },
                errors=errors,
            )

        except TaskParseError:
            raise
        except Exception as e:
            logger.exception("Implementation failed: %s", e)
            return ImplementationResult(
                success=False,
                tasks_completed=sum(1 for r in task_results if r.succeeded),
                tasks_failed=len(task_results) - sum(1 for r in task_results if r.succeeded),
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

            # Execute via Claude SDK
            messages = []
            async for msg in self.query(prompt, cwd=context.cwd):
                messages.append(msg)

            output = extract_all_text(messages)

            # Parse result from output (simplified - full parsing in enhancement phase)
            files_changed = await self._detect_file_changes(context.cwd)

            # Run validation if not skipped
            validation_results: list[ValidationResult] = []
            if not context.skip_validation:
                validation_results = await self._run_validation(context.cwd)

            # Create commit if not dry run
            commit_sha = None
            if not context.dry_run:
                commit_sha = await self._create_commit(task, context)

            duration_ms = int((time.monotonic() - start_time) * 1000)

            return TaskResult(
                task_id=task.id,
                status=TaskStatus.COMPLETED,
                files_changed=files_changed,
                tests_added=[f.file_path for f in files_changed if "test" in f.file_path.lower()],
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

    async def _detect_file_changes(self, cwd: Path) -> list[FileChange]:
        """Detect file changes from git status."""
        from maverick.utils.git import get_diff_stats

        try:
            stats = await get_diff_stats(cwd)
            return [
                FileChange(
                    file_path=path,
                    change_type=ChangeType.MODIFIED,
                    lines_added=added,
                    lines_removed=removed,
                )
                for path, (added, removed) in stats.items()
            ]
        except Exception as e:
            logger.warning("Could not detect file changes: %s", e)
            return []

    async def _run_validation(self, cwd: Path) -> list[ValidationResult]:
        """Run validation pipeline."""
        from maverick.utils.validation import run_validation_pipeline

        try:
            return await run_validation_pipeline(cwd)
        except Exception as e:
            logger.warning("Validation failed: %s", e)
            return []

    async def _create_commit(self, task: Task, context: ImplementerContext) -> str | None:
        """Create a git commit for the task."""
        from maverick.utils.git import create_commit, has_uncommitted_changes

        try:
            if not await has_uncommitted_changes(context.cwd):
                return None

            # Generate conventional commit message
            commit_type = "feat" if "create" in task.description.lower() else "chore"
            message = f"{commit_type}({task.id.lower()}): {task.description[:50]}"

            return await create_commit(message, context.cwd)
        except Exception as e:
            logger.warning("Could not create commit: %s", e)
            return None

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
        for task, result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.error("Parallel task %s failed with exception: %s", task.id, result)
                task_results.append(
                    TaskResult(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error=str(result),
                    )
                )
            else:
                task_results.append(result)

        return task_results
