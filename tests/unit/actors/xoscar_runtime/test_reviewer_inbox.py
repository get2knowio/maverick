"""Unit tests for :class:`ReviewerActor` (airframe-stub injection path).

Exercises the supervisor-facing contract:

* ``send_review`` forwards :class:`SubmitReviewPayload` to the typed
  ``correctness_review_ready`` / ``completeness_review_ready`` methods
  and the back-compat ``review_ready`` method.
* Airframe runtime errors translate to :class:`PromptError` via
  ``prompt_error`` with ``transient`` / ``quota_exhausted`` flags set
  by the existing classifiers.
* ``send_aggregate_review`` routes failures through
  ``payload_parse_error`` (non-fatal at the workflow level) and success
  through ``aggregate_review_ready``.
* ``new_bead`` forwards to ``agent.rotate_session()``.

Uses :class:`StubReviewerAgent` as the ``agent=`` injection — no
real adapter SDK, no HTTP transport. Prompt-content and session-id
tests from the legacy substrate file were dropped — those exercise
behavior that is now the agent's business, not the actor shell's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import xoscar as xo
from airframe.errors import RuntimeAuthError

from maverick.actors.xoscar.messages import (
    AggregateReviewRequest,
    NewBeadRequest,
    PromptError,
    ReviewRequest,
)
from maverick.actors.xoscar.pool import create_pool
from maverick.actors.xoscar.reviewer import ReviewerActor
from maverick.payloads import ReviewFindingPayload, SubmitReviewPayload
from tests.unit.agents.airframe_stubs import StubReviewerAgent


class _SupervisorSpy(xo.Actor):
    async def __post_create__(self) -> None:
        self._review_ready_calls: list[SubmitReviewPayload] = []
        self._correctness_calls: list[SubmitReviewPayload] = []
        self._completeness_calls: list[SubmitReviewPayload] = []
        self._aggregate_calls: list[SubmitReviewPayload] = []
        self._prompt_errors: list[PromptError] = []
        self._payload_parse_errors: list[tuple[str, str]] = []

    @xo.no_lock
    async def review_ready(self, payload: SubmitReviewPayload) -> None:
        self._review_ready_calls.append(payload)

    @xo.no_lock
    async def correctness_review_ready(self, payload: SubmitReviewPayload) -> None:
        self._correctness_calls.append(payload)

    @xo.no_lock
    async def completeness_review_ready(self, payload: SubmitReviewPayload) -> None:
        self._completeness_calls.append(payload)

    @xo.no_lock
    async def aggregate_review_ready(self, payload: SubmitReviewPayload) -> None:
        self._aggregate_calls.append(payload)

    @xo.no_lock
    async def prompt_error(self, error: PromptError) -> None:
        self._prompt_errors.append(error)

    @xo.no_lock
    async def payload_parse_error(self, tool: str, message: str) -> None:
        self._payload_parse_errors.append((tool, message))

    async def get_state(self) -> dict[str, Any]:
        return {
            "review_ready": [p.model_dump() for p in self._review_ready_calls],
            "correctness_ready": [p.model_dump() for p in self._correctness_calls],
            "completeness_ready": [p.model_dump() for p in self._completeness_calls],
            "aggregate": [p.model_dump() for p in self._aggregate_calls],
            "prompt_errors": [
                {
                    "phase": e.phase,
                    "error": e.error,
                    "transient": e.transient,
                    "quota_exhausted": e.quota_exhausted,
                    "unit_id": e.unit_id,
                }
                for e in self._prompt_errors
            ],
            "payload_parse_errors": list(self._payload_parse_errors),
        }


@pytest.fixture
async def review_pool() -> AsyncIterator[str]:
    """Torn-down-on-exit xoscar pool; no runtime registration."""
    pool, address = await create_pool()
    try:
        yield address
    finally:
        await pool.stop()


def _approved_payload() -> SubmitReviewPayload:
    return SubmitReviewPayload(approved=True)


def _findings_payload(*findings: dict[str, Any]) -> SubmitReviewPayload:
    return SubmitReviewPayload(
        approved=False,
        findings=tuple(ReviewFindingPayload.model_validate(f) for f in findings),
    )


# ---------------------------------------------------------------------------
# Per-bead review
# ---------------------------------------------------------------------------


async def test_review_success_routes_to_supervisor(review_pool: str) -> None:
    """Correctness payload reaches both typed and back-compat methods."""
    sup = await xo.create_actor(_SupervisorSpy, address=review_pool, uid="sup-rev-1")
    reviewer_agent = StubReviewerAgent(
        review_kind="correctness",
        review_payloads=[_approved_payload()],
    )
    reviewer = await xo.create_actor(
        ReviewerActor,
        sup,
        cwd="/tmp",
        review_kind="correctness",
        agent=reviewer_agent,
        address=review_pool,
        uid="rev-1",
    )
    try:
        await reviewer.send_review(
            ReviewRequest(
                bead_id="bead-1",
                bead_description="Add a docstring",
                work_unit_md="md",
                briefing_context="",
            )
        )
        state = await sup.get_state()
        assert len(state["correctness_ready"]) == 1
        assert state["correctness_ready"][0]["approved"] is True
        # Back-compat fan-out.
        assert len(state["review_ready"]) == 1
        assert state["prompt_errors"] == []
    finally:
        await xo.destroy_actor(reviewer)
        await xo.destroy_actor(sup)


async def test_review_with_findings_routes_payload(review_pool: str) -> None:
    """Findings round-trip through the actor and arrive typed."""
    sup = await xo.create_actor(_SupervisorSpy, address=review_pool, uid="sup-rev-2")
    finding = {"severity": "major", "issue": "missing test", "file": "x.py"}
    reviewer_agent = StubReviewerAgent(
        review_kind="completeness",
        review_payloads=[_findings_payload(finding)],
    )
    reviewer = await xo.create_actor(
        ReviewerActor,
        sup,
        cwd="/tmp",
        review_kind="completeness",
        agent=reviewer_agent,
        address=review_pool,
        uid="rev-2",
    )
    try:
        await reviewer.send_review(
            ReviewRequest(
                bead_id="bead-2",
                bead_description="x",
                work_unit_md="md",
                briefing_context="",
            )
        )
        state = await sup.get_state()
        assert len(state["completeness_ready"]) == 1
        delivered: dict = state["completeness_ready"][0]
        assert delivered["approved"] is False
        assert len(delivered["findings"]) == 1
        validated = SubmitReviewPayload.model_validate(delivered)
        assert isinstance(validated.findings[0], ReviewFindingPayload)
        assert validated.findings[0].severity == "major"
    finally:
        await xo.destroy_actor(reviewer)
        await xo.destroy_actor(sup)


async def test_review_auth_error_routes_to_prompt_error(review_pool: str) -> None:
    sup = await xo.create_actor(_SupervisorSpy, address=review_pool, uid="sup-rev-3")
    reviewer_agent = StubReviewerAgent()
    reviewer_agent.raise_error = RuntimeAuthError("bad key")
    reviewer = await xo.create_actor(
        ReviewerActor,
        sup,
        cwd="/tmp",
        agent=reviewer_agent,
        address=review_pool,
        uid="rev-3",
    )
    try:
        await reviewer.send_review(
            ReviewRequest(
                bead_id="bead-3",
                bead_description="x",
                work_unit_md="md",
                briefing_context="",
            )
        )
        state = await sup.get_state()
        assert state["review_ready"] == []
        assert len(state["prompt_errors"]) == 1
        err = state["prompt_errors"][0]
        assert err["phase"] == "review"
        assert err["unit_id"] == "bead-3"
        assert "bad key" in err["error"]
    finally:
        await xo.destroy_actor(reviewer)
        await xo.destroy_actor(sup)


async def test_new_bead_rotates_agent_session(review_pool: str) -> None:
    """new_bead forwards to agent.rotate_session()."""
    sup = await xo.create_actor(_SupervisorSpy, address=review_pool, uid="sup-rev-5")
    reviewer_agent = StubReviewerAgent()
    reviewer = await xo.create_actor(
        ReviewerActor,
        sup,
        cwd="/tmp",
        agent=reviewer_agent,
        address=review_pool,
        uid="rev-5",
    )
    try:
        assert reviewer_agent.rotate_calls == 0
        await reviewer.new_bead(NewBeadRequest(bead_id="b2"))
        assert reviewer_agent.rotate_calls == 1
    finally:
        await xo.destroy_actor(reviewer)
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Aggregate review
# ---------------------------------------------------------------------------


async def test_aggregate_success_routes_to_supervisor(review_pool: str) -> None:
    sup = await xo.create_actor(_SupervisorSpy, address=review_pool, uid="sup-agg-1")
    reviewer_agent = StubReviewerAgent(aggregate_payloads=[_approved_payload()])
    reviewer = await xo.create_actor(
        ReviewerActor,
        sup,
        cwd="/tmp",
        agent=reviewer_agent,
        address=review_pool,
        uid="rev-agg-1",
    )
    try:
        await reviewer.send_aggregate_review(
            AggregateReviewRequest(
                objective="ship feature",
                bead_list="bead 1\nbead 2",
                diff_stat="x | 1 +",
                bead_count=2,
            )
        )
        state = await sup.get_state()
        assert len(state["aggregate"]) == 1
        assert state["payload_parse_errors"] == []
    finally:
        await xo.destroy_actor(reviewer)
        await xo.destroy_actor(sup)


async def test_aggregate_failure_routes_to_payload_parse_error(
    review_pool: str,
) -> None:
    """Aggregate failures must NOT raise prompt_error — they're non-fatal."""
    sup = await xo.create_actor(_SupervisorSpy, address=review_pool, uid="sup-agg-2")
    reviewer_agent = StubReviewerAgent()
    reviewer_agent.raise_error = RuntimeAuthError("auth")
    reviewer = await xo.create_actor(
        ReviewerActor,
        sup,
        cwd="/tmp",
        agent=reviewer_agent,
        address=review_pool,
        uid="rev-agg-2",
    )
    try:
        await reviewer.send_aggregate_review(
            AggregateReviewRequest(objective="x", bead_list="y", diff_stat="z", bead_count=1)
        )
        state = await sup.get_state()
        assert state["aggregate"] == []
        assert state["prompt_errors"] == []
        assert len(state["payload_parse_errors"]) == 1
        tool, msg = state["payload_parse_errors"][0]
        assert tool == "aggregate_review"
        assert "auth" in msg
    finally:
        await xo.destroy_actor(reviewer)
        await xo.destroy_actor(sup)
