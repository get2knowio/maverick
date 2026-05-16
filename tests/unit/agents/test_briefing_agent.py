"""Tests for :class:`maverick.agents.briefing.agent.BriefingAgent`."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from airframe.cost import CostRecord
from airframe.errors import RuntimeStructuredOutputError
from airframe.protocol import RuntimeResult
from pydantic import BaseModel

from maverick.agents.briefing.agent import BriefingAgent, opencode_agent_for


class _NavigatorPayload(BaseModel):
    summary: str
    notes: str = ""


def _payload() -> dict[str, Any]:
    return {"summary": "all clear", "notes": ""}


def _cost() -> CostRecord:
    return CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.01,
        input_tokens=10,
        output_tokens=20,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )


def _make_runtime(structured: dict[str, Any] | None) -> Any:
    runtime = MagicMock()
    runtime.label = "stub"
    runtime.execute = AsyncMock(
        return_value=RuntimeResult(
            text="" if structured is not None else "I refuse",
            structured=structured,
            cost=_cost(),
            finish="end_turn",
        )
    )
    runtime.reset = AsyncMock()
    runtime.close = AsyncMock()
    return runtime


def _make_agent(runtime: Any) -> BriefingAgent:
    return BriefingAgent(
        runtime=runtime,
        cwd="/tmp",
        agent_name="navigator",
        result_model=_NavigatorPayload,
    )


async def test_brief_returns_typed_payload() -> None:
    runtime = _make_runtime(_payload())
    async with _make_agent(runtime) as agent:
        payload = await agent.brief("the project is X")
    assert isinstance(payload, _NavigatorPayload)
    assert payload.summary == "all clear"


async def test_brief_wraps_prompt() -> None:
    runtime = _make_runtime(_payload())
    async with _make_agent(runtime) as agent:
        await agent.brief("project context here")
    sent = runtime.execute.await_args.args[0]
    assert "Briefing input" in sent
    assert "project context here" in sent
    assert "no findings" in sent


async def test_persona_resolved_from_agent_name() -> None:
    runtime = _make_runtime(_payload())
    async with _make_agent(runtime) as agent:
        await agent.brief("x")
    assert runtime.execute.await_args.kwargs["persona"] == "maverick.navigator"


async def test_per_instance_schema_used_in_execute() -> None:
    runtime = _make_runtime(_payload())
    async with _make_agent(runtime) as agent:
        await agent.brief("x")
    assert runtime.execute.await_args.kwargs["schema"] is _NavigatorPayload


def test_opencode_agent_for_known_and_unknown() -> None:
    assert opencode_agent_for("navigator") == "maverick.navigator"
    assert opencode_agent_for("nonexistent") is None


async def test_brief_raises_on_missing_structured_payload() -> None:
    runtime = _make_runtime(None)
    async with _make_agent(runtime) as agent:
        with pytest.raises(RuntimeStructuredOutputError):
            await agent.brief("x")


async def test_lifecycle_routes_to_runtime() -> None:
    runtime = _make_runtime(_payload())
    agent = _make_agent(runtime)
    await agent.open()
    await agent.rotate_session()
    runtime.reset.assert_awaited_once()
    await agent.close()
    runtime.close.assert_awaited_once()


async def test_cost_record_captured() -> None:
    runtime = _make_runtime(_payload())
    async with _make_agent(runtime) as agent:
        await agent.brief("x")
        assert agent.last_cost_record is not None
        assert agent.last_cost_record.cost_usd == 0.01
