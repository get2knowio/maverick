"""``IsolationSession`` — the primitive's public orchestration surface.

Provisions a per-unit isolated workspace, lets an agent mutate files there,
folds the delta into the checkout as one application on success, and
discards or retains it on failure per policy. See
../../../specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md.
"""

from __future__ import annotations

import dataclasses
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.exceptions import (
    IsolationBoundaryError,
    IsolationLockedError,
    IsolationRecoveryRequiredError,
    IsolationUndoFailedError,
)
from maverick.library.actions.jj import jj_restore_operation
from maverick.logging import get_logger
from maverick.workspace import foldback, journal, lifecycle
from maverick.workspace.journal import ApplicationRecord
from maverick.workspace.models import FoldBackOutcome, IsolationLease

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Container
    from datetime import datetime

    from maverick.jj.client import JjClient
    from maverick.workspace.models import (
        CheckoutPath,
        FoldBackResult,
        IsolationPolicy,
        UnitOfWork,
    )

__all__ = [
    "IsolationSession",
    "assert_checkout",
    "register_live_workspace",
    "unregister_live_workspace",
]

logger = get_logger(__name__)

#: Process-global registry of currently-live workspace roots, across every
#: `IsolationSession` in the process. Not per-session: bd/ledger/commit-
#: graph entry points (`assert_checkout`'s callers) have no session
#: reference to consult — the guard must work as a free function (research.md
#: R9 layer 2, contract C6). Populated on `lease()` entry, discarded on
#: exit, so a torn-down workspace's path stops being rejected.
_ACTIVE_WORKSPACE_ROOTS: set[Path] = set()


def register_live_workspace(path: Path) -> Path:
    """Mark *path* as a live workspace root for `assert_checkout`.

    `lease()` calls this itself. Exposed for consumers that cannot use its
    `async with`-scoped convenience wrapper — Burr's actions are
    independently-invoked async functions with no shared lexical scope
    spanning a bead's provision -> fold-back -> commit sequence (fly's
    `_isolation.py`), so they drive `lifecycle.provision`/`teardown`
    directly and must register/unregister the boundary themselves.

    Returns:
        The resolved path, for the caller to pass back to
        :func:`unregister_live_workspace`.
    """
    resolved = path.resolve()
    _ACTIVE_WORKSPACE_ROOTS.add(resolved)
    return resolved


def unregister_live_workspace(path: Path) -> None:
    """Undo :func:`register_live_workspace`. Idempotent."""
    _ACTIVE_WORKSPACE_ROOTS.discard(path.resolve())


def assert_checkout(path: Path | str) -> None:
    """Raise `IsolationBoundaryError` if *path* resolves inside any live
    workspace root (contract C6, FR-021).

    Every bd, ledger, and commit-graph entry point calls this with its
    target directory. Resolves against the actual live workspace roots
    tracked by every open `IsolationSession.lease()` in this process —
    never a path-shape heuristic, so a workspace root that happens to look
    like an ordinary directory is still caught, and a path that merely
    *looks* workspace-shaped (e.g. lives under `.maverick/workspaces/`)
    is never rejected unless a lease is actually live there.

    Args:
        path: The candidate directory a caller is about to operate against.

    Raises:
        IsolationBoundaryError: *path* resolves inside a live workspace root.
    """
    candidate = Path(path).resolve()
    for root in _ACTIVE_WORKSPACE_ROOTS:
        if candidate == root or candidate.is_relative_to(root):
            raise IsolationBoundaryError(
                f"{candidate} resolves inside the live isolated workspace {root} — "
                "bd, ledger, and commit-graph operations must target the checkout, "
                "never a workspace.",
                path=str(candidate),
                workspace_root=str(root),
            )


class IsolationSession:
    """Owns one isolated run's lifecycle: lease -> fold-back -> undo ->
    teardown/sweep, over a single checkout and :class:`IsolationPolicy`.

    See contracts/isolation-primitive.md for the full behavioral contract.
    """

    def __init__(
        self,
        *,
        checkout: CheckoutPath,
        policy: IsolationPolicy,
        jj_client: JjClient,
        run_id: str,
        now: Callable[[], datetime],
        home: Path | None = None,
    ) -> None:
        self._checkout = checkout
        self._policy = policy
        self._jj_client = jj_client
        self._run_id = run_id
        self._now = now
        self._home = home
        #: Workspaces this session registered that have not been released
        #: yet, keyed by resolved root. `lease()` keeps this empty by
        #: construction; a consumer driving `provision`/`teardown` across
        #: separate call sites (Burr actions have no shared lexical scope
        #: spanning a unit) can leave entries here if the run halts
        #: mid-unit, and `__aexit__` is where those get cleaned up.
        self._live_units: dict[Path, UnitOfWork] = {}

    async def __aenter__(self) -> IsolationSession:
        """Acquire this checkout's run-scoped exclusivity (contract C1) and
        refuse on a stale, uncleared application journal (contract C2).

        Raises:
            IsolationRecoveryRequiredError: A prior run's `ApplicationRecord`
                was found uncleared. No automatic rollback is performed.
            IsolationLockedError: Another isolated run already holds this
                checkout's lock.
        """
        stale = await journal.read_record(self._checkout)
        if stale is not None:
            logger.warning(
                "isolation_journal_stale",
                unit_key=stale.unit_key,
                workflow=stale.workflow,
                operation=stale.operation,
                workspace_path=stale.workspace_path,
                restore_operation_id=stale.restore_operation_id,
            )
            raise IsolationRecoveryRequiredError(
                f"a prior isolated run's {stale.operation!r} application for unit "
                f"{stale.unit_key!r} was left uncleared — the checkout may be mid-"
                f"application. No automatic rollback was performed. To recover, "
                f"inspect the workspace at {stale.workspace_path!r} and, if appropriate, "
                f"run 'jj op restore {stale.restore_operation_id}' by hand, then remove "
                f"the journal file before retrying.",
                unit_key=stale.unit_key,
                operation=stale.operation,
                workspace_path=stale.workspace_path,
                restore_operation_id=stale.restore_operation_id,
            )

        acquired = await journal.acquire_lock(self._checkout)
        if not acquired:
            pid = journal.holding_pid(self._checkout)
            logger.warning("isolation_lock_held", holding_pid=pid)
            raise IsolationLockedError(
                f"another isolated run (pid {pid}) already holds this checkout's "
                "isolation lock. Isolated runs are exclusive per checkout.",
                pid=pid if pid is not None else -1,
            )
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Release this checkout's lock, after cleaning up any unit still
        holding a workspace.

        `lease()` unregisters and tears down in its own `finally`, so it
        never leaves anything here. A consumer that cannot use it —
        fly's Burr actions register in `provision_workspace` and release in
        `teardown_workspace`, two independently-invoked functions with no
        `finally` bridging them — leaves both the registration and the
        workspace behind whenever the run halts between the two. This is
        the one place with a real `finally` spanning the whole run, so the
        symmetry is restored here rather than left to the next run's sweep
        (which only happens if there *is* a next isolated run).
        """
        try:
            await self._release_live_units(failed=any(e is not None for e in exc))
        finally:
            await journal.release_lock(self._checkout)

    async def _release_live_units(self, *, failed: bool) -> None:
        """Unregister and tear down (or retain) every still-live unit."""
        for path, unit in list(self._live_units.items()):
            self.release_unit(path)
            try:
                if failed and self._policy.retain_on_failure:
                    await lifecycle.retain(checkout=self._checkout, policy=self._policy, unit=unit)
                else:
                    await lifecycle.teardown(
                        checkout=self._checkout,
                        policy=self._policy,
                        unit=unit,
                        jj_client=self._jj_client,
                    )
            except Exception as exc:  # noqa: BLE001 — cleanup must not mask the real error
                logger.warning(
                    "isolation_session_cleanup_failed",
                    workflow=self._policy.workflow,
                    unit_key=unit.key,
                    workspace_path=str(path),
                    error=str(exc),
                )

    def register_unit(self, unit: UnitOfWork, path: Path) -> Path:
        """Register *path* as live for *unit*, session-scoped.

        Prefer this over the free :func:`register_live_workspace` — it adds
        the same process-global guard entry, and additionally makes
        `__aexit__` responsible for the unit if the caller never releases
        it.

        Returns:
            The resolved path, for the caller to pass to
            :meth:`release_unit`.
        """
        resolved = register_live_workspace(path)
        self._live_units[resolved] = unit
        return resolved

    def release_unit(self, path: Path) -> None:
        """Undo :meth:`register_unit`. Idempotent."""
        resolved = path.resolve()
        unregister_live_workspace(resolved)
        self._live_units.pop(resolved, None)

    @asynccontextmanager
    async def lease(self, unit: UnitOfWork) -> AsyncIterator[IsolationLease]:
        """Provision a workspace for *unit*, yield the lease, then tear
        down (or retain, per policy) on exit.

        Contract C3: provisioning happens before the body runs, so a
        provisioning failure never lets an agent start. Teardown/retention
        happens on exit, following `policy.retain_on_failure` when the
        body raised.
        """
        checkout_path: Path = self._checkout
        workspace_path = await lifecycle.provision(
            checkout=checkout_path,
            policy=self._policy,
            unit=unit,
            jj_client=self._jj_client,
        )
        lease = IsolationLease(
            unit=unit,
            workspace_path=workspace_path,
            workspace_name=workspace_path.name,
            checkout=self._checkout,
            created_at=self._now(),
        )
        resolved_workspace_path = self.register_unit(unit, workspace_path)
        failed = False
        try:
            yield lease
        except BaseException:
            failed = True
            raise
        finally:
            self.release_unit(resolved_workspace_path)
            if failed and self._policy.retain_on_failure:
                await lifecycle.retain(checkout=checkout_path, policy=self._policy, unit=unit)
            else:
                await lifecycle.teardown(
                    checkout=checkout_path,
                    policy=self._policy,
                    unit=unit,
                    jj_client=self._jj_client,
                )

    async def fold_back(
        self, lease: IsolationLease, *, fold_scope: tuple[str, ...] | None = None
    ) -> FoldBackResult:
        """Move `lease`'s workspace delta into the checkout as one
        application. See contract C4.

        Args:
            lease: The live workspace to fold back.
            fold_scope: Per-call override for `policy.fold_scope`. Most
                callers omit this and get the policy's own scope (fly:
                `()`, unscoped). The spec chain overrides it per call
                because its scope — `specs/<feature-dir>`— isn't known
                until the `specify` step resolves the feature directory,
                which happens *after* the session (and its policy) is
                already constructed for the run.
        """
        return await foldback.fold_back(
            checkout=self._checkout,
            lease=lease,
            fold_scope=fold_scope if fold_scope is not None else self._policy.fold_scope,
            fold_exclusions=self._policy.fold_exclusions,
            run_id=self._run_id,
            workflow=self._policy.workflow,
            now=self._now,
        )

    async def sync_workspace(self, workspace_path: Path) -> None:
        """Bring *workspace_path* up to date with the repo's current jj
        operation before an agent writes into it.

        Only load-bearing for a `reuse=True` policy (spec-chain): a
        workspace that survives across multiple `fold_back` calls goes
        stale the moment *any* jj command runs anywhere in the repo after
        the last sync — including its own prior `fold_back`'s squash. Left
        unsynced, the next agent write lands on disk before the workspace
        next talks to jj, and the stale-recovery path inside `fold_back`
        resets the working copy to the workspace's last known commit,
        discarding that write. Call this immediately before handing the
        workspace to the agent, not just after the previous fold-back.
        """
        await foldback.sync_workspace(workspace_path)

    async def undo(self, lease: IsolationLease, result: FoldBackResult) -> None:
        """Restore the checkout to its pre-fold-back state (contract C5).

        Postconditions: the checkout is byte-identical to its pre-fold-back
        state, including unrelated uncommitted work the user had there; the
        workspace still holds the rejected delta (`jj op restore` rewinds
        the workspace's working-copy commit too, research.md R5), so a fix
        round resumes in place.

        Writes an `ApplicationRecord` (`operation="undo"`) before mutating
        the checkout, clearing it only on success — on failure the record
        is left in place, deliberately, as the crash-recovery marker
        (FR-049).

        Raises:
            IsolationUndoFailedError: `jj op restore` failed. Never
                swallowed, never silently retried — the caller must halt
                the run; no further unit may begin.
        """
        logger.info(
            "isolation_undo_started",
            unit_key=lease.unit.key,
            workflow=self._policy.workflow,
            workspace_path=str(lease.workspace_path),
            restore_operation_id=result.restore_operation_id,
        )
        await journal.write_record(
            self._checkout,
            ApplicationRecord(
                run_id=self._run_id,
                workflow=self._policy.workflow,
                unit_key=lease.unit.key,
                operation="undo",
                restore_operation_id=result.restore_operation_id,
                workspace_path=str(lease.workspace_path),
                started_at=self._now(),
            ),
        )
        restore = await jj_restore_operation(result.restore_operation_id, cwd=self._checkout)
        if not restore["success"]:
            logger.error(
                "isolation_undo_failed",
                unit_key=lease.unit.key,
                workflow=self._policy.workflow,
                workspace_path=str(lease.workspace_path),
                restore_operation_id=result.restore_operation_id,
                error=restore["error"],
            )
            # Deliberately not cleared — the uncleared record is what makes
            # this failure recoverable rather than silently lost.
            raise IsolationUndoFailedError(
                f"failed to restore checkout to operation {result.restore_operation_id}: "
                f"{restore['error']}. The checkout may hold an unverified fold-back delta — "
                f"manual recovery required (see 'jj op log' and 'jj op restore "
                f"{result.restore_operation_id}').",
                workspace_path=str(lease.workspace_path),
                restore_operation_id=result.restore_operation_id,
            )
        await journal.clear_record(self._checkout)
        logger.info(
            "isolation_undo_completed",
            unit_key=lease.unit.key,
            workflow=self._policy.workflow,
            workspace_path=str(lease.workspace_path),
        )

    def mark_rejected(self, result: FoldBackResult, *, diagnostic: str = "") -> FoldBackResult:
        """Relabel a successful (`APPLIED`/`EMPTY`) fold-back as `REJECTED`
        after an environment-level check failed and :meth:`undo` has
        already been called (FR-012, FR-013, FR-019).

        Pure — performs no I/O and does not itself call :meth:`undo`; the
        caller must undo first, since `REJECTED` only makes sense once the
        checkout has actually been restored. This is the check-placement
        surface: artifact-level checks run inside the lease before
        `fold_back`; environment-level checks are the caller's
        responsibility after it, and this is how their rejection becomes
        part of the typed result rather than a bespoke caller-side flag.
        """
        return dataclasses.replace(
            result,
            outcome=FoldBackOutcome.REJECTED,
            diagnostic=diagnostic or result.diagnostic,
        )

    async def sweep(self, *, keep: Container[str]) -> None:
        """Collect this checkout's abandoned workspaces under this
        workflow. See contract C7."""
        await lifecycle.sweep(
            checkout=self._checkout,
            policy=self._policy,
            jj_client=self._jj_client,
            keep=keep,
        )
