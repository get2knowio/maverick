"""Hidden jj-workspace lifecycle for the spec-chain workflow (R3).

Per-feature isolated workspace under
``~/.maverick/workspaces/<project-slug>/spec-chain/<feature>/``, built on
the canonical :class:`~maverick.jj.client.JjClient`. bd never runs inside
this workspace — all bead/ledger writes happen in the user's checkout via
the workflow, which is why the historic bd/workspace impedance mismatch
that retired the general-purpose ``WorkspaceManager`` does not apply here.
See specs/050-headless-spec-chain/research.md R3.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.exceptions import JjError, SpecChainWorkspaceError
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.jj.client import JjClient

__all__ = ["prepare_workspace"]

logger = get_logger(__name__)


def _workspace_dir(*, home: Path, cwd: Path, feature: str) -> Path:
    return home / ".maverick" / "workspaces" / cwd.name / "spec-chain" / feature


async def prepare_workspace(
    *,
    cwd: Path,
    feature: str,
    prd_path: Path,
    reuse: bool,
    jj_client: JjClient,
    home: Path | None = None,
) -> Path:
    """Create, reuse, or recreate the hidden workspace for *feature*.

    Args:
        cwd: The user's colocated checkout (source repo for ``workspace_add``).
        feature: Feature slug — the workspace path is per-feature, so two
            features never share a directory.
        prd_path: PRD file to copy into the workspace (it may be untracked
            in the user's checkout).
        reuse: ``True`` for an active, resumable chain — reuse the on-disk
            workspace as-is. ``False`` for a completed or fresh chain —
            forget+wipe any stale workspace, then create clean.
        jj_client: Injected :class:`JjClient` bound to *cwd*.
        home: Override for ``~`` (tests only). Defaults to :meth:`Path.home`.

    Returns:
        The resolved workspace directory path.

    Raises:
        SpecChainWorkspaceError: The underlying jj workspace operation failed.
    """
    home = home or Path.home()
    workspace_dir = _workspace_dir(home=home, cwd=cwd, feature=feature)

    if not (reuse and workspace_dir.exists()):
        # Forget any jj-registered workspace of this name BEFORE recreating.
        # Do this even when the on-disk dir is gone: the user may have
        # cleared ``~/.maverick/workspaces`` while jj still tracks the
        # workspace, and ``jj workspace add`` fails on that lingering
        # name collision. Best-effort — a name that was never registered
        # (a genuinely fresh feature) makes ``forget`` error, which is not
        # a problem; a real collision instead surfaces on ``workspace_add``
        # below.
        try:
            await jj_client.workspace_forget(workspace_dir.name)
        except JjError as exc:
            logger.debug(
                "spec_chain_workspace_forget_skipped",
                workspace=str(workspace_dir),
                error=str(exc),
            )
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)

        try:
            await jj_client.workspace_add(workspace_dir)
        except JjError as exc:
            raise SpecChainWorkspaceError(
                f"failed to create workspace {workspace_dir}: {exc}"
            ) from exc

    inputs_dir = workspace_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(prd_path, inputs_dir / prd_path.name)

    logger.info(
        "spec_chain_workspace_ready",
        feature=feature,
        workspace_path=str(workspace_dir),
        reused=reuse and workspace_dir.exists(),
    )
    return workspace_dir
