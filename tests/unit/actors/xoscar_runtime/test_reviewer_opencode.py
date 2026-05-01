"""Unit tests for :class:`OpenCodeReviewerActor`.

Exercises the supervisor-facing contract:

* ``send_review`` forwards :class:`SubmitReviewPayload` to
  ``review_ready`` on success.
* OpenCode errors are translated to :class:`PromptError` via
  ``prompt_error``, with ``transient`` / ``quota_exhausted`` flags set
  by the existing classifiers.
* ``send_aggregate_review`` routes failures through
  ``payload_parse_error`` (non-fatal at the workflow level) and success
  through ``aggregate_review_ready``.
* ``new_bead`` rotates the OpenCode session.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import xoscar as xo

from maverick.actors.xoscar.messages import (
    AggregateReviewRequest,
    NewBeadRequest,
    PromptError,
    ReviewRequest,
)
from maverick.actors.xoscar.pool import create_pool
from maverick.actors.xoscar.reviewer_opencode import OpenCodeReviewerActor
from maverick.runtime.opencode import (
    OpenCodeAuthError,
    OpenCodeServerHandle,
    SendResult,
    invalidate_cache,
    register_opencode_handle,
    unregister_opencode_handle,
)
from maverick.tools.agent_inbox.models import ReviewFindingPayload, SubmitReviewPayload

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeProcess:
    pid = 0
    returncode = 0

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return 0


def _fake_handle() -> OpenCodeServerHandle:
    return OpenCodeServerHandle(
        base_url="http://fake-opencode",
        password="fake",
        pid=0,
        _process=_FakeProcess(),  # type: ignore[arg-type]
    )


class _SupervisorSpy(xo.Actor):
    async def __post_create__(self) -> None:
        self._review_ready_calls: list[SubmitReviewPayload] = []
        self._aggregate_calls: list[SubmitReviewPayload] = []
        self._prompt_errors: list[PromptError] = []
        self._payload_parse_errors: list[tuple[str, str]] = []

    @xo.no_lock
    async def review_ready(self, payload: SubmitReviewPayload) -> None:
        self._review_ready_calls.append(payload)

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


class _StubClient:
    """Minimal OpenCode client stub that returns a scripted SendResult."""

    def __init__(
        self,
        *,
        send_result: SendResult | None = None,
        send_error: BaseException | None = None,
    ) -> None:
        self._send_result = send_result
        self._send_error = send_error
        self._next_session = 0
        self.created_sessions: list[str | None] = []
        self.deleted_sessions: list[str] = []
        self.send_calls: list[str] = []
        self.closed = False

    @property
    def base_url(self) -> str:
        return "http://stub"

    async def list_providers(self) -> dict[str, Any]:
        return {"providers": []}

    async def create_session(self, *, title: str | None = None, **_: Any) -> str:
        self.created_sessions.append(title)
        sid = f"ses_{self._next_session}"
        self._next_session += 1
        return sid

    async def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return True

    async def send_with_event_watch(
        self,
        session_id: str,
        content: str,
        **_: Any,
    ) -> SendResult:
        self.send_calls.append(content)
        if self._send_error is not None:
            raise self._send_error
        return self._send_result or SendResult(message={}, text="", structured=None, valid=False)

    async def aclose(self) -> None:
        self.closed = True


class _PatchedReviewer(OpenCodeReviewerActor):
    """Reviewer with a pre-installed stub client."""

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str = "/tmp",
        send_result: SendResult | None = None,
        send_error: BaseException | None = None,
    ) -> None:
        super().__init__(supervisor_ref, cwd=cwd)
        self._stub_send_result = send_result
        self._stub_send_error = send_error
        self.stub_client: _StubClient | None = None

    async def _build_client(self) -> Any:  # type: ignore[override]
        client = _StubClient(send_result=self._stub_send_result, send_error=self._stub_send_error)
        self.stub_client = client
        return client

    async def get_session_id(self) -> str | None:
        return self._session_id

    async def get_send_count(self) -> int:
        return len(self.stub_client.send_calls) if self.stub_client else 0

    async def get_send_calls(self) -> list[str]:
        return list(self.stub_client.send_calls) if self.stub_client else []

    async def get_deleted_sessions(self) -> list[str]:
        return list(self.stub_client.deleted_sessions) if self.stub_client else []


@pytest.fixture
async def review_pool() -> AsyncIterator[str]:
    invalidate_cache()
    pool, address = await create_pool()
    register_opencode_handle(address, _fake_handle())
    try:
        yield address
    finally:
        unregister_opencode_handle(address)
        await pool.stop()


def _approved_send_result(approved: bool, findings: tuple[dict, ...] = ()) -> SendResult:
    structured = {"approved": approved, "findings": list(findings)}
    return SendResult(
        message={"info": {"structured": structured}, "parts": []},
        text="",
        structured=structured,
        valid=True,
        info={},
    )


# ---------------------------------------------------------------------------
# Per-bead review
# ---------------------------------------------------------------------------


async def test_review_success_routes_to_supervisor(review_pool: str) -> None:
    address = review_pool
    sup = await xo.create_actor(_SupervisorSpy, address=address, uid="sup-rev-1")
    reviewer = await xo.create_actor(
        _PatchedReviewer,
        sup,
        cwd="/tmp",
        send_result=_approved_send_result(True),
        address=address,
        uid="rev-1",
    )
    try:
        await reviewer.send_review(
            ReviewRequest(bead_id="bead-1", bead_description="Add a docstring")
        )
        state = await sup.get_state()
        assert len(state["review_ready"]) == 1
        assert state["review_ready"][0]["approved"] is True
        assert state["prompt_errors"] == []
    finally:
        await xo.destroy_actor(reviewer)
        await xo.destroy_actor(sup)


async def test_review_with_findings_routes_payload(review_pool: str) -> None:
    address = review_pool
    sup = await xo.create_actor(_SupervisorSpy, address=address, uid="sup-rev-2")
    finding = {"severity": "major", "issue": "missing test", "file": "x.py"}
    reviewer = await xo.create_actor(
        _PatchedReviewer,
        sup,
        cwd="/tmp",
        send_result=_approved_send_result(False, (finding,)),
        address=address,
        uid="rev-2",
    )
    try:
        await reviewer.send_review(ReviewRequest(bead_id="bead-2", bead_description="x"))
        state = await sup.get_state()
        assert len(state["review_ready"]) == 1
        delivered: dict = state["review_ready"][0]
        assert delivered["approved"] is False
        assert len(delivered["findings"]) == 1
        # Payload survived round-trip through Pydantic typing.
        validated = SubmitReviewPayload.model_validate(delivered)
        assert isinstance(validated.findings[0], ReviewFindingPayload)
        assert validated.findings[0].severity == "major"
    finally:
        await xo.destroy_actor(reviewer)
        await xo.destroy_actor(sup)


async def test_review_auth_error_routes_to_prompt_error(review_pool: str) -> None:
    address = review_pool
    sup = await xo.create_actor(_SupervisorSpy, address=address, uid="sup-rev-3")
    reviewer = await xo.create_actor(
        _PatchedReviewer,
        sup,
        cwd="/tmp",
        send_error=OpenCodeAuthError("bad key"),
        address=address,
        uid="rev-3",
    )
    try:
        await reviewer.send_review(ReviewRequest(bead_id="bead-3", bead_description="x"))
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


async def test_followup_review_uses_short_prompt(review_pool: str) -> None:
    """First review prompt is the long context one; second is the short
    'review changes only' prompt."""
    address = review_pool
    sup = await xo.create_actor(_SupervisorSpy, address=address, uid="sup-rev-4")
    reviewer = await xo.create_actor(
        _PatchedReviewer,
        sup,
        cwd="/tmp",
        send_result=_approved_send_result(True),
        address=address,
        uid="rev-4",
    )
    try:
        request = ReviewRequest(bead_id="bead-4", bead_description="task")
        await reviewer.send_review(request)
        await reviewer.send_review(request)
        send_count = await reviewer.get_send_count()
        assert send_count == 2
        calls = await reviewer.get_send_calls()
        first, second = calls[:2]
        assert "Review checklist" in first
        assert "Review checklist" not in second
    finally:
        await xo.destroy_actor(reviewer)
        await xo.destroy_actor(sup)


async def test_new_bead_rotates_session(review_pool: str) -> None:
    address = review_pool
    sup = await xo.create_actor(_SupervisorSpy, address=address, uid="sup-rev-5")
    reviewer = await xo.create_actor(
        _PatchedReviewer,
        sup,
        cwd="/tmp",
        send_result=_approved_send_result(True),
        address=address,
        uid="rev-5",
    )
    try:
        await reviewer.send_review(ReviewRequest(bead_id="b1", bead_description="x"))
        sid_first = await reviewer.get_session_id()
        await reviewer.new_bead(NewBeadRequest(bead_id="b2"))
        # Session pointer cleared.
        assert await reviewer.get_session_id() is None
        # Fresh send opens a new session.
        await reviewer.send_review(ReviewRequest(bead_id="b2", bead_description="y"))
        sid_second = await reviewer.get_session_id()
        assert sid_first is not None and sid_second is not None
        assert sid_first != sid_second
        deleted = await reviewer.get_deleted_sessions()
        assert sid_first in deleted
    finally:
        await xo.destroy_actor(reviewer)
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Aggregate review
# ---------------------------------------------------------------------------


async def test_aggregate_success_routes_to_supervisor(review_pool: str) -> None:
    address = review_pool
    sup = await xo.create_actor(_SupervisorSpy, address=address, uid="sup-agg-1")
    reviewer = await xo.create_actor(
        _PatchedReviewer,
        sup,
        cwd="/tmp",
        send_result=_approved_send_result(True),
        address=address,
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
    address = review_pool
    sup = await xo.create_actor(_SupervisorSpy, address=address, uid="sup-agg-2")
    reviewer = await xo.create_actor(
        _PatchedReviewer,
        sup,
        cwd="/tmp",
        send_error=OpenCodeAuthError("auth"),
        address=address,
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
