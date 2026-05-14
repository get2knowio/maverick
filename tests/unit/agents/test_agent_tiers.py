"""Tests for tier cascade + cost telemetry on :class:`Agent`.

Same shape as the legacy ``test_opencode_mixin_tiers.py`` — programmable
client returning per-binding behaviour — but tests the ``Agent`` class
directly, no xoscar pool, no registry. Tier overrides are passed via
the ``tier_overrides=`` constructor argument.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from pydantic import BaseModel

from maverick.agents.base import Agent
from maverick.runtime.opencode import (
    OpenCodeAuthError,
    ProviderModel,
    SendResult,
    Tier,
    invalidate_cache,
)

from .conftest import fake_handle


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

    def __init__(self, *, binding_behavior: dict[str, BaseException | SendResult]) -> None:
        self._behavior = binding_behavior
        self.send_calls: list[dict[str, Any]] = []
        self.list_provider_calls = 0
        self.created_sessions: list[str] = []
        self.deleted_sessions: list[str] = []

    @property
    def base_url(self) -> str:
        # Use a unique URL per fake client so the validation cache
        # (keyed by base_url) doesn't bleed across tests.
        return f"http://stub-{id(self)}"

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
        return _structured({"approved": True})

    async def aclose(self) -> None:
        return None


class _ReviewAgent(Agent):
    result_model: ClassVar[type[BaseModel]] = ReviewPayload
    provider_tier: ClassVar[str] = "review"

    def __init__(self, *, client: _CascadeClient, tier_overrides: dict[str, Tier]) -> None:
        super().__init__(
            handle=fake_handle(),
            cwd="/tmp",
            tier_overrides=tier_overrides,
        )
        self._injected_client = client

    def _build_client(self) -> Any:  # type: ignore[override]
        return self._injected_client

    async def review(self) -> Any:
        return await self._send_structured("review please")


def _two_binding_review_tier() -> dict[str, Tier]:
    return {
        "review": Tier(
            name="review",
            bindings=(
                ProviderModel("openrouter", "anthropic/claude-haiku-4.5"),
                ProviderModel("openrouter", "qwen/qwen3-coder"),
            ),
        )
    }


@pytest.fixture(autouse=True)
def _clear_validation_cache() -> None:
    invalidate_cache()


async def test_cascade_falls_over_on_auth_error() -> None:
    client = _CascadeClient(
        binding_behavior={
            "openrouter/anthropic/claude-haiku-4.5": OpenCodeAuthError("bad key"),
            "openrouter/qwen/qwen3-coder": _structured({"approved": True}),
        }
    )
    agent = _ReviewAgent(client=client, tier_overrides=_two_binding_review_tier())
    async with agent:
        result = await agent.review()
    assert isinstance(result, ReviewPayload)
    assert result.approved is True

    bindings = [s["binding"] for s in client.send_calls]
    assert bindings == [
        "openrouter/anthropic/claude-haiku-4.5",
        "openrouter/qwen/qwen3-coder",
    ]
    failed = sorted(b.label for b in agent._failed_bindings)  # noqa: SLF001
    assert "openrouter/anthropic/claude-haiku-4.5" in failed


async def test_cascade_skips_failed_bindings_on_subsequent_sends() -> None:
    """Once a binding fails, the agent remembers and doesn't retry it."""
    client = _CascadeClient(
        binding_behavior={
            "openrouter/anthropic/claude-haiku-4.5": OpenCodeAuthError("bad"),
            "openrouter/qwen/qwen3-coder": _structured({"approved": True}),
        }
    )
    agent = _ReviewAgent(client=client, tier_overrides=_two_binding_review_tier())
    async with agent:
        await agent.review()
        await agent.review()
        await agent.review()
    bindings = [s["binding"] for s in client.send_calls]
    # First call cascades over haiku (1 fail + 1 success); subsequent
    # calls go straight to qwen (1 success each).
    assert bindings.count("openrouter/anthropic/claude-haiku-4.5") == 1
    assert bindings.count("openrouter/qwen/qwen3-coder") == 3


async def test_cost_record_captured_after_each_send() -> None:
    client = _CascadeClient(
        binding_behavior={
            "openrouter/anthropic/claude-haiku-4.5": _structured({"approved": True}),
        }
    )
    agent = _ReviewAgent(client=client, tier_overrides=_two_binding_review_tier())
    async with agent:
        await agent.review()
        cost = agent.last_cost_record
    assert cost is not None
    rec = cost.to_dict()
    assert rec["modelID"] == "anthropic/claude-haiku-4.5"
    assert rec["cost_usd"] == pytest.approx(0.0001)
    assert rec["input_tokens"] == 10


async def test_validation_runs_once_per_binding() -> None:
    """Each binding is validated against /provider exactly once across sends."""
    client = _CascadeClient(
        binding_behavior={
            "openrouter/anthropic/claude-haiku-4.5": _structured({"approved": True}),
        }
    )
    agent = _ReviewAgent(client=client, tier_overrides=_two_binding_review_tier())
    async with agent:
        await agent.review()
        await agent.review()
        await agent.review()
    # 1 binding validated → 1 /provider call total.
    assert client.list_provider_calls == 1
    validated = sorted(b.label for b in agent._validated_bindings)  # noqa: SLF001
    assert validated == ["openrouter/anthropic/claude-haiku-4.5"]


async def test_cascade_exhausted_propagates_last_error() -> None:
    client = _CascadeClient(
        binding_behavior={
            "openrouter/anthropic/claude-haiku-4.5": OpenCodeAuthError("haiku auth"),
            "openrouter/qwen/qwen3-coder": OpenCodeAuthError("qwen auth"),
        }
    )
    agent = _ReviewAgent(client=client, tier_overrides=_two_binding_review_tier())
    async with agent:
        with pytest.raises(OpenCodeAuthError) as exc:
            await agent.review()
    assert "qwen auth" in str(exc.value)
