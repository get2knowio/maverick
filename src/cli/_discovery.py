"""Task discovery module for Maverick CLI.

Discovers tasks.md files in specs/ directory, applies ordering rules,
and filters out completed specs.
"""

import re
from pathlib import Path

from src.cli._models import DiscoveredTask
from src.common.logging import get_logger


logger = get_logger(__name__)

# Regex pattern to extract numeric prefix from directory names
NUMERIC_PREFIX_PATTERN = re.compile(r"^(\d+)-")


def discover_tasks(
    repo_root: Path,
    target_task_file: Path | None = None,
) -> list[DiscoveredTask]:
    """Discover task files in specs/ directory.

    Searches for tasks.md files under specs/, excludes specs-completed/,
    and orders by numeric prefix then filename.

    Args:
        repo_root: Absolute path to repository root
        target_task_file: Optional specific task file to discover (filters to just this one)

    Returns:
        List of DiscoveredTask objects ordered by numeric prefix then filename

    Raises:
        ValueError: If repo_root is invalid or target_task_file not found
    """
    if not repo_root.exists():
        raise ValueError(f"Repository root does not exist: {repo_root}")

    if not repo_root.is_dir():
        raise ValueError(f"Repository root is not a directory: {repo_root}")

    specs_dir = repo_root / "specs"

    if not specs_dir.exists():
        logger.warning(
            f"Specs directory not found: {specs_dir}. No tasks will be discovered."
        )
        return []

    if not specs_dir.is_dir():
        raise ValueError(f"Specs path is not a directory: {specs_dir}")

    # If target task file specified, validate and return just that one
    if target_task_file is not None:
        return _discover_single_task(repo_root, target_task_file)

    # Discover all tasks
    discovered_tasks: list[DiscoveredTask] = []

    # Iterate over subdirectories in specs/
    for spec_dir_path in specs_dir.iterdir():
        if not spec_dir_path.is_dir():
            continue

        # Skip specs-completed/
        if spec_dir_path.name == "specs-completed":
            logger.debug(f"Skipping completed specs directory: {spec_dir_path}")
            continue

        # Look for tasks.md in this spec directory
        tasks_file = spec_dir_path / "tasks.md"
        if not tasks_file.exists():
            logger.debug(f"No tasks.md found in: {spec_dir_path}")
            continue

        # Extract numeric prefix and detect if directory uses numeric prefix
        numeric_prefix = _extract_numeric_prefix(spec_dir_path.name)

        discovered_task = DiscoveredTask(
            file_path=str(tasks_file.resolve()),
            spec_dir=str(spec_dir_path.resolve()),
            numeric_prefix=numeric_prefix,
            directory_name=spec_dir_path.name,
        )

        discovered_tasks.append(discovered_task)
        logger.debug(
            f"Discovered task: {discovered_task.directory_name} "
            f"(prefix={discovered_task.numeric_prefix})"
        )

    # Sort by numeric prefix for prefixed directories, then directory name.
    # Directories without a numeric prefix are ordered after all prefixed ones.
    discovered_tasks.sort(
        key=lambda task: (
            0 if _has_numeric_prefix(task.directory_name) else 1,
            task.numeric_prefix,
            task.directory_name,
        )
    )

    logger.info(f"Discovered {len(discovered_tasks)} task(s)")

    return discovered_tasks


def _discover_single_task(repo_root: Path, target_task_file: Path) -> list[DiscoveredTask]:
    """Discover a single specific task file.

    Args:
        repo_root: Absolute path to repository root
        target_task_file: Absolute path to target task file

    Returns:
        List containing single DiscoveredTask

    Raises:
        ValueError: If target_task_file is invalid or not found
    """
    if not target_task_file.exists():
        raise ValueError(f"Target task file does not exist: {target_task_file}")

    if not target_task_file.is_file():
        raise ValueError(f"Target task path is not a file: {target_task_file}")

    # Validate task file is under repo_root
    try:
        target_task_file.relative_to(repo_root)
    except ValueError as e:
        raise ValueError(
            f"Target task file must be under repo_root: "
            f"{target_task_file} not under {repo_root}"
        ) from e

    # Get spec directory (parent of task file)
    spec_dir_path = target_task_file.parent

    # Extract numeric prefix
    numeric_prefix = _extract_numeric_prefix(spec_dir_path.name)

    discovered_task = DiscoveredTask(
        file_path=str(target_task_file.resolve()),
        spec_dir=str(spec_dir_path.resolve()),
        numeric_prefix=numeric_prefix,
        directory_name=spec_dir_path.name,
    )

    logger.info(f"Discovered single task: {discovered_task.directory_name}")

    return [discovered_task]


def _extract_numeric_prefix(directory_name: str) -> int:
    """Extract numeric prefix from directory name.

    Matches pattern like "001-feature" and extracts 1 (as int).
    If no match, returns 0.

    Args:
        directory_name: Directory name to parse

    Returns:
        Numeric prefix as integer (0 if no prefix found)
    """
    match = NUMERIC_PREFIX_PATTERN.match(directory_name)
    if match:
        return int(match.group(1))
    return 0


def _has_numeric_prefix(directory_name: str) -> bool:
    """Return True if directory name starts with a numeric prefix."""
    return bool(NUMERIC_PREFIX_PATTERN.match(directory_name))
