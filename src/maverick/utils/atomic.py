"""Atomic file write utilities.

This module provides atomic file write operations using the atomicwrites library.
Atomic writes ensure files are either completely written or not modified at all,
preventing data corruption from crashes or interrupted writes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atomicwrites import atomic_write  # type: ignore[import-untyped]

__all__ = [
    "atomic_write_json",
    "atomic_write_text",
]


def atomic_write_text(
    path: Path | str,
    content: str,
    *,
    encoding: str = "utf-8",
    mkdir: bool = True,
) -> None:
    """Write text content to a file atomically.

    Writes to a temporary file first, then atomically renames it to the target path.
    If the write fails, the original file (if any) is left unchanged.

    Args:
        path: Destination file path (Path or str).
        content: Text content to write.
        encoding: Character encoding to use. Defaults to "utf-8".
        mkdir: If True, create parent directories if they don't exist.
            Defaults to True.

    Raises:
        OSError: If the write or rename operation fails.

    Example:
        >>> atomic_write_text("/path/to/file.txt", "Hello, world!")
        >>> atomic_write_text(Path("config.json"), '{"key": "value"}')
    """
    file_path = Path(path)

    if mkdir:
        file_path.parent.mkdir(parents=True, exist_ok=True)

    with atomic_write(str(file_path), mode="w", encoding=encoding, overwrite=True) as f:
        f.write(content)


def atomic_write_json(
    path: Path | str,
    data: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = False,
    encoding: str = "utf-8",
    mkdir: bool = True,
) -> None:
    """Write data as JSON to a file atomically.

    Serializes the data to JSON and writes it atomically. Uses atomic_write_text
    internally for the actual write operation.

    Args:
        path: Destination file path (Path or str).
        data: Data to serialize as JSON. Must be JSON-serializable.
        indent: Number of spaces for JSON indentation, or None for compact output.
            Defaults to 2.
        ensure_ascii: If True, escape non-ASCII characters. Defaults to False.
        encoding: Character encoding to use. Defaults to "utf-8".
        mkdir: If True, create parent directories if they don't exist.
            Defaults to True.

    Raises:
        OSError: If the write or rename operation fails.
        TypeError: If the data is not JSON-serializable.
        ValueError: If the data contains values that cannot be serialized.

    Example:
        >>> atomic_write_json("/path/to/data.json", {"key": "value"})
        >>> atomic_write_json(Path("config.json"), [1, 2, 3], indent=None)
    """
    content = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
    atomic_write_text(path, content, encoding=encoding, mkdir=mkdir)
