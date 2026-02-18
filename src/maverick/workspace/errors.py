"""Workspace error hierarchy."""

from __future__ import annotations

from maverick.exceptions.base import MaverickError


class WorkspaceError(MaverickError):
    """Base exception for workspace operations.

    Attributes:
        workspace_path: Path to the workspace that experienced the error.
    """

    def __init__(
        self,
        message: str,
        *,
        workspace_path: str | None = None,
    ) -> None:
        self.workspace_path = workspace_path
        super().__init__(message)


class WorkspaceNotFoundError(WorkspaceError):
    """Workspace directory does not exist."""


class WorkspaceCloneError(WorkspaceError):
    """Failed to clone user repo into workspace."""


class WorkspaceBootstrapError(WorkspaceError):
    """Failed to run setup command in workspace."""
