"""File path extraction utilities for Maverick.

This module provides functionality to extract file path references from text.
"""

from __future__ import annotations

import re

__all__ = [
    "extract_file_paths",
]


def extract_file_paths(text: str) -> list[str]:
    """Extract file path references from text.

    Looks for patterns like src/foo.py, ./bar/baz.ts, path/to/file.ext.
    Filters out common false positives like URLs and version numbers.

    Args:
        text: Text to scan for file paths.

    Returns:
        List of extracted file paths (deduplicated, order preserved).

    Example:
        >>> extract_file_paths("Check src/main.py and ./tests/test_main.py")
        ['src/main.py', './tests/test_main.py']
    """
    # Pattern matches paths with at least one directory separator and a file extension
    # Excludes URLs (http://, https://) and common false positives
    pattern = re.compile(
        r"(?<![:/])(?:\.?/)?(?:[\w.-]+/)+[\w.-]+\.(?:py|ts|js|tsx|jsx|rs|go|java|kt|rb|php|c|cpp|h|hpp|md|yaml|yml|json|toml|txt|sql|sh|bash)(?![/\w])",
        re.IGNORECASE,
    )

    matches = pattern.findall(text)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for match in matches:
        # Clean up leading ./ for consistency
        clean_path = match.lstrip("./") if match.startswith("./") else match
        if clean_path not in seen:
            seen.add(clean_path)
            result.append(match)

    return result
