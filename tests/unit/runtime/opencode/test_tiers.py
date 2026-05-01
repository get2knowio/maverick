"""Unit tests for the provider-tier resolver and cascade logic."""

from __future__ import annotations

import pytest

from maverick.runtime.opencode import (
    CASCADE_ERRORS,
    DEFAULT_TIERS,
    OpenCodeAuthError,
    OpenCodeContextOverflowError,
    OpenCodeError,
    OpenCodeModelNotFoundError,
    OpenCodeStructuredOutputError,
    OpenCodeTransientError,
    ProviderModel,
    SendResult,
    Tier,
    cascade_send,
    cost_record_from_send,
    resolve_tier,
    tiers_from_config,
)

# ---------------------------------------------------------------------------
# resolve_tier
# ---------------------------------------------------------------------------


def test_resolve_tier_returns_default_for_known_name() -> None:
    tier = resolve_tier("review")
    assert isinstance(tier, Tier)
    assert tier.name == "review"
    assert len(tier.bindings) >= 1


def test_resolve_tier_uses_override_when_provided() -> None:
    custom = Tier(
        name="review",
        bindings=(ProviderModel("custom", "model-x"),),
    )
    tier = resolve_tier("review", override={"review": custom})
    assert tier is custom


def test_resolve_tier_falls_back_to_default_when_override_missing_key() -> None:
    custom = Tier("review", bindings=(ProviderModel("custom", "x"),))
    tier = resolve_tier("review", override={"implement": custom})
    assert tier.name == "review"
    assert tier.bindings == DEFAULT_TIERS["review"].bindings


def test_resolve_tier_raises_on_unknown_name() -> None:
    with pytest.raises(KeyError):
        resolve_tier("nonexistent")


def test_default_tiers_cover_every_role_actor_declares() -> None:
    """Every actor's ``provider_tier`` ClassVar must resolve out-of-the-box."""
    expected = {"review", "implement", "briefing", "decompose", "generate"}
    assert expected.issubset(DEFAULT_TIERS.keys())


def test_tier_construction_rejects_empty_bindings() -> None:
    with pytest.raises(ValueError):
        Tier("empty", bindings=())


# ---------------------------------------------------------------------------
# cascade_send
# ---------------------------------------------------------------------------


def _success(structured: dict | None = None) -> SendResult:
    return SendResult(
        message={"info": {"structured": structured}, "parts": []},
        text="",
        structured=structured,
        valid=structured is not None,
        info={"providerID": "x", "modelID": "y"},
    )


@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda: OpenCodeAuthError("bad key"),
        lambda: OpenCodeModelNotFoundError("no such model"),
        lambda: OpenCodeStructuredOutputError("model didn't tool-call", retries=0),
        lambda: OpenCodeTransientError("502 bad gateway"),
    ],
)
async def test_cascade_falls_over_on_each_cascadable_error(exc_factory) -> None:
    tier = Tier(
        "review",
        bindings=(
            ProviderModel("p", "first"),
            ProviderModel("p", "second"),
        ),
    )
    calls: list[ProviderModel] = []

    async def send(binding: ProviderModel) -> SendResult:
        calls.append(binding)
        if binding.model_id == "first":
            raise exc_factory()
        return _success({"ok": True})

    outcome = await cascade_send(tier, send)
    assert outcome.binding.model_id == "second"
    assert [c.model_id for c in calls] == ["first", "second"]
    assert len(outcome.failed_bindings) == 1


async def test_cascade_does_not_retry_skipped_bindings() -> None:
    tier = Tier(
        "review",
        bindings=(
            ProviderModel("p", "first"),
            ProviderModel("p", "second"),
        ),
    )
    seen: list[str] = []

    async def send(binding: ProviderModel) -> SendResult:
        seen.append(binding.model_id)
        return _success({"ok": True})

    skip = {ProviderModel("p", "first")}
    outcome = await cascade_send(tier, send, skip=skip)
    assert seen == ["second"]
    assert outcome.binding.model_id == "second"


async def test_cascade_raises_when_every_binding_fails() -> None:
    tier = Tier(
        "review",
        bindings=(
            ProviderModel("p", "first"),
            ProviderModel("p", "second"),
        ),
    )

    async def send(binding: ProviderModel) -> SendResult:
        raise OpenCodeAuthError(f"auth failed on {binding.model_id}")

    with pytest.raises(OpenCodeAuthError) as exc:
        await cascade_send(tier, send)
    # The last failure surfaces (cascade preserves the most recent error).
    assert "second" in str(exc.value)


async def test_cascade_does_not_swallow_context_overflow() -> None:
    tier = Tier(
        "review",
        bindings=(ProviderModel("p", "first"), ProviderModel("p", "second")),
    )

    async def send(binding: ProviderModel) -> SendResult:
        raise OpenCodeContextOverflowError("too big")

    with pytest.raises(OpenCodeContextOverflowError):
        await cascade_send(tier, send)


def test_cascade_errors_set_includes_expected_classes() -> None:
    """Sanity-check that the cascade error tuple covers what we test."""
    assert OpenCodeAuthError in CASCADE_ERRORS
    assert OpenCodeModelNotFoundError in CASCADE_ERRORS
    assert OpenCodeTransientError in CASCADE_ERRORS
    assert OpenCodeStructuredOutputError in CASCADE_ERRORS
    # Context overflow is intentionally NOT cascadable.
    assert OpenCodeContextOverflowError not in CASCADE_ERRORS


async def test_cascade_outcome_records_attempts_and_failures() -> None:
    tier = Tier(
        "review",
        bindings=(
            ProviderModel("p", "first"),
            ProviderModel("p", "second"),
            ProviderModel("p", "third"),
        ),
    )

    async def send(binding: ProviderModel) -> SendResult:
        if binding.model_id in {"first", "second"}:
            raise OpenCodeAuthError(f"failed {binding.model_id}")
        return _success({"ok": True})

    outcome = await cascade_send(tier, send)
    assert [a.model_id for a in outcome.attempts] == ["first", "second", "third"]
    assert [b.model_id for b, _ in outcome.failed_bindings] == ["first", "second"]
    assert outcome.binding.model_id == "third"


# ---------------------------------------------------------------------------
# cost_record_from_send
# ---------------------------------------------------------------------------


def test_cost_record_extracts_full_info_block() -> None:
    info = {
        "providerID": "openrouter",
        "modelID": "anthropic/claude-haiku-4.5",
        "cost": 0.0123,
        "tokens": {
            "input": 1000,
            "output": 200,
            "cache": {"read": 50, "write": 10},
        },
        "finish": "tool-calls",
    }
    result = SendResult(
        message={"info": info},
        text="",
        structured=None,
        valid=False,
        info=info,
    )
    record = cost_record_from_send(result)
    assert record.provider_id == "openrouter"
    assert record.model_id == "anthropic/claude-haiku-4.5"
    assert record.cost_usd == pytest.approx(0.0123)
    assert record.input_tokens == 1000
    assert record.output_tokens == 200
    assert record.cache_read_tokens == 50
    assert record.cache_write_tokens == 10
    assert record.finish == "tool-calls"


def test_cost_record_handles_missing_fields() -> None:
    result = SendResult(message={}, text="", structured=None, valid=False, info={})
    record = cost_record_from_send(result)
    assert record.provider_id is None
    assert record.model_id is None
    assert record.cost_usd is None
    assert record.input_tokens == 0


# ---------------------------------------------------------------------------
# tiers_from_config
# ---------------------------------------------------------------------------


def test_tiers_from_config_returns_empty_when_unset() -> None:
    class _Empty:
        provider_tiers = None

    assert tiers_from_config(_Empty()) == {}


def test_tiers_from_config_translates_pydantic_block() -> None:
    from maverick.config import ProviderModelEntry, ProviderTiersConfig

    block = ProviderTiersConfig(
        tiers={
            "review": [
                ProviderModelEntry(provider="openrouter", model_id="anthropic/claude-haiku-4.5"),
                ProviderModelEntry(provider="openrouter", model_id="qwen/qwen3-coder"),
            ],
            "implement": [
                ProviderModelEntry(provider="custom", model_id="x"),
            ],
        }
    )

    class _Cfg:
        provider_tiers = block

    out = tiers_from_config(_Cfg())
    assert set(out.keys()) == {"review", "implement"}
    assert out["review"].bindings[0].model_id == "anthropic/claude-haiku-4.5"
    assert out["review"].bindings[1].model_id == "qwen/qwen3-coder"
    assert out["implement"].bindings == (ProviderModel("custom", "x"),)


def test_tiers_from_config_skips_empty_tier_lists() -> None:
    """An empty list under a tier key is treated as "no override for that tier".

    Tier construction rejects empty bindings, so we filter the empty list
    out instead of raising.
    """
    from maverick.config import ProviderTiersConfig

    block = ProviderTiersConfig(tiers={"review": []})

    class _Cfg:
        provider_tiers = block

    out = tiers_from_config(_Cfg())
    assert out == {}


def test_unrecognized_error_is_not_cascadable() -> None:
    """Generic OpenCodeError (not a subclass listed in CASCADE_ERRORS) propagates."""
    tier = Tier("review", bindings=(ProviderModel("p", "first"),))

    async def send(_: ProviderModel) -> SendResult:
        raise OpenCodeError("generic failure")

    import asyncio

    with pytest.raises(OpenCodeError):
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            cascade_send(tier, send)
        )
