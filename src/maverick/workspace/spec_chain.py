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
from collections.abc import Container
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.exceptions import JjError, SpecChainWorkspaceError
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.jj.client import JjClient

__all__ = ["prepare_workspace", "sweep_stale_workspaces", "teardown_workspace"]

logger = get_logger(__name__)


def _workspace_root(*, home: Path, cwd: Path) -> Path:
    return home / ".maverick" / "workspaces" / cwd.name / "spec-chain"


def _workspace_dir(*, home: Path, cwd: Path, feature: str) -> Path:
    return _workspace_root(home=home, cwd=cwd) / feature


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


async def teardown_workspace(
    *,
    cwd: Path,
    feature: str,
    jj_client: JjClient,
    home: Path | None = None,
) -> None:
    """Un-register and delete *feature*'s hidden workspace.

    Safe by construction: the workspace holds nothing durable. Landing copies
    workspace -> checkout after every step, nothing is ever committed inside
    it, and ``_reseed_workspace_from_checkout`` rebuilds a fresh one from the
    checkout on resume. Resume depends on the checkpoint and the landed
    artifacts, never on this directory surviving.

    Call only for a *completed* chain. A halted or interrupted one keeps its
    workspace: it is the only copy of the failing step's partial output, and
    resume reuses it.

    ``workspace_forget`` must precede the removal. Deleting the directory
    first leaves jj still tracking the name — which both blocks a later
    ``workspace_add`` and strands the workspace's working-copy commit as an
    anonymous head in the *user's* commit graph, visible in their ``jj log``
    forever.

    Best-effort throughout: every failure is logged and swallowed. A chain
    that did all five steps must not be reported as failed because cleanup
    could not finish.

    Args:
        cwd: The user's checkout — names the per-project workspace root.
        feature: Feature slug; also the jj workspace name.
        jj_client: Injected :class:`JjClient` bound to *cwd*.
        home: Override for ``~`` (tests only).
    """
    home = home or Path.home()
    workspace_dir = _workspace_dir(home=home, cwd=cwd, feature=feature)

    try:
        await jj_client.workspace_forget(workspace_dir.name)
    except Exception as exc:  # noqa: BLE001 — cleanup must never sink a completed chain
        logger.debug(
            "spec_chain_workspace_forget_failed",
            workspace=str(workspace_dir),
            error=str(exc),
        )

    try:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)
    except OSError as exc:
        logger.warning(
            "spec_chain_workspace_remove_failed",
            workspace=str(workspace_dir),
            error=str(exc),
        )
        return

    logger.info("spec_chain_workspace_torn_down", feature=feature, workspace=str(workspace_dir))


async def sweep_stale_workspaces(
    *,
    cwd: Path,
    jj_client: JjClient,
    keep: Container[str],
    home: Path | None = None,
) -> None:
    """Collect this project's workspaces whose features are not in *keep*.

    Teardown-on-completion alone does not bound growth: it never fires for a
    chain the user abandoned with Ctrl-C, which is the realistic leak. This
    sweeps whatever is left over from previous runs.

    Scoped to *cwd*'s own workspace root — another checkout's workspaces are
    not ours to collect, and their resumable state lives in a different
    ``.maverick/runs``.

    Args:
        cwd: The user's checkout — names the per-project workspace root.
        jj_client: Injected :class:`JjClient` bound to *cwd*.
        keep: Feature names to preserve. The caller owns this policy; pass
            ``state.resumable_features(cwd)`` plus whatever the current run
            is about to use.
        home: Override for ``~`` (tests only).
    """
    home = home or Path.home()
    root = _workspace_root(home=home, cwd=cwd)
    if not root.is_dir():
        return

    try:
        entries = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError as exc:
        logger.warning("spec_chain_workspace_sweep_unreadable", root=str(root), error=str(exc))
        return

    for entry in entries:
        if entry.name in keep:
            continue
        # Per-entry isolation: one undeletable workspace must not strand
        # every later one.
        await teardown_workspace(cwd=cwd, feature=entry.name, jj_client=jj_client, home=home)
