"""Tests for :class:`maverick.agents.base.Agent`.

Covers:

* Lifecycle (``open`` / ``close`` / ``rotate_session``).
* ``_send_structured`` returns a typed payload validated against
  ``result_model`` and unwraps the envelope (Landmine 3).
* ``_send_text`` returns the assistant's plain-text response.
* Model validation runs on first send and is cached after.
* Error classification (``RuntimeAuthError``, payload-validation
  failures) propagates to the caller.

Tests exercise :class:`Agent` directly — no xoscar pool involved. The
OpenCode client is replaced with a fake via the ``_build_client`` hook.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from pydantic import BaseModel

from maverick.agents.base import Agent, AgentPayloadValidationError
from maverick.runtime.opencode import RuntimeAuthError, SendResult

from .conftest import FakeClient, fake_handle, payload_send_result


class ReviewPayload(BaseModel):
    approved: bool
    notes: str = ""


class _TestAgent(Agent):
    """Concrete Agent with two domain methods.

    Tests inject a fake client via ``client_factory=`` at construction
    — no subclassing required. Use the :func:`_make_agent` helper below.
    """

    result_model: ClassVar[type[BaseModel]] = ReviewPayload

    async def review(self, prompt: str) -> BaseModel:
        return await self._send_structured(prompt)

    async def chat(self, prompt: str) -> str:
        return await self._send_text(prompt)


def _make_agent(client: FakeClient, **kwargs: Any) -> _TestAgent:
    return _TestAgent(
        handle=fake_handle(),
        cwd="/tmp",
        client_factory=lambda: client,
        **kwargs,
    )


async def test_send_structured_returns_validated_payload() -> None:
    client = FakeClient(send_result=payload_send_result({"approved": True, "notes": "looks good"}))
    agent = _make_agent(client)
    async with agent:
        payload = await agent.review("review this diff")
    assert isinstance(payload, ReviewPayload)
    assert payload.approved is True
    assert payload.notes == "looks good"

    assert len(client.send_calls) == 1
    assert client.send_calls[0]["format"]["type"] == "json_schema"
    schema = client.send_calls[0]["format"]["schema"]
    assert "approved" in schema["properties"]


async def test_send_structured_unwraps_envelope_via_send_result() -> None:
    """Mirror Landmine 3: the agent still produces a typed payload from the
    already-unwrapped structured field on the SendResult."""
    client = FakeClient(send_result=payload_send_result({"approved": False, "notes": ""}))
    agent = _make_agent(client)
    async with agent:
        payload = await agent.review("review")
    assert isinstance(payload, ReviewPayload)
    assert payload.approved is False


async def test_send_structured_raises_payload_validation_error() -> None:
    """Server returns a structured payload, but it doesn't match the model."""
    bad_result = SendResult(
        message={"info": {"structured": {"unexpected": "field"}}, "parts": []},
        text="",
        structured={"unexpected": "field"},
        valid=True,
        info={},
    )
    client = FakeClient(send_result=bad_result)
    agent = _make_agent(client)
    async with agent:
        with pytest.raises(AgentPayloadValidationError):
            await agent.review("review")


async def test_send_structured_propagates_classified_runtime_error() -> None:
    client = FakeClient(send_error=RuntimeAuthError("bad key"))
    agent = _make_agent(client)
    async with agent:
        with pytest.raises(RuntimeAuthError):
            await agent.review("review")


async def test_send_text_returns_plain_text() -> None:
    text_result = SendResult(
        message={"info": {}, "parts": [{"type": "text", "text": "hi"}]},
        text="hi from model",
        structured=None,
        valid=False,
        info={},
    )
    client = FakeClient(send_result=text_result)
    agent = _make_agent(client)
    async with agent:
        text = await agent.chat("say hello")
    assert text == "hi from model"
    # Plain-text path doesn't pass a format block.
    assert client.send_calls[0]["format"] is None


async def test_session_is_lazily_created_on_first_send() -> None:
    client = FakeClient(send_result=payload_send_result({"approved": True}))
    agent = _make_agent(client)
    async with agent:
        # No session yet — lazy.
        assert agent._session_id is None  # noqa: SLF001
        await agent.review("first")
        sid_after_first = agent._session_id  # noqa: SLF001
        assert sid_after_first is not None
        # Second send reuses the same session.
        await agent.review("second")
        assert agent._session_id == sid_after_first  # noqa: SLF001


async def test_rotate_session_deletes_current_and_lazy_recreates() -> None:
    client = FakeClient(send_result=payload_send_result({"approved": True}))
    agent = _make_agent(client)
    async with agent:
        await agent.review("first")
        sid_before = agent._session_id  # noqa: SLF001
        await agent.rotate_session()
        # Session pointer cleared.
        assert agent._session_id is None  # noqa: SLF001
        # Next send opens a fresh session.
        await agent.review("second")
        sid_after = agent._session_id  # noqa: SLF001
    assert sid_after is not None and sid_after != sid_before
    assert sid_before in client.deleted_sessions


async def test_close_deletes_session_and_closes_client() -> None:
    client = FakeClient(send_result=payload_send_result({"approved": True}))
    agent = _make_agent(client)
    async with agent:
        await agent.review("once")
        sid = agent._session_id  # noqa: SLF001
        assert client.closed is False
    # After context exit (close), the session was deleted and the
    # client closed.
    assert sid is not None
    assert sid in client.deleted_sessions
    assert client.closed is True


async def test_client_factory_substitutes_default_client() -> None:
    """Constructor ``client_factory=`` injects a fake without subclassing.

    Demonstrates the test pattern the rest of this module relies on: no
    ``_build_client`` override, no ``_*ForTest`` subclass — just pass a
    zero-arg callable that returns the desired client. Called lazily on
    the first send.
    """
    client = FakeClient(send_result=payload_send_result({"approved": True}))
    factory_calls = {"count": 0}

    def factory() -> Any:
        factory_calls["count"] += 1
        return client

    agent = _TestAgent(handle=fake_handle(), cwd="/tmp", client_factory=factory)
    # Factory is not invoked at construction — only at first send.
    assert factory_calls["count"] == 0
    async with agent:
        await agent.review("hello")
        # Same factory-returned client is held during the session.
        assert agent._client is client  # noqa: SLF001
    assert factory_calls["count"] == 1


async def test_model_validation_runs_once_then_caches() -> None:
    from maverick.executor.config import StepConfig

    client = FakeClient(send_result=payload_send_result({"approved": True}))
    agent = _make_agent(
        client,
        step_config=StepConfig(
            provider="openrouter",
            model_id="openai/gpt-oss-120b:free",
        ),
    )
    async with agent:
        await agent.review("first")
        await agent.review("second")
        await agent.review("third")
        # /provider should be hit exactly once — the cascade caches the
        # validated binding.
        assert client.list_provider_calls == 1
        # Send was issued each time with the correct model block.
        for call in client.send_calls:
            assert call["model"] == {
                "providerID": "openrouter",
                "modelID": "openai/gpt-oss-120b:free",
            }
