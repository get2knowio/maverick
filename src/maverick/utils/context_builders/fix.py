"""Fix context builder for Maverick agents.

This module provides the build_fix_context function which extracts validation
errors and provides surrounding source code context for fix agents.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

from maverick.logging import get_logger
from maverick.utils.files import _read_file_safely, truncate_file
from maverick.utils.secrets import detect_secrets

if TYPE_CHECKING:
    from maverick.runners.models import ValidationOutput

__all__ = [
    "build_fix_context",
]

logger = get_logger(__name__)

# Type alias for context dictionaries
ContextDict: TypeAlias = dict[str, Any]

# Default values
DEFAULT_CONTEXT_LINES = 10


def build_fix_context(
    validation_output: ValidationOutput,
    files: list[Path],
    *,
    context_lines: int = DEFAULT_CONTEXT_LINES,
) -> ContextDict:
    """Build context for fix agents.

    Extracts validation errors and provides surrounding source code context
    around each error location.

    Args:
        validation_output: ValidationOutput containing error information.
        files: List of file paths to include source context for.
        context_lines: Lines of context around each error (default 10).

    Returns:
        ContextDict with keys:
        - errors: List of error dicts with file, line, message, severity, code
        - source_files: Dict mapping file paths to truncated content with context
        - error_summary: Human-readable summary (e.g., "3 errors in 2 files")
        - _metadata: TruncationMetadata with truncation info

    Raises:
        No exceptions are raised; missing files are handled gracefully.

    Note:
        File I/O errors return empty content with appropriate metadata.

    Example:
        >>> ctx = build_fix_context(validation_result, [Path("src/main.py")])
        >>> ctx['error_summary']
        '3 errors in 2 files'
    """
    truncated = False
    sections_affected: list[str] = []
    original_lines = 0
    kept_lines = 0

    # Extract errors from validation output
    errors: list[dict[str, Any]] = []
    error_lines_by_file: dict[str, list[int]] = {}

    for stage in validation_output.stages:
        for error in stage.errors:
            errors.append(
                {
                    "file": error.file,
                    "line": error.line,
                    "message": error.message,
                    "severity": error.severity or "error",
                    "code": error.code,
                }
            )
            # Track error lines per file
            if error.file not in error_lines_by_file:
                error_lines_by_file[error.file] = []
            error_lines_by_file[error.file].append(error.line)

    # Read source files with context around errors
    source_files: dict[str, str] = {}
    for file_path in files:
        if not file_path.exists():
            continue

        content, _ = _read_file_safely(file_path)
        if not content:
            continue

        file_str = str(file_path)
        error_lines = error_lines_by_file.get(file_str, [])

        # If this file has errors, truncate around them
        if error_lines:
            content_lines = content.count("\n") + 1
            original_lines += content_lines
            # Calculate reasonable budget: each error line gets context + some padding
            max_lines_budget = len(error_lines) * (context_lines * 2 + 5)
            truncated_content = truncate_file(
                content,
                max_lines=max_lines_budget,
                around_lines=error_lines,
                context_lines=context_lines,
            )
            truncated_lines = truncated_content.count("\n") + 1
            kept_lines += truncated_lines
            if truncated_lines < content_lines:
                truncated = True
                if "source_files" not in sections_affected:
                    sections_affected.append("source_files")
            source_files[file_str] = truncated_content
        else:
            # No errors in this file - include full content up to limit
            content_lines = content.count("\n") + 1
            original_lines += content_lines
            kept_lines += content_lines
            source_files[file_str] = content

    # Check for secrets in source files
    for file_str, content in source_files.items():
        secrets = detect_secrets(content)
        for line_num, pattern in secrets:
            logger.warning(
                "Potential secret detected in %s at line %d: %s pattern",
                file_str,
                line_num,
                pattern,
            )

    # Generate error summary
    error_count = len(errors)
    file_count = len({e["file"] for e in errors})
    if error_count == 0:
        error_summary = "No errors"
    elif error_count == 1:
        error_summary = "1 error in 1 file"
    elif file_count == 1:
        error_summary = f"{error_count} errors in 1 file"
    else:
        error_summary = f"{error_count} errors in {file_count} files"

    return {
        "errors": errors,
        "source_files": source_files,
        "error_summary": error_summary,
        "_metadata": {
            "truncated": truncated,
            "original_lines": original_lines,
            "kept_lines": kept_lines,
            "sections_affected": sections_affected,
        },
    }
