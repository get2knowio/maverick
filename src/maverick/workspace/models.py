"""Typed models for workspace lifecycle results."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.jj.client import JjClient


class WorkspaceState(str, Enum):
    """Lifecycle state of a workspace.

    Attributes:
        ACTIVE: Workspace is in use by fly.
        EJECTED: User chose eject; workspace preserved for finalize.
        FINALIZED: Finalize completed; workspace may be cleaned up.
    """

    ACTIVE = "active"
    EJECTED = "ejected"
    FINALIZED = "finalized"


@dataclass(frozen=True, slots=True)
class WorkspaceInfo:
    """Metadata about a managed workspace.

    Attributes:
        workspace_path: Absolute path to the workspace directory.
        user_repo_path: Absolute path to the user's original repository.
        state: Current lifecycle state.
        created_at: ISO-8601 creation timestamp.
    """

    workspace_path: str
    user_repo_path: str
    state: str = WorkspaceState.ACTIVE.value
    created_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Result of running the workspace setup command.

    Attributes:
        success: True if the setup command succeeded.
        output: Combined stdout/stderr from the setup command.
    """

    success: bool = True
    output: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Result of syncing workspace from origin.

    Attributes:
        success: True if fetch succeeded.
    """

    success: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TeardownResult:
    """Result of workspace teardown.

    Attributes:
        success: True if cleanup completed.
        removed: True if the directory was removed.
    """

    success: bool = True
    removed: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    """Active workspace handle threaded through workflows.

    The canonical "where to operate" value. Replaces ad-hoc ``cwd`` strings
    so every action that touches state knows which repo it's targeting.
    Carries a JjClient factory so callers can run jj operations without
    re-resolving the workspace path.

    Attributes:
        path: Absolute path to the workspace directory.
        user_repo_path: Absolute path to the user's original repo.
        project_name: Project identifier (derived from user_repo_path.name).
        created: True if this attachment created a fresh workspace,
            False if it reused an existing one.
    """

    path: Path
    user_repo_path: Path
    project_name: str
    created: bool = False

    @property
    def cwd(self) -> Path:
        """Alias for ``path`` — the canonical cwd for actions."""
        return self.path

    def jj_client(self) -> JjClient:
        """Return a :class:`JjClient` rooted at this workspace.

        Importing JjClient lazily to avoid a circular import — workspace
        models are loaded by ``maverick.jj.repository``.
        """
        from maverick.jj.client import JjClient

        return JjClient(cwd=self.path)
