"""Workspace lifecycle manager.

Creates, bootstraps, syncs, and tears down hidden jj workspaces at
``~/.maverick/workspaces/<project>/``.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from maverick.jj.client import JjClient
from maverick.jj.errors import JjError
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner
from maverick.workspace.errors import (
    WorkspaceBootstrapError,
    WorkspaceCloneError,
    WorkspaceError,
)
from maverick.workspace.models import (
    BootstrapResult,
    SyncResult,
    TeardownResult,
    WorkspaceInfo,
    WorkspaceState,
)

logger = get_logger(__name__)

#: Default root for workspace directories.
DEFAULT_WORKSPACE_ROOT = Path.home() / ".maverick" / "workspaces"

#: Metadata file written inside each workspace.
WORKSPACE_META_FILE = ".maverick-workspace.json"


class WorkspaceManager:
    """Manage the lifecycle of a hidden jj workspace.

    A workspace is a ``jj git clone`` of the user's repository stored
    under ``~/.maverick/workspaces/<project-name>/``.

    Args:
        user_repo_path: Absolute path to the user's git repository.
        workspace_root: Base directory for workspaces (default:
            ``~/.maverick/workspaces/``).
        setup_command: Optional shell command to run after cloning
            (e.g., ``"uv sync"``).
        teardown_command: Optional shell command to run before removal.

    Example:
        ```python
        mgr = WorkspaceManager(
            user_repo_path=Path("/home/user/project"),
            setup_command="uv sync",
        )
        info = await mgr.create_and_bootstrap()
        jj = mgr.get_jj_client()
        ```
    """

    def __init__(
        self,
        user_repo_path: Path,
        workspace_root: Path | None = None,
        setup_command: str | None = None,
        teardown_command: str | None = None,
    ) -> None:
        self._user_repo_path = user_repo_path.resolve()
        self._workspace_root = (workspace_root or DEFAULT_WORKSPACE_ROOT).resolve()
        self._setup_command = setup_command
        self._teardown_command = teardown_command
        self._project_name = self._user_repo_path.name

    # =====================================================================
    # Properties
    # =====================================================================

    @property
    def workspace_path(self) -> Path:
        """Absolute path to this project's workspace directory."""
        return self._workspace_root / self._project_name

    @property
    def exists(self) -> bool:
        """True if the workspace directory already exists."""
        return self.workspace_path.is_dir()

    @property
    def meta_path(self) -> Path:
        """Path to the workspace metadata file."""
        return self.workspace_path / WORKSPACE_META_FILE

    # =====================================================================
    # Lifecycle: create
    # =====================================================================

    async def create(self) -> WorkspaceInfo:
        """Clone the user's repo into the workspace via ``jj git clone``.

        Idempotent: if the workspace already exists and is healthy,
        returns its metadata without re-cloning.

        Returns:
            :class:`WorkspaceInfo` with the workspace path and state.

        Raises:
            WorkspaceCloneError: If the clone fails.
        """
        if self.exists and self.meta_path.exists():
            logger.info(
                "workspace_already_exists",
                workspace_path=str(self.workspace_path),
            )
            return self._read_meta()

        # Ensure parent directory exists
        self._workspace_root.mkdir(parents=True, exist_ok=True)

        # Clone via jj — use a temporary JjClient rooted at the parent
        # (jj git clone creates the target directory)
        client = JjClient(cwd=self._workspace_root)
        try:
            await client.git_clone(
                source=self._user_repo_path,
                target=self.workspace_path,
            )
        except JjError as e:
            raise WorkspaceCloneError(
                f"Failed to clone {self._user_repo_path} "
                f"into {self.workspace_path}: {e}",
                workspace_path=str(self.workspace_path),
            ) from e

        # Write metadata
        now = datetime.now(tz=UTC).isoformat()
        info = WorkspaceInfo(
            workspace_path=str(self.workspace_path),
            user_repo_path=str(self._user_repo_path),
            state=WorkspaceState.ACTIVE.value,
            created_at=now,
        )
        self._write_meta(info)

        logger.info(
            "workspace_created",
            workspace_path=str(self.workspace_path),
            user_repo_path=str(self._user_repo_path),
        )
        return info

    # =====================================================================
    # Lifecycle: bootstrap
    # =====================================================================

    async def bootstrap(self) -> BootstrapResult:
        """Run the setup command inside the workspace.

        Returns:
            :class:`BootstrapResult`.

        Raises:
            WorkspaceBootstrapError: If the setup command fails.
            WorkspaceError: If the workspace does not exist.
        """
        if not self.exists:
            raise WorkspaceError(
                "Cannot bootstrap: workspace does not exist. Run create() first.",
                workspace_path=str(self.workspace_path),
            )

        if not self._setup_command:
            logger.debug("workspace_bootstrap_skipped", reason="no setup command")
            return BootstrapResult(success=True, output="")

        runner = CommandRunner(cwd=self.workspace_path, timeout=600.0)
        parts = self._setup_command.split()
        result = await runner.run(parts, cwd=self.workspace_path)

        if not result.success:
            raise WorkspaceBootstrapError(
                f"Setup command failed: {self._setup_command}: {result.stderr.strip()}",
                workspace_path=str(self.workspace_path),
            )

        logger.info(
            "workspace_bootstrapped",
            command=self._setup_command,
            duration_ms=result.duration_ms,
        )
        return BootstrapResult(success=True, output=result.output)

    # =====================================================================
    # Lifecycle: create + bootstrap
    # =====================================================================

    async def create_and_bootstrap(self) -> WorkspaceInfo:
        """Create the workspace and run the setup command.

        Returns:
            :class:`WorkspaceInfo`.
        """
        info = await self.create()
        await self.bootstrap()
        return info

    # =====================================================================
    # Lifecycle: sync
    # =====================================================================

    async def sync_from_origin(self) -> SyncResult:
        """Fetch the latest changes from origin into the workspace.

        Returns:
            :class:`SyncResult`.

        Raises:
            WorkspaceError: If the workspace does not exist.
        """
        if not self.exists:
            raise WorkspaceError(
                "Cannot sync: workspace does not exist.",
                workspace_path=str(self.workspace_path),
            )

        client = self.get_jj_client()
        await client.git_fetch()
        logger.info("workspace_synced", workspace_path=str(self.workspace_path))
        return SyncResult(success=True)

    # =====================================================================
    # Lifecycle: teardown
    # =====================================================================

    async def teardown(self) -> TeardownResult:
        """Clean up and remove the workspace directory.

        Runs the teardown command (if configured) before removal.

        Returns:
            :class:`TeardownResult`.
        """
        if not self.exists:
            logger.debug("workspace_teardown_noop", reason="does not exist")
            return TeardownResult(success=True, removed=False)

        # Run teardown command if configured
        if self._teardown_command:
            runner = CommandRunner(cwd=self.workspace_path, timeout=300.0)
            parts = self._teardown_command.split()
            result = await runner.run(parts, cwd=self.workspace_path)
            if not result.success:
                logger.warning(
                    "workspace_teardown_command_failed",
                    command=self._teardown_command,
                    stderr=result.stderr.strip(),
                )

        # Remove the workspace directory
        shutil.rmtree(self.workspace_path, ignore_errors=True)
        logger.info(
            "workspace_torn_down",
            workspace_path=str(self.workspace_path),
        )
        return TeardownResult(success=True, removed=True)

    # =====================================================================
    # State management
    # =====================================================================

    def get_state(self) -> WorkspaceState | None:
        """Read the current workspace state from metadata.

        Returns:
            :class:`WorkspaceState`, or None if no metadata exists.
        """
        if not self.meta_path.exists():
            return None
        info = self._read_meta()
        return WorkspaceState(info.state)

    def set_state(self, state: WorkspaceState) -> None:
        """Update the workspace state in metadata.

        Args:
            state: New state to write.
        """
        info = self._read_meta()
        updated = WorkspaceInfo(
            workspace_path=info.workspace_path,
            user_repo_path=info.user_repo_path,
            state=state.value,
            created_at=info.created_at,
        )
        self._write_meta(updated)

    # =====================================================================
    # JjClient factory
    # =====================================================================

    def get_jj_client(self) -> JjClient:
        """Return a :class:`JjClient` configured for this workspace.

        Returns:
            JjClient with ``cwd`` set to the workspace path.
        """
        return JjClient(cwd=self.workspace_path)

    # =====================================================================
    # Internal helpers
    # =====================================================================

    def _write_meta(self, info: WorkspaceInfo) -> None:
        """Write workspace metadata to disk."""
        self.meta_path.write_text(json.dumps(info.to_dict(), indent=2) + "\n")

    def _read_meta(self) -> WorkspaceInfo:
        """Read workspace metadata from disk."""
        data = json.loads(self.meta_path.read_text())
        return WorkspaceInfo(
            workspace_path=data.get("workspace_path", str(self.workspace_path)),
            user_repo_path=data.get("user_repo_path", str(self._user_repo_path)),
            state=data.get("state", WorkspaceState.ACTIVE.value),
            created_at=data.get("created_at", ""),
        )
