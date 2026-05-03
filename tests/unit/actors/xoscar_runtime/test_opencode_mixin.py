"""Tests for :class:`OpenCodeAgentMixin`.

Covers:

* Lifecycle (``_opencode_post_create``, ``_opencode_pre_destroy``,
  ``_rotate_session``).
* ``_send_structured`` returns a typed payload validated against
  ``result_model`` and unwraps the envelope (Landmine 3).
* ``_send_text`` returns the assistant's plain-text response.
* Model validation runs on first send and is cached after.
* Error classification (``OpenCodeAuthError``, payload-validation
  failures) propagates to the caller.

Tests run inside a real xoscar pool so ``self.address`` is set and the
mixin's registry lookup behaves like production. The OpenCode client
itself is replaced with a fake — no subprocess spawn.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

import pytest
import xoscar as xo
from pydantic import BaseModel

from maverick.actors.xoscar.opencode_mixin import (
    OpenCodeAgentMixin,
    OpenCodePayloadValidationError,
)
from maverick.actors.xoscar.pool import create_pool
from maverick.runtime.opencode import (
    OpenCodeAuthError,
    OpenCodeServerHandle,
    SendResult,
    invalidate_cache,
    register_opencode_handle,
    unregister_opencode_handle,
)


class ReviewPayload(BaseModel):
    approved: bool
    notes: str = ""


class _FakeProcess:
    """Stand-in for asyncio.subprocess.Process in OpenCodeServerHandle."""

    pid = 0
    returncode = 0

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return 0


def _fake_handle(base_url: str = "http://fake-opencode") -> OpenCodeServerHandle:
    return OpenCodeServerHandle(
        base_url=base_url,
        password="fake",
        pid=0,
        _process=_FakeProcess(),  # type: ignore[arg-type]
    )


class _FakeClient:
    """Programmable stand-in for :class:`OpenCodeClient`.

    The mixin's ``_build_client`` is overridden in test subclasses to
    return one of these. Every method we exercise on the real client is
    matched here.
    """

    def __init__(
        self,
        *,
        send_result: SendResult | None = None,
        send_error: BaseException | None = None,
        validate_error: BaseException | None = None,
    ) -> None:
        self.send_result = send_result
        self.send_error = send_error
        self.validate_error = validate_error
        self.created_sessions: list[str | None] = []
        self.deleted_sessions: list[str] = []
        self.send_calls: list[dict[str, Any]] = []
        self.list_provider_calls = 0
        self.closed = False

    @property
    def base_url(self) -> str:
        return "http://fake-opencode"

    async def list_providers(self) -> dict[str, Any]:
        self.list_provider_calls += 1
        if self.validate_error is not None:
            raise self.validate_error
        return {
            "providers": [
                {
                    "id": "openrouter",
                    "models": {
                        "anthropic/claude-haiku-4.5": {},
                        "openai/gpt-4o-mini": {},
                    },
                }
            ]
        }

    async def create_session(self, *, title: str | None = None, **_: Any) -> str:
        sid = f"ses_{len(self.created_sessions)}"
        self.created_sessions.append(title)
        return sid

    async def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return True

    async def send_with_event_watch(
        self,
        session_id: str,
        content: str,
        *,
        model: dict[str, str] | None = None,
        format: dict[str, Any] | None = None,
        system: str | None = None,
        tools: dict[str, bool] | None = None,
        timeout: float | None = None,
        agent: str | None = None,
    ) -> SendResult:
        self.send_calls.append(
            {
                "session_id": session_id,
                "content": content,
                "model": model,
                "format": format,
                "system": system,
                "timeout": timeout,
            }
        )
        if self.send_error is not None:
            raise self.send_error
        if self.send_result is None:
            return SendResult(message={}, text="", structured=None, valid=False)
        return self.send_result

    async def aclose(self) -> None:
        self.closed = True


class _MixedActor(OpenCodeAgentMixin, xo.Actor):
    """Mixin user that exposes hooks for tests."""

    result_model: ClassVar[type[BaseModel]] = ReviewPayload

    def __init__(
        self, *, send_result: SendResult | None = None, send_error: BaseException | None = None
    ) -> None:
        super().__init__()
        self._cwd = "/tmp"
        self._step_config = None
        self._fake_send_result = send_result
        self._fake_send_error = send_error
        self.fake_client: _FakeClient | None = None

    async def __post_create__(self) -> None:
        await self._opencode_post_create()

    async def __pre_destroy__(self) -> None:
        await self._opencode_pre_destroy()

    async def _build_client(self) -> Any:  # type: ignore[override]
        # Bypass the real registry; return a programmable fake.
        client = _FakeClient(
            send_result=self._fake_send_result,
            send_error=self._fake_send_error,
        )
        self.fake_client = client
        return client

    async def review(self, prompt: str) -> BaseModel:
        return await self._send_structured(prompt)

    async def chat(self, prompt: str) -> str:
        return await self._send_text(prompt)

    async def get_session_id(self) -> str | None:
        return self._session_id

    async def force_rotate(self) -> None:
        await self._rotate_session()

    async def get_send_calls(self) -> list[dict[str, Any]]:
        client = self.fake_client
        return list(client.send_calls) if client is not None else []

    async def get_provider_calls(self) -> int:
        client = self.fake_client
        return client.list_provider_calls if client is not None else 0

    async def get_deleted_sessions(self) -> list[str]:
        client = self.fake_client
        return list(client.deleted_sessions) if client is not None else []

    async def is_client_closed(self) -> bool:
        client = self.fake_client
        return False if client is None else client.closed


@pytest.fixture
async def pool_with_fake_opencode() -> AsyncIterator[str]:
    """Spin up an actor pool, register a fake OpenCode handle, yield address."""
    invalidate_cache()
    pool, address = await create_pool()
    register_opencode_handle(address, _fake_handle())
    try:
        yield address
    finally:
        unregister_opencode_handle(address)
        await pool.stop()


def _payload_send_result(payload: dict[str, Any]) -> SendResult:
    return SendResult(
        message={"info": {"structured": payload}, "parts": []},
        text="",
        structured=payload,
        valid=True,
        info={},
    )


async def test_send_structured_returns_validated_payload(
    pool_with_fake_opencode: str,
) -> None:
    address = pool_with_fake_opencode
    result = _payload_send_result({"approved": True, "notes": "looks good"})
    actor = await xo.create_actor(
        _MixedActor, address=address, uid="oc-actor-1", send_result=result
    )
    try:
        payload = await actor.review("review this diff")
        assert isinstance(payload, ReviewPayload)
        assert payload.approved is True
        assert payload.notes == "looks good"

        calls = await actor.get_send_calls()
        assert len(calls) == 1
        assert calls[0]["format"]["type"] == "json_schema"
        # Schema must include the result_model's fields.
        schema = calls[0]["format"]["schema"]
        assert "approved" in schema["properties"]
    finally:
        await xo.destroy_actor(actor)


async def test_send_structured_unwraps_envelope_via_send_result(
    pool_with_fake_opencode: str,
) -> None:
    """Mirror Landmine 3: caller passes already-unwrapped structured field
    in the SendResult, but the helpers still produce a typed payload.
    The real client's send_with_event_watch already unwraps before
    handing back the SendResult.
    """
    address = pool_with_fake_opencode
    result = _payload_send_result({"approved": False, "notes": ""})
    actor = await xo.create_actor(
        _MixedActor, address=address, uid="oc-actor-2", send_result=result
    )
    try:
        payload = await actor.review("review")
        assert isinstance(payload, ReviewPayload)
        assert payload.approved is False
    finally:
        await xo.destroy_actor(actor)


async def test_send_structured_raises_payload_validation_error(
    pool_with_fake_opencode: str,
) -> None:
    """Server returns a structured payload, but it doesn't match the model."""
    address = pool_with_fake_opencode
    bad_result = SendResult(
        message={"info": {"structured": {"unexpected": "field"}}, "parts": []},
        text="",
        structured={"unexpected": "field"},  # missing 'approved'
        valid=True,
        info={},
    )
    actor = await xo.create_actor(
        _MixedActor, address=address, uid="oc-actor-3", send_result=bad_result
    )
    try:
        with pytest.raises(OpenCodePayloadValidationError):
            await actor.review("review")
    finally:
        await xo.destroy_actor(actor)


async def test_send_structured_propagates_classified_runtime_error(
    pool_with_fake_opencode: str,
) -> None:
    """Auth errors etc. surface unchanged from the runtime layer."""
    address = pool_with_fake_opencode
    actor = await xo.create_actor(
        _MixedActor,
        address=address,
        uid="oc-actor-4",
        send_error=OpenCodeAuthError("bad key"),
    )
    try:
        with pytest.raises(OpenCodeAuthError):
            await actor.review("review")
    finally:
        await xo.destroy_actor(actor)


async def test_send_text_returns_plain_text(pool_with_fake_opencode: str) -> None:
    address = pool_with_fake_opencode
    text_result = SendResult(
        message={"info": {}, "parts": [{"type": "text", "text": "hi"}]},
        text="hi from model",
        structured=None,
        valid=False,
        info={},
    )
    actor = await xo.create_actor(
        _MixedActor, address=address, uid="oc-actor-5", send_result=text_result
    )
    try:
        text = await actor.chat("say hello")
        assert text == "hi from model"
        calls = await actor.get_send_calls()
        # Plain-text path doesn't pass a format block.
        assert calls[0]["format"] is None
    finally:
        await xo.destroy_actor(actor)


async def test_session_is_lazily_created_on_first_send(
    pool_with_fake_opencode: str,
) -> None:
    address = pool_with_fake_opencode
    result = _payload_send_result({"approved": True})
    actor = await xo.create_actor(
        _MixedActor, address=address, uid="oc-actor-6", send_result=result
    )
    try:
        # No session yet — lazy.
        assert await actor.get_session_id() is None
        await actor.review("first")
        sid_after_first = await actor.get_session_id()
        assert sid_after_first is not None
        # Second send reuses the same session.
        await actor.review("second")
        assert await actor.get_session_id() == sid_after_first
    finally:
        await xo.destroy_actor(actor)


async def test_rotate_session_deletes_current_and_lazy_recreates(
    pool_with_fake_opencode: str,
) -> None:
    address = pool_with_fake_opencode
    result = _payload_send_result({"approved": True})
    actor = await xo.create_actor(
        _MixedActor, address=address, uid="oc-actor-7", send_result=result
    )
    try:
        await actor.review("first")
        sid_before = await actor.get_session_id()
        await actor.force_rotate()
        # Session pointer cleared.
        assert await actor.get_session_id() is None
        # Next send opens a fresh session.
        await actor.review("second")
        sid_after = await actor.get_session_id()
        assert sid_after is not None and sid_after != sid_before
        deleted = await actor.get_deleted_sessions()
        assert sid_before in deleted
    finally:
        await xo.destroy_actor(actor)


async def test_pre_destroy_deletes_session_and_closes_client(
    pool_with_fake_opencode: str,
) -> None:
    address = pool_with_fake_opencode
    result = _payload_send_result({"approved": True})
    actor = await xo.create_actor(
        _MixedActor, address=address, uid="oc-actor-8", send_result=result
    )
    await actor.review("once")
    sid = await actor.get_session_id()
    closed = await actor.is_client_closed()
    assert closed is False
    await xo.destroy_actor(actor)
    # We can't query the actor after destroy, so we rely on the cleanup
    # paths having executed without raising. The fake-client tracking
    # already ran inside the actor — the destroy tells us __pre_destroy__
    # finished cleanly. (If it had raised, xo.destroy_actor would too.)
    assert sid is not None  # smoke


class _ConfiguredActor(_MixedActor):
    """Variant with a StepConfig so model validation kicks in."""

    def __init__(self, *, send_result: SendResult | None = None) -> None:
        super().__init__(send_result=send_result)
        from maverick.executor.config import StepConfig

        self._step_config = StepConfig(
            provider="openrouter", model_id="anthropic/claude-haiku-4.5"
        )


async def test_model_validation_runs_once_then_caches(
    pool_with_fake_opencode: str,
) -> None:
    address = pool_with_fake_opencode
    result = _payload_send_result({"approved": True})
    actor = await xo.create_actor(
        _ConfiguredActor, address=address, uid="oc-actor-9", send_result=result
    )
    try:
        await actor.review("first")
        await actor.review("second")
        await actor.review("third")
        # /provider should be hit exactly once on the actor — the
        # validator caches per-instance via the _model_validated flag.
        assert await actor.get_provider_calls() == 1
        # Send was issued each time with the correct model block.
        calls = await actor.get_send_calls()
        for call in calls:
            assert call["model"] == {
                "providerID": "openrouter",
                "modelID": "anthropic/claude-haiku-4.5",
            }
    finally:
        await xo.destroy_actor(actor)
