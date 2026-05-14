"""Tests for :class:`maverick.agents.generator.GeneratorAgent`."""

from __future__ import annotations

from typing import Any

from maverick.agents.generator import GeneratorAgent
from maverick.payloads import SubmitFlightPlanPayload

from .conftest import FakeClient, fake_handle, payload_send_result


class _GeneratorAgentForTest(GeneratorAgent):
    def __init__(self, *, client: FakeClient, **kwargs: Any) -> None:
        super().__init__(handle=fake_handle(), cwd="/tmp", **kwargs)
        self._fake_client = client

    def _build_client(self) -> Any:  # type: ignore[override]
        return self._fake_client


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


async def test_generate_returns_typed_payload() -> None:
    client = FakeClient(send_result=payload_send_result(_flight_plan_payload()))
    agent = _GeneratorAgentForTest(client=client)
    async with agent:
        payload = await agent.generate("PRD body")
    assert isinstance(payload, SubmitFlightPlanPayload)
    assert payload.objective == "ship the thing"


async def test_generate_wraps_prompt() -> None:
    client = FakeClient(send_result=payload_send_result(_flight_plan_payload()))
    agent = _GeneratorAgentForTest(client=client)
    async with agent:
        await agent.generate("RAW PRD CONTENT")
    sent = client.send_calls[0]["content"]
    assert "PRD and briefing" in sent
    assert "RAW PRD CONTENT" in sent


async def test_generate_uses_correct_persona() -> None:
    client = FakeClient(send_result=payload_send_result(_flight_plan_payload()))
    agent = _GeneratorAgentForTest(client=client)
    async with agent:
        await agent.generate("x")
    assert client.send_calls[0]["agent"] == "maverick.generator"
