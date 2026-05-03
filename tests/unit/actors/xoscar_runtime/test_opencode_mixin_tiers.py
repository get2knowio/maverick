"""Tests for tier cascade + cost telemetry on :class:`OpenCodeAgentMixin`.

Builds on the patterns in ``test_opencode_mixin.py`` — a real xoscar
pool plus a fake-handle, fake-client setup — and adds a programmable
client that simulates per-binding errors so we can prove the cascade
swaps bindings on cascadable errors and stays on the winning binding
for subsequent sends.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

import pytest
import xoscar as xo
from pydantic import BaseModel

from maverick.actors.xoscar.opencode_mixin import OpenCodeAgentMixin
from maverick.actors.xoscar.pool import create_pool
from maverick.runtime.opencode import (
    OpenCodeAuthError,
    OpenCodeServerHandle,
    ProviderModel,
    SendResult,
    Tier,
    invalidate_cache,
    register_opencode_handle,
    register_tier_overrides,
    unregister_opencode_handle,
    unregister_tier_overrides,
)


class _FakeProcess:
    pid = 0
    returncode = 0

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return 0


def _fake_handle() -> OpenCodeServerHandle:
    return OpenCodeServerHandle(
        base_url="http://fake-opencode",
        password="fake",
        pid=0,
        _process=_FakeProcess(),  # type: ignore[arg-type]
    )


class ReviewPayload(BaseModel):
    approved: bool


def _structured(payload: dict[str, Any]) -> SendResult:
    info = {
        "providerID": "openrouter",
        "modelID": "anthropic/claude-haiku-4.5",
        "structured": payload,
        "tokens": {"input": 10, "output": 5, "cache": {"read": 0, "write": 0}},
        "cost": 0.0001,
    }
    return SendResult(
        message={"info": info, "parts": []},
        text="",
        structured=payload,
        valid=True,
        info=info,
    )


class _CascadeClient:
    """Fake client that lets the test script per-binding behaviour."""

    def __init__(
        self,
        *,
        binding_behavior: dict[str, BaseException | SendResult],
    ) -> None:
        self._behavior = binding_behavior
        self.send_calls: list[dict[str, Any]] = []
        self.list_provider_calls = 0
        self.created_sessions: list[str] = []
        self.deleted_sessions: list[str] = []

    @property
    def base_url(self) -> str:
        return "http://stub"

    async def list_providers(self) -> dict[str, Any]:
        self.list_provider_calls += 1
        return {
            "all": [
                {
                    "id": "openrouter",
                    "models": {
                        "anthropic/claude-haiku-4.5": {},
                        "qwen/qwen3-coder": {},
                    },
                }
            ],
            "connected": ["openrouter"],
            "default": {"openrouter": "anthropic/claude-haiku-4.5"},
        }

    async def create_session(self, *, title: str | None = None, **_: Any) -> str:
        sid = f"ses_{len(self.created_sessions)}"
        self.created_sessions.append(sid)
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
        binding_label = f"{model['providerID']}/{model['modelID']}" if model else "(none)"
        self.send_calls.append(
            {"binding": binding_label, "session_id": session_id, "format": format}
        )
        action = self._behavior.get(binding_label)
        if isinstance(action, BaseException):
            raise action
        if isinstance(action, SendResult):
            return action
        # Default: success.
        return _structured({"approved": True})

    async def aclose(self) -> None:
        return None


class _ReviewActor(OpenCodeAgentMixin, xo.Actor):
    result_model: ClassVar[type[BaseModel]] = ReviewPayload
    provider_tier: ClassVar[str] = "review"

    def __init__(
        self,
        *,
        client: _CascadeClient,
    ) -> None:
        super().__init__()
        self._cwd = "/tmp"
        self._step_config = None
        self._injected_client = client

    async def __post_create__(self) -> None:
        await self._opencode_post_create()

    async def __pre_destroy__(self) -> None:
        await self._opencode_pre_destroy()

    async def _build_client(self) -> Any:  # type: ignore[override]
        # Defer to the parent so tier_overrides_for(self.address) runs.
        from maverick.runtime.opencode import tier_overrides_for

        if self._tier_overrides is None:
            self._tier_overrides = tier_overrides_for(self.address)
        return self._injected_client

    async def review(self) -> Any:
        return await self._send_structured("review please")

    async def get_send_log(self) -> list[dict[str, Any]]:
        return list(self._injected_client.send_calls)

    async def get_failed_bindings(self) -> list[str]:
        return sorted(b.label for b in self._failed_bindings)

    async def get_validated_bindings(self) -> list[str]:
        return sorted(b.label for b in self._validated_bindings)

    async def get_last_cost(self) -> dict[str, Any] | None:
        rec = self._last_cost_record
        return rec.to_dict() if rec is not None else None


@pytest.fixture
async def pool_with_review_tier() -> AsyncIterator[str]:
    """Pool with a 2-binding review tier override registered."""
    invalidate_cache()
    pool, address = await create_pool()
    register_opencode_handle(address, _fake_handle())
    register_tier_overrides(
        address,
        {
            "review": Tier(
                name="review",
                bindings=(
                    ProviderModel("openrouter", "anthropic/claude-haiku-4.5"),
                    ProviderModel("openrouter", "qwen/qwen3-coder"),
                ),
            )
        },
    )
    try:
        yield address
    finally:
        unregister_tier_overrides(address)
        unregister_opencode_handle(address)
        await pool.stop()


async def test_cascade_falls_over_on_auth_error(pool_with_review_tier: str) -> None:
    address = pool_with_review_tier
    client = _CascadeClient(
        binding_behavior={
            "openrouter/anthropic/claude-haiku-4.5": OpenCodeAuthError("bad key"),
            "openrouter/qwen/qwen3-coder": _structured({"approved": True}),
        }
    )
    actor = await xo.create_actor(_ReviewActor, client=client, address=address, uid="cascade-1")
    try:
        result = await actor.review()
        assert isinstance(result, ReviewPayload)
        assert result.approved is True

        log = await actor.get_send_log()
        assert [s["binding"] for s in log] == [
            "openrouter/anthropic/claude-haiku-4.5",
            "openrouter/qwen/qwen3-coder",
        ]
        assert "openrouter/anthropic/claude-haiku-4.5" in await actor.get_failed_bindings()
    finally:
        await xo.destroy_actor(actor)


async def test_cascade_skips_failed_bindings_on_subsequent_sends(
    pool_with_review_tier: str,
) -> None:
    """Once a binding fails, the actor remembers and doesn't retry it."""
    address = pool_with_review_tier
    client = _CascadeClient(
        binding_behavior={
            "openrouter/anthropic/claude-haiku-4.5": OpenCodeAuthError("bad"),
            "openrouter/qwen/qwen3-coder": _structured({"approved": True}),
        }
    )
    actor = await xo.create_actor(_ReviewActor, client=client, address=address, uid="cascade-2")
    try:
        await actor.review()
        await actor.review()
        await actor.review()

        log = await actor.get_send_log()
        # First call cascades over haiku (1 fail + 1 success);
        # subsequent calls go straight to qwen (1 success each).
        bindings = [s["binding"] for s in log]
        assert bindings.count("openrouter/anthropic/claude-haiku-4.5") == 1
        assert bindings.count("openrouter/qwen/qwen3-coder") == 3
    finally:
        await xo.destroy_actor(actor)


async def test_cost_record_captured_after_each_send(
    pool_with_review_tier: str,
) -> None:
    address = pool_with_review_tier
    client = _CascadeClient(
        binding_behavior={
            "openrouter/anthropic/claude-haiku-4.5": _structured({"approved": True}),
        }
    )
    actor = await xo.create_actor(_ReviewActor, client=client, address=address, uid="cost-1")
    try:
        await actor.review()
        cost = await actor.get_last_cost()
        assert cost is not None
        assert cost["modelID"] == "anthropic/claude-haiku-4.5"
        assert cost["cost_usd"] == pytest.approx(0.0001)
        assert cost["input_tokens"] == 10
    finally:
        await xo.destroy_actor(actor)


async def test_validation_runs_once_per_binding(
    pool_with_review_tier: str,
) -> None:
    """Each binding is validated against /provider exactly once across sends."""
    address = pool_with_review_tier
    client = _CascadeClient(
        binding_behavior={
            "openrouter/anthropic/claude-haiku-4.5": _structured({"approved": True}),
        }
    )
    actor = await xo.create_actor(_ReviewActor, client=client, address=address, uid="validate-1")
    try:
        await actor.review()
        await actor.review()
        await actor.review()
        # 1 binding validated → 1 /provider call total
        assert client.list_provider_calls == 1
        validated = await actor.get_validated_bindings()
        assert validated == ["openrouter/anthropic/claude-haiku-4.5"]
    finally:
        await xo.destroy_actor(actor)


async def test_cascade_exhausted_propagates_last_error(
    pool_with_review_tier: str,
) -> None:
    address = pool_with_review_tier
    client = _CascadeClient(
        binding_behavior={
            "openrouter/anthropic/claude-haiku-4.5": OpenCodeAuthError("haiku auth"),
            "openrouter/qwen/qwen3-coder": OpenCodeAuthError("qwen auth"),
        }
    )
    actor = await xo.create_actor(_ReviewActor, client=client, address=address, uid="exhaust-1")
    try:
        with pytest.raises(OpenCodeAuthError) as exc:
            await actor.review()
        assert "qwen auth" in str(exc.value)
    finally:
        await xo.destroy_actor(actor)
