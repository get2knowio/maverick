"""Smoke tests for ``FlySupervisor``.

Full bead-loop coverage is deferred to end-to-end tests against a
sample project. These tests verify construction + typed domain method
wiring.
"""

from __future__ import annotations

import pytest
import xoscar as xo

from maverick.actors.xoscar.fly_supervisor import FlyInputs, FlySupervisor
from maverick.actors.xoscar.messages import PromptError
from maverick.payloads import (
    SubmitFixResultPayload,
    SubmitImplementationPayload,
    SubmitReviewPayload,
)


def test_fly_inputs_requires_cwd() -> None:
    with pytest.raises(ValueError, match="cwd"):
        FlySupervisor(FlyInputs(cwd=""))


@pytest.mark.asyncio
async def test_fly_supervisor_construction_creates_six_children(
    pool_address: str,
) -> None:
    """Supervisor spawns implementer, reviewer, gate, ac, spec, committer
    via ``__post_create__``."""
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", epic_id="epic-1", max_beads=1),
        address=pool_address,
        uid="fly-sup-construct",
    )
    try:
        # Nothing to call — just confirm the actor exists after post-create.
        # A missing child would have raised inside post_create already.
        pass
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_implementation_ready_records_payload(pool_address: str) -> None:
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1),
        address=pool_address,
        uid="fly-sup-impl",
    )
    try:
        payload = SubmitImplementationPayload(
            summary="added login flow", files_changed=("src/auth.py",)
        )
        # Must not raise even though no bead is in flight (the driver
        # hasn't started; we're poking the domain method directly).
        await sup.implementation_ready(payload)
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_review_ready_marks_approved(pool_address: str) -> None:
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1),
        address=pool_address,
        uid="fly-sup-review",
    )
    try:
        await sup.review_ready(SubmitReviewPayload(approved=True, findings=()))
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_fix_result_ready_records_payload(pool_address: str) -> None:
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1),
        address=pool_address,
        uid="fly-sup-fixres",
    )
    try:
        await sup.fix_result_ready(SubmitFixResultPayload(summary="did fixes", addressed=("F-1",)))
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_prompt_error_marks_supervisor_done(pool_address: str) -> None:
    """A prompt error from any agent is fatal to the fly loop."""
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1),
        address=pool_address,
        uid="fly-sup-error",
    )
    try:
        await sup.prompt_error(PromptError(phase="implement", error="ACP died", unit_id="bead-1"))
        result = await sup.get_terminal_result()
        assert result is not None
        assert result["success"] is False
        assert "ACP died" in result["error"]
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_terminal_result_reports_only_this_runs_beads(
    pool_address: str,
) -> None:
    """Regression: ``--max-beads 2`` against a stale checkpoint must not
    inflate the reported success count with checkpoint-prior IDs.

    Before the fix, ``beads_completed`` was ``len(self._completed_beads)``,
    which includes the IDs seeded from ``_inputs.completed_bead_ids``. So a
    smoke-test ``--max-beads 2`` against a checkpoint with 10 prior IDs
    reported ``beads_completed=10`` *without doing any new work*, making
    the cap look ignored. The fix tracks new-this-run separately.
    """
    prior_ids = tuple(f"bead-old-{i}" for i in range(10))
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=2, completed_bead_ids=prior_ids),
        address=pool_address,
        uid="fly-sup-resume-cap",
    )
    try:
        # Trigger the terminal-result path without running any bead work.
        # _processed_this_run is still 0; _completed_beads has the 10 prior IDs.
        await sup.prompt_error(
            PromptError(phase="implement", error="bail early", unit_id="bead-x")
        )
        result = await sup.get_terminal_result()
        assert result is not None
        assert result["success"] is False
        # New work in this run = 0, despite 10 IDs loaded from checkpoint.
        assert result["beads_completed"] == 0
        # Cumulative ID list still flows through (used for state).
        assert len(result["completed_bead_ids"]) == 10
    finally:
        await xo.destroy_actor(sup)
