"""Output formatting utilities for Maverick CLI.

This module defines output format options and formatting helpers for CLI commands.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

__all__ = [
    "OutputFormat",
    "format_error",
    "format_success",
    "format_warning",
    "format_json",
    "format_table",
]


class OutputFormat(str, Enum):
    """Supported output formats for CLI commands.

    Values:
        TUI: Interactive terminal UI (default when TTY available).
        JSON: Machine-readable JSON output.
        MARKDOWN: Formatted markdown for documentation.
        TEXT: Plain text output (default in non-TTY).
    """

    TUI = "tui"
    JSON = "json"
    MARKDOWN = "markdown"
    TEXT = "text"


def format_error(
    message: str, details: list[str] | None = None, suggestion: str | None = None
) -> str:
    """Format an error message with optional details and suggestion.

    Args:
        message: Primary error message.
        details: Optional list of detail lines to include.
        suggestion: Optional suggestion for resolving the error.

    Returns:
        Formatted error string with details and suggestion if provided.

    Example:
        >>> result = format_error(
        ...     "Failed to load config",
        ...     details=["File not found"],
        ...     suggestion="Run 'maverick init'"
        ... )
        >>> print(result)
        Error: Failed to load config
          File not found
        Suggestion: Run 'maverick init'
    """
    lines = [f"Error: {message}"]

    if details:
        for detail in details:
            lines.append(f"  {detail}")

    if suggestion:
        lines.append(f"Suggestion: {suggestion}")

    return "\n".join(lines)


def format_success(message: str) -> str:
    """Format a success message.

    Args:
        message: Success message to format.

    Returns:
        Formatted success string.

    Example:
        >>> format_success("Workflow completed")
        'Success: Workflow completed'
    """
    return f"Success: {message}"


def format_warning(message: str) -> str:
    """Format a warning message.

    Args:
        message: Warning message to format.

    Returns:
        Formatted warning string.

    Example:
        >>> format_warning("Config file not found, using defaults")
        'Warning: Config file not found, using defaults'
    """
    return f"Warning: {message}"


def format_json(data: Any) -> str:
    """Format data as indented JSON.

    Args:
        data: Any JSON-serializable data structure.

    Returns:
        Formatted JSON string with 2-space indentation.

    Raises:
        TypeError: If data is not JSON-serializable.

    Example:
        >>> format_json({"status": "success", "count": 3})
        '{\\n  "status": "success",\\n  "count": 3\\n}'
    """
    return json.dumps(data, indent=2)


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format data as a simple text table with pipe separators.

    Args:
        headers: Column headers.
        rows: Data rows, each row should have same length as headers.

    Returns:
        Formatted table string with columns separated by pipes.

    Example:
        >>> result = format_table(
        ...     ["Name", "Status"],
        ...     [["Task 1", "Done"], ["Task 2", "Pending"]]
        ... )
        >>> print(result)
        Name   | Status
        Task 1 | Done
        Task 2 | Pending
    """
    if not headers:
        return ""

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(cell))

    # Format rows
    lines = []

    # Header row
    header_parts = [h.ljust(col_widths[i]) for i, h in enumerate(headers)]
    lines.append(" | ".join(header_parts))

    # Data rows
    for row in rows:
        row_parts = [
            cell.ljust(col_widths[i]) if i < len(col_widths) else cell
            for i, cell in enumerate(row)
        ]
        lines.append(" | ".join(row_parts))

    return "\n".join(lines)
