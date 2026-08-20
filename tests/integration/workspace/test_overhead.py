"""Overhead-budget integration test for the isolation primitive.

Contract: `specs/057-isolated-bead-workspaces/spec.md` FR-050/SC-012 —
provisioning, fold-back, and teardown combined must add no more than 5
seconds of overhead per unit of work.

This measures the primitive's own overhead directly — `IsolationSession
.lease()` (provision on entry, teardown on exit) wrapping a `fold_back()`
call — rather than driving the full `maverick fly` workflow. That keeps the
test fast, deterministic, and free of agent/model stubbing: FR-050's budget
is about the primitive's mechanics (jj workspace add / squash / workspace
forget), not about anything an agent does in between, so timing those three
steps in isolation is a faithful, much cheaper proxy for the same
measurement the success criterion describes (isolated run minus normal run,
divided by unit count) — the "normal run" side of that difference is zero
seconds of primitive overhead by construction, so the isolated side's
per-unit cost *is* the overhead.

Task ID (tasks.md): T111.
"""

from __future__ import annotations

import time
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
from maverick.workspace.models import CheckoutPath

pytestmark = pytest.mark.integration

#: "per unit of work" implies averaging over several units to smooth out
#: one-off scheduling hiccups, per FR-050's own wording — not a single
#: sample.
_UNIT_COUNT = 5

#: FR-050 / SC-012's budget. 5s is generous for work that should normally
#: take well under 1s on typical hardware, so a plain average-of-N assertion
#: is robust without extra statistical machinery.
_MAX_AVERAGE_OVERHEAD_SECONDS = 5.0


def _make_session(colocated_repo: JjClient, isolation_home: Path) -> IsolationSession:
    """An `IsolationSession` bound to the fixture checkout, mirroring
    `test_foldback.py`'s `_make_session` helper (T111 must not modify
    `conftest.py`, so this is a private, file-local copy)."""
    policy = IsolationPolicy(
        workflow="overhead",
        root=isolation_home,
        reuse=False,
        retain_on_failure=False,
        fold_scope=(),
        fold_exclusions=(),
    )
    return IsolationSession(
        checkout=CheckoutPath(colocated_repo.cwd),
        policy=policy,
        jj_client=colocated_repo,
        run_id="test-overhead-run",
        now=lambda: datetime.now(UTC),
        home=isolation_home,
    )


async def test_provision_foldback_teardown_average_overhead_within_budget(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """FR-050/SC-012: averaged over several units, provision + fold-back +
    teardown must add no more than 5 seconds of overhead per unit.

    For each of `_UNIT_COUNT` units: time from just before `session.lease()`
    provisions a fresh workspace, through writing a couple of small files
    (simulating agent work) and folding them back, to just after the
    `lease()` context manager's teardown on exit. `IsolationSession
    .__aenter__`/`__aexit__` (the checkout-wide run lock) is deliberately
    excluded from the timed region — it runs once per session, not once per
    unit, and FR-050's budget is specifically "per unit of work".
    """
    session = _make_session(colocated_repo, isolation_home)
    elapsed_per_unit: list[float] = []

    async with session:
        for i in range(_UNIT_COUNT):
            unit = UnitOfWork(key=f"overhead-{i}", label=f"Overhead unit {i}")

            start = time.perf_counter()
            async with session.lease(unit) as lease:
                # A couple of small writes, simulating an agent step's
                # output — nothing elaborate, per the task's guidance.
                (lease.workspace_path / f"agent-output-{i}.txt").write_text(
                    f"work item {i}\n", encoding="utf-8"
                )
                (lease.workspace_path / f"notes-{i}.md").write_text(
                    f"# unit {i}\nsome notes from the simulated agent step\n",
                    encoding="utf-8",
                )

                result = await session.fold_back(lease)
                assert result.outcome == FoldBackOutcome.APPLIED, (
                    f"unit {i}: expected fold_back() to report APPLIED for a "
                    f"real delta, got {result.outcome!r} — the overhead "
                    "measurement below would be meaningless if fold-back "
                    "didn't actually move anything."
                )
            # `lease()`'s context manager tears the workspace down (or
            # retains it, per policy — not here since retain_on_failure is
            # False and nothing raised) on exit, so this includes teardown.
            elapsed_per_unit.append(time.perf_counter() - start)

            assert (colocated_repo.cwd / f"agent-output-{i}.txt").exists(), (
                f"unit {i}: fold-back reported APPLIED but the file never "
                "reached the checkout — measuring overhead over a no-op "
                "would understate real cost."
            )

    average = sum(elapsed_per_unit) / len(elapsed_per_unit)
    assert average <= _MAX_AVERAGE_OVERHEAD_SECONDS, (
        f"average per-unit provision+fold-back+teardown overhead "
        f"{average:.3f}s exceeds the {_MAX_AVERAGE_OVERHEAD_SECONDS}s budget "
        f"(FR-050, SC-012). Per-unit timings (s): "
        f"{[round(t, 3) for t in elapsed_per_unit]}"
    )
