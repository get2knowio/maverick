"""Project type detection module for maverick init.

This module detects project type from marker files (pyproject.toml,
package.json, go.mod, Cargo.toml, galaxy.yml, ansible.cfg, etc.).

The earlier Claude-assisted detection path was removed when Maverick
switched to a single OpenCode HTTP runtime substrate: detection runs
during ``maverick init`` before any actor pool exists, and the marker-
only path is reliable for every project type Maverick supports — adding
a server-spawn-shutdown to init for parity with markers added complexity
without improving outcomes.

Usage:
    from maverick.init.detector import detect_project_type, find_marker_files

    result = await detect_project_type(Path.cwd())
    print(f"Detected: {result.primary_type.value}")
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from maverick.init.models import (
    MARKER_FILE_MAP,
    DetectionConfidence,
    ProjectDetectionResult,
    ProjectMarker,
    ProjectType,
    ValidationCommands,
)
from maverick.logging import get_logger

__all__ = [
    "find_marker_files",
    "build_detection_context",
    "detect_project_type",
    "get_validation_commands",
]


# =============================================================================
# Module Logger
# =============================================================================

logger = get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

#: Maximum content length to read from marker files
MAX_CONTENT_LENGTH = 2000

#: Maximum tree depth for directory listing
MAX_TREE_DEPTH = 3

#: Maximum marker file search depth
MAX_MARKER_DEPTH = 2


# =============================================================================
# Public Functions
# =============================================================================


def find_marker_files(
    project_path: Path,
    max_depth: int = MAX_MARKER_DEPTH,
) -> list[ProjectMarker]:
    """Find project marker files in directory tree.

    Walks the directory tree up to max_depth and looks for known marker files
    that indicate project type (e.g., pyproject.toml, package.json).

    Args:
        project_path: Path to project root.
        max_depth: Maximum directory depth to search.

    Returns:
        List of ProjectMarker instances found, sorted by priority.

    Example:
        markers = find_marker_files(Path.cwd())
        for marker in markers:
            print(f"{marker.file_name}: {marker.project_type.value}")
    """
    markers: list[ProjectMarker] = []

    if not project_path.exists():
        logger.warning("Project path does not exist: %s", project_path)
        return markers

    if not project_path.is_dir():
        logger.warning("Project path is not a directory: %s", project_path)
        return markers

    # Walk directory tree up to max_depth
    for current_dir, _, files in _walk_with_depth(project_path, max_depth):
        for file_name in files:
            if file_name not in MARKER_FILE_MAP:
                continue

            project_type, priority = MARKER_FILE_MAP[file_name]
            file_path = current_dir / file_name

            # Read content (truncated)
            content = _read_file_content(file_path, MAX_CONTENT_LENGTH)

            marker = ProjectMarker(
                file_name=file_name,
                file_path=str(file_path),
                project_type=project_type,
                content=content,
                priority=priority,
            )
            markers.append(marker)

    # Sort by priority (lower = higher priority)
    markers.sort(key=lambda m: m.priority)

    logger.debug(
        "Found %d marker files in %s",
        len(markers),
        project_path,
    )

    return markers


def build_detection_context(
    project_path: Path,
    markers: list[ProjectMarker],
    *,
    max_tree_depth: int = MAX_TREE_DEPTH,
    max_content_length: int = MAX_CONTENT_LENGTH,
) -> str:
    """Build a human-readable context string describing a project.

    Constructs a formatted string containing the directory tree and marker
    file contents. Originally consumed by the (now removed) Claude-assisted
    detection path; retained because it's still useful for verbose ``init``
    output, debugging, and diagnostics.

    Args:
        project_path: Path to project root.
        markers: Detected marker files.
        max_tree_depth: Directory tree depth.
        max_content_length: Max chars per marker file.

    Returns:
        Formatted context string.
    """
    sections: list[str] = []

    # Add project info
    sections.append(f"# Project: {project_path.name}")
    sections.append(f"Path: {project_path}")
    sections.append("")

    # Add directory tree
    tree = _generate_tree(project_path, max_tree_depth)
    sections.append("## Directory Structure")
    sections.append("```")
    sections.append(tree)
    sections.append("```")
    sections.append("")

    # Add marker files with contents
    if markers:
        sections.append("## Detected Marker Files")
        sections.append("")

        for marker in markers:
            sections.append(f"### {marker.file_name}")
            sections.append(f"Path: {marker.file_path}")
            sections.append(f"Project Type: {marker.project_type.value}")
            sections.append("")

            if marker.content:
                # Truncate content if needed
                content = marker.content
                if len(content) > max_content_length:
                    content = content[:max_content_length] + "\n... [truncated]"

                sections.append("```")
                sections.append(content)
                sections.append("```")
            else:
                sections.append("(empty or unreadable)")
            sections.append("")

    return "\n".join(sections)


async def detect_project_type(
    project_path: Path,
    *,
    override_type: ProjectType | None = None,
) -> ProjectDetectionResult:
    """Detect project type from marker files.

    Walks the project tree, finds known marker files, and applies a
    priority-weighted scoring heuristic to choose a primary project type.

    Note: this function is ``async`` for historical reasons — earlier
    versions called the Claude SDK. It performs no I/O concurrency today
    and is safe to call from any async context.

    Args:
        project_path: Path to project root.
        override_type: Force specific project type (skip detection).

    Returns:
        ProjectDetectionResult with detected type and findings.

    Example:
        result = await detect_project_type(Path.cwd())
        print(f"Detected: {result.primary_type.value}")
        for finding in result.findings:
            print(f"  - {finding}")
    """
    # Handle override case - return immediately
    if override_type is not None:
        logger.info("Using override project type: %s", override_type.value)
        return ProjectDetectionResult(
            primary_type=override_type,
            detected_types=(override_type,),
            confidence=DetectionConfidence.HIGH,
            findings=(f"Project type manually set to {override_type.value}",),
            markers=(),
            validation_commands=ValidationCommands.for_project_type(override_type),
            detection_method="override",
        )

    # Find marker files and apply heuristics
    markers = find_marker_files(project_path)
    return _detect_from_markers(markers)


def get_validation_commands(project_type: ProjectType) -> ValidationCommands:
    """Get default validation commands for project type.

    This is a thin wrapper around ValidationCommands.for_project_type()
    for convenience and API consistency.

    Args:
        project_type: Detected or overridden project type.

    Returns:
        ValidationCommands with appropriate defaults.

    Example:
        commands = get_validation_commands(ProjectType.PYTHON)
        print(commands.format_cmd)  # ('ruff', 'format', '.')
    """
    return ValidationCommands.for_project_type(project_type)


# =============================================================================
# Private Functions
# =============================================================================


def _walk_with_depth(
    root: Path,
    max_depth: int,
) -> list[tuple[Path, list[str], list[str]]]:
    """Walk directory tree with depth limit.

    Args:
        root: Root directory to start walking.
        max_depth: Maximum depth to walk (0 = root only).

    Returns:
        List of (dirpath, dirnames, filenames) tuples.
    """
    result: list[tuple[Path, list[str], list[str]]] = []

    def _walk_recursive(current: Path, depth: int) -> None:
        if depth > max_depth:
            return

        try:
            entries = list(current.iterdir())
        except PermissionError:
            logger.debug("Permission denied: %s", current)
            return
        except OSError as e:
            logger.debug("Error reading directory %s: %s", current, e)
            return

        dirs: list[str] = []
        files: list[str] = []

        for entry in entries:
            # Skip hidden files/directories
            if entry.name.startswith("."):
                continue

            if entry.is_dir():
                dirs.append(entry.name)
            elif entry.is_file():
                files.append(entry.name)

        result.append((current, dirs, files))

        # Recurse into subdirectories
        for dir_name in dirs:
            _walk_recursive(current / dir_name, depth + 1)

    _walk_recursive(root, 0)
    return result


def _read_file_content(path: Path, max_length: int) -> str | None:
    """Read file content, truncated to max_length.

    Args:
        path: Path to file.
        max_length: Maximum content length.

    Returns:
        File content (truncated), or None if unreadable.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_length:
            content = content[:max_length]
        return content
    except (OSError, PermissionError) as e:
        logger.debug("Could not read file %s: %s", path, e)
        return None


def _generate_tree(root: Path, max_depth: int) -> str:
    """Generate a text-based directory tree.

    Args:
        root: Root directory.
        max_depth: Maximum depth to display.

    Returns:
        Text representation of directory tree.
    """
    lines: list[str] = [root.name + "/"]

    def _add_entries(current: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return

        try:
            entries = sorted(
                [e for e in current.iterdir() if not e.name.startswith(".")],
                key=lambda e: (e.is_file(), e.name.lower()),
            )
        except (PermissionError, OSError):
            return

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "`-- " if is_last else "|-- "
            extension = "    " if is_last else "|   "

            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                if depth < max_depth:
                    _add_entries(entry, prefix + extension, depth + 1)
            else:
                lines.append(f"{prefix}{connector}{entry.name}")

    _add_entries(root, "", 0)
    return "\n".join(lines)


def _detect_from_markers(markers: list[ProjectMarker]) -> ProjectDetectionResult:
    """Perform marker-only detection.

    Uses heuristics based on marker files to determine project type.

    Args:
        markers: List of detected marker files.

    Returns:
        ProjectDetectionResult with marker-based detection.
    """
    if not markers:
        return ProjectDetectionResult(
            primary_type=ProjectType.UNKNOWN,
            detected_types=(ProjectType.UNKNOWN,),
            confidence=DetectionConfidence.LOW,
            findings=("No marker files found",),
            markers=(),
            validation_commands=ValidationCommands.for_project_type(ProjectType.UNKNOWN),
            detection_method="markers",
        )

    # Count types by priority-weighted frequency
    type_scores: Counter[ProjectType] = Counter()
    for marker in markers:
        # Lower priority = higher score contribution
        score = 10 - min(marker.priority, 9)
        type_scores[marker.project_type] += score

    # Get all detected types
    detected_types = tuple(type_scores.keys())

    # Primary type is the one with highest score
    primary_type = type_scores.most_common(1)[0][0]

    # Determine confidence
    if len(type_scores) == 1:
        confidence = DetectionConfidence.HIGH
    elif type_scores.most_common(1)[0][1] > type_scores.most_common(2)[1][1] * 2:
        # Primary has more than 2x the score of second place
        confidence = DetectionConfidence.MEDIUM
    else:
        confidence = DetectionConfidence.LOW

    # Build findings
    findings = tuple(f"{marker.file_name} found at {marker.file_path}" for marker in markers)

    return ProjectDetectionResult(
        primary_type=primary_type,
        detected_types=detected_types,
        confidence=confidence,
        findings=findings,
        markers=tuple(markers),
        validation_commands=ValidationCommands.for_project_type(primary_type),
        detection_method="markers",
    )
