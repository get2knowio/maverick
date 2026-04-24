"""Tests for ``ImplementerActor`` and ``ReviewerActor`` inbox dispatch."""

from __future__ import annotations

from typing import Any

import pytest
import xoscar as xo

from maverick.actors.xoscar.implementer import ImplementerActor
from maverick.actors.xoscar.reviewer import ReviewerActor
from maverick.tools.agent_inbox.models import (
    SubmitFixResultPayload,
    SubmitImplementationPayload,
    SubmitReviewPayload,
)


class _FlyRecorder(xo.Actor):
    async def __post_create__(self) -> None:
        self._calls: list[tuple[str, Any]] = []

    async def implementation_ready(self, payload: SubmitImplementationPayload) -> None:
        self._calls.append(("implementation_ready", payload))

    async def fix_result_ready(self, payload: SubmitFixResultPayload) -> None:
        self._calls.append(("fix_result_ready", payload))

    async def review_ready(self, payload: SubmitReviewPayload) -> None:
        self._calls.append(("review_ready", payload))

    async def aggregate_review_ready(self, payload: SubmitReviewPayload) -> None:
        self._calls.append(("aggregate_review_ready", payload))

    async def payload_parse_error(self, tool: str, message: str) -> None:
        self._calls.append(("payload_parse_error", (tool, message)))

    async def prompt_error(self, error: Any) -> None:
        self._calls.append(("prompt_error", error))

    async def calls(self) -> list[tuple[str, Any]]:
        return list(self._calls)


@pytest.mark.asyncio
async def test_implementer_forwards_submit_implementation(pool_address: str) -> None:
    supervisor = await xo.create_actor(
        _FlyRecorder, address=pool_address, uid="impl-sup"
    )
    impl = await xo.create_actor(
        ImplementerActor,
        supervisor,
        cwd="/tmp",
        address=pool_address,
        uid="impl-1",
    )
    try:
        args = {"summary": "did the work", "files_changed": ["src/foo.py"]}
        result = await impl.on_tool_call("submit_implementation", args)
        assert result == "ok"
        calls = await supervisor.calls()
        assert len(calls) == 1
        kind, payload = calls[0]
        assert kind == "implementation_ready"
        assert isinstance(payload, SubmitImplementationPayload)
        assert payload.summary == "did the work"
    finally:
        await xo.destroy_actor(impl)
        await xo.destroy_actor(supervisor)


@pytest.mark.asyncio
async def test_implementer_forwards_submit_fix_result(pool_address: str) -> None:
    supervisor = await xo.create_actor(
        _FlyRecorder, address=pool_address, uid="impl-sup-fr"
    )
    impl = await xo.create_actor(
        ImplementerActor,
        supervisor,
        cwd="/tmp",
        address=pool_address,
        uid="impl-fr",
    )
    try:
        args = {"summary": "addressed findings", "addressed": ["F-1", "F-2"]}
        result = await impl.on_tool_call("submit_fix_result", args)
        assert result == "ok"
        calls = await supervisor.calls()
        assert len(calls) == 1
        kind, payload = calls[0]
        assert kind == "fix_result_ready"
        assert isinstance(payload, SubmitFixResultPayload)
    finally:
        await xo.destroy_actor(impl)
        await xo.destroy_actor(supervisor)


@pytest.mark.asyncio
async def test_implementer_rejects_unowned_tool(pool_address: str) -> None:
    supervisor = await xo.create_actor(
        _FlyRecorder, address=pool_address, uid="impl-sup-rej"
    )
    impl = await xo.create_actor(
        ImplementerActor,
        supervisor,
        cwd="/tmp",
        address=pool_address,
        uid="impl-rej",
    )
    try:
        result = await impl.on_tool_call("submit_review", {"approved": True})
        assert result == "error"
        calls = await supervisor.calls()
        assert len(calls) == 1
        kind, detail = calls[0]
        assert kind == "payload_parse_error"
        tool, _msg = detail
        assert tool == "submit_review"
    finally:
        await xo.destroy_actor(impl)
        await xo.destroy_actor(supervisor)


@pytest.mark.asyncio
async def test_reviewer_forwards_per_bead_review(pool_address: str) -> None:
    supervisor = await xo.create_actor(
        _FlyRecorder, address=pool_address, uid="rev-sup"
    )
    rev = await xo.create_actor(
        ReviewerActor,
        supervisor,
        cwd="/tmp",
        address=pool_address,
        uid="rev-1",
    )
    try:
        # Default (_in_aggregate=False) → review_ready branch.
        args = {"approved": False, "findings": [
            {"severity": "critical", "issue": "broken", "file": "src/x.py", "line": 1}
        ]}
        result = await rev.on_tool_call("submit_review", args)
        assert result == "ok"
        calls = await supervisor.calls()
        assert len(calls) == 1
        kind, payload = calls[0]
        assert kind == "review_ready"
        assert isinstance(payload, SubmitReviewPayload)
        assert payload.approved is False
    finally:
        await xo.destroy_actor(rev)
        await xo.destroy_actor(supervisor)
