"""Integration tests for `IsolationSession.undo()` against a real,
throwaway jj-colocated checkout.

Contract: `specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md`
(section "Behavioral contract" C5, and the contract-test table T9-T11).
Mechanism: `specs/057-isolated-bead-workspaces/research.md` R5 (`session
.undo()` runs `jj op restore <result.restore_operation_id>` from the
checkout; validated against real jj 0.44 that this both (1) restores the
checkout's own unrelated uncommitted work byte-identically, because `op
restore` rewinds the *operation*, not the working copy's content in
isolation, and (2) rewinds the workspace's working-copy commit too, so the
rejected delta is still there afterward for a fix round to resume from).

"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from maverick.exceptions import IsolationUndoFailedError
from maverick.jj.client import JjClient
from maverick.workspace import (
    CheckoutPath,
    FoldBackOutcome,
    IsolationPolicy,
    IsolationSession,
    UnitOfWork,
)

pytestmark = pytest.mark.integration


def _make_session(
    colocated_repo: JjClient,
    isolation_home: Path,
    *,
    workflow: str = "fly",
    run_id: str = "test-run",
) -> IsolationSession:
    """Build an `IsolationSession` bound to the fixture checkout.

    `policy.root` and the constructor's `home=` both point at the
    throwaway `isolation_home` fixture so nothing here ever touches a
    developer's real `~/.maverick/workspaces`.
    """
    policy = IsolationPolicy(
        workflow=workflow,
        root=isolation_home,
        reuse=True,
        retain_on_failure=False,
        fold_scope=(),
        fold_exclusions=(),
    )
    return IsolationSession(
        checkout=CheckoutPath(colocated_repo.cwd),
        policy=policy,
        jj_client=colocated_repo,
        run_id=run_id,
        now=lambda: datetime.now(UTC),
        home=isolation_home,
    )


def _unit(key: str, label: str) -> UnitOfWork:
    return UnitOfWork(key=key, label=label, seed_inputs=())


# ---------------------------------------------------------------------------
# T038 -- contract T9: undo restores the checkout byte-identically,
# including unrelated uncommitted work the user had there before the unit
# started (FR-014, SC-003).
# ---------------------------------------------------------------------------


async def test_undo_restores_checkout_including_unrelated_uncommitted_work(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """The checkout may hold the user's own unrelated, uncommitted edit
    when a unit starts. `undo()` must bring that edit back unchanged --
    not lose it, not merge it with the rejected delta -- while removing
    everything the rejected fold-back applied.

    Mechanism (research.md R5): `jj op restore` rewinds the *operation*,
    so a checkout edit made before the fold-back operation is restored
    exactly as it was, independent of what the fold-back itself did.
    """
    checkout = colocated_repo.cwd
    tracked_path = checkout / "tracked.txt"

    # The user's own unrelated, uncommitted work -- present before the
    # unit is ever leased, and never touched by the workspace at all.
    tracked_path.write_text("checkout wip\n", encoding="utf-8")

    pre_foldback_status = await JjClient(cwd=checkout).status()
    pre_foldback_entries = {entry.name for entry in checkout.iterdir()}

    session = _make_session(colocated_repo, isolation_home)
    unit = _unit("bead-038", "T038 unit")

    async with session:
        async with session.lease(unit) as lease:
            (lease.workspace_path / "new_feature.py").write_text(
                "# rejected work\n", encoding="utf-8"
            )

            result = await session.fold_back(lease)
            assert result.outcome == FoldBackOutcome.APPLIED
            assert (checkout / "new_feature.py").exists()

            await session.undo(lease, result)

    # The unrelated checkout edit survived undo, unchanged.
    assert tracked_path.read_text(encoding="utf-8") == "checkout wip\n"

    # The rejected delta is gone from the checkout.
    assert not (checkout / "new_feature.py").exists()

    # The checkout's file listing and jj status match what they were
    # right before the fold-back -- undo is a full round trip, not just a
    # partial cleanup of the one file we asserted on above.
    assert {entry.name for entry in checkout.iterdir()} == pre_foldback_entries
    post_undo_status = await JjClient(cwd=checkout).status()
    assert post_undo_status.output == pre_foldback_status.output


# ---------------------------------------------------------------------------
# T039 -- contract T10: after undo the workspace still holds the rejected
# delta, so a fix round resumes in place (FR-017).
# ---------------------------------------------------------------------------


async def test_undo_leaves_rejected_delta_in_workspace_for_fix_round(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """`undo()` rewinds the checkout, but the workspace itself must still
    hold the rejected delta afterward -- a fix round needs to resume
    editing exactly where the agent left off, not from a clean workspace.

    Mechanism (research.md R5): `jj op restore` rewinds the workspace's
    working-copy commit too, so the delta the agent wrote is still there
    after the restore.

    Asserted within the same `lease()` block deliberately -- undo must
    happen, and the delta must still be inspectable, before the lease's
    own teardown ever runs.
    """
    session = _make_session(colocated_repo, isolation_home)
    unit = _unit("bead-039", "T039 unit")

    rejected_content = "# work the reviewer rejected, resume here\n"

    async with session:
        async with session.lease(unit) as lease:
            rejected_path = lease.workspace_path / "rejected_work.py"
            rejected_path.write_text(rejected_content, encoding="utf-8")

            result = await session.fold_back(lease)
            assert result.outcome == FoldBackOutcome.APPLIED

            await session.undo(lease, result)

            # Still inside the lease: the delta must still be sitting in
            # the workspace, ready for a fix round to pick up.
            assert rejected_path.exists()
            assert rejected_path.read_text(encoding="utf-8") == rejected_content


# ---------------------------------------------------------------------------
# T040 -- contract T11: an undo failure raises IsolationUndoFailedError,
# leaves the journal record in place, and names both what the checkout now
# contains and how to recover (FR-018).
# ---------------------------------------------------------------------------


async def test_undo_failure_raises_with_recovery_details(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """A `jj op restore` failure during undo must never be swallowed or
    silently retried: it must surface as `IsolationUndoFailedError`
    naming the workspace path (what the checkout may still contain) and
    the restore operation id it was attempting to reach (how to recover
    manually via `jj op restore <id>`).

    Forced by handing `undo()` a `FoldBackResult` with a fabricated,
    non-existent `restore_operation_id` -- `jj op restore` fails for a
    real reason (unknown operation), the same failure mode a corrupted or
    GC'd operation log would produce in production.

    Note: an all-zeros id is *not* usable here -- jj treats it as a valid
    (if destructive) prefix match for the root operation and happily
    restores to it (verified by hand against real jj 0.44). `"f" * 40` is
    not a prefix of any real operation id jj would ever mint, so it
    reliably fails with "No operation ID matching ...".
    """
    session = _make_session(colocated_repo, isolation_home)
    unit = _unit("bead-040", "T040 unit")

    bogus_operation_id = "f" * 40

    async with session:
        async with session.lease(unit) as lease:
            (lease.workspace_path / "work.py").write_text("# in flight\n", encoding="utf-8")

            result = await session.fold_back(lease)
            assert result.outcome == FoldBackOutcome.APPLIED

            bogus_result = dataclasses.replace(result, restore_operation_id=bogus_operation_id)

            with pytest.raises(IsolationUndoFailedError) as excinfo:
                await session.undo(lease, bogus_result)

            error = excinfo.value
            # The typed attributes name what the checkout may still
            # contain (the workspace holding the stranded delta) and how
            # to recover (the operation id a human can hand back to
            # `jj op restore` by hand) -- FR-018's two required facts.
            assert error.workspace_path == str(lease.workspace_path)
            assert error.restore_operation_id == bogus_operation_id
            # The message text itself names the recovery handle too, so
            # the failure is diagnosable from a bare log line alone.
            assert bogus_operation_id in str(error)

    # Contract C5/T11: a failed undo leaves the in-progress application
    # journal record in place (FR-049) so a later `IsolationSession
    # .__aenter__` refuses to start a new unit until a human recovers
    # manually (`IsolationRecoveryRequiredError`, contract C2). The
    # session itself has already exited (releasing the run lock only —
    # the journal is a separate, deliberately-not-cleared marker), so this
    # asserts against the checkout directly.
    journal_path = colocated_repo.cwd / ".maverick" / "runs" / "isolation-journal.json"
    assert journal_path.exists()
    record = json.loads(journal_path.read_text(encoding="utf-8"))
    assert record["unit_key"] == unit.key
    assert record["operation"] == "undo"
    assert record["restore_operation_id"] == bogus_operation_id
