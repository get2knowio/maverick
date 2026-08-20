"""Fold-back mechanics: snapshot, squash, conflict-detect, undo.

Implements contract C4/C5 of
../../../specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md.
The workspace-snapshot-before-squash ordering here is the single most
failure-prone step in the whole primitive (research.md R3) — it is a single
chokepoint, never a step a caller can forget.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.exceptions import IsolationError
from maverick.jj.client import JjClient
from maverick.library.actions.jj import (
    jj_fold_back as _jj_fold_back_action,
)
from maverick.library.actions.jj import (
    jj_list_conflicts,
    jj_restore_operation,
    jj_snapshot_operation,
    jj_workspace_snapshot,
)
from maverick.logging import get_logger
from maverick.workspace import journal
from maverick.workspace.journal import ApplicationRecord
from maverick.workspace.models import FoldBackOutcome, FoldBackResult

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from maverick.workspace.models import CheckoutPath, IsolationLease

__all__ = ["fold_back", "sync_workspace"]

logger = get_logger(__name__)

#: Always excluded from every fold-back regardless of the caller's policy
#: (data-model.md: "fold_exclusions ... always applied, always includes
#: ~.maverick"). Orchestrator state must never travel workspace -> checkout
#: (FR-011); /.maverick is gitignored anyway, but the fileset makes it a
#: contract rather than an accident of .gitignore (research.md R2).
_ALWAYS_EXCLUDED: tuple[str, ...] = (".maverick",)

#: The `jj status` line prefixes for the "Working copy changes:" block
#: (Modified / Added / Deleted / Renamed / Copied). Matches research.md
#: R2's verified example output (`M a.txt`, `D b.txt`, `A c.txt`).
_STATUS_CHANGE_PREFIXES = ("M ", "A ", "D ", "R ", "C ")

#: The header line `jj status` prints above its conflict-path block
#: (research.md R4's verified example).
_CONFLICT_WARNING_HEADER = "unresolved conflicts at these paths:"

#: Substring `jj` uses in its stale-working-copy error (research.md R5).
_STALE_WORKING_COPY_MARKER = "stale"


def _build_fileset(fold_scope: tuple[str, ...], fold_exclusions: tuple[str, ...]) -> str:
    """Combine `fold_scope`/`fold_exclusions` into one jj fileset expression.

    `~.maverick` is always folded in regardless of what the caller's policy
    supplies. Empty `fold_scope` means "everything not excluded" per
    data-model.md.
    """
    exclusions: tuple[str, ...] = tuple(dict.fromkeys((*fold_exclusions, *_ALWAYS_EXCLUDED)))
    negated = [f"~{entry}" for entry in exclusions]
    if fold_scope:
        scope_expr = "(" + " | ".join(fold_scope) + ")"
        return " & ".join([scope_expr, *negated])
    return " & ".join(negated)


def _resolve_status_path(entry: str) -> str:
    """Resolve one `jj status` change-line path token to its post-change
    (new) repo-relative path.

    Plain M/A/D paths pass through unchanged. R(ename)/C(opy) lines use
    jj's git-style compact notation — a shared prefix factored out of a
    `{old => new}` braced suffix, e.g. `src/foo/{a.txt => b.txt}` or a
    bare `{a.txt => b.txt}` with no shared prefix (verified against real
    jj 0.44 output; a naive fixed-offset slice mis-parses this as one
    literal path containing a brace/arrow). This extracts the *new*
    path — what now actually exists on disk in the checkout after the
    squash, which is what ``applied_paths``/``conflicting_paths`` report.
    """
    if "{" not in entry or "}" not in entry or "=>" not in entry:
        return entry
    prefix, _, rest = entry.partition("{")
    inside, _, suffix = rest.partition("}")
    _old, sep, new = inside.partition("=>")
    if not sep:
        return entry
    return f"{prefix}{new.strip()}{suffix}"


def _extract_applied_paths(status_output: str) -> tuple[str, ...]:
    """Parse the `Working copy changes:` block of `jj status` output into
    repo-relative posix paths (research.md R2's verified example)."""
    paths: list[str] = []
    for line in status_output.splitlines():
        stripped = line.strip()
        if stripped.startswith(_STATUS_CHANGE_PREFIXES):
            paths.append(_resolve_status_path(stripped[2:].strip()))
    return tuple(paths)


def _extract_conflicting_paths(status_output: str) -> tuple[str, ...]:
    """Parse the "unresolved conflicts at these paths:" warning block of
    `jj status` output (research.md R4's verified example)."""
    paths: list[str] = []
    in_block = False
    for line in status_output.splitlines():
        if _CONFLICT_WARNING_HEADER in line:
            in_block = True
            continue
        if not in_block:
            continue
        stripped = line.strip()
        if not stripped:
            break
        paths.append(_resolve_status_path(stripped.split()[0]))
    return tuple(paths)


async def sync_workspace(workspace_path: Path) -> None:
    """Force a working-copy snapshot inside the workspace (R3's mandatory
    chokepoint) — recovering from a stale-working-copy error (research.md
    R5) instead of letting it escape as an opaque `JjError`.

    Public: also the pre-write sync a `reuse=True` caller (spec-chain) must
    run immediately before an agent writes into a workspace it didn't just
    provision. Any jj command anywhere in the repo — the checkout's own
    auto-snapshot, another workspace's squash, even a plain read that
    triggers one — advances the shared operation log and makes every other
    workspace stale relative to it, independent of whether that operation
    touched the workspace's own tree. `jj workspace update-stale` resets
    the *files on disk* to match the workspace's last known commit, which
    is safe here (nothing has been written yet) but destructive the moment
    it runs *after* new content has already landed on disk uncommitted —
    exactly what happened when recovery only ran reactively inside
    `fold_back`, after the agent had already written (057's post-migration
    regression: a reused workspace's second-and-later steps recovered from
    staleness by discarding that step's own just-written artifact)."""
    result = await jj_workspace_snapshot(cwd=workspace_path)
    if result.success:
        return

    error = result.error or ""
    if _STALE_WORKING_COPY_MARKER not in error.lower():
        raise IsolationError(f"failed to snapshot workspace {workspace_path}: {error}")

    logger.warning(
        "isolation_workspace_stale_recovering", workspace_path=str(workspace_path), error=error
    )
    client = JjClient(cwd=workspace_path)
    await client.workspace_update_stale()
    retry = await jj_workspace_snapshot(cwd=workspace_path)
    if not retry.success:
        raise IsolationError(
            f"failed to snapshot workspace {workspace_path} after stale recovery: {retry.error}"
        )
    logger.info("isolation_workspace_stale_recovered", workspace_path=str(workspace_path))


async def fold_back(
    *,
    checkout: CheckoutPath,
    lease: IsolationLease,
    fold_scope: tuple[str, ...],
    fold_exclusions: tuple[str, ...],
    run_id: str,
    workflow: str,
    now: Callable[[], datetime],
) -> FoldBackResult:
    """Move `lease`'s workspace delta into `checkout` as one application.

    Follows contract C4's mandatory ordering: snapshot the workspace (R3's
    chokepoint) -> capture the checkout's restore operation -> squash with
    `fold_scope`/`fold_exclusions` -> query `conflicts()` -> restore on
    conflict.

    Args:
        checkout: The user's checkout — the squash's `--into` target.
        lease: The live workspace to fold back.
        fold_scope: jj filesets bounding what may fold back (empty means
            "everything not excluded").
        fold_exclusions: Additional exclusions beyond the always-applied
            `~.maverick` (e.g. the protection policy's protected set,
            research.md R11).

    Returns:
        :class:`FoldBackResult`. `EMPTY` is a success (FR-006); `CONFLICT`
        restores the checkout before returning, so the checkout is left
        unchanged (SC-005).

    Raises:
        IsolationError: The workspace snapshot or the squash itself failed
            for a reason unrelated to conflict or empty-delta (e.g. a
            genuine jj/process error).
    """
    started = time.perf_counter()
    logger.info(
        "isolation_fold_back_started",
        unit_key=lease.unit.key,
        workflow=workflow,
        workspace_path=str(lease.workspace_path),
    )

    # Step 1 (R3): force the workspace's own working-copy snapshot BEFORE
    # anything else. Skipping this yields a successful, empty fold-back
    # with no error — the single sharpest edge in this mechanism.
    await sync_workspace(lease.workspace_path)

    # Step 2: capture the checkout's restore point before mutating it.
    snapshot = await jj_snapshot_operation(cwd=checkout)
    if not snapshot["success"]:
        raise IsolationError(f"failed to snapshot checkout operation: {snapshot['error']}")
    restore_operation_id: str = snapshot["operation_id"]

    # Step 3: write the ApplicationRecord BEFORE mutating the checkout — the
    # crash-recovery marker for FR-049. Cleared in step 6.
    await journal.write_record(
        checkout,
        ApplicationRecord(
            run_id=run_id,
            workflow=workflow,
            unit_key=lease.unit.key,
            operation="fold-back",
            restore_operation_id=restore_operation_id,
            workspace_path=str(lease.workspace_path),
            started_at=now(),
        ),
    )

    # Step 4: squash the workspace's delta into the checkout.
    fileset = _build_fileset(fold_scope, fold_exclusions)
    squash_result = await _jj_fold_back_action(
        lease.workspace_name, into="@", filesets=(fileset,) if fileset else (), cwd=checkout
    )
    if not squash_result.success:
        raise IsolationError(f"fold-back squash failed: {squash_result.error}")

    duration = time.perf_counter() - started

    # Step 5: the exit code is not the signal — conflicts() is.
    conflicts = await jj_list_conflicts("@", cwd=checkout)
    if not conflicts["success"]:
        raise IsolationError(f"failed to query conflicts after fold-back: {conflicts['error']}")

    client = JjClient(cwd=checkout)
    status = await client.status()

    if conflicts["change_ids"]:
        conflicting_paths = _extract_conflicting_paths(status.output)
        restore = await jj_restore_operation(restore_operation_id, cwd=checkout)
        if not restore["success"]:
            raise IsolationError(
                f"failed to restore checkout after fold-back conflict: {restore['error']}"
            )
        diagnostic = f"conflict in: {', '.join(conflicting_paths)}"
        logger.warning(
            "isolation_conflict",
            unit_key=lease.unit.key,
            workspace_path=str(lease.workspace_path),
            conflicting_paths=conflicting_paths,
        )
        result = FoldBackResult(
            outcome=FoldBackOutcome.CONFLICT,
            conflicting_paths=conflicting_paths,
            restore_operation_id=restore_operation_id,
            diagnostic=diagnostic,
            duration_seconds=duration,
        )
    else:
        # `status.output` reflects the checkout's *entire* uncommitted
        # delta, not just what this squash moved — the journal record
        # written in step 3 lands directly in the checkout and is still
        # uncommitted here. `.maverick` is never part of what fold-back
        # applies (it's always excluded from the fileset itself), so drop
        # it from the reported paths regardless of how it got there.
        applied_paths = tuple(
            path
            for path in _extract_applied_paths(status.output)
            if not any(path == ex or path.startswith(f"{ex}/") for ex in _ALWAYS_EXCLUDED)
        )
        outcome = FoldBackOutcome.APPLIED if applied_paths else FoldBackOutcome.EMPTY
        result = FoldBackResult(
            outcome=outcome,
            applied_paths=applied_paths,
            restore_operation_id=restore_operation_id,
            diagnostic="",
            duration_seconds=duration,
        )

    # Step 6: the application completed (applied, empty, or conflict-
    # restored) — clear the marker. A raise anywhere above this point
    # deliberately leaves the record in place (FR-049's crash signal).
    await journal.clear_record(checkout)

    # Step 7: re-sync the workspace to the operation the squash (or the
    # conflict restore) just created. `<ws>@`'s tree was rewritten out from
    # under the on-disk workspace by that operation — left alone, the
    # *next* caller's first write lands in a workspace jj already considers
    # stale, and `sync_workspace`'s stale recovery
    # (`jj workspace update-stale`) resets the working copy to the last
    # commit jj knows about, silently discarding that write (research.md
    # R5 undersold this: recovery is safe here — nothing new has been
    # written since the squash — but destructive if deferred until the
    # next step has already written into a stale workspace). Best-effort:
    # a failure here just means the next fold-back's own chokepoint (step
    # 1) does the recovery instead, which is safe as long as nothing else
    # has written into the workspace since.
    try:
        await sync_workspace(lease.workspace_path)
    except IsolationError as exc:
        logger.warning(
            "isolation_workspace_post_foldback_resync_failed",
            workspace_path=str(lease.workspace_path),
            error=str(exc),
        )

    logger.info(
        "isolation_fold_back_completed",
        unit_key=lease.unit.key,
        workflow=workflow,
        workspace_path=str(lease.workspace_path),
        outcome=result.outcome.value,
        duration_seconds=result.duration_seconds,
    )
    return result
