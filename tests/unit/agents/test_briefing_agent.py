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


def _payload() -> dict[str, Any]:
    return {"summary": "all clear", "notes": ""}


def _make_agent(client: FakeClient) -> BriefingAgent:
    return BriefingAgent(
        handle=fake_handle(),
        cwd="/tmp",
        agent_name="navigator",
        result_model=_NavigatorPayload,
        client_factory=lambda: client,
    )


async def test_brief_returns_typed_payload() -> None:
    client = FakeClient(send_result=payload_send_result(_payload()))
    async with _make_agent(client) as agent:
        payload = await agent.brief("the project is X")
    assert isinstance(payload, _NavigatorPayload)
    assert payload.summary == "all clear"


async def test_brief_wraps_prompt() -> None:
    client = FakeClient(send_result=payload_send_result(_payload()))
    async with _make_agent(client) as agent:
        await agent.brief("project context here")
    sent = client.send_calls[0]["content"]
    assert "Briefing input" in sent
    assert "project context here" in sent
    # Greenfield-friendly preamble is present.
    assert "no findings" in sent


async def test_persona_resolved_from_agent_name() -> None:
    client = FakeClient(send_result=payload_send_result(_payload()))
    async with _make_agent(client) as agent:
        await agent.brief("x")
    assert client.send_calls[0]["agent"] == "maverick.navigator"


async def test_per_instance_schema_overrides_class_default() -> None:
    client = FakeClient(send_result=payload_send_result(_payload()))
    async with _make_agent(client) as agent:
        await agent.brief("x")
    schema = client.send_calls[0]["format"]["schema"]
    assert "summary" in schema["properties"]


def test_opencode_agent_for_known_and_unknown() -> None:
    assert opencode_agent_for("navigator") == "maverick.navigator"
    assert opencode_agent_for("nonexistent") is None


# ---------------------------------------------------------------------------
# Pattern D path — runtime= constructor
# ---------------------------------------------------------------------------


def test_constructor_requires_handle_or_runtime() -> None:
    """Pattern D safety: must pick exactly one transport."""
    import pytest

    with pytest.raises(ValueError, match="handle.*runtime"):
        BriefingAgent(cwd="/tmp", agent_name="navigator", result_model=_NavigatorPayload)


def test_constructor_rejects_both_handle_and_runtime() -> None:
    """Both transports at once is a programmer error."""
    from unittest.mock import MagicMock

    import pytest

    fake_runtime = MagicMock()
    with pytest.raises(ValueError, match="both"):
        BriefingAgent(
            handle=fake_handle(),
            runtime=fake_runtime,
            cwd="/tmp",
            agent_name="navigator",
            result_model=_NavigatorPayload,
        )


async def test_brief_via_runtime_returns_typed_payload() -> None:
    """The Pattern D path: brief() goes through runtime.execute()."""
    from unittest.mock import AsyncMock, MagicMock

    from maverick.runtime.cost import CostRecord
    from maverick.runtime.protocol import RuntimeResult

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
            text="",
            structured={"summary": "ok", "notes": "via runtime"},
            cost=cost,
            finish="end_turn",
        )
    )
    fake_runtime.reset = AsyncMock()
    fake_runtime.aclose = AsyncMock()

    agent = BriefingAgent(
        runtime=fake_runtime,
        cwd="/tmp",
        agent_name="navigator",
        result_model=_NavigatorPayload,
    )
    async with agent:
        payload = await agent.brief("the project is X")

    assert isinstance(payload, _NavigatorPayload)
    assert payload.summary == "ok"
    assert payload.notes == "via runtime"
    # runtime.execute was called with the schema and persona.
    call = fake_runtime.execute.await_args
    assert call.kwargs["schema"] is _NavigatorPayload
    assert call.kwargs["persona"] == "maverick.navigator"
    # Cost record was captured.
    assert agent.last_cost_record is cost


async def test_brief_via_runtime_raises_on_missing_structured_payload() -> None:
    """If the runtime returns structured=None, brief() raises."""
    from unittest.mock import AsyncMock, MagicMock

    import pytest

    from maverick.runtime.cost import CostRecord
    from maverick.runtime.errors import RuntimeStructuredOutputError
    from maverick.runtime.protocol import RuntimeResult

    fake_runtime = MagicMock()
    fake_runtime.label = "claude_code"
    fake_runtime.execute = AsyncMock(
        return_value=RuntimeResult(
            text="I refuse",
            structured=None,
            cost=CostRecord(
                provider_id="anthropic",
                model_id="claude-haiku-4-5",
                cost_usd=0.0,
                input_tokens=0,
                output_tokens=0,
                cache_read_tokens=0,
                cache_write_tokens=0,
                finish="end_turn",
            ),
            finish="end_turn",
        )
    )
    fake_runtime.reset = AsyncMock()
    fake_runtime.aclose = AsyncMock()

    agent = BriefingAgent(
        runtime=fake_runtime,
        cwd="/tmp",
        agent_name="navigator",
        result_model=_NavigatorPayload,
    )
    async with agent:
        with pytest.raises(RuntimeStructuredOutputError):
            await agent.brief("x")


async def test_rotate_session_routes_to_runtime_reset() -> None:
    from unittest.mock import AsyncMock, MagicMock

    fake_runtime = MagicMock()
    fake_runtime.label = "claude_code"
    fake_runtime.reset = AsyncMock()
    fake_runtime.aclose = AsyncMock()

    agent = BriefingAgent(
        runtime=fake_runtime,
        cwd="/tmp",
        agent_name="navigator",
        result_model=_NavigatorPayload,
    )
    await agent.open()
    await agent.rotate_session()
    fake_runtime.reset.assert_awaited_once()
    await agent.close()
    fake_runtime.aclose.assert_awaited_once()
