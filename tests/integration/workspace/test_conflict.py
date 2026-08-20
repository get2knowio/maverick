"""Contract test for `IsolationSession.fold_back()`'s conflict handling.

Covers tasks.md T027 -- contract T8
(specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md,
"Divergent edit to the same file -> CONFLICT, paths named, checkout
unchanged", FR-008, SC-005).

Background (research.md R4, validated against real jj 0.44): jj does not
fail on a conflicting squash -- it *materializes* a conflict. A checkout
edit to `a.txt` (uncommitted) plus a divergent workspace edit to the same
`a.txt`, both starting from the same base, squash cleanly (exit 0!) but
leave `@` conflicted:

    $ jj squash --from 'ws1@' --into @ '~.maverick'
    Once the conflicts are resolved, you can inspect the result with `jj diff`.
    $ jj status
    Working copy  (@) : xwktyysp 44433777 (conflict) (no description set)
    Warning: There are unresolved conflicts at these paths:
    a.txt    2-sided conflict

So the exit code is not the signal -- the implementation must detect this
via jj's `conflicts()` revset (contract C4 step 5) and respond by
restoring the checkout to its pre-squash operation, returning
`FoldBackOutcome.CONFLICT` with `conflicting_paths` populated. The checkout
must end up **unchanged** by the attempt, not left mid-conflict.

None of `src/maverick/workspace/{session,foldback,models}.py`'s
isolation-primitive surface exists yet at the time this file is written
(TDD red phase) -- every test here is expected to fail on import
(`ImportError`/`ModuleNotFoundError`) until a later phase implements
`maverick.workspace.IsolationSession` and friends. That failure mode is
the point, not a bug in this file.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from maverick.jj.client import JjClient
from maverick.workspace import (
    FoldBackOutcome,
    IsolationPolicy,
    IsolationSession,
    UnitOfWork,
)

pytestmark = pytest.mark.integration

# The fixture seeds tracked.txt with this exact content -- see
# tests/integration/workspace/conftest.py's colocated_repo.
_BASE_CONTENT = "tracked\n"
_CHECKOUT_EDIT = "checkout's own divergent edit\n"
_WORKSPACE_EDIT = "workspace's own divergent edit\n"


def _fixed_now() -> datetime:
    """A deterministic clock -- the primitive never calls `datetime.now()`
    directly (054's clock-seam convention, reused here for `IsolationLease
    .created_at`)."""
    return datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)


def _policy(*, root: Path, workflow: str = "test-workflow") -> IsolationPolicy:
    return IsolationPolicy(workflow=workflow, root=root)


async def test_divergent_edit_yields_conflict_and_leaves_checkout_unchanged(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """T027: a divergent edit to `tracked.txt` in both the checkout and the
    workspace, starting from the same base, must fold back as `CONFLICT`
    with `tracked.txt` named in `conflicting_paths` and the diagnostic --
    and the checkout must be left exactly as the checkout's own edit made
    it, with no unresolved-conflict marker (contract T8, FR-008, SC-005).
    """
    checkout = colocated_repo.cwd
    tracked_path = checkout / "tracked.txt"
    assert tracked_path.read_text(encoding="utf-8") == _BASE_CONTENT

    policy = _policy(root=isolation_home)
    session = IsolationSession(
        checkout=checkout,
        policy=policy,
        jj_client=colocated_repo,
        run_id="run-t027",
        now=_fixed_now,
        home=isolation_home,
    )
    unit = UnitOfWork(key="bd-1", label="Divergent edit")

    async with session:
        async with session.lease(unit) as lease:
            # The workspace forked from the checkout's @ at lease-creation
            # time, so both edits below start from the same base
            # (_BASE_CONTENT) -- neither side is aware of the other, which
            # is exactly the scenario research.md R4 validated.
            workspace_tracked_path = lease.workspace_path / "tracked.txt"
            assert workspace_tracked_path.read_text(encoding="utf-8") == _BASE_CONTENT

            # Divergent edit #1: directly in the checkout, uncommitted.
            tracked_path.write_text(_CHECKOUT_EDIT, encoding="utf-8")

            # Divergent edit #2: independently, inside the workspace.
            workspace_tracked_path.write_text(_WORKSPACE_EDIT, encoding="utf-8")

            result = await session.fold_back(lease)

            assert result.outcome == FoldBackOutcome.CONFLICT

            # Every conflicting path is named, and it is never empty on
            # CONFLICT (data-model.md's FoldBackResult contract, SC-005).
            assert result.conflicting_paths
            assert "tracked.txt" in result.conflicting_paths

            # The diagnostic names the conflicting path too.
            assert "tracked.txt" in result.diagnostic

            # The restore-on-conflict handle was populated -- the operation
            # captured before the squash, used to roll the checkout back.
            assert result.restore_operation_id

            # The checkout is left exactly as the checkout's own edit made
            # it -- not the workspace's content, not a jj conflict-marker
            # blob, not corrupted (SC-005's "checkout left unchanged").
            assert tracked_path.read_text(encoding="utf-8") == _CHECKOUT_EDIT

        # And the checkout shows no unresolved conflict once fold-back has
        # restored it -- read via a fresh client, independent of whatever
        # internal state the session holds.
        fresh_status = await JjClient(cwd=checkout).status()
        assert fresh_status.conflict is False


async def test_session_remains_usable_after_a_conflict(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """A CONFLICT outcome must not corrupt the session's ability to keep
    going: after restoring the checkout, a second, unrelated unit of work
    -- touching a different file -- must still be able to lease and fold
    back cleanly (contract C4's "no partial delta left behind" and C7's
    per-entry isolation, exercised end to end through a real conflict
    rather than asserted in isolation).
    """
    checkout = colocated_repo.cwd
    tracked_path = checkout / "tracked.txt"
    readme_path = checkout / "README.md"

    policy = _policy(root=isolation_home)
    session = IsolationSession(
        checkout=checkout,
        policy=policy,
        jj_client=colocated_repo,
        run_id="run-t027-continuity",
        now=_fixed_now,
        home=isolation_home,
    )

    conflicting_unit = UnitOfWork(key="bd-conflict", label="Divergent edit")
    clean_unit = UnitOfWork(key="bd-clean", label="Unrelated, clean edit")

    async with session:
        async with session.lease(conflicting_unit) as lease:
            tracked_path.write_text(_CHECKOUT_EDIT, encoding="utf-8")
            (lease.workspace_path / "tracked.txt").write_text(_WORKSPACE_EDIT, encoding="utf-8")
            first_result = await session.fold_back(lease)

        assert first_result.outcome == FoldBackOutcome.CONFLICT

        async with session.lease(clean_unit) as lease:
            (lease.workspace_path / "README.md").write_text(
                "# repo\n\nupdated by the second, unrelated unit\n",
                encoding="utf-8",
            )
            second_result = await session.fold_back(lease)

    assert second_result.outcome == FoldBackOutcome.APPLIED
    assert "README.md" in second_result.applied_paths
    assert readme_path.read_text(encoding="utf-8") == (
        "# repo\n\nupdated by the second, unrelated unit\n"
    )
    # The first unit's rejected edit never leaked into the checkout.
    assert tracked_path.read_text(encoding="utf-8") == _CHECKOUT_EDIT
