"""Tests for :class:`maverick.agents.generator.GeneratorAgent`."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.agents.generator import GeneratorAgent
from maverick.payloads import SubmitFlightPlanPayload


def _flight_plan_payload() -> dict[str, Any]:
    return {
        "kind": "submit_flight_plan",
        "objective": "ship the thing",
        "context": "we need it",
        "success_criteria": [
            {
                "kind": "flight_plan_success_criterion",
                "description": "tests pass",
                "verification": "make test",
            }
        ],
    }


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


def _make_runtime(structured: dict[str, Any]) -> Any:
    runtime = MagicMock()
    runtime.label = "stub"
    runtime.execute = AsyncMock(
        return_value=RuntimeResult(text="", structured=structured, cost=_cost(), finish="end_turn")
    )
    runtime.reset = AsyncMock()
    runtime.close = AsyncMock()
    return runtime


async def test_generate_returns_typed_payload() -> None:
    runtime = _make_runtime(_flight_plan_payload())
    agent = GeneratorAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        payload = await agent.generate("PRD body")
    assert isinstance(payload, SubmitFlightPlanPayload)
    assert payload.objective == "ship the thing"
    call = runtime.execute.await_args
    assert call.kwargs["schema"] is SubmitFlightPlanPayload
    assert call.kwargs["persona"] == "maverick.generator"


async def test_generate_wraps_prompt() -> None:
    runtime = _make_runtime(_flight_plan_payload())
    agent = GeneratorAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        await agent.generate("RAW PRD CONTENT")
    sent = runtime.execute.await_args.args[0]
    assert "PRD and briefing" in sent
    assert "RAW PRD CONTENT" in sent


async def test_close_routes_to_runtime() -> None:
    runtime = _make_runtime(_flight_plan_payload())
    agent = GeneratorAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        pass
    runtime.close.assert_awaited_once()
