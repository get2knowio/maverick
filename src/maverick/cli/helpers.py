"""Helper functions for CLI command implementations.

This module contains reusable helper functions extracted from CLI commands
to improve readability and testability.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.cli.output import format_error
from maverick.exceptions import GitError, NotARepositoryError
from maverick.git import GitRepository

if TYPE_CHECKING:
    from maverick.models.review import ReviewResult

__all__ = [
    "validate_branch",
    "detect_task_file",
    "get_git_branch",
    "validate_pr",
    "count_tasks",
    "format_review_text",
    "format_review_markdown",
    "execute_dsl_workflow",
]


def validate_branch(branch_name: str) -> tuple[bool, str | None]:
    """Validate that a git branch exists.

    Uses GitRepository wrapper per CLAUDE.md canonical library standards.

    Args:
        branch_name: Name of the branch to validate.

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.
        If invalid, error_message contains the formatted error.

    Example:
        >>> valid, error = validate_branch("main")
        >>> if not valid:
        ...     print(error)
    """
    try:
        repo = GitRepository(Path.cwd())

        # Check if branch exists in local branches
        branches = [b.name for b in repo._repo.branches]
        if branch_name in branches:
            return True, None

        # Branch doesn't exist - check if we're on it (new branch, no commits)
        current = repo.current_branch()
        if current == branch_name:
            return True, None

        # Branch doesn't exist
        suggestion = f"Create branch with 'git checkout -b {branch_name}'"
        error_msg = format_error(
            f"Branch '{branch_name}' does not exist",
            suggestion=suggestion,
        )
        return False, error_msg

    except NotARepositoryError:
        error_msg = format_error(
            "Not a git repository",
            suggestion="Initialize with 'git init' or navigate to a git repository",
        )
        return False, error_msg
    except GitError as e:
        error_msg = format_error(f"Git error: {e}")
        return False, error_msg


def detect_task_file(branch_name: str | None = None) -> Path | None:
    """Auto-detect task file location.

    Looks for tasks.md in standard locations:
    1. specs/<branch_name>/tasks.md (if branch_name provided, Speckit convention)
    2. tasks.md (in current directory)

    Args:
        branch_name: Optional branch name to check branch-specific task file.

    Returns:
        Path to task file if found, None otherwise.

    Example:
        >>> task_file = detect_task_file("feature-123")
        >>> if task_file:
        ...     print(f"Found: {task_file}")
    """
    potential_paths: list[Path] = []

    if branch_name:
        # Speckit convention
        potential_paths.append(Path(f"specs/{branch_name}/tasks.md"))

    potential_paths.append(Path("tasks.md"))

    for path in potential_paths:
        if path.exists():
            return path

    return None


def get_git_branch() -> tuple[str | None, str | None]:
    """Get the current git branch name.

    Uses GitRepository wrapper per CLAUDE.md canonical library standards.

    Returns:
        Tuple of (branch_name, error_message). If successful, error_message is None.
        If error, branch_name may be None or a placeholder like "(detached HEAD)".

    Example:
        >>> branch, error = get_git_branch()
        >>> if error:
        ...     print(f"Error: {error}")
        >>> else:
        ...     print(f"On branch: {branch}")
    """
    try:
        repo = GitRepository(Path.cwd())
        branch = repo.current_branch()

        # current_branch returns commit SHA if detached
        if len(branch) == 40 and all(c in "0123456789abcdef" for c in branch):
            return "(detached HEAD)", None

        return branch, None

    except NotARepositoryError:
        error_msg = format_error(
            "Not a git repository",
            suggestion="Initialize with 'git init' or navigate to a git repository",
        )
        return None, error_msg
    except GitError as e:
        error_msg = format_error(f"Git error: {e}")
        return None, error_msg


def validate_pr(pr_number: int) -> tuple[bool, str | None, dict[str, str] | None]:
    """Validate that a pull request exists and get its details.

    Args:
        pr_number: Pull request number to validate.

    Returns:
        Tuple of (is_valid, error_message, pr_data). If valid, error_message is None
        and pr_data contains headRefName and baseRefName. If invalid, pr_data is None.

    Example:
        >>> valid, error, data = validate_pr(123)
        >>> if not valid:
        ...     print(error)
        >>> else:
        ...     head = data['headRefName']
        ...     base = data['baseRefName']
        ...     print(f"PR #{pr_number}: {head} -> {base}")
    """
    import json

    try:
        # First validate PR exists
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            suggestion = (
                "Check the PR number and ensure you have access to the repository"
            )
            error_msg = format_error(
                f"Pull request #{pr_number} not found",
                suggestion=suggestion,
            )
            return False, error_msg, None

        # Get PR details
        pr_info_result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(pr_number),
                "--json",
                "headRefName,baseRefName",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if pr_info_result.returncode != 0:
            error_msg = format_error(
                f"Failed to fetch PR #{pr_number} details",
            )
            return False, error_msg, None

        pr_data = json.loads(pr_info_result.stdout)
        return True, None, pr_data

    except subprocess.TimeoutExpired:
        error_msg = format_error("GitHub CLI command timed out")
        return False, error_msg, None
    except FileNotFoundError:
        error_msg = format_error(
            "GitHub CLI (gh) is not installed",
            suggestion="Install from https://cli.github.com/",
        )
        return False, error_msg, None
    except json.JSONDecodeError as e:
        error_msg = format_error(f"Failed to parse PR details: {e}")
        return False, error_msg, None


def count_tasks(task_file: Path) -> tuple[int, int]:
    """Count pending and completed tasks in a task file.

    Args:
        task_file: Path to tasks.md file.

    Returns:
        Tuple of (pending_count, completed_count).

    Example:
        >>> pending, completed = count_tasks(Path("tasks.md"))
        >>> print(f"{pending} pending, {completed} completed")
    """
    from maverick.logging import get_logger

    logger = get_logger(__name__)

    try:
        content = task_file.read_text()
        # Count pending tasks: lines with - [ ]
        pending = len(re.findall(r"^-\s*\[\s*\]", content, re.MULTILINE))
        # Count completed tasks: lines with - [x] or - [X]
        completed = len(re.findall(r"^-\s*\[[xX]\]", content, re.MULTILINE))
        return pending, completed
    except Exception as e:
        logger.warning("failed_to_count_tasks", file=str(task_file), error=str(e))
        return 0, 0


def format_review_text(result: ReviewResult) -> str:
    """Format review result as text for console output.

    Args:
        result: ReviewResult from CodeReviewerAgent.

    Returns:
        Formatted text string.
    """
    lines = [f"\n{result.summary}"]

    if result.findings:
        lines.append(f"\nFound {len(result.findings)} issue(s):\n")
        for i, finding in enumerate(result.findings, 1):
            severity_label = finding.severity.value.upper()
            lines.append(f"{i}. [{severity_label}] {finding.file}")
            if finding.line:
                lines.append(f"   Line {finding.line}")
            lines.append(f"   {finding.message}")
            if finding.suggestion:
                lines.append(f"   Suggestion: {finding.suggestion}")
            lines.append("")

    return "\n".join(lines)


def format_review_markdown(result: ReviewResult, pr_number: int) -> str:
    """Format review result as markdown.

    Args:
        result: ReviewResult from CodeReviewerAgent.
        pr_number: Pull request number.

    Returns:
        Formatted markdown string.
    """
    lines = [
        f"# Code Review: PR #{pr_number}",
        "",
        "## Summary",
        "",
        result.summary,
        "",
    ]

    if result.findings:
        lines.extend(
            [
                f"## Findings ({len(result.findings)})",
                "",
            ]
        )

        # Group findings by severity
        from maverick.models.review import ReviewFinding, ReviewSeverity

        severity_groups: dict[ReviewSeverity, list[ReviewFinding]] = {
            ReviewSeverity.CRITICAL: [],
            ReviewSeverity.MAJOR: [],
            ReviewSeverity.MINOR: [],
            ReviewSeverity.SUGGESTION: [],
        }

        for finding in result.findings:
            severity_groups[finding.severity].append(finding)

        # Output findings by severity
        for severity in [
            ReviewSeverity.CRITICAL,
            ReviewSeverity.MAJOR,
            ReviewSeverity.MINOR,
            ReviewSeverity.SUGGESTION,
        ]:
            findings = severity_groups[severity]
            if findings:
                lines.extend(
                    [
                        f"### {severity.value.capitalize()} ({len(findings)})",
                        "",
                    ]
                )

                for finding in findings:
                    location = f"{finding.file}"
                    if finding.line:
                        location += f":{finding.line}"

                    lines.extend(
                        [
                            f"**{location}**",
                            "",
                            finding.message,
                            "",
                        ]
                    )

                    if finding.suggestion:
                        lines.extend(
                            [
                                "*Suggestion:*",
                                "",
                                finding.suggestion,
                                "",
                            ]
                        )

    lines.extend(
        [
            "## Metadata",
            "",
            f"- Files reviewed: {result.files_reviewed}",
        ]
    )

    if result.metadata:
        if "branch" in result.metadata:
            lines.append(f"- Branch: {result.metadata['branch']}")
        if "base_branch" in result.metadata:
            lines.append(f"- Base branch: {result.metadata['base_branch']}")
        if "duration_ms" in result.metadata:
            duration_sec = result.metadata["duration_ms"] / 1000
            lines.append(f"- Duration: {duration_sec:.2f}s")

    return "\n".join(lines)


async def execute_dsl_workflow(
    workflow_name: str,
    inputs: dict[str, Any],
    *,
    workflow_dir: Path | None = None,
) -> AsyncIterator[Any]:
    """Execute a DSL workflow from the library.

    This helper loads and executes a YAML workflow definition using the
    DSL execution engine. It's designed for use in CLI commands that need
    to run workflows.

    Args:
        workflow_name: Name of the workflow file (without .yaml extension)
            Example: "fly", "refuel"
        inputs: Input parameters for the workflow
            Example: {"branch_name": "001-foo", "task_file": "specs/001-foo/tasks.md"}
        workflow_dir: Optional directory containing workflow files.
            Defaults to src/maverick/library/workflows/

    Yields:
        DSL progress events (WorkflowStarted, StepStarted, StepCompleted,
        WorkflowCompleted)

    Example:
        ```python
        inputs = {"branch_name": "001-foo", "skip_review": False}
        async for event in execute_dsl_workflow("fly", inputs):
            if isinstance(event, StepStarted):
                click.echo(f"Starting: {event.step_name}")
            elif isinstance(event, WorkflowCompleted):
                click.echo(f"Success: {event.result.success}")
        ```
    """
    from pathlib import Path

    from maverick.dsl.serialization.executor.executor import WorkflowFileExecutor
    from maverick.dsl.serialization.registry import ComponentRegistry
    from maverick.dsl.serialization.schema import WorkflowFile

    # Default to library workflows
    if workflow_dir is None:
        import maverick.library.workflows

        workflow_dir = Path(maverick.library.workflows.__file__).parent

    # Load workflow file
    workflow_path = workflow_dir / f"{workflow_name}.yaml"
    if not workflow_path.exists():
        msg = f"Workflow not found: {workflow_path}"
        raise FileNotFoundError(msg)

    workflow_yaml = workflow_path.read_text(encoding="utf-8")
    workflow_file = WorkflowFile.from_yaml(workflow_yaml)

    # Create registry and executor
    registry = ComponentRegistry()
    executor = WorkflowFileExecutor(registry=registry)

    # Execute and yield events
    async for event in executor.execute(workflow_file, inputs=inputs):
        yield event
