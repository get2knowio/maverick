"""Project type detection module for maverick init.

This module provides functions to detect project type using marker files
and optionally Claude AI for enhanced detection. It supports Python, Node.js,
Go, Rust, and Ansible projects.

Usage:
    from maverick.init.detector import detect_project_type, find_marker_files

    # Detect with Claude AI
    result = await detect_project_type(Path.cwd())
    print(f"Detected: {result.primary_type.value}")

    # Marker-only detection (no API call)
    result = await detect_project_type(Path.cwd(), use_claude=False)
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query

from maverick.constants import CLAUDE_HAIKU_LATEST
from maverick.exceptions.init import DetectionError
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

#: Default model for project detection (use Haiku for speed/cost)
DEFAULT_DETECTION_MODEL = CLAUDE_HAIKU_LATEST

#: Maximum content length to read from marker files
MAX_CONTENT_LENGTH = 2000

#: Maximum tree depth for directory listing
MAX_TREE_DEPTH = 3

#: Maximum marker file search depth
MAX_MARKER_DEPTH = 2

#: Detection prompt template
DETECTION_PROMPT = """\
Analyze this project and identify the project type.

{context}

Return a JSON object with:
- "primary_type": one of python, nodejs, go, rust, ansible_collection, \
ansible_playbook, unknown
- "detected_types": list of all detected types
- "confidence": "high", "medium", or "low"
- "findings": list of evidence strings (e.g., "pyproject.toml found at root")

Return ONLY the JSON object, no additional text."""

#: System prompt for detection
DETECTION_SYSTEM_PROMPT = """\
You are a project type analyzer. Given information about a project's \
structure and configuration files, identify the primary project type.

Analyze marker files carefully:
- pyproject.toml, setup.py, requirements.txt -> Python
- package.json -> Node.js
- go.mod -> Go
- Cargo.toml -> Rust
- galaxy.yml -> Ansible Collection
- ansible.cfg, requirements.yml (without galaxy.yml) -> Ansible Playbook

Return your analysis as a single JSON object. Be concise and accurate."""


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
    """Build context string for Claude detection prompt.

    Constructs a formatted context string containing directory tree
    and marker file contents for Claude to analyze.

    Args:
        project_path: Path to project root.
        markers: Detected marker files.
        max_tree_depth: Directory tree depth.
        max_content_length: Max chars per marker file.

    Returns:
        Formatted context string for Claude.

    Example:
        markers = find_marker_files(Path.cwd())
        context = build_detection_context(Path.cwd(), markers)
        # Context includes directory tree and marker file contents
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
    use_claude: bool = True,
    override_type: ProjectType | None = None,
    model: str = DEFAULT_DETECTION_MODEL,
    timeout: float = 30.0,
) -> ProjectDetectionResult:
    """Detect project type using Claude or marker-based heuristics.

    Uses a combination of marker file detection and optionally Claude AI
    to determine the project type. When Claude is used, it provides more
    nuanced analysis and higher confidence scores.

    Args:
        project_path: Path to project root.
        use_claude: Use Claude for detection (False = marker-only).
        override_type: Force specific project type.
        model: Claude model for detection.
        timeout: Detection timeout in seconds.

    Returns:
        ProjectDetectionResult with detected type and findings.

    Raises:
        DetectionError: If detection fails completely.

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

    # Find marker files
    markers = find_marker_files(project_path)

    if use_claude:
        # Use Claude for detection
        return await _detect_with_claude(
            project_path=project_path,
            markers=markers,
            model=model,
            timeout=timeout,
        )
    else:
        # Marker-only detection
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
            validation_commands=ValidationCommands.for_project_type(
                ProjectType.UNKNOWN
            ),
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
    findings = tuple(
        f"{marker.file_name} found at {marker.file_path}" for marker in markers
    )

    return ProjectDetectionResult(
        primary_type=primary_type,
        detected_types=detected_types,
        confidence=confidence,
        findings=findings,
        markers=tuple(markers),
        validation_commands=ValidationCommands.for_project_type(primary_type),
        detection_method="markers",
    )


async def _detect_with_claude(
    project_path: Path,
    markers: list[ProjectMarker],
    model: str,
    timeout: float,
) -> ProjectDetectionResult:
    """Perform Claude-assisted detection.

    Uses Claude AI to analyze project structure and marker files
    for more accurate detection.

    Args:
        project_path: Path to project root.
        markers: Detected marker files.
        model: Claude model to use.
        timeout: Request timeout in seconds.

    Returns:
        ProjectDetectionResult with Claude-assisted detection.

    Raises:
        DetectionError: If Claude API call fails.
    """
    context = build_detection_context(project_path, markers)
    prompt = DETECTION_PROMPT.format(context=context)

    options = ClaudeAgentOptions(
        system_prompt=DETECTION_SYSTEM_PROMPT,
        model=model,
        max_turns=1,
        allowed_tools=[],
    )

    logger.info("Detecting project type with Claude model: %s", model)

    try:
        # Query Claude with timeout
        response_text = await asyncio.wait_for(
            _query_claude(prompt, options),
            timeout=timeout,
        )

        # Parse response
        result = _parse_detection_response(response_text, markers)
        return result

    except TimeoutError:
        logger.warning(
            "Claude detection timed out after %.1fs, falling back to markers",
            timeout,
        )
        return _detect_from_markers(markers)

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse Claude response as JSON: %s", e)
        # Fall back to marker detection
        return _detect_from_markers(markers)

    except Exception as e:
        logger.error("Claude detection failed: %s", e)
        raise DetectionError(
            f"Project type detection failed: {e}",
            claude_error=e,
        ) from e


async def _query_claude(prompt: str, options: ClaudeAgentOptions) -> str:
    """Query Claude and return text response.

    Args:
        prompt: User prompt.
        options: Claude agent options.

    Returns:
        Text response from Claude.
    """
    text_parts: list[str] = []

    async for message in query(prompt=prompt, options=options):
        # Extract text from AssistantMessage
        if type(message).__name__ == "AssistantMessage":
            text = _extract_text_from_message(message)
            if text:
                text_parts.append(text)

    return "\n".join(text_parts)


def _extract_text_from_message(message: Any) -> str:
    """Extract text content from a message.

    Args:
        message: Message object from Claude SDK.

    Returns:
        Extracted text content.
    """
    if hasattr(message, "content"):
        content = message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if hasattr(block, "text"):
                    parts.append(block.text)
                elif isinstance(block, str):
                    parts.append(block)
            return "".join(parts)
    return ""


def _parse_detection_response(
    response_text: str,
    markers: list[ProjectMarker],
) -> ProjectDetectionResult:
    """Parse Claude's detection response.

    Args:
        response_text: Raw response from Claude.
        markers: Original marker files.

    Returns:
        ProjectDetectionResult parsed from response.

    Raises:
        json.JSONDecodeError: If response is not valid JSON.
    """
    # Extract JSON from response (handle markdown code blocks)
    json_text = response_text.strip()

    # Remove markdown code block if present
    if json_text.startswith("```"):
        # Find the end of the code block
        lines = json_text.split("\n")
        start = 1  # Skip first line (```json or ```)
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        json_text = "\n".join(lines[start:end])

    # Parse JSON
    data = json.loads(json_text)

    # Extract primary type
    primary_type_str = data.get("primary_type", "unknown")
    primary_type = ProjectType.from_string(primary_type_str)

    # Extract detected types
    detected_type_strs = data.get("detected_types", [primary_type_str])
    detected_types = tuple(ProjectType.from_string(t) for t in detected_type_strs)

    # Extract confidence
    confidence_str = data.get("confidence", "low")
    confidence_map = {
        "high": DetectionConfidence.HIGH,
        "medium": DetectionConfidence.MEDIUM,
        "low": DetectionConfidence.LOW,
    }
    confidence = confidence_map.get(confidence_str.lower(), DetectionConfidence.LOW)

    # Extract findings
    findings = tuple(data.get("findings", []))

    return ProjectDetectionResult(
        primary_type=primary_type,
        detected_types=detected_types,
        confidence=confidence,
        findings=findings,
        markers=tuple(markers),
        validation_commands=ValidationCommands.for_project_type(primary_type),
        detection_method="claude",
    )
