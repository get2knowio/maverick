"""Phase 3 tier-routing tests — reviewer + decomposer-detail.

The implementer-side tier-routing tests live in
``test_fly_tier_routing.py``. Phase 3 extends the same dispatch
primitives to the ReviewerActor (per-bead) and the refuel
decomposer-detail pool (per-unit). These tests exercise:

* :class:`FlySupervisor` builds one reviewer per defined tier and
  dispatches by bead complexity (no escalation).
* :class:`RefuelSupervisor` builds one decomposer per defined tier
  and dispatches detail prompts by per-unit outline complexity.
* The shared resolver (:meth:`FlySupervisor._resolve_tier_in`) is
  pure and works against any actor map.

End-to-end fly + refuel runs against the sample project are the
acceptance check (run by hand).
"""

from __future__ import annotations

import pytest
import xoscar as xo

from maverick.actors.xoscar.fly_supervisor import (
    _DEFAULT_TIER,
    TIER_ORDER,
    FlyInputs,
    FlySupervisor,
)
from maverick.config import (
    DecomposerTiersConfig,
    ImplementerTierConfig,
    ReviewerTiersConfig,
)

# ---------------------------------------------------------------------------
# Reviewer tier routing — fly supervisor.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_mode_uses_single_reviewer(pool_address: str) -> None:
    """When reviewer_tiers is None, one reviewer under _DEFAULT_TIER."""
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, reviewer_tiers=None),
        address=pool_address,
        uid="fly-reviewer-legacy",
    )
    try:
        reviewers = await sup.t_peek_reviewers()
        assert list(reviewers.keys()) == [_DEFAULT_TIER]
        # Resolution always returns the default sentinel in legacy.
        for c in (None, "trivial", "simple", "moderate", "complex"):
            tier = await sup.t_resolve_reviewer_tier(c)
            assert tier == _DEFAULT_TIER
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_reviewer_tier_mode_spawns_one_actor_per_defined_tier(
    pool_address: str,
) -> None:
    tiers = ReviewerTiersConfig(
        trivial=ImplementerTierConfig(provider="opencode"),
        moderate=ImplementerTierConfig(provider="claude"),
        complex=ImplementerTierConfig(provider="claude", model_id="opus"),
    )
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, reviewer_tiers=tiers),
        address=pool_address,
        uid="fly-reviewer-spawn",
    )
    try:
        reviewers = await sup.t_peek_reviewers()
        # Only the three defined tiers — `simple` was omitted.
        assert sorted(reviewers.keys()) == ["complex", "moderate", "trivial"]
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_reviewer_tier_mode_routes_by_complexity(pool_address: str) -> None:
    tiers = ReviewerTiersConfig(
        trivial=ImplementerTierConfig(provider="opencode"),
        simple=ImplementerTierConfig(provider="opencode"),
        moderate=ImplementerTierConfig(provider="claude"),
        complex=ImplementerTierConfig(provider="claude", model_id="opus"),
    )
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, reviewer_tiers=tiers),
        address=pool_address,
        uid="fly-reviewer-route",
    )
    try:
        for complexity in TIER_ORDER:
            tier = await sup.t_resolve_reviewer_tier(complexity)
            assert tier == complexity, (
                f"Expected reviewer complexity {complexity!r} to route to its own tier"
            )
        # Unclassified bead defaults to moderate.
        assert await sup.t_resolve_reviewer_tier(None) == "moderate"
        assert await sup.t_resolve_reviewer_tier("garbage") == "moderate"
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_reviewer_tier_mode_rounds_down_when_tier_missing(
    pool_address: str,
) -> None:
    """Sparse tiers — same round-DOWN rule the implementer uses."""
    tiers = ReviewerTiersConfig(
        simple=ImplementerTierConfig(provider="opencode"),
        complex=ImplementerTierConfig(provider="claude", model_id="opus"),
    )
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, reviewer_tiers=tiers),
        address=pool_address,
        uid="fly-reviewer-sparse",
    )
    try:
        # `moderate` rounds DOWN to `simple` (next-cheaper defined tier).
        assert await sup.t_resolve_reviewer_tier("moderate") == "simple"
        # `trivial` has no tier at-or-below; rounds UP to first defined.
        assert await sup.t_resolve_reviewer_tier("trivial") == "simple"
        # `complex` is defined; routes to itself.
        assert await sup.t_resolve_reviewer_tier("complex") == "complex"
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_reviewer_and_implementer_tiers_are_independent(
    pool_address: str,
) -> None:
    """Setting only implementer_tiers must not affect reviewer wiring,
    and vice versa — they're orthogonal config slots."""
    impl_tiers_cfg = ReviewerTiersConfig(
        simple=ImplementerTierConfig(provider="opencode"),
        complex=ImplementerTierConfig(provider="claude"),
    )
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(
            cwd="/tmp",
            max_beads=1,
            implementer_tiers=None,
            reviewer_tiers=impl_tiers_cfg,
        ),
        address=pool_address,
        uid="fly-mixed-tiers",
    )
    try:
        # Implementer is in legacy mode.
        impls = await sup.t_peek_implementers()
        assert list(impls.keys()) == [_DEFAULT_TIER]
        # Reviewer uses tiers.
        revs = await sup.t_peek_reviewers()
        assert sorted(revs.keys()) == ["complex", "simple"]
    finally:
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Generic resolver — pure, no actor pool needed.
# ---------------------------------------------------------------------------


def test_resolve_tier_in_legacy_mode_returns_default_sentinel() -> None:
    actors = {_DEFAULT_TIER: object()}
    for c in (None, "trivial", "simple", "moderate", "complex", "garbage"):
        assert FlySupervisor._resolve_tier_in(actors, c) == _DEFAULT_TIER


def test_resolve_tier_in_routes_known_complexity_to_self() -> None:
    actors = dict.fromkeys(TIER_ORDER, object())
    for c in TIER_ORDER:
        assert FlySupervisor._resolve_tier_in(actors, c) == c


def test_resolve_tier_in_unknown_complexity_defaults_to_moderate() -> None:
    actors = dict.fromkeys(TIER_ORDER, object())
    assert FlySupervisor._resolve_tier_in(actors, None) == "moderate"
    assert FlySupervisor._resolve_tier_in(actors, "garbage") == "moderate"


def test_resolve_tier_in_rounds_down_then_up() -> None:
    actors = {"simple": object(), "complex": object()}
    # moderate → simple (round DOWN to next-cheaper defined).
    assert FlySupervisor._resolve_tier_in(actors, "moderate") == "simple"
    # trivial → simple (nothing at-or-below, round UP to first defined).
    assert FlySupervisor._resolve_tier_in(actors, "trivial") == "simple"
    # complex → complex (defined).
    assert FlySupervisor._resolve_tier_in(actors, "complex") == "complex"


def test_resolve_tier_in_escalation_walks_defined_tiers_up() -> None:
    actors = {"simple": object(), "moderate": object(), "complex": object()}
    assert FlySupervisor._resolve_tier_in(actors, "simple", 0) == "simple"
    assert FlySupervisor._resolve_tier_in(actors, "simple", 1) == "moderate"
    assert FlySupervisor._resolve_tier_in(actors, "simple", 2) == "complex"
    # Cap at the highest defined tier.
    assert FlySupervisor._resolve_tier_in(actors, "simple", 99) == "complex"


def test_resolve_tier_in_escalation_skips_undefined_gaps() -> None:
    """When `moderate` is undefined, simple's escalation jumps to complex."""
    actors = {"simple": object(), "complex": object()}
    assert FlySupervisor._resolve_tier_in(actors, "simple", 1) == "complex"


# ---------------------------------------------------------------------------
# Decomposer-detail tier routing — refuel supervisor.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decomposer_legacy_mode_uses_round_robin_pool(
    pool_address: str,
) -> None:
    """When decomposer_tiers is None, the refuel supervisor builds the
    legacy round-robin pool of N workers; no demand pool is constructed."""
    from types import SimpleNamespace

    from maverick.actors.xoscar.refuel_supervisor import (
        RefuelInputs,
        RefuelSupervisor,
    )

    plan = SimpleNamespace(name="test", objective="x", success_criteria=[])
    sup = await xo.create_actor(
        RefuelSupervisor,
        RefuelInputs(
            cwd="/tmp",
            flight_plan=plan,
            decomposer_pool_size=2,
            skip_briefing=True,
            decomposer_tiers=None,
        ),
        address=pool_address,
        uid="refuel-decomposer-legacy",
    )
    try:
        snapshot = await sup.t_peek_decomposers()
        assert snapshot["mode"] == "legacy"
        assert snapshot["pool_size"] == 2
        assert snapshot["demand_pool"] is None
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_decomposer_tier_mode_uses_demand_pool(
    pool_address: str,
) -> None:
    """In tier mode the supervisor constructs an empty demand pool — actors
    spawn on demand as detail fan-out runs, not at supervisor init."""
    from types import SimpleNamespace

    from maverick.actors.xoscar.refuel_supervisor import (
        RefuelInputs,
        RefuelSupervisor,
    )

    plan = SimpleNamespace(name="test", objective="x", success_criteria=[])
    tiers = DecomposerTiersConfig(
        moderate=ImplementerTierConfig(provider="opencode"),
        complex=ImplementerTierConfig(provider="claude"),
    )
    sup = await xo.create_actor(
        RefuelSupervisor,
        RefuelInputs(
            cwd="/tmp",
            flight_plan=plan,
            decomposer_pool_size=3,  # cap on the demand pool
            skip_briefing=True,
            decomposer_tiers=tiers,
        ),
        address=pool_address,
        uid="refuel-decomposer-tiers",
    )
    try:
        snapshot = await sup.t_peek_decomposers()
        assert snapshot["mode"] == "tiered"
        assert snapshot["pool_size"] == 0  # no legacy round-robin actors
        # Demand pool present, cap == decomposer_pool_size, empty at start.
        assert snapshot["demand_pool"]["cap"] == 3
        assert snapshot["demand_pool"]["total"] == 0
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_decomposer_empty_tiers_falls_back_to_single_pool_worker(
    pool_address: str,
) -> None:
    """An empty tiers config (every slot None) is treated as 'no tiers' —
    the supervisor builds a single fallback pool worker so detail
    fan-out can still proceed."""
    from types import SimpleNamespace

    from maverick.actors.xoscar.refuel_supervisor import (
        RefuelInputs,
        RefuelSupervisor,
    )

    plan = SimpleNamespace(name="test", objective="x", success_criteria=[])
    sup = await xo.create_actor(
        RefuelSupervisor,
        RefuelInputs(
            cwd="/tmp",
            flight_plan=plan,
            decomposer_pool_size=3,
            skip_briefing=True,
            decomposer_tiers=DecomposerTiersConfig(),  # all None
        ),
        address=pool_address,
        uid="refuel-decomposer-empty-tiers",
    )
    try:
        snapshot = await sup.t_peek_decomposers()
        assert snapshot["mode"] == "legacy"
        assert snapshot["pool_size"] == 1
        assert snapshot["demand_pool"] is None
    finally:
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Reviewer transient-error escalation (FUTURE.md §2.10 follow-up).
# ---------------------------------------------------------------------------
#
# The reviewer's tier is normally fixed by the bead's complexity (no
# escalation). But on a *transient* prompt error (HTTP 5xx, "no
# capacity"), the supervisor walks one tier up and replays the same
# review request. These tests exercise the resolver + can_escalate
# helpers that drive that loop, plus the legacy mode's no-op behaviour.


@pytest.mark.asyncio
async def test_reviewer_resolver_accepts_escalation_level(pool_address: str) -> None:
    """Bumping the escalation level walks the reviewer one tier up."""
    tiers = ReviewerTiersConfig(
        simple=ImplementerTierConfig(provider="gemini"),
        moderate=ImplementerTierConfig(provider="copilot"),
        complex=ImplementerTierConfig(provider="claude"),
    )
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, reviewer_tiers=tiers),
        address=pool_address,
        uid="fly-reviewer-escalation",
    )
    try:
        # Simple complexity, no escalation → simple tier.
        assert await sup.t_resolve_reviewer_tier("simple") == "simple"
        # +1 → walks up to next defined tier.
        assert await sup.t_resolve_reviewer_tier("simple", 1) == "moderate"
        # +2 → top tier.
        assert await sup.t_resolve_reviewer_tier("simple", 2) == "complex"
        # +3 → already at top, stays at complex (caller checks
        # can_escalate to know whether to bump further).
        assert await sup.t_resolve_reviewer_tier("simple", 3) == "complex"
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_can_escalate_reviewer_walks_up_then_stops(pool_address: str) -> None:
    """``can_escalate_reviewer`` returns True until the top tier."""
    tiers = ReviewerTiersConfig(
        simple=ImplementerTierConfig(provider="gemini"),
        moderate=ImplementerTierConfig(provider="copilot"),
        complex=ImplementerTierConfig(provider="claude"),
    )
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, reviewer_tiers=tiers),
        address=pool_address,
        uid="fly-reviewer-can-escalate",
    )
    try:
        # From simple → moderate is escalable.
        assert await sup.t_can_escalate_reviewer("simple", 0) is True
        # From moderate → complex is escalable.
        assert await sup.t_can_escalate_reviewer("simple", 1) is True
        # From complex → nothing higher.
        assert await sup.t_can_escalate_reviewer("simple", 2) is False
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_can_escalate_reviewer_legacy_returns_false(pool_address: str) -> None:
    """Legacy single-actor mode never escalates."""
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, reviewer_tiers=None),
        address=pool_address,
        uid="fly-reviewer-can-escalate-legacy",
    )
    try:
        assert await sup.t_can_escalate_reviewer("simple", 0) is False
        assert await sup.t_can_escalate_reviewer(None, 0) is False
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_can_escalate_reviewer_at_top_tier_returns_false(
    pool_address: str,
) -> None:
    """When the bead already routes to the top defined tier, no escalation."""
    tiers = ReviewerTiersConfig(
        complex=ImplementerTierConfig(provider="claude"),
    )
    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=1, reviewer_tiers=tiers),
        address=pool_address,
        uid="fly-reviewer-top-tier",
    )
    try:
        # Only one tier defined → can't go higher.
        assert await sup.t_can_escalate_reviewer("complex", 0) is False
        assert await sup.t_can_escalate_reviewer("simple", 0) is False
    finally:
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Graceful-stop honouring at bead-loop boundary.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bead_loop_exits_when_graceful_stop_requested(
    pool_address: str,
) -> None:
    """When the graceful-stop flag is set before the loop polls, the
    loop returns without calling ``select_next_bead`` — no bead gets
    pulled from the queue and no bead processing starts."""
    from maverick.workflows.fly_beads.graceful_stop import (
        request_graceful_stop,
        reset_graceful_stop,
    )

    sup = await xo.create_actor(
        FlySupervisor,
        FlyInputs(cwd="/tmp", max_beads=10, reviewer_tiers=None),
        address=pool_address,
        uid="fly-graceful-stop",
    )
    try:
        reset_graceful_stop()  # paranoia in case a prior test set it
        request_graceful_stop()

        processed = await sup.t_run_bead_loop_for_test()

        # Loop short-circuited at the top of the iteration before
        # ``select_next_bead`` ran, so no bead was processed.
        assert processed == 0
    finally:
        reset_graceful_stop()
        await xo.destroy_actor(sup)
