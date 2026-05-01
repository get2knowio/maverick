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
    WorkspaceContext,
    WorkspaceInfo,
    WorkspaceState,
)

logger = get_logger(__name__)

#: Default root for workspace directories.
DEFAULT_WORKSPACE_ROOT = Path.home() / ".maverick" / "workspaces"

#: Metadata file written inside each workspace.
WORKSPACE_META_FILE = ".maverick-workspace.json"

#: Marker file written in the user repo pointing to its workspace.
#: Per-checkout state, gitignored. Lets two clones of the same project at
#: different paths attach to distinct workspaces (otherwise both would hash
#: to ``~/.maverick/workspaces/<project>/``).
USER_REPO_MARKER_FILE = ".maverick/workspace.json"


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
                f"Failed to clone {self._user_repo_path} into {self.workspace_path}: {e}",
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
        await self._bootstrap_beads()
        await self.bootstrap()
        return info

    # =====================================================================
    # Lifecycle: find_or_create (Architecture A entry point)
    # =====================================================================

    async def find_or_create(self) -> WorkspaceContext:
        """Locate an existing workspace for this project, or create one.

        The canonical entry point under Architecture A: every workflow
        that needs to operate on the project (plan, refuel, fly) calls
        this to get a :class:`WorkspaceContext` and threads it through
        every action.

        - If a workspace exists at the expected path, returns a context
          attached to it (``created=False``).
        - Otherwise, clones the user repo, bootstraps bd, runs the setup
          command, propagates git identity, and writes the user-repo
          marker file. Returns a context with ``created=True``.

        The marker file at ``<user_repo>/.maverick/workspace.json``
        records which workspace this checkout is bound to. Reading the
        marker is best-effort — if it is missing or stale, attachment
        falls back to the deterministic ``~/.maverick/workspaces/<name>/``
        location.

        Returns:
            :class:`WorkspaceContext` with ``path`` set to the workspace
            and ``created`` indicating whether a clone was performed.

        Raises:
            WorkspaceCloneError: If creation is required and clone fails.
            WorkspaceBootstrapError: If the optional setup command fails.
        """
        already_exists = self.exists and self.meta_path.exists()
        if not already_exists:
            await self.create_and_bootstrap()
            await self._propagate_git_identity()
            self._write_user_repo_marker()
        else:
            # Attaching to an existing workspace — pull in any user-repo
            # edits so this command sees the latest state. Best-effort:
            # if fetch fails (network, no remote), the command can still
            # proceed against whatever state is in the workspace.
            try:
                await self.sync_from_origin()
            except (WorkspaceError, JjError) as exc:
                logger.warning(
                    "workspace_sync_failed_on_attach",
                    workspace_path=str(self.workspace_path),
                    error=str(exc),
                )

        return WorkspaceContext(
            path=self.workspace_path,
            user_repo_path=self._user_repo_path,
            project_name=self._project_name,
            created=not already_exists,
        )

    async def finalize(
        self,
        message: str,
        *,
        teardown: bool = True,
        bookmark: str | None = None,
    ) -> None:
        """Commit, push, merge into user repo, then (optionally) tear down.

        The exit ramp for hermetic commands (``plan``, ``refuel``):

        1. Snapshot any uncommitted work in the workspace as a single
           commit with *message* (via :func:`jj_snapshot_changes`).
        2. Set a temporary bookmark on the snapshot commit and push it
           to the user repo via ``jj git push``.
        3. Apply that bookmark to the user repo's current branch
           (jj-native rebase if colocated, ``git merge`` otherwise).
        4. Delete the temporary bookmark.
        5. Tear down the workspace (unless *teardown* is False).

        Push or merge failures preserve the workspace so the user can
        recover manually (``cd ~/.maverick/workspaces/<project>`` then
        ``jj git push`` / ``git merge maverick/<project>``).

        Args:
            message: Commit description for the snapshot.
            teardown: If False, skip the workspace removal. Useful for
                callers that want to chain more work, e.g. tests.
            bookmark: Bookmark name used for the round-trip. Defaults
                to ``maverick/<project>`` so it never collides with the
                user's own branches.

        Raises:
            WorkspaceError: If snapshot, push, or merge fails. The
                workspace is preserved on failure.
        """
        from maverick.library.actions.jj import jj_snapshot_changes

        bookmark_name = bookmark or f"maverick/{self._project_name}"

        # 1 — snapshot the workspace working copy
        snap = await jj_snapshot_changes(message=message, cwd=self.workspace_path)
        if not snap.success:
            raise WorkspaceError(
                f"workspace finalize: snapshot failed: {snap.error}",
                workspace_path=str(self.workspace_path),
            )
        if not snap.committed:
            # Nothing to push and no bookmark to clean up. Skip merge,
            # honour teardown so callers don't end up with a stale
            # workspace just because the command was a no-op.
            logger.debug(
                "workspace_finalize_noop",
                workspace_path=str(self.workspace_path),
            )
            if teardown:
                await self.teardown()
            return

        # 2 — push to user repo on a maverick-owned bookmark
        client = self.get_jj_client()
        try:
            await client.bookmark_set(bookmark_name, revision="@-")
            await client.git_push(bookmark=bookmark_name)
        except JjError as exc:
            raise WorkspaceError(
                f"workspace finalize: push failed: {exc}",
                workspace_path=str(self.workspace_path),
            ) from exc

        # 3 — apply the bookmark in the user's current branch
        ok, error = await self.apply_to_user_repo(bookmark_name)
        if not ok:
            raise WorkspaceError(
                f"workspace finalize: apply to user repo failed: {error}",
                workspace_path=str(self.workspace_path),
            )

        # 4 — delete the temporary bookmark in the user repo
        await self.cleanup_user_repo_branch(bookmark_name)

        # 5 — tear down the workspace
        if teardown:
            await self.teardown()

    # =====================================================================
    # User-repo bridging (workspace → user repo apply)
    # =====================================================================

    async def apply_to_user_repo(
        self,
        bookmark_name: str,
    ) -> tuple[bool, str | None]:
        """Apply a workspace-pushed bookmark to the user repo's current branch.

        The single canonical bridge from workspace state to user-repo
        state. Picks the right tool for the user's repo:

        - **Colocated jj** (``.jj/`` exists alongside ``.git/``): use
          ``jj rebase`` so the user repo's jj op log records the
          integration and stays in sync with git.
        - **Plain git only**: use ``git merge``. There is no jj layer
          in the user repo to keep in sync.

        Args:
            bookmark_name: Branch that was pushed from the workspace.

        Returns:
            ``(ok, error)`` — ``error`` is ``None`` on success.
        """
        repo_path = self._user_repo_path
        if (repo_path / ".jj").is_dir():
            try:
                client = JjClient(cwd=repo_path)
                # Bring the bookmark into jj's view (the git push set
                # the git ref but jj's bookmark store needs a fetch to
                # see it).
                try:
                    await client.git_fetch()
                except JjError:
                    pass
                await client.rebase(revision="@", destination=bookmark_name)
                return True, None
            except Exception as exc:  # noqa: BLE001 — surface as caller error
                return False, str(exc)

        from maverick.library.actions.git import git_merge

        merge_result = await git_merge(bookmark_name, cwd=repo_path)
        if merge_result.success:
            return True, None
        return False, merge_result.error

    async def cleanup_user_repo_branch(self, bookmark_name: str) -> None:
        """Best-effort delete of a temporary branch from the user repo.

        Same colocation logic as :meth:`apply_to_user_repo`: jj if
        available, git otherwise. Failure is logged but never raises.
        """
        runner = CommandRunner(timeout=30.0)
        repo_path = self._user_repo_path
        if (repo_path / ".jj").is_dir():
            try:
                await runner.run(
                    ["jj", "bookmark", "delete", bookmark_name],
                    cwd=repo_path,
                )
                return
            except Exception:
                logger.debug("jj_bookmark_delete_failed", branch=bookmark_name)
                # Fall through to git as a backup.

        try:
            await runner.run(
                ["git", "branch", "-d", bookmark_name],
                cwd=repo_path,
            )
        except Exception:
            logger.debug("branch_cleanup_failed", branch=bookmark_name)

    def context(self) -> WorkspaceContext | None:
        """Return a context for an existing workspace, or None.

        Read-only attach: does not create or bootstrap. Use this when a
        command (e.g. ``maverick brief``) wants to inspect workspace
        state without committing to a write path.
        """
        if not self.exists:
            return None
        return WorkspaceContext(
            path=self.workspace_path,
            user_repo_path=self._user_repo_path,
            project_name=self._project_name,
            created=False,
        )

    # =====================================================================
    # User-repo marker file (per-checkout binding)
    # =====================================================================

    @property
    def user_repo_marker_path(self) -> Path:
        """Path to the marker file in the user repo."""
        return self._user_repo_path / USER_REPO_MARKER_FILE

    def _write_user_repo_marker(self) -> None:
        """Persist the workspace path to the user repo's marker file.

        Best-effort — failure is logged but does not abort the create
        flow. Worst case is the next command rediscovers the workspace
        via the deterministic path.
        """
        marker = self.user_repo_marker_path
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(
                json.dumps(
                    {
                        "workspace_path": str(self.workspace_path),
                        "project_name": self._project_name,
                    },
                    indent=2,
                )
                + "\n"
            )
        except OSError as exc:
            logger.warning(
                "user_repo_marker_write_failed",
                marker=str(marker),
                error=str(exc),
            )

    async def _propagate_git_identity(self) -> None:
        """Copy git user.name / user.email from user repo into workspace.

        Mirrors the helper in ``actions/workspace.py`` so ``find_or_create``
        is a drop-in replacement for the legacy two-step flow.
        """
        runner = CommandRunner(timeout=10.0)
        for key in ("user.name", "user.email"):
            try:
                result = await runner.run(
                    ["git", "config", key],
                    cwd=self._user_repo_path,
                )
            except OSError as exc:
                logger.debug("git_identity_read_failed", key=key, error=str(exc))
                continue
            value = result.stdout.strip()
            if not value:
                continue
            try:
                await runner.run(
                    ["jj", "config", "set", "--repo", key, value],
                    cwd=self.workspace_path,
                )
            except OSError as exc:
                logger.debug("jj_identity_write_failed", key=key, error=str(exc))

    async def _bootstrap_beads(self) -> None:
        """Materialize bd's local Dolt database from the cloned ``.beads/issues.jsonl``.

        ``jj git clone`` brings over committed files, so the workspace
        gets ``.beads/issues.jsonl`` (which the user's repo tracks) but
        not the dolt working directory (which is gitignored). Without
        this step bd queries inside the workspace see an empty issue
        index — fly's "create review bead" path then fails with
        ``parent issue <epic> not found`` because it can't see the epic
        the user just created.

        ``init_or_bootstrap`` is idempotent: if bd is already initialized
        it returns SKIP. So this is safe to call on every workspace
        create, including re-runs.

        Best-effort: a bd hiccup shouldn't block fly entirely. The
        in-workflow code path that needs bd will re-fail with a clear
        message later if this didn't take.
        """
        # Local import to keep workspace.manager import-light — bd client
        # pulls in subprocess machinery we don't need for teardown paths.
        from maverick.beads.client import BeadClient
        from maverick.exceptions.beads import BeadLifecycleError

        if not (self.workspace_path / ".beads" / "issues.jsonl").is_file():
            logger.debug(
                "workspace_bd_bootstrap_skipped",
                reason="no .beads/issues.jsonl in clone",
                workspace_path=str(self.workspace_path),
            )
            return

        client = BeadClient(cwd=self.workspace_path)
        try:
            action = await client.init_or_bootstrap()
        except BeadLifecycleError as exc:
            logger.warning(
                "workspace_bd_bootstrap_failed",
                workspace_path=str(self.workspace_path),
                error=str(exc),
            )
            return

        logger.info(
            "workspace_bd_bootstrapped",
            workspace_path=str(self.workspace_path),
            action=action.value,
        )

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
