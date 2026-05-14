"""Tests for :class:`maverick.agents.coding.CodingAgent`."""

from __future__ import annotations

from typing import Any

import pytest

from maverick.agents.coding import CodingAgent
from maverick.payloads import SubmitFixResultPayload, SubmitImplementationPayload

from .conftest import FakeClient, fake_handle, payload_send_result


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


def _make_agent(client: FakeClient) -> CodingAgent:
    return CodingAgent(handle=fake_handle(), cwd="/tmp", client_factory=lambda: client)


async def test_implement_returns_typed_payload() -> None:
    client = FakeClient(send_result=payload_send_result(_impl_payload()))
    async with _make_agent(client) as agent:
        payload = await agent.implement("do the thing", bead_id="b-1")
    assert isinstance(payload, SubmitImplementationPayload)
    assert payload.summary == "did the work"
    # Verify the agent sent a json_schema format block.
    assert len(client.send_calls) == 1
    call = client.send_calls[0]
    assert call["format"]["type"] == "json_schema"
    schema = call["format"]["schema"]
    assert "summary" in schema["properties"]
    # Persona is forwarded.
    assert call["agent"] == "maverick.implementer"
    # Bead id is recorded for cost telemetry.
    assert agent.current_bead_id == "b-1"


async def test_fix_returns_typed_payload() -> None:
    client = FakeClient(send_result=payload_send_result(_fix_payload()))
    async with _make_agent(client) as agent:
        payload = await agent.fix("fix this", bead_id="b-2")
    assert isinstance(payload, SubmitFixResultPayload)
    assert payload.summary == "fixed it"
    assert agent.current_bead_id == "b-2"


async def test_implement_then_fix_share_session() -> None:
    """The same agent reuses its session across implement → fix."""
    # Switch the result between calls.
    client = FakeClient(send_result=payload_send_result(_impl_payload()))
    async with _make_agent(client) as agent:
        await agent.implement("do it", bead_id="b-3")
        sid_after_impl = agent._session_id  # noqa: SLF001 — test introspection
        # Swap the next response and call fix.
        client.send_result = payload_send_result(_fix_payload())
        await agent.fix("fix it", bead_id="b-3")
        sid_after_fix = agent._session_id  # noqa: SLF001
    assert sid_after_impl is not None
    assert sid_after_fix == sid_after_impl
    # Two sends, one session created.
    assert len(client.send_calls) == 2
    assert len(client.created_sessions) == 1


async def test_rotate_session_drops_session() -> None:
    client = FakeClient(send_result=payload_send_result(_impl_payload()))
    async with _make_agent(client) as agent:
        await agent.implement("first", bead_id="b-4")
        first_sid = agent._session_id  # noqa: SLF001
        await agent.rotate_session()
        assert agent._session_id is None  # noqa: SLF001
        client.send_result = payload_send_result(_impl_payload())
        await agent.implement("second", bead_id="b-4")
        second_sid = agent._session_id  # noqa: SLF001
    assert second_sid is not None and second_sid != first_sid
    assert first_sid in client.deleted_sessions


async def test_construction_requires_cwd() -> None:
    with pytest.raises(ValueError, match="requires 'cwd'"):
        CodingAgent(handle=fake_handle(), cwd="")
