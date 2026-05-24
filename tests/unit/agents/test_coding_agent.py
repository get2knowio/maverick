"""Tests for :class:`maverick.agents.coding.CodingAgent`."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.agents.coding import CodingAgent
from maverick.payloads import SubmitFixResultPayload, SubmitImplementationPayload


def _impl_payload() -> dict[str, Any]:
    return {
        "kind": "submit_implementation",
        "summary": "did the work",
        "files_changed": ["a.py"],
        "commands_run": [],
        "verification": "tests pass",
        "next_step": "commit",
    }


def _fix_payload() -> dict[str, Any]:
    return {
        "kind": "submit_fix_result",
        "summary": "fixed it",
        "files_changed": ["a.py"],
        "commands_run": [],
        "verification": "tests pass",
        "addressed_findings": ["finding-1"],
    }


def _cost() -> CostRecord:
    return CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.05,
        input_tokens=50,
        output_tokens=100,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )


def _make_runtime(structured: dict[str, Any]) -> Any:
    runtime = MagicMock()
    runtime.label = "stub"
    runtime.execute = AsyncMock(
        return_value=RuntimeResult(text="", structured=structured, cost=_cost(), finish="end_turn")
    )
    runtime.reset = AsyncMock()
    runtime.close = AsyncMock()
    return runtime


async def test_implement_returns_typed_payload() -> None:
    runtime = _make_runtime(_impl_payload())
    agent = CodingAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        payload = await agent.implement("do the work")
    assert isinstance(payload, SubmitImplementationPayload)
    assert payload.summary == "did the work"
    call = runtime.execute.await_args
    assert call.kwargs["schema"] is SubmitImplementationPayload
    assert call.kwargs["persona"] == "maverick.implementer"


async def test_fix_uses_fix_schema() -> None:
    runtime = _make_runtime(_fix_payload())
    agent = CodingAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        payload = await agent.fix("fix the bug")
    assert isinstance(payload, SubmitFixResultPayload)
    call = runtime.execute.await_args
    assert call.kwargs["schema"] is SubmitFixResultPayload


async def test_rotate_session_resets_runtime() -> None:
    runtime = _make_runtime(_impl_payload())
    agent = CodingAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        await agent.implement("first")
        await agent.rotate_session()
    runtime.reset.assert_awaited()


async def test_close_calls_runtime_close() -> None:
    runtime = _make_runtime(_impl_payload())
    agent = CodingAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        pass
    runtime.close.assert_awaited_once()


def test_construction_requires_cwd() -> None:
    with pytest.raises(ValueError, match="requires 'cwd'"):
        CodingAgent(runtime=MagicMock(), cwd="")
