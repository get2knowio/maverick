"""``WorkspaceManager`` — colocate user repo, manage jj-workspace working copy.

Lifecycle:

1. :meth:`ensure_colocated` — runs ``jj git init --colocate`` in the
   user's checkout if ``.jj/`` is missing. Idempotent. Callers
   (typically ``maverick init``) run this once per project; runtime
   workflows can call it defensively.

2. :meth:`find_or_create` — returns the workspace path. Creates it
   via ``jj workspace add`` if missing. The workspace is a sibling
   working copy of the user's checkout — same backing repo, separate
   working tree.

3. :meth:`teardown` — runs ``jj workspace forget`` and removes the
   working tree directory. Commits made in the workspace stay in the
   shared op log and are visible in the user's checkout via
   ``jj log``.

Path layout::

    ~/.maverick/workspaces/<project-slug>/   # the jj workspace directory

The ``<project-slug>`` is the user repo's directory basename. One
workspace per user repo for the interim model — the architecture's
per-invocation isolation lands later.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from maverick.jj.client import JjClient
from maverick.jj.errors import JjError
from maverick.logging import get_logger

logger = get_logger(__name__)

WORKSPACES_ROOT = Path.home() / ".maverick" / "workspaces"


class WorkspaceManager:
    """Lifecycle manager for the per-project hidden jj workspace.

    Args:
        user_repo_path: The user's checkout directory. Must exist and
            be a git repo (colocate is run on first call when ``.jj/``
            is absent).
        workspaces_root: Override for the workspaces directory
            (defaults to ``~/.maverick/workspaces/``). Tests pass a
            ``tmp_path``-rooted location.
    """

    def __init__(
        self,
        user_repo_path: Path,
        workspaces_root: Path | None = None,
    ) -> None:
        self._user_repo_path = user_repo_path.resolve()
        root = workspaces_root or WORKSPACES_ROOT
        self._workspace_path = (root / self._user_repo_path.name).resolve()

    @property
    def user_repo_path(self) -> Path:
        return self._user_repo_path

    @property
    def workspace_path(self) -> Path:
        """Where the jj workspace lives on disk."""
        return self._workspace_path

    @property
    def workspace_name(self) -> str:
        """Workspace's jj-internal name (its directory basename)."""
        return self._workspace_path.name

    @property
    def exists(self) -> bool:
        """True when the workspace directory contains a ``.jj`` marker
        — i.e., ``jj workspace add`` has run successfully."""
        return self._workspace_path.is_dir() and (self._workspace_path / ".jj").exists()

    def is_colocated(self) -> bool:
        """True when the user repo has both ``.git/`` and ``.jj/``."""
        return (self._user_repo_path / ".git").exists() and (self._user_repo_path / ".jj").exists()

    async def ensure_colocated(self) -> None:
        """Run ``jj git init --colocate`` in the user repo if not yet
        colocated.

        Idempotent: returns immediately when ``.jj/`` is already
        present. Best-effort: failures raise :class:`JjError` so the
        caller can decide whether init should fail (default) or
        continue degraded.
        """
        if self.is_colocated():
            return
        if not (self._user_repo_path / ".git").exists():
            raise JjError(
                f"User repo at {self._user_repo_path} is not a git "
                "repo — colocate requires an existing .git/ to bind to."
            )
        client = JjClient(cwd=self._user_repo_path)
        await client.git_init(colocate=True)
        logger.info(
            "workspace.colocated_user_repo",
            user_repo=str(self._user_repo_path),
        )

    async def find_or_create(self) -> Path:
        """Return the workspace path; create the workspace if missing.

        Calls :meth:`ensure_colocated` first so the user repo has a
        ``.jj/`` to add a workspace from. The workspace is created via
        ``jj workspace add`` invoked from inside the user repo.

        Returns:
            Resolved path to the workspace working tree.

        Raises:
            JjError: When colocate or ``jj workspace add`` fails.
        """
        await self.ensure_colocated()
        if self.exists:
            logger.debug(
                "workspace.found_existing",
                workspace=str(self._workspace_path),
            )
            return self._workspace_path

        client = JjClient(cwd=self._user_repo_path)
        await client.workspace_add(self._workspace_path)
        logger.info(
            "workspace.created",
            workspace=str(self._workspace_path),
            user_repo=str(self._user_repo_path),
        )
        return self._workspace_path

    async def teardown(self) -> None:
        """Drop the workspace from jj's tracking and delete the
        directory.

        Runs ``jj workspace forget <name>`` from the user repo (the
        workspace itself may already be gone), then ``rm -rf`` on the
        on-disk directory. Commits made in the workspace remain in the
        shared op log and are visible from the user repo's ``jj log``.

        Idempotent: silently returns when the workspace doesn't exist
        on disk and forget fails.
        """
        if not (self._workspace_path.exists()):
            logger.debug(
                "workspace.teardown_noop",
                workspace=str(self._workspace_path),
            )
            return

        # Forget first so jj stops tracking the workspace; then rm -rf
        # the directory. Order matters: deleting the directory while
        # jj still tracks it leaves a stale workspace entry.
        client = JjClient(cwd=self._user_repo_path)
        try:
            await client.workspace_forget(self.workspace_name)
        except JjError as exc:
            # The workspace might already be forgotten (e.g., after a
            # crashed prior teardown). Log and continue to rm -rf.
            logger.debug(
                "workspace.forget_failed_continuing",
                workspace=self.workspace_name,
                error=str(exc),
            )

        try:
            shutil.rmtree(self._workspace_path)
            logger.info(
                "workspace.teardown_completed",
                workspace=str(self._workspace_path),
            )
        except OSError as exc:
            logger.warning(
                "workspace.rmtree_failed",
                workspace=str(self._workspace_path),
                error=str(exc),
            )
