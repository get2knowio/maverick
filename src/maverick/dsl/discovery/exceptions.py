"""Discovery exceptions for workflow discovery.

This module implements the exception types defined in the discovery contract.
"""

from __future__ import annotations

from pathlib import Path


class WorkflowDiscoveryError(Exception):
    """Base exception for discovery errors."""

    pass


class WorkflowConflictError(WorkflowDiscoveryError):
    """Raised when multiple workflows share name at same precedence level.

    Attributes:
        name: The conflicting workflow name.
        source: The precedence level where conflict occurred.
        conflicting_paths: Paths of the conflicting files.
    """

    def __init__(
        self,
        name: str,
        source: str,
        conflicting_paths: tuple[Path, ...],
    ) -> None:
        """Initialize workflow conflict error.

        Args:
            name: The conflicting workflow name.
            source: The precedence level where conflict occurred.
            conflicting_paths: Paths of the conflicting files.
        """
        self.name = name
        self.source = source
        self.conflicting_paths = conflicting_paths
        paths_str = ", ".join(str(p) for p in conflicting_paths)
        message = f"Multiple workflows named '{name}' at {source} level: {paths_str}"
        super().__init__(message)
