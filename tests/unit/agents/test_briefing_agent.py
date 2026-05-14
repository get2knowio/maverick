"""Tests for :class:`maverick.agents.briefing.agent.BriefingAgent`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from maverick.agents.briefing.agent import BriefingAgent, opencode_agent_for

from .conftest import FakeClient, fake_handle, payload_send_result


class _NavigatorPayload(BaseModel):
    """Tiny stand-in for SubmitNavigatorBriefPayload in tests."""

    summary: str
    notes: str = ""


class _BriefingAgentForTest(BriefingAgent):
    def __init__(self, *, client: FakeClient, **kwargs: Any) -> None:
        super().__init__(handle=fake_handle(), cwd="/tmp", **kwargs)
        self._fake_client = client

    def _build_client(self) -> Any:  # type: ignore[override]
        return self._fake_client


def _payload() -> dict[str, Any]:
    return {"summary": "all clear", "notes": ""}


async def test_brief_returns_typed_payload() -> None:
    client = FakeClient(send_result=payload_send_result(_payload()))
    agent = _BriefingAgentForTest(
        client=client,
        agent_name="navigator",
        result_model=_NavigatorPayload,
    )
    async with agent:
        payload = await agent.brief("the project is X")
    assert isinstance(payload, _NavigatorPayload)
    assert payload.summary == "all clear"


async def test_brief_wraps_prompt() -> None:
    client = FakeClient(send_result=payload_send_result(_payload()))
    agent = _BriefingAgentForTest(
        client=client,
        agent_name="navigator",
        result_model=_NavigatorPayload,
    )
    async with agent:
        await agent.brief("project context here")
    sent = client.send_calls[0]["content"]
    assert "Briefing input" in sent
    assert "project context here" in sent
    # Greenfield-friendly preamble is present.
    assert "no findings" in sent


async def test_persona_resolved_from_agent_name() -> None:
    client = FakeClient(send_result=payload_send_result(_payload()))
    agent = _BriefingAgentForTest(
        client=client,
        agent_name="navigator",
        result_model=_NavigatorPayload,
    )
    async with agent:
        await agent.brief("x")
    assert client.send_calls[0]["agent"] == "maverick.navigator"


async def test_per_instance_schema_overrides_class_default() -> None:
    client = FakeClient(send_result=payload_send_result(_payload()))
    agent = _BriefingAgentForTest(
        client=client,
        agent_name="navigator",
        result_model=_NavigatorPayload,
    )
    async with agent:
        await agent.brief("x")
    schema = client.send_calls[0]["format"]["schema"]
    assert "summary" in schema["properties"]


def test_opencode_agent_for_known_and_unknown() -> None:
    assert opencode_agent_for("navigator") == "maverick.navigator"
    assert opencode_agent_for("nonexistent") is None
