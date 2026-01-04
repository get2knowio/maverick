"""Task file parsing actions."""

from __future__ import annotations

from pathlib import Path

from maverick.logging import get_logger
from maverick.utils.task_parser import parse_tasks_file

logger = get_logger(__name__)


async def get_phase_names(task_file: str | Path) -> list[str]:
    """Extract phase names from a tasks.md file.

    Parses the task file and returns a list of phase names in the order
    they appear. Phase names are extracted from ## headers.

    Args:
        task_file: Path to the tasks.md file.

    Returns:
        List of phase names in order. Empty list if no phases defined.

    Example:
        ```python
        phases = await get_phase_names("specs/feature/tasks.md")
        # Returns: ["Setup", "Implementation", "Testing"]
        ```
    """
    path = Path(task_file)

    if not path.exists():
        logger.warning("Task file not found", task_file=str(path))
        return []

    try:
        _tasks, phases_dict = parse_tasks_file(path)
        # Return phase names that contain at least one task
        # (filters out documentation headers like "Format:", "Path Conventions", etc.)
        phase_names = [name for name, tasks in phases_dict.items() if tasks]
        logger.info(
            "Extracted phase names from task file",
            task_file=str(path),
            phase_count=len(phase_names),
        )
        return phase_names
    except Exception as e:
        logger.error("Failed to parse task file", task_file=str(path), error=str(e))
        return []
