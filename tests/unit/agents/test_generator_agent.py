"""Tests for :class:`maverick.agents.generator.GeneratorAgent`."""

from __future__ import annotations

from typing import Any

from maverick.agents.generator import GeneratorAgent
from maverick.payloads import SubmitFlightPlanPayload

from .conftest import FakeClient, fake_handle, payload_send_result


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


def _make_agent(client: FakeClient) -> GeneratorAgent:
    return GeneratorAgent(handle=fake_handle(), cwd="/tmp", client_factory=lambda: client)


async def test_generate_returns_typed_payload() -> None:
    client = FakeClient(send_result=payload_send_result(_flight_plan_payload()))
    async with _make_agent(client) as agent:
        payload = await agent.generate("PRD body")
    assert isinstance(payload, SubmitFlightPlanPayload)
    assert payload.objective == "ship the thing"


async def test_generate_wraps_prompt() -> None:
    client = FakeClient(send_result=payload_send_result(_flight_plan_payload()))
    async with _make_agent(client) as agent:
        await agent.generate("RAW PRD CONTENT")
    sent = client.send_calls[0]["content"]
    assert "PRD and briefing" in sent
    assert "RAW PRD CONTENT" in sent


async def test_generate_uses_correct_persona() -> None:
    client = FakeClient(send_result=payload_send_result(_flight_plan_payload()))
    async with _make_agent(client) as agent:
        await agent.generate("x")
    assert client.send_calls[0]["agent"] == "maverick.generator"


# ---------------------------------------------------------------------------
# Pattern D path — runtime= constructor
# ---------------------------------------------------------------------------


def test_constructor_requires_handle_or_runtime() -> None:
    import pytest

    with pytest.raises(ValueError, match="handle.*runtime"):
        GeneratorAgent(cwd="/tmp")


def test_constructor_rejects_both_handle_and_runtime() -> None:
    from unittest.mock import MagicMock

    import pytest

    with pytest.raises(ValueError, match="both"):
        GeneratorAgent(handle=fake_handle(), runtime=MagicMock(), cwd="/tmp")


async def test_generate_via_runtime_returns_typed_payload() -> None:
    """Pattern D path: generate() goes through runtime.execute()."""
    from unittest.mock import AsyncMock, MagicMock

    from airframe.cost import CostRecord
    from airframe.protocol import RuntimeResult

    cost = CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.01,
        input_tokens=10,
        output_tokens=20,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )
    fake_runtime = MagicMock()
    fake_runtime.label = "claude_code"
    fake_runtime.execute = AsyncMock(
        return_value=RuntimeResult(
            text="", structured=_flight_plan_payload(), cost=cost, finish="end_turn"
        )
    )
    fake_runtime.reset = AsyncMock()
    fake_runtime.close = AsyncMock()

    agent = GeneratorAgent(runtime=fake_runtime, cwd="/tmp")
    async with agent:
        payload = await agent.generate("PRD body")

    assert isinstance(payload, SubmitFlightPlanPayload)
    assert payload.objective == "ship the thing"
    call = fake_runtime.execute.await_args
    assert call.kwargs["schema"] is SubmitFlightPlanPayload
    assert call.kwargs["persona"] == "maverick.generator"
    fake_runtime.close.assert_awaited_once()
