"""Tests for ImplementerActor + ReviewerActor under the OpenCode runtime.

Exercises the supervisor-facing contract (``implementation_ready``,
``fix_result_ready``, ``review_ready``, ``payload_parse_error``,
``prompt_error``) without spawning a real OpenCode subprocess. The mixin's
client construction is overridden via a ``_PatchedActor`` subclass so we
can script exact :class:`SendResult` instances per send.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import xoscar as xo

from maverick.actors.xoscar.implementer import ImplementerActor
from maverick.actors.xoscar.messages import (
    FlyFixRequest,
    ImplementRequest,
    NewBeadRequest,
    PromptError,
)
from maverick.actors.xoscar.pool import create_pool
from maverick.actors.xoscar.reviewer import ReviewerActor
from maverick.runtime.opencode import (
    OpenCodeAuthError,
    OpenCodeServerHandle,
    SendResult,
    invalidate_cache,
    register_opencode_handle,
    unregister_opencode_handle,
)
from maverick.tools.agent_inbox.models import (
    SubmitFixResultPayload,
    SubmitImplementationPayload,
    SubmitReviewPayload,
)


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


class _SupervisorRecorder(xo.Actor):
    async def __post_create__(self) -> None:
        self._calls: list[tuple[str, Any]] = []

    @xo.no_lock
    async def implementation_ready(self, payload: SubmitImplementationPayload) -> None:
        self._calls.append(("implementation_ready", payload.model_dump()))

    @xo.no_lock
    async def fix_result_ready(self, payload: SubmitFixResultPayload) -> None:
        self._calls.append(("fix_result_ready", payload.model_dump()))

    @xo.no_lock
    async def review_ready(self, payload: SubmitReviewPayload) -> None:
        self._calls.append(("review_ready", payload.model_dump()))

    @xo.no_lock
    async def aggregate_review_ready(self, payload: SubmitReviewPayload) -> None:
        self._calls.append(("aggregate_review_ready", payload.model_dump()))

    @xo.no_lock
    async def payload_parse_error(self, tool: str, message: str) -> None:
        self._calls.append(("payload_parse_error", (tool, message)))

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


class _StubClient:
    """Programmable OpenCode client stub.

    ``send_results`` is consumed in order; the first send pops the head.
    A ``send_error`` short-circuits with the named exception.
    """

    def __init__(
        self,
        *,
        send_results: list[SendResult] | None = None,
        send_error: BaseException | None = None,
    ) -> None:
        self._send_results = list(send_results or [])
        self._send_error = send_error
        self.created_sessions: list[str | None] = []
        self.deleted_sessions: list[str] = []
        self.send_calls: list[dict[str, Any]] = []
        self.closed = False

    @property
    def base_url(self) -> str:
        return "http://stub"

    async def list_providers(self) -> dict[str, Any]:
        return {"all": [], "connected": []}

    async def create_session(self, *, title: str | None = None, **_: Any) -> str:
        sid = f"ses_{len(self.created_sessions)}"
        self.created_sessions.append(title)
        return sid

    async def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return True

    async def send_with_event_watch(
        self,
        session_id: str,
        content: str,
        **kwargs: Any,
    ) -> SendResult:
        self.send_calls.append(
            {
                "session_id": session_id,
                "content": content,
                "format": kwargs.get("format"),
                "model": kwargs.get("model"),
            }
        )
        if self._send_error is not None:
            raise self._send_error
        if not self._send_results:
            return SendResult(message={}, text="", structured=None, valid=False)
        return self._send_results.pop(0)

    async def aclose(self) -> None:
        self.closed = True


class _PatchedImplementer(ImplementerActor):
    """Implementer that uses an in-process stub client."""

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str = "/tmp",
        send_results: list[SendResult] | None = None,
        send_error: BaseException | None = None,
    ) -> None:
        super().__init__(supervisor_ref, cwd=cwd)
        self._stub_send_results = send_results
        self._stub_send_error = send_error
        self.stub_client: _StubClient | None = None

    async def _build_client(self) -> Any:  # type: ignore[override]
        client = _StubClient(
            send_results=self._stub_send_results, send_error=self._stub_send_error
        )
        self.stub_client = client
        return client

    async def get_send_calls(self) -> list[dict[str, Any]]:
        return list(self.stub_client.send_calls) if self.stub_client else []


class _PatchedReviewer(ReviewerActor):
    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str = "/tmp",
        send_results: list[SendResult] | None = None,
        send_error: BaseException | None = None,
    ) -> None:
        super().__init__(supervisor_ref, cwd=cwd)
        self._stub_send_results = send_results
        self._stub_send_error = send_error
        self.stub_client: _StubClient | None = None

    async def _build_client(self) -> Any:  # type: ignore[override]
        client = _StubClient(
            send_results=self._stub_send_results, send_error=self._stub_send_error
        )
        self.stub_client = client
        return client


@pytest.fixture
async def actor_pool_address() -> AsyncIterator[str]:
    invalidate_cache()
    pool, address = await create_pool()
    register_opencode_handle(address, _fake_handle())
    try:
        yield address
    finally:
        unregister_opencode_handle(address)
        await pool.stop()


def _structured(payload: dict[str, Any]) -> SendResult:
    return SendResult(
        message={"info": {"structured": payload}, "parts": []},
        text="",
        structured=payload,
        valid=True,
        info={},
    )


# ---------------------------------------------------------------------------
# Implementer
# ---------------------------------------------------------------------------


async def test_implementer_forwards_submit_implementation(actor_pool_address: str) -> None:
    address = actor_pool_address
    sup = await xo.create_actor(_SupervisorRecorder, address=address, uid="sup-1")
    impl_payload = {
        "summary": "implemented",
        "files_changed": [],
        "tests_added": [],
    }
    impl = await xo.create_actor(
        _PatchedImplementer,
        sup,
        cwd="/tmp",
        send_results=[_structured(impl_payload)],
        address=address,
        uid="impl-1",
    )
    try:
        await impl.send_implement(ImplementRequest(bead_id="b-1", prompt="implement x"))
        calls = await sup.get_calls()
        assert any(name == "implementation_ready" for name, _ in calls)
        assert not any(name == "prompt_error" for name, _ in calls)
        # The send was framed with a json_schema format
        send_calls = await impl.get_send_calls()
        fmt = send_calls[0]["format"]
        assert fmt is not None and fmt["type"] == "json_schema"
    finally:
        await xo.destroy_actor(impl)
        await xo.destroy_actor(sup)


async def test_implementer_forwards_submit_fix_result(actor_pool_address: str) -> None:
    address = actor_pool_address
    sup = await xo.create_actor(_SupervisorRecorder, address=address, uid="sup-2")
    fix_payload = {
        "summary": "fixed",
        "files_changed": [],
        "addressed_findings": [],
    }
    impl = await xo.create_actor(
        _PatchedImplementer,
        sup,
        cwd="/tmp",
        send_results=[_structured(fix_payload)],
        address=address,
        uid="impl-2",
    )
    try:
        await impl.send_fix(FlyFixRequest(bead_id="b-2", prompt="fix x"))
        calls = await sup.get_calls()
        assert any(name == "fix_result_ready" for name, _ in calls)
    finally:
        await xo.destroy_actor(impl)
        await xo.destroy_actor(sup)


async def test_implementer_routes_auth_error_to_prompt_error(
    actor_pool_address: str,
) -> None:
    address = actor_pool_address
    sup = await xo.create_actor(_SupervisorRecorder, address=address, uid="sup-3")
    impl = await xo.create_actor(
        _PatchedImplementer,
        sup,
        cwd="/tmp",
        send_error=OpenCodeAuthError("bad key"),
        address=address,
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


async def test_implementer_new_bead_rotates_session(actor_pool_address: str) -> None:
    address = actor_pool_address
    sup = await xo.create_actor(_SupervisorRecorder, address=address, uid="sup-4")
    impl = await xo.create_actor(
        _PatchedImplementer,
        sup,
        cwd="/tmp",
        send_results=[
            _structured({"summary": "a", "files_changed": [], "tests_added": []}),
            _structured({"summary": "b", "files_changed": [], "tests_added": []}),
        ],
        address=address,
        uid="impl-4",
    )
    try:
        await impl.send_implement(ImplementRequest(bead_id="b-1", prompt="x"))
        await impl.new_bead(NewBeadRequest(bead_id="b-2"))
        await impl.send_implement(ImplementRequest(bead_id="b-2", prompt="y"))
        send_calls = await impl.get_send_calls()
        # Two distinct sessions used.
        sessions = {c["session_id"] for c in send_calls}
        assert len(sessions) == 2
    finally:
        await xo.destroy_actor(impl)
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Reviewer (smoke — full coverage in test_reviewer_opencode.py)
# ---------------------------------------------------------------------------


async def test_reviewer_forwards_submit_review(actor_pool_address: str) -> None:
    address = actor_pool_address
    sup = await xo.create_actor(_SupervisorRecorder, address=address, uid="sup-r")
    payload = {"approved": True, "findings": []}
    reviewer = await xo.create_actor(
        _PatchedReviewer,
        sup,
        cwd="/tmp",
        send_results=[_structured(payload)],
        address=address,
        uid="rev-1",
    )
    try:
        from maverick.actors.xoscar.messages import ReviewRequest

        await reviewer.send_review(ReviewRequest(bead_id="b-1", bead_description="x"))
        calls = await sup.get_calls()
        assert any(name == "review_ready" for name, _ in calls)
    finally:
        await xo.destroy_actor(reviewer)
        await xo.destroy_actor(sup)
