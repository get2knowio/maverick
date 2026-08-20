"""Workspace provisioning, teardown, and sweep.

Generalizes ``workspace/spec_chain.py``'s per-feature workspace lifecycle
into a ``(workflow, key)``-keyed primitive shared by every isolation
consumer. Preserves its two load-bearing rules: ``workspace_forget`` always
precedes ``rmtree`` (including when the directory is already gone), and
teardown/sweep are best-effort and never sink a completed unit.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.exceptions import IsolationProvisioningError, JjError
from maverick.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Container

    from maverick.jj.client import JjClient
    from maverick.workspace.models import IsolationPolicy, UnitOfWork

__all__ = ["provision", "sweep", "teardown", "workspace_dir", "workspace_root"]

logger = get_logger(__name__)


def workspace_root(*, root: Path, checkout: Path, workflow: str) -> Path:
    """``root/<project>/<workflow>/`` — ``<project>`` is the checkout's
    basename, matching ``workspace/spec_chain.py``'s ``_workspace_root``
    precedent, generalized with a ``<workflow>`` segment (research.md R7)."""
    return root / checkout.name / workflow


def workspace_dir(*, root: Path, checkout: Path, workflow: str, key: str) -> Path:
    """``root/<project>/<workflow>/<key>/`` — contract C3's provisioning path."""
    return workspace_root(root=root, checkout=checkout, workflow=workflow) / key


async def provision(
    *,
    checkout: Path,
    policy: IsolationPolicy,
    unit: UnitOfWork,
    jj_client: JjClient,
) -> Path:
    """Create, reuse, or recreate the workspace for *unit*.

    Contract C3: ``workspace_forget`` runs first, unconditionally —
    including when the directory is already absent — then ``rmtree``,
    unless ``policy.reuse`` and the directory exists. Provisioning failure
    raises before any agent runs (FR-001 edge case).

    Args:
        checkout: The user's colocated checkout (source repo for
            ``workspace_add``).
        policy: This run's :class:`IsolationPolicy`.
        unit: The unit being provisioned for — ``unit.key`` names the
            workspace directory and the jj workspace itself.
        jj_client: Injected :class:`JjClient` bound to *checkout*.

    Returns:
        The resolved workspace directory path.

    Raises:
        IsolationProvisioningError: The workspace could not be created —
            message distinguishes "could not isolate" from "the work
            failed" (contract C3).
    """
    workspace_path = workspace_dir(
        root=policy.root, checkout=checkout, workflow=policy.workflow, key=unit.key
    )

    reused = policy.reuse and workspace_path.exists()
    if not reused:
        # Best-effort: a name that was never registered (a genuinely fresh
        # unit) makes forget error, which is not a problem; a real
        # collision instead surfaces on workspace_add below.
        try:
            await jj_client.workspace_forget(workspace_path.name)
        except JjError as exc:
            logger.debug(
                "isolation_workspace_forget_skipped",
                workspace_path=str(workspace_path),
                error=str(exc),
            )
        try:
            if workspace_path.exists():
                await asyncio.to_thread(shutil.rmtree, workspace_path)
        except OSError as exc:
            raise IsolationProvisioningError(
                f"could not isolate: failed to clear stale workspace at {workspace_path}: {exc}",
                workspace_path=str(workspace_path),
            ) from exc

        try:
            await jj_client.workspace_add(workspace_path, revision="@")
        except (JjError, OSError) as exc:
            raise IsolationProvisioningError(
                f"could not isolate: failed to create workspace at {workspace_path}: {exc}",
                workspace_path=str(workspace_path),
            ) from exc

    await asyncio.to_thread(_seed_inputs, workspace_path, unit.seed_inputs)

    logger.info(
        "isolation_provisioned",
        unit_key=unit.key,
        workflow=policy.workflow,
        workspace_path=str(workspace_path),
        reused=reused,
    )
    return workspace_path


def _seed_inputs(workspace_path: Path, seed_inputs: tuple[Path, ...]) -> None:
    """Copy `unit.seed_inputs` files into `<workspace>/inputs/` — files
    absent from committed history that the agent still needs (FR-004),
    mirroring `workspace/spec_chain.py`'s PRD-copy precedent."""
    if not seed_inputs:
        return
    inputs_dir = workspace_path / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    for src in seed_inputs:
        shutil.copyfile(src, inputs_dir / src.name)
    logger.info(
        "isolation_seeded",
        workspace_path=str(workspace_path),
        seed_inputs=tuple(str(p) for p in seed_inputs),
    )


async def teardown(
    *,
    checkout: Path,
    policy: IsolationPolicy,
    unit: UnitOfWork,
    jj_client: JjClient,
) -> None:
    """Un-register and delete *unit*'s workspace.

    Contract C7: ``workspace_forget`` always precedes removal — reversing
    them leaves jj tracking the name, blocking the next ``workspace_add``
    and stranding an anonymous head in the user's ``jj log`` forever.
    Best-effort throughout: every failure is logged and swallowed. A unit
    that completed successfully must never be reported as failed because
    cleanup could not finish.

    Args:
        checkout: The user's checkout — names the per-project workspace root.
        policy: This run's :class:`IsolationPolicy`.
        unit: The unit whose workspace is being torn down.
        jj_client: Injected :class:`JjClient` bound to *checkout*.
    """
    workspace_path = workspace_dir(
        root=policy.root, checkout=checkout, workflow=policy.workflow, key=unit.key
    )

    try:
        await jj_client.workspace_forget(workspace_path.name)
    except Exception as exc:  # noqa: BLE001 — cleanup must never sink a completed unit
        logger.debug(
            "isolation_workspace_forget_failed",
            workspace_path=str(workspace_path),
            error=str(exc),
        )

    try:
        if workspace_path.exists():
            await asyncio.to_thread(shutil.rmtree, workspace_path)
    except OSError as exc:
        logger.warning(
            "isolation_workspace_remove_failed",
            workspace_path=str(workspace_path),
            error=str(exc),
        )
        return

    logger.info(
        "isolation_torn_down",
        unit_key=unit.key,
        workflow=policy.workflow,
        workspace_path=str(workspace_path),
    )


async def retain(*, checkout: Path, policy: IsolationPolicy, unit: UnitOfWork) -> None:
    """Log that a failed unit's workspace was kept on disk (FR-025)."""
    workspace_path = workspace_dir(
        root=policy.root, checkout=checkout, workflow=policy.workflow, key=unit.key
    )
    logger.info(
        "isolation_retained",
        unit_key=unit.key,
        workflow=policy.workflow,
        workspace_path=str(workspace_path),
    )


async def sweep(
    *,
    checkout: Path,
    policy: IsolationPolicy,
    jj_client: JjClient,
    keep: Container[str],
) -> None:
    """Collect this project's workspaces (under this workflow) whose keys
    are not in *keep*.

    Teardown-on-completion alone does not bound growth: it never fires for
    a unit the user abandoned with Ctrl-C, which is the realistic leak.
    Scoped to *checkout*'s own workspace root under *policy.workflow* only
    (FR-026) — another checkout's or another workflow's workspaces are not
    ours to collect. Per-entry isolated (FR-027): one undeletable workspace
    must not strand every later one, and no sweep failure fails the run.

    Candidates come from **two** sources, unioned (FR-028): the on-disk
    directory listing, and jj's own workspace registry (``jj workspace
    list``). A directory and its jj registration can diverge — a user may
    clear ``~/.maverick/workspaces`` by hand while jj still tracks the
    name, or an interrupted run may leave a jj registration with no
    directory at all — and correctness must not depend on either surviving
    alone.

    Args:
        checkout: The user's checkout — names the per-project workspace root.
        policy: This run's :class:`IsolationPolicy`.
        jj_client: Injected :class:`JjClient` bound to *checkout*.
        keep: Keys to preserve. The caller owns this policy.
    """
    from maverick.exceptions import JjError
    from maverick.workspace.models import UnitOfWork

    root = workspace_root(root=policy.root, checkout=checkout, workflow=policy.workflow)

    names: set[str] = set()

    def _list_workspace_dirs() -> list[str]:
        return [p.name for p in root.iterdir() if p.is_dir()]

    if await asyncio.to_thread(root.is_dir):
        try:
            names.update(await asyncio.to_thread(_list_workspace_dirs))
        except OSError as exc:
            logger.warning("isolation_workspace_sweep_unreadable", root=str(root), error=str(exc))

    try:
        resolved_root = root.resolve()
        listed = await jj_client.workspace_list()
        for info in listed.workspaces:
            if info.name == "default":
                continue  # the checkout's own workspace — never a sweep candidate
            if not info.path:
                # jj records no root for a workspace whose directory is
                # currently missing (verified against real jj 0.44 — not
                # a stable historical path, just absent) — exactly the
                # FR-028 scenario this sweep exists for. There is no
                # location info left to filter by, so this falls back to
                # including it by name. jj's registry is itself per-repo
                # (this checkout's own .jj/), so cross-*checkout*
                # contamination (FR-026's actual concern, verified by
                # test_sweep.py) is structurally impossible here; the
                # residual risk is a same-named workspace belonging to a
                # *different workflow* in this same checkout, which
                # naming conventions (bead ids vs. feature slugs) make
                # negligible — and leaving a directory-less registration
                # forever is a worse outcome than that residual risk.
                names.add(info.name)
                continue
            candidate = Path(info.path)
            if not candidate.is_absolute():
                candidate = checkout / candidate
            candidate = candidate.resolve()
            if candidate == resolved_root or candidate.is_relative_to(resolved_root):
                names.add(info.name)
    except JjError as exc:
        logger.warning("isolation_workspace_sweep_jj_list_failed", root=str(root), error=str(exc))

    for name in sorted(names):
        if name in keep:
            continue
        await teardown(
            checkout=checkout,
            policy=policy,
            unit=UnitOfWork(key=name, label=name),
            jj_client=jj_client,
        )
        logger.info("isolation_swept", workflow=policy.workflow, workspace_path=name)
