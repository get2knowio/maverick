"""Integration tests for the artifact-level / environment-level check
placement contract that a *consumer* of `IsolationSession` (US3's
`maverick fly --isolated` Burr actions) must follow.

Contract: `specs/057-isolated-bead-workspaces/research.md` R6 ("Two check
placements: artifact-level checks run inside the workspace, before
fold-back ... environment-level checks run against the checkout, after
fold-back ... On environment-level rejection, `session.undo()` runs, and
the outcome is recorded as `FoldBackOutcome.REJECTED` — distinguishable
from `CONFLICT` (fold-back mechanics) and `DISCARDED` (agent failure)").
See also `specs/057-isolated-bead-workspaces/data-model.md`'s
`FoldBackOutcome`/`REJECTED` section and
`specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md`.

`IsolationSession` has no dedicated "run a check" method — per the
contract, "the primitive doesn't run checks itself": provisioning,
fold-back, and undo are all it owns. Artifact-level and environment-level
checks are the caller's responsibility. These tests are therefore small
simulations of the consumer pattern a workflow action follows, written
entirely against `IsolationSession`'s existing public surface
(`lease`, `fold_back`, `undo`) — they are not exercising a not-yet-built
API.

Task IDs (tasks.md): T045, T046.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

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
        run_id="test-run",
        now=lambda: datetime.now(UTC),
        home=isolation_home,
    )


def _unit(key: str, label: str) -> UnitOfWork:
    return UnitOfWork(key=key, label=label, seed_inputs=())


# ---------------------------------------------------------------------------
# T045 -- an artifact-level check failure discards the delta without ever
# reaching the checkout (FR-013, US2 acceptance scenario 1).
# ---------------------------------------------------------------------------


def _artifact_level_check(workspace_path: Path) -> str | None:
    """Simulate a consumer's artifact-level check: a plain Python
    assertion over the workspace's produced files, no toolchain needed.

    Returns a failure reason, or `None` if the check passes. Here: a
    required marker file (standing in for e.g. "the agent must produce
    a MANIFEST") is missing.
    """
    marker = workspace_path / "MANIFEST.txt"
    if not marker.exists():
        return "artifact-level check failed: MANIFEST.txt was not produced"
    return None


async def test_artifact_level_check_failure_discards_without_reaching_checkout(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """When an artifact-level check fails on the workspace's own files,
    the correct consumer behavior is to never call `session.fold_back()`
    at all -- letting the lease exit without folding back. The checkout
    must be left byte-identical to its pre-lease state, exactly as if the
    unit had never run (same technique as `test_foldback.py`'s T029: a
    discarded delta must never partially or fully reach the checkout).
    """
    tracked_before = (colocated_repo.cwd / "tracked.txt").read_bytes()
    readme_before = (colocated_repo.cwd / "README.md").read_bytes()
    entries_before = {entry.name for entry in colocated_repo.cwd.iterdir()}

    session = _make_session(colocated_repo, isolation_home)
    unit = _unit("bead-045", "T045 unit")

    async with session:
        async with session.lease(unit) as lease:
            # Simulate an agent step's output: a real file, but not the
            # one the artifact-level check requires.
            (lease.workspace_path / "partial-output.txt").write_text(
                "agent wrote something, but not the required manifest\n",
                encoding="utf-8",
            )
            (lease.workspace_path / "tracked.txt").write_text(
                "edited in the workspace, never folded back\n", encoding="utf-8"
            )

            failure_reason = _artifact_level_check(lease.workspace_path)

            assert failure_reason is not None
            assert "MANIFEST.txt" in failure_reason

            # The consumer's correct reaction to an artifact-level check
            # failure: do NOT call session.fold_back(lease). Let the
            # lease exit and its lifecycle (teardown/retain) handle
            # cleanup. Nothing below this point calls fold_back().

    # The checkout is untouched -- the delta never reached it.
    assert (colocated_repo.cwd / "tracked.txt").read_bytes() == tracked_before
    assert (colocated_repo.cwd / "README.md").read_bytes() == readme_before
    assert {entry.name for entry in colocated_repo.cwd.iterdir()} == entries_before
    assert not (colocated_repo.cwd / "partial-output.txt").exists()

    checkout_status = await JjClient(cwd=colocated_repo.cwd).status()
    assert "The working copy has no changes." in checkout_status.output


# ---------------------------------------------------------------------------
# T046 -- after an environment-level rejection, the verification output is
# available to the fix round alongside the rejected delta, not just the
# delta (FR-017, US2 acceptance scenario 4).
# ---------------------------------------------------------------------------


def _environment_level_check(checkout_path: Path) -> str | None:
    """Simulate a consumer's environment-level check: something that
    needs the checkout's own toolchain/environment (here, standing in
    for a real lint/test/format gate with a trivial failing subprocess
    run against the checkout -- not the workspace, which is exactly
    the point: this class of check cannot run inside the workspace
    because a `.venv`/installed toolchain doesn't travel there).

    Returns a captured verification-output string on failure, or `None`
    if the check passes.
    """
    completed = subprocess.run(
        [sys.executable, "-c", "import sys; sys.exit(1)"],
        cwd=checkout_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return "gate failed: 3 lint errors"
    return None


async def test_environment_level_rejection_preserves_output_and_delta_for_fix_round(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """After fold-back applies a delta, an environment-level check run
    against the *checkout* (never the workspace -- it needs the real
    toolchain) can still reject it. On rejection the consumer calls
    `session.undo()`, and afterward:

    (a) the checkout is restored -- the applied file is gone, unrelated
        pre-existing checkout content intact (mirrors `test_undo.py`'s
        T038 idiom);
    (b) the workspace still holds the rejected delta, inspected here
        while still inside the same `lease()` block (mirrors
        `test_undo.py`'s T039 idiom), ready for a fix round to resume
        from;
    (c) the captured verification output string is still available in
        the same scope, alongside that delta -- demonstrating a fix-round
        consumer would have both simultaneously, not just the delta.

    `FoldBackResult` is frozen, so per research.md R6 marking the outcome
    `REJECTED` is a caller-applied relabeling via `dataclasses.replace`
    -- not something `fold_back()`/`undo()` themselves return.
    """
    checkout = colocated_repo.cwd
    readme_before = (checkout / "README.md").read_bytes()

    session = _make_session(colocated_repo, isolation_home)
    unit = _unit("bead-046", "T046 unit")

    rejected_content = "# work an environment-level gate rejected\n"

    async with session:
        async with session.lease(unit) as lease:
            rejected_path = lease.workspace_path / "gated_work.py"
            rejected_path.write_text(rejected_content, encoding="utf-8")

            result = await session.fold_back(lease)
            assert result.outcome == FoldBackOutcome.APPLIED
            assert (checkout / "gated_work.py").exists()

            # Environment-level check: runs against the checkout, after
            # fold-back, because it needs a toolchain that doesn't
            # travel into the workspace.
            verification_output = _environment_level_check(checkout)
            assert verification_output is not None
            assert verification_output == "gate failed: 3 lint errors"

            # Consumer reaction to an environment-level rejection:
            # undo the fold-back...
            await session.undo(lease, result)

            # ...and relabel the outcome as REJECTED for reporting --
            # a caller-side relabeling, since FoldBackResult is frozen
            # and fold_back()/undo() never return REJECTED themselves.
            rejected_result = dataclasses.replace(result, outcome=FoldBackOutcome.REJECTED)
            assert rejected_result.outcome == FoldBackOutcome.REJECTED
            # Everything else about the original successful fold-back is
            # preserved verbatim -- REJECTED is purely a relabeling.
            assert rejected_result.applied_paths == result.applied_paths
            assert rejected_result.conflicting_paths == result.conflicting_paths
            assert rejected_result.restore_operation_id == result.restore_operation_id
            assert rejected_result.diagnostic == result.diagnostic
            assert rejected_result.duration_seconds == result.duration_seconds

            # (a) checkout restored: the applied file is gone.
            assert not (checkout / "gated_work.py").exists()

            # (b) workspace still holds the rejected delta, still
            # inspectable inside this same lease.
            assert rejected_path.exists()
            assert rejected_path.read_text(encoding="utf-8") == rejected_content

            # (c) both the verification output and the rejected delta
            # are simultaneously available in the same scope -- exactly
            # what a fix-round consumer needs.
            assert verification_output
            assert rejected_path.read_text(encoding="utf-8")

    # (a) continued: unrelated pre-existing checkout content intact.
    assert (checkout / "README.md").read_bytes() == readme_before
