"""Tests for ImplementerActor + ReviewerActor (airframe-stub injection path).

Exercises the supervisor-facing contract (``implementation_ready``,
``fix_result_ready``, ``review_ready``, ``payload_parse_error``,
``prompt_error``) by injecting a stub :class:`StubCodingAgent` /
:class:`StubReviewerAgent` via the actor's ``agent=`` constructor
parameter — no OpenCode subprocess, no airframe SDK adapter, no HTTP
transport.

The shared :func:`pool_address` fixture (see ``conftest.py``) provides
a torn-down-on-exit xoscar pool. Tests register ``__pre_destroy__``-
sensitive actors and destroy them explicitly via :func:`xo.destroy_actor`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import xoscar as xo
from airframe.errors import RuntimeAuthError

from maverick.actors.xoscar.implementer import ImplementerActor
from maverick.actors.xoscar.messages import (
    FlyFixRequest,
    ImplementRequest,
    NewBeadRequest,
    PromptError,
    ReviewRequest,
)
from maverick.actors.xoscar.pool import create_pool
from maverick.actors.xoscar.reviewer import ReviewerActor
from maverick.payloads import (
    SubmitFixResultPayload,
    SubmitImplementationPayload,
    SubmitReviewPayload,
)
from tests.unit.agents.airframe_stubs import StubCodingAgent, StubReviewerAgent


class _SupervisorRecorder(xo.Actor):
    """Captures every supervisor-bound call for later assertion."""

    async def __post_create__(self) -> None:
        self._calls: list[tuple[str, Any]] = []

    @xo.no_lock
    async def implementation_ready(self, payload: SubmitImplementationPayload) -> None:
        self._calls.append(("implementation_ready", payload.model_dump()))

    @xo.no_lock
    async def fix_result_ready(self, payload: SubmitFixResultPayload) -> None:
        self._calls.append(("fix_result_ready", payload.model_dump()))

    @xo.no_lock
    async def correctness_review_ready(self, payload: SubmitReviewPayload) -> None:
        self._calls.append(("correctness_review_ready", payload.model_dump()))

    @xo.no_lock
    async def completeness_review_ready(self, payload: SubmitReviewPayload) -> None:
        self._calls.append(("completeness_review_ready", payload.model_dump()))

    @xo.no_lock
    async def review_ready(self, payload: SubmitReviewPayload) -> None:
        self._calls.append(("review_ready", payload.model_dump()))

    @xo.no_lock
    async def prompt_error(self, error: PromptError) -> None:
        self._calls.append(
            (
                "prompt_error",
                {
                    "phase": error.phase,
                    "error": error.error,
                    "transient": error.transient,
                    "quota_exhausted": error.quota_exhausted,
                    "unit_id": error.unit_id,
                },
            )
        )

    async def get_calls(self) -> list[tuple[str, Any]]:
        return list(self._calls)


@pytest.fixture
async def pool_address() -> AsyncIterator[str]:
    """Yield a torn-down-on-exit xoscar pool address.

    Pattern D: no OpenCode handle to register — the stubbed agent
    bypasses every runtime concern.
    """
    pool, address = await create_pool()
    try:
        yield address
    finally:
        await pool.stop()


# ---------------------------------------------------------------------------
# Implementer
# ---------------------------------------------------------------------------


async def test_implementer_forwards_submit_implementation(pool_address: str) -> None:
    """implement() success path: payload reaches supervisor.implementation_ready."""
    sup = await xo.create_actor(_SupervisorRecorder, address=pool_address, uid="sup-1")
    payload = SubmitImplementationPayload(summary="implemented")
    coder = StubCodingAgent(implement_payloads=[payload])
    impl = await xo.create_actor(
        ImplementerActor,
        sup,
        cwd="/tmp",
        agent=coder,
        address=pool_address,
        uid="impl-1",
    )
    try:
        await impl.send_implement(ImplementRequest(bead_id="b-1", prompt="implement x"))
        calls = await sup.get_calls()
        assert any(name == "implementation_ready" for name, _ in calls)
        assert not any(name == "prompt_error" for name, _ in calls)
        # The agent saw the prompt verbatim.
        assert coder.calls == [("implement", {"prompt": "implement x"})]
    finally:
        await xo.destroy_actor(impl)
        await xo.destroy_actor(sup)


async def test_implementer_forwards_submit_fix_result(pool_address: str) -> None:
    """fix() success path: payload reaches supervisor.fix_result_ready."""
    sup = await xo.create_actor(_SupervisorRecorder, address=pool_address, uid="sup-2")
    payload = SubmitFixResultPayload(summary="fixed")
    coder = StubCodingAgent(fix_payloads=[payload])
    impl = await xo.create_actor(
        ImplementerActor,
        sup,
        cwd="/tmp",
        agent=coder,
        address=pool_address,
        uid="impl-2",
    )
    try:
        await impl.send_fix(FlyFixRequest(bead_id="b-2", prompt="fix x"))
        calls = await sup.get_calls()
        assert any(name == "fix_result_ready" for name, _ in calls)
    finally:
        await xo.destroy_actor(impl)
        await xo.destroy_actor(sup)


async def test_implementer_routes_auth_error_to_prompt_error(pool_address: str) -> None:
    """Airframe RuntimeAuthError surfaces as a classified PromptError."""
    sup = await xo.create_actor(_SupervisorRecorder, address=pool_address, uid="sup-3")
    coder = StubCodingAgent()
    coder.raise_error = RuntimeAuthError("bad key")
    impl = await xo.create_actor(
        ImplementerActor,
        sup,
        cwd="/tmp",
        agent=coder,
        address=pool_address,
        uid="impl-3",
    )
    try:
        await impl.send_implement(ImplementRequest(bead_id="b-3", prompt="x"))
        calls = await sup.get_calls()
        prompt_errors = [c for c in calls if c[0] == "prompt_error"]
        assert len(prompt_errors) == 1
        err = prompt_errors[0][1]
        assert err["phase"] == "implement"
        assert err["unit_id"] == "b-3"
        assert "bad key" in err["error"]
    finally:
        await xo.destroy_actor(impl)
        await xo.destroy_actor(sup)


async def test_implementer_new_bead_rotates_session(pool_address: str) -> None:
    """new_bead() forwards to agent.rotate_session()."""
    sup = await xo.create_actor(_SupervisorRecorder, address=pool_address, uid="sup-4")
    coder = StubCodingAgent(
        implement_payloads=[
            SubmitImplementationPayload(summary="a"),
            SubmitImplementationPayload(summary="b"),
        ]
    )
    impl = await xo.create_actor(
        ImplementerActor,
        sup,
        cwd="/tmp",
        agent=coder,
        address=pool_address,
        uid="impl-4",
    )
    try:
        await impl.send_implement(ImplementRequest(bead_id="b-1", prompt="x"))
        assert coder.rotate_calls == 0
        await impl.new_bead(NewBeadRequest(bead_id="b-2"))
        assert coder.rotate_calls == 1
        await impl.send_implement(ImplementRequest(bead_id="b-2", prompt="y"))
        # Both implement payloads got consumed.
        assert len(coder.implement_payloads) == 0
    finally:
        await xo.destroy_actor(impl)
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Reviewer (smoke — full coverage in test_reviewer_opencode.py)
# ---------------------------------------------------------------------------


async def test_reviewer_forwards_submit_review(pool_address: str) -> None:
    """review() payload reaches both per-kind and back-compat methods."""
    sup = await xo.create_actor(_SupervisorRecorder, address=pool_address, uid="sup-r")
    payload = SubmitReviewPayload(approved=True)
    reviewer_agent = StubReviewerAgent(
        review_kind="correctness", review_payloads=[payload]
    )
    reviewer = await xo.create_actor(
        ReviewerActor,
        sup,
        cwd="/tmp",
        review_kind="correctness",
        agent=reviewer_agent,
        address=pool_address,
        uid="rev-1",
    )
    try:
        await reviewer.send_review(
            ReviewRequest(
                bead_id="b-1",
                bead_description="x",
                work_unit_md="md",
                briefing_context="",
            )
        )
        calls = await sup.get_calls()
        # Correctness lens lands twice: typed correctness_review_ready
        # + back-compat review_ready fan-out.
        assert any(name == "correctness_review_ready" for name, _ in calls)
        assert any(name == "review_ready" for name, _ in calls)
    finally:
        await xo.destroy_actor(reviewer)
        await xo.destroy_actor(sup)
