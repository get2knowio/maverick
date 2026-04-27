"""Tests for the FlySupervisor's per-bead complexity tier routing.

FUTURE.md §2.10 Phase 2: when ``actors.fly.implementer.tiers`` is set,
the fly supervisor spawns one ``ImplementerActor`` per defined tier and
dispatches each bead to the actor matching its decomposer-assigned
``complexity``. On fix-loop overflow at a tier, the bead is escalated
one tier upward.

These tests exercise the routing primitives in isolation. End-to-end
fly-with-tiers flows are deferred to e2e on a sample project.
"""

from __future__ import annotations

import pytest
import xoscar as xo

from maverick.actors.xoscar.fly_supervisor import (
    _DEFAULT_TIER,
    TIER_ORDER,
    FlyInputs,
    FlySupervisor,
    _extract_complexity_from_md,
)
from maverick.config import ImplementerTierConfig, ImplementerTiersConfig

# ---------------------------------------------------------------------------
# Frontmatter extraction — pure helper, no actor pool needed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["trivial", "simple", "moderate", "complex"])
def test_extract_complexity_reads_frontmatter(value: str) -> None:
    md = f"---\nwork-unit: wu-1\ncomplexity: {value}\n---\n\n## Task\n\nfoo\n"
    assert _extract_complexity_from_md(md) == value


def test_extract_complexity_returns_none_when_field_missing() -> None:
    md = "---\nwork-unit: wu-1\nsequence: 1\n---\n\n## Task\n\nfoo\n"
    assert _extract_complexity_from_md(md) is None


def test_extract_complexity_returns_none_for_unknown_value() -> None:
    md = (
        "---\n"
        "work-unit: wu-1\n"
        "complexity: epic\n"  # not in TIER_ORDER
        "---\n\n## Task\n\nfoo\n"
    )
    assert _extract_complexity_from_md(md) is None


def test_extract_complexity_handles_quoted_value() -> None:
    md = '---\nwork-unit: wu-1\ncomplexity: "moderate"\n---\n\n## Task\n\nfoo\n'
    assert _extract_complexity_from_md(md) == "moderate"


def test_extract_complexity_handles_no_frontmatter() -> None:
    assert _extract_complexity_from_md("## Task\n\nfoo\n") is None
    assert _extract_complexity_from_md("") is None


# ---------------------------------------------------------------------------
# Legacy mode (no tiers config) — single implementer actor, no routing.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_mode_uses_single_implementer(pool_address: str) -> None:
    """When implementer_tiers is None, one actor is created and routing
    always returns the _DEFAULT_TIER fallback regardless of complexity."""
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, implementer_tiers=None),
        address=pool_address,
        uid="fly-tier-legacy",
    )
    try:
        # `_implementers` is the new tier map. Legacy mode populates it
        # with a single _DEFAULT_TIER entry.
        impls = await _peek_implementers(sup)
        assert list(impls.keys()) == [_DEFAULT_TIER]

        # _resolve_implementer_tier always returns _DEFAULT_TIER in legacy.
        for c in (None, "trivial", "simple", "moderate", "complex"):
            tier = await _resolve_tier(sup, c, 0)
            assert tier == _DEFAULT_TIER
    finally:
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Tier mode — N actors spawned, complexity drives dispatch.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier_mode_spawns_one_actor_per_defined_tier(pool_address: str) -> None:
    tiers = ImplementerTiersConfig(
        trivial=ImplementerTierConfig(provider="opencode"),
        moderate=ImplementerTierConfig(provider="claude"),
        complex=ImplementerTierConfig(provider="claude", model_id="opus"),
    )
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, implementer_tiers=tiers),
        address=pool_address,
        uid="fly-tier-spawn",
    )
    try:
        impls = await _peek_implementers(sup)
        # Only the three defined tiers — `simple` was omitted.
        assert sorted(impls.keys()) == ["complex", "moderate", "trivial"]
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_tier_mode_routes_by_complexity(pool_address: str) -> None:
    """Bead complexity → matching tier when defined."""
    tiers = ImplementerTiersConfig(
        trivial=ImplementerTierConfig(provider="opencode"),
        simple=ImplementerTierConfig(provider="opencode"),
        moderate=ImplementerTierConfig(provider="claude"),
        complex=ImplementerTierConfig(provider="claude", model_id="opus"),
    )
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, implementer_tiers=tiers),
        address=pool_address,
        uid="fly-tier-route",
    )
    try:
        for complexity in TIER_ORDER:
            tier = await _resolve_tier(sup, complexity, 0)
            assert tier == complexity, (
                f"Expected complexity {complexity!r} to route to its own tier"
            )
        # Unclassified bead defaults to moderate.
        assert await _resolve_tier(sup, None, 0) == "moderate"
        assert await _resolve_tier(sup, "garbage", 0) == "moderate"
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_tier_mode_rounds_down_when_tier_missing(pool_address: str) -> None:
    """Sparse tiers config: a complexity with no matching tier rounds DOWN
    to the nearest cheaper defined tier (and rounds UP only if no cheaper
    tier exists)."""
    tiers = ImplementerTiersConfig(
        simple=ImplementerTierConfig(provider="opencode"),
        complex=ImplementerTierConfig(provider="claude", model_id="opus"),
    )
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, implementer_tiers=tiers),
        address=pool_address,
        uid="fly-tier-sparse",
    )
    try:
        # `moderate` rounds DOWN to `simple` (next-cheaper defined tier).
        assert await _resolve_tier(sup, "moderate", 0) == "simple"
        # `trivial` has no tier at-or-below; rounds UP to first defined.
        assert await _resolve_tier(sup, "trivial", 0) == "simple"
        # `complex` is defined; routes to itself.
        assert await _resolve_tier(sup, "complex", 0) == "complex"
    finally:
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Escalation: fix-loop overflow promotes the bead one tier up.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalation_steps_up_one_tier(pool_address: str) -> None:
    """escalation_level=1 on a `simple` bead targets `moderate` (next up)."""
    tiers = ImplementerTiersConfig(
        simple=ImplementerTierConfig(provider="opencode"),
        moderate=ImplementerTierConfig(provider="claude"),
        complex=ImplementerTierConfig(provider="claude", model_id="opus"),
    )
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, implementer_tiers=tiers),
        address=pool_address,
        uid="fly-tier-escalate",
    )
    try:
        assert await _resolve_tier(sup, "simple", 0) == "simple"
        assert await _resolve_tier(sup, "simple", 1) == "moderate"
        assert await _resolve_tier(sup, "simple", 2) == "complex"
        # Capped at the highest defined tier.
        assert await _resolve_tier(sup, "simple", 99) == "complex"
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_can_escalate_returns_false_at_top_tier(pool_address: str) -> None:
    """A bead already at the highest defined tier cannot escalate further."""
    tiers = ImplementerTiersConfig(
        simple=ImplementerTierConfig(provider="opencode"),
        complex=ImplementerTierConfig(provider="claude", model_id="opus"),
    )
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, implementer_tiers=tiers),
        address=pool_address,
        uid="fly-tier-cap",
    )
    try:
        # `complex` bead at level 0 -> already at top; can't escalate.
        assert await _can_escalate(sup, "complex", 0) is False
        # `simple` bead at level 0 -> can escalate to `complex` (skips
        # missing `moderate`).
        assert await _can_escalate(sup, "simple", 0) is True
        # `simple` bead at level 1 -> already routed to `complex`; no more.
        assert await _can_escalate(sup, "simple", 1) is False
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_can_escalate_always_false_in_legacy_mode(pool_address: str) -> None:
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, implementer_tiers=None),
        address=pool_address,
        uid="fly-tier-legacy-escalate",
    )
    try:
        for c in (None, "trivial", "simple", "moderate", "complex"):
            for level in (0, 1, 2):
                assert await _can_escalate(sup, c, level) is False
    finally:
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Tier-config merge: override fields stack on top of base StepConfig.
# ---------------------------------------------------------------------------


def test_merge_tier_config_replaces_only_set_fields() -> None:
    from maverick.executor.config import StepConfig

    base = StepConfig(
        provider="claude",
        model_id="sonnet",
        timeout=600,
        max_tokens=64000,
        temperature=0.0,
    )
    override = ImplementerTierConfig(
        provider="opencode",
        model_id="openrouter/openai/gpt-oss-120b",
        # timeout / max_tokens / temperature deliberately left None.
    )
    merged = FlySupervisor._merge_tier_config(base, override)
    assert merged.provider == "opencode"
    assert merged.model_id == "openrouter/openai/gpt-oss-120b"
    # Untouched fields fall through from base.
    assert merged.timeout == 600
    assert merged.max_tokens == 64000
    assert merged.temperature == 0.0


def test_merge_tier_config_synthesizes_when_no_base() -> None:
    override = ImplementerTierConfig(
        provider="opencode",
        model_id="moonshotai/kimi-k2.6",
        timeout=900,
    )
    merged = FlySupervisor._merge_tier_config(None, override)
    assert merged.provider == "opencode"
    assert merged.model_id == "moonshotai/kimi-k2.6"
    assert merged.timeout == 900


def test_merge_tier_config_returns_base_when_override_empty() -> None:
    from maverick.executor.config import StepConfig

    base = StepConfig(provider="claude", model_id="sonnet")
    merged = FlySupervisor._merge_tier_config(base, ImplementerTierConfig())
    # No override fields -> identity.
    assert merged is base


# ---------------------------------------------------------------------------
# Helpers — xoscar method dispatch into private methods for inspection.
# ---------------------------------------------------------------------------


async def _peek_implementers(sup: xo.ActorRef) -> dict[str, xo.ActorRef]:
    """Read the supervisor's _implementers map. xoscar attribute access
    isn't supported, so dispatch a small custom method via xo.create_actor's
    exposed methods. Workaround: use a sentinel domain method we add for
    test inspection."""
    return await sup.t_peek_implementers()


async def _resolve_tier(sup: xo.ActorRef, complexity: str | None, level: int) -> str:
    return await sup.t_resolve_tier(complexity, level)


async def _can_escalate(sup: xo.ActorRef, complexity: str | None, level: int) -> bool:
    return await sup.t_can_escalate(complexity, level)
