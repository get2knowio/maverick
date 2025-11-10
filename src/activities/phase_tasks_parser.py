"""Temporal activity for parsing Speckit tasks.md documents.

This module provides a Temporal activity for parsing task markdown files
into structured phase definitions. It supports both file-based and inline
content parsing, and computes a hash for change detection.

Key Features:
    - Parse tasks.md from file path or inline content
    - Extract phase definitions with task lists
    - Compute content hash for change detection
    - Validate input parameters and file existence
    - Structured logging for observability

Logging Events (structured logger):
    - parse_started: Activity begins parsing tasks.md
    - parse_completed: Successfully parsed phases from tasks.md (includes phase_count)

Error Handling:
    - FileNotFoundError: If tasks_md_path doesn't exist
    - ValueError: If both or neither of path/content provided
    - ValueError: If path is not absolute
    - Parsing errors propagate from parse_tasks_markdown utility

Examples:
    Parse from file:
    >>> request = ParseTasksMdRequest(tasks_md_path="/workspace/tasks.md")
    >>> result = await parse_tasks_md(request)
    >>> print(f"Found {len(result.phases)} phases")

    Parse from inline content:
    >>> request = ParseTasksMdRequest(tasks_md_content="# Phase 1\\n- Task 1")
    >>> result = await parse_tasks_md(request)
    >>> print(result.tasks_md_hash)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from temporalio import activity

from src.models.phase_automation import PhaseDefinition
from src.utils.logging import get_structured_logger
from src.utils.tasks_markdown import compute_tasks_md_hash, parse_tasks_markdown


logger = get_structured_logger("activity.parse_tasks_md")


@dataclass(frozen=True)
class ParseTasksMdRequest:
    """Input parameters for parsing a tasks.md document.
    
    Exactly one of tasks_md_path or tasks_md_content must be provided.
    
    Attributes:
        tasks_md_path: Absolute path to tasks.md file (mutually exclusive with tasks_md_content)
        tasks_md_content: Inline tasks.md content (mutually exclusive with tasks_md_path)
        
    Invariants:
        - Exactly one of tasks_md_path or tasks_md_content must be non-None
        - If tasks_md_path is provided, it must be an absolute path
        - Path is normalized to string representation
    """

    tasks_md_path: str | Path | None = None
    tasks_md_content: str | None = None

    def __post_init__(self) -> None:
        """Validate input parameters and normalize paths."""
        has_path = self.tasks_md_path is not None
        has_content = self.tasks_md_content is not None
        if has_path == has_content:
            raise ValueError("Provide either tasks_md_path or tasks_md_content")

        if has_path:
            raw_path = Path(self.tasks_md_path or "")
            if not raw_path.is_absolute():
                raise ValueError("tasks_md_path must be absolute")
            object.__setattr__(self, "tasks_md_path", str(raw_path))


@dataclass(frozen=True)
class ParseTasksMdResult:
    """Parsed representation of a tasks.md document.
    
    Contains the parsed phase definitions, original content, and a hash for
    change detection.
    
    Attributes:
        source_path: Absolute path to source file (None if parsed from inline content)
        source_content: Full content of the tasks.md document
        tasks_md_hash: SHA-256 hash of source_content for change detection
        phases: Sequence of PhaseDefinition objects extracted from the document
        
    Invariants:
        - source_content must be non-empty
        - tasks_md_hash must be non-empty
        - source_path normalized to string if provided
        - phases converted to immutable tuple
    """

    source_path: str | None
    source_content: str
    tasks_md_hash: str
    phases: Sequence[PhaseDefinition]

    def __post_init__(self) -> None:
        """Validate result and normalize mutable fields."""
        if not self.source_content:
            raise ValueError("source_content must be non-empty")
        if not self.tasks_md_hash:
            raise ValueError("tasks_md_hash must be non-empty")
        if self.source_path is not None:
            object.__setattr__(self, "source_path", str(self.source_path))
        object.__setattr__(self, "phases", tuple(self.phases))


@activity.defn(name="parse_tasks_md")
async def parse_tasks_md(request: ParseTasksMdRequest) -> ParseTasksMdResult:
    """Parse Speckit tasks markdown into structured phase definitions.
    
    This activity reads a tasks.md file (or inline content) and extracts
    phase definitions using the tasks_markdown utility. It computes a hash
    of the content for change detection and validation.
    
    Args:
        request: ParseTasksMdRequest with either tasks_md_path or tasks_md_content
        
    Returns:
        ParseTasksMdResult containing:
            - source_path: Original file path (if file-based parsing)
            - source_content: Full tasks.md content
            - tasks_md_hash: SHA-256 hash for change detection
            - phases: Sequence of PhaseDefinition objects
            
    Raises:
        FileNotFoundError: If tasks_md_path doesn't exist
        ValueError: If request validation fails (neither/both path and content)
        
    Logging:
        - Emits "parse_started" with source type (path/content)
        - Emits "parse_completed" with phase_count and source type
        
    Examples:
        >>> request = ParseTasksMdRequest(tasks_md_path="/workspace/tasks.md")
        >>> result = await parse_tasks_md(request)
        >>> print(f"Parsed {len(result.phases)} phases")
        >>> print(f"Content hash: {result.tasks_md_hash}")
    """

    logger.info(
        "parse_started",
        source="path" if request.tasks_md_path else "content",
    )

    if request.tasks_md_path is not None:
        path = Path(request.tasks_md_path)
        if not path.exists():
            raise FileNotFoundError(f"tasks.md path does not exist: {path}")
        content = path.read_text(encoding="utf-8")
        source_path = str(path)
    else:
        content = request.tasks_md_content or ""
        source_path = None

    phases = parse_tasks_markdown(content)
    tasks_md_hash = compute_tasks_md_hash(content)

    logger.info(
        "parse_completed",
        phase_count=len(phases),
        source="path" if source_path else "content",
    )

    return ParseTasksMdResult(
        source_path=source_path,
        source_content=content,
        tasks_md_hash=tasks_md_hash,
        phases=phases,
    )


__all__ = ["ParseTasksMdRequest", "ParseTasksMdResult", "parse_tasks_md"]
