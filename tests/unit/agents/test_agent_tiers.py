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
    """Fake client that lets the test script per-binding behaviour.

    ``binding_behavior`` is the single-action shape (one result/exception
    used for every call). ``binding_sequence`` is the FIFO-list shape:
    each call pops the next action for that binding (useful for testing
    retry-then-succeed paths).
    """

    def __init__(
        self,
        *,
        binding_behavior: dict[str, BaseException | SendResult] | None = None,
        binding_sequence: dict[str, list[BaseException | SendResult]] | None = None,
    ) -> None:
        self._behavior = binding_behavior or {}
        self._sequence = {k: list(v) for k, v in (binding_sequence or {}).items()}
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
        # Sequence-style behavior wins over the single-action map when set.
        seq = self._sequence.get(binding_label)
        if seq:
            action: BaseException | SendResult = seq.pop(0)
        else:
            action = self._behavior.get(binding_label)  # type: ignore[assignment]
        if isinstance(action, BaseException):
            raise action
        if isinstance(action, SendResult):
            return action
        return _structured({"approved": True})

    async def aclose(self) -> None:
        return None


class _ReviewAgent(Agent):
    """Concrete Agent with one domain method; client injected via factory."""

    result_model: ClassVar[type[BaseModel]] = ReviewPayload
    provider_tier: ClassVar[str] = "review"

    async def review(self) -> Any:
        return await self._send_structured("review please")


def _make_review_agent(*, client: _CascadeClient, tier_overrides: dict[str, Tier]) -> _ReviewAgent:
    return _ReviewAgent(
        handle=fake_handle(),
        cwd="/tmp",
        tier_overrides=tier_overrides,
        client_factory=lambda: client,
    )


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
    agent = _make_review_agent(client=client, tier_overrides=_two_binding_review_tier())
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
    agent = _make_review_agent(client=client, tier_overrides=_two_binding_review_tier())
    async with agent:
        await agent.review()
        await agent.review()
        await agent.review()
    bindings = [s["binding"] for s in client.send_calls]
    # First call cascades over haiku (1 fail + 1 success); subsequent
    # calls go straight to qwen (1 success each).
    assert bindings.count("openrouter/anthropic/claude-haiku-4.5") == 1
    assert bindings.count("openrouter/qwen/qwen3-coder") == 3


async def test_rotate_session_clears_failed_bindings() -> None:
    """rotate_session() resets cascade stickiness so transient blips don't persist.

    Without this, a single auth blip mid-run permanently rules out the
    affected binding, and the cascade slowly collapses to whatever
    provider hasn't blipped yet. The /provider snapshot
    (``_validated_bindings``) is intentionally preserved — the live
    server's catalog doesn't change between beads.
    """
    client = _CascadeClient(
        binding_behavior={
            "openrouter/anthropic/claude-haiku-4.5": OpenCodeAuthError("transient"),
            "openrouter/qwen/qwen3-coder": _structured({"approved": True}),
        }
    )
    agent = _make_review_agent(client=client, tier_overrides=_two_binding_review_tier())
    async with agent:
        await agent.review()  # haiku fails → cascade to qwen succeeds.

        failed_before = {b.label for b in agent._failed_bindings}  # noqa: SLF001
        validated_before = {b.label for b in agent._validated_bindings}  # noqa: SLF001
        assert "openrouter/anthropic/claude-haiku-4.5" in failed_before

        await agent.rotate_session()

        assert agent._failed_bindings == set()  # noqa: SLF001
        # /provider snapshot is preserved — re-validating is wasted latency.
        assert {b.label for b in agent._validated_bindings} == validated_before  # noqa: SLF001

        # Next send retries haiku — and fails over again. Confirms the
        # binding was actually retried, not skipped from cache.
        await agent.review()

    haiku_calls = [
        s for s in client.send_calls if s["binding"] == "openrouter/anthropic/claude-haiku-4.5"
    ]
    assert len(haiku_calls) == 2


async def test_cost_record_captured_after_each_send() -> None:
    client = _CascadeClient(
        binding_behavior={
            "openrouter/anthropic/claude-haiku-4.5": _structured({"approved": True}),
        }
    )
    agent = _make_review_agent(client=client, tier_overrides=_two_binding_review_tier())
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
    agent = _make_review_agent(client=client, tier_overrides=_two_binding_review_tier())
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
    agent = _make_review_agent(client=client, tier_overrides=_two_binding_review_tier())
    async with agent:
        with pytest.raises(OpenCodeAuthError) as exc:
            await agent.review()
    assert "qwen auth" in str(exc.value)


async def test_transient_error_retries_on_same_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient blip retries the same binding before falling over.

    Pre-3.6 a single ``OpenCodeTransientError`` made the cascade fall
    straight over to the next provider. Now tenacity wraps the per-binding
    send: two transient blips followed by a success stays on the original
    binding.
    """
    from maverick.runtime.opencode import OpenCodeTransientError

    # No actual sleeps in tests.
    monkeypatch.setattr("maverick.agents.base.TRANSIENT_RETRY_WAIT_MIN_SECONDS", 0)
    monkeypatch.setattr("maverick.agents.base.TRANSIENT_RETRY_WAIT_MAX_SECONDS", 0)

    haiku = "openrouter/anthropic/claude-haiku-4.5"
    client = _CascadeClient(
        binding_sequence={
            haiku: [
                OpenCodeTransientError("503-1"),
                OpenCodeTransientError("503-2"),
                _structured({"approved": True}),
            ]
        }
    )
    agent = _make_review_agent(client=client, tier_overrides=_two_binding_review_tier())
    async with agent:
        result = await agent.review()

    assert isinstance(result, ReviewPayload)
    # All three calls hit haiku — no fallover to qwen.
    bindings = [s["binding"] for s in client.send_calls]
    assert bindings == [haiku, haiku, haiku]
    # haiku is NOT in the failed-bindings set (the eventual success cleared
    # the transient blip).
    assert all(b.label != haiku for b in agent._failed_bindings)  # noqa: SLF001


async def test_transient_retry_exhausts_then_falls_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If every retry on binding A fails transiently, cascade to B."""
    from maverick.runtime.opencode import OpenCodeTransientError

    monkeypatch.setattr("maverick.agents.base.TRANSIENT_RETRY_WAIT_MIN_SECONDS", 0)
    monkeypatch.setattr("maverick.agents.base.TRANSIENT_RETRY_WAIT_MAX_SECONDS", 0)

    haiku = "openrouter/anthropic/claude-haiku-4.5"
    qwen = "openrouter/qwen/qwen3-coder"
    client = _CascadeClient(
        binding_behavior={haiku: OpenCodeTransientError("flapping")},
        binding_sequence={qwen: [_structured({"approved": True})]},
    )
    agent = _make_review_agent(client=client, tier_overrides=_two_binding_review_tier())
    async with agent:
        result = await agent.review()

    assert isinstance(result, ReviewPayload)
    # Three retries on haiku, then one success on qwen.
    bindings = [s["binding"] for s in client.send_calls]
    assert bindings == [haiku, haiku, haiku, qwen]


async def test_auth_error_does_not_retry_same_binding() -> None:
    """Non-transient cascade errors (auth) fall over immediately, no retry."""
    haiku = "openrouter/anthropic/claude-haiku-4.5"
    qwen = "openrouter/qwen/qwen3-coder"
    client = _CascadeClient(
        binding_behavior={
            haiku: OpenCodeAuthError("bad key"),
            qwen: _structured({"approved": True}),
        }
    )
    agent = _make_review_agent(client=client, tier_overrides=_two_binding_review_tier())
    async with agent:
        await agent.review()

    bindings = [s["binding"] for s in client.send_calls]
    # Exactly one attempt on haiku (the auth error doesn't retry),
    # then one on qwen.
    assert bindings == [haiku, qwen]
