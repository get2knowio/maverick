"""Workspace isolation package.

Provides :class:`WorkspaceManager` for creating and managing hidden jj
workspaces at ``~/.maverick/workspaces/<project>/``.
"""

from __future__ import annotations

from maverick.workspace.errors import (
    WorkspaceBootstrapError,
    WorkspaceCloneError,
    WorkspaceError,
    WorkspaceNotFoundError,
)
from maverick.workspace.manager import WorkspaceManager
from maverick.workspace.models import (
    BootstrapResult,
    SyncResult,
    TeardownResult,
    WorkspaceContext,
    WorkspaceInfo,
    WorkspaceState,
)

__all__ = [
    "BootstrapResult",
    "SyncResult",
    "TeardownResult",
    "WorkspaceBootstrapError",
    "WorkspaceCloneError",
    "WorkspaceContext",
    "WorkspaceError",
    "WorkspaceInfo",
    "WorkspaceManager",
    "WorkspaceNotFoundError",
    "WorkspaceState",
]
