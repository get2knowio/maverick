"""Task file parser for .specify tasks.md format.

This module provides functions for parsing tasks.md files into structured
Task objects following the .specify format conventions.
"""

from __future__ import annotations

import re
from pathlib import Path

from maverick.exceptions import TaskParseError
from maverick.logging import get_logger
from maverick.models.implementation import Task, TaskStatus

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Regex patterns for parsing task lines
# Format: - [ ] T001 [P] [US1] Description text here
TASK_LINE_PATTERN = re.compile(
    r"^-\s*\[([xX\s])\]\s*"  # Checkbox: [ ], [x], or [X]
    r"(T\d{3,})\s*"  # Task ID: T001, T123, etc.
    r"(?:\[P\]|P:)?\s*"  # Optional parallel marker: [P] or P:
    r"(?:\[(US\d+)\])?\s*"  # Optional user story: [US1], [US2]
    r"(.+)$",  # Description (rest of line)
    re.IGNORECASE,
)

# Pattern to check for parallel marker
PARALLEL_PATTERN = re.compile(r"\[P\]|P:", re.IGNORECASE)

# Pattern for phase headers
PHASE_HEADER_PATTERN = re.compile(r"^##\s+(.+)$")


# =============================================================================
# Parser Functions
# =============================================================================


def parse_task_line(
    line: str, line_number: int, current_phase: str | None = None
) -> Task | None:
    """Parse a single task line into a Task object.

    Args:
        line: The line to parse.
        line_number: Line number for error reporting.
        current_phase: Current phase name from most recent header.

    Returns:
        Task object if line is a valid task, None otherwise.

    Raises:
        TaskParseError: If line looks like a task but has invalid format.
    """
    # Skip empty lines and non-task lines
    stripped = line.strip()
    if not stripped or not stripped.startswith("- ["):
        return None

    match = TASK_LINE_PATTERN.match(stripped)
    if not match:
        # Line looks like a task but doesn't match pattern
        if stripped.startswith("- [") and "T" in stripped:
            raise TaskParseError(
                f"Invalid task format at line {line_number}: {stripped[:50]}...",
                line_number=line_number,
            )
        return None

    checkbox, task_id, user_story, description = match.groups()

    # Determine status from checkbox
    status = TaskStatus.COMPLETED if checkbox.lower() == "x" else TaskStatus.PENDING

    # Check for parallel marker in the original line
    is_parallel = bool(PARALLEL_PATTERN.search(line))

    # Clean up description (remove parallel marker if present)
    description = PARALLEL_PATTERN.sub("", description).strip()
    description = re.sub(r"\[US\d+\]", "", description).strip()

    return Task(
        id=task_id.upper(),
        description=description,
        status=status,
        parallel=is_parallel,
        user_story=user_story.upper() if user_story else None,
        phase=current_phase,
        dependencies=[],  # Dependencies determined by task order in file
    )


def parse_tasks_md(content: str) -> tuple[list[Task], dict[str, list[Task]]]:
    """Parse tasks.md content into Task objects.

    Args:
        content: Full content of the tasks.md file.

    Returns:
        Tuple of (tasks_list, phases_dict) where:
        - tasks_list: All tasks in order of appearance
        - phases_dict: Tasks grouped by phase name

    Raises:
        TaskParseError: If file format is invalid.
    """
    tasks: list[Task] = []
    phases: dict[str, list[Task]] = {}
    current_phase: str | None = None

    lines = content.split("\n")

    for line_number, line in enumerate(lines, start=1):
        # Check for phase header
        phase_match = PHASE_HEADER_PATTERN.match(line.strip())
        if phase_match:
            current_phase = phase_match.group(1).strip()
            if current_phase not in phases:
                phases[current_phase] = []
            continue

        # Try to parse as task
        try:
            task = parse_task_line(line, line_number, current_phase)
            if task:
                tasks.append(task)
                if current_phase:
                    phases[current_phase].append(task)
        except TaskParseError:
            raise
        except Exception as e:
            raise TaskParseError(
                f"Unexpected error parsing line {line_number}: {e}",
                line_number=line_number,
            ) from e

    logger.debug(
        "Parsed %d tasks in %d phases from tasks.md",
        len(tasks),
        len(phases),
    )

    return tasks, phases


def parse_tasks_file(path: Path) -> tuple[list[Task], dict[str, list[Task]]]:
    """Parse a tasks.md file.

    Args:
        path: Path to the tasks.md file.

    Returns:
        Tuple of (tasks_list, phases_dict).

    Raises:
        TaskParseError: If file format is invalid.
        FileNotFoundError: If file doesn't exist.
    """
    content = path.read_text(encoding="utf-8")
    return parse_tasks_md(content)


def get_pending_count(tasks: list[Task]) -> int:
    """Count pending tasks.

    Args:
        tasks: List of tasks.

    Returns:
        Number of pending tasks.
    """
    return sum(1 for t in tasks if t.status == TaskStatus.PENDING)


def get_completed_count(tasks: list[Task]) -> int:
    """Count completed tasks.

    Args:
        tasks: List of tasks.

    Returns:
        Number of completed tasks.
    """
    return sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)


def format_task_checkbox(task: Task) -> str:
    """Format a task back to markdown checkbox format.

    Args:
        task: Task to format.

    Returns:
        Markdown checkbox line.
    """
    checkbox = "[x]" if task.status == TaskStatus.COMPLETED else "[ ]"
    parallel = "[P] " if task.parallel else ""
    user_story = f"[{task.user_story}] " if task.user_story else ""
    return f"- {checkbox} {task.id} {parallel}{user_story}{task.description}"
