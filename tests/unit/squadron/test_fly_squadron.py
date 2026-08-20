"""Tests for :class:`maverick.squadron.fly.FlySquadron`.

Pattern D path: the squadron constructs agents via
:func:`maverick.runtime.agent_factory.runtime_for_agent`, which is
stubbed via the shared :func:`stub_airframe_runtime` fixture.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from maverick.config import AgentBindingConfig, AgentsConfig, MaverickConfig
from maverick.squadron.fly import DEFAULT_TIER, FlySquadron


async def test_open_builds_agents_under_default_tier(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """No tier configs → one coder + one pair of reviewers under DEFAULT_TIER."""
    async with FlySquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        assert list(squadron.coders) == [DEFAULT_TIER]
        assert list(squadron.correctness_reviewers) == [DEFAULT_TIER]
        assert list(squadron.completeness_reviewers) == [DEFAULT_TIER]
    # One coder + two reviewers = three airframe runtimes constructed.
    assert len(stub_airframe_runtime["constructed"]) == 3


async def test_squadron_requires_agents_config(tmp_path: Path) -> None:
    """An empty ``agents:`` block surfaces as a clear ValueError at open."""
    config = MaverickConfig()  # nothing in agents
    with pytest.raises(ValueError, match="agents.implement"):
        async with FlySquadron(cwd=tmp_path, config=config):
            pass


async def test_per_tier_coder_built_when_implementer_tiers_configured(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """``implementer_tiers`` → one coder per defined tier; overrides flow through.

    Per-complexity ``ImplementerTierConfig`` is converted to an
    :class:`AgentBindingConfig` and passed as ``binding_override=`` to
    the factory, so the resulting runtime is pinned to the tier's
    provider/model_id (not the role default).
    """
    from maverick.config import ImplementerTierConfig, ImplementerTiersConfig

    tiers = ImplementerTiersConfig(
        simple=ImplementerTierConfig(provider="opencode", model_id="gpt-5-nano"),
        complex=ImplementerTierConfig(provider="claude", model_id="claude-opus-4-7"),
    )
    async with FlySquadron(
        cwd=tmp_path,
        config=config_with_agents,
        implementer_tiers=tiers,
    ) as squadron:
        assert set(squadron.coders) == {"simple", "complex"}
        assert squadron.coder_for("simple") is not squadron.coder_for("complex")
        # Lookup for an undefined tier falls back to an arbitrary cached
        # coder — the supervisor's escalation resolver handles unknown
        # tiers before reaching us.
        assert squadron.coder_for("trivial") in squadron.coders.values()
    # The factory was called with the per-tier provider IDs.
    providers = [r.provider_id for r in stub_airframe_runtime["constructed"]]
    assert "opencode" in providers  # simple
    assert "claude" in providers  # complex (or the role default — both match)


async def test_implementer_tier_override_pins_model_on_runtime(
    stub_airframe_runtime: dict[str, Any],
    tmp_path: Path,
) -> None:
    """A defined tier's (provider, model_id) lands on the constructed runtime."""
    from maverick.config import ImplementerTierConfig, ImplementerTiersConfig

    config = MaverickConfig(
        agents=AgentsConfig(
            implement=AgentBindingConfig(provider="claude", model_id="claude-sonnet-4-6"),
            review=AgentBindingConfig(provider="claude", model_id="claude-haiku-4-5"),
        )
    )
    tiers = ImplementerTiersConfig(
        complex=ImplementerTierConfig(provider="claude", model_id="claude-opus-4-7"),
    )
    async with FlySquadron(
        cwd=tmp_path,
        config=config,
        implementer_tiers=tiers,
    ) as squadron:
        assert "complex" in squadron.coders
    # Find the runtime built for the `complex` coder — it should be
    # pinned to claude-opus-4-7 (the tier override), not the
    # claude-sonnet-4-6 role default.
    pinned_models = {r.model for r in stub_airframe_runtime["constructed"]}
    assert "claude-opus-4-7" in pinned_models


async def test_default_tier_fallback_when_no_implementer_tiers(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """No tier configs → one coder under DEFAULT_TIER (legacy single-actor mode)."""
    async with FlySquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        assert list(squadron.coders) == [DEFAULT_TIER]
        assert squadron.coder_for("anything") is squadron.coder_for(DEFAULT_TIER)


async def test_rotate_for_new_bead_resets_each_runtime(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """rotate_for_new_bead rotates every agent's session.

    Every squadron now builds a real ``ProtectionPolicy`` at open time
    (056-context-file-protection), so ``Agent.rotate_session`` is a
    close-and-reopen of the airframe session rather than
    ``runtime.reset()`` (research.md R4) — the first session opened at
    ``open()`` gets closed and a fresh one takes its place.
    """
    async with FlySquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        await squadron.rotate_for_new_bead()
        # All three constructed runtimes (coder + correctness + completeness)
        # opened a session at squadron-open and closed-and-reopened it
        # during rotate — checked before the `async with` exit closes
        # everything again.
        for runtime in stub_airframe_runtime["constructed"]:
            assert len(runtime.sessions) == 2, runtime.sessions
            assert runtime.sessions[0].close_calls == 1
            assert runtime.sessions[1].close_calls == 0
    # The legacy reset() path is untouched once sessions are in play.
    assert all(r.reset_calls == 0 for r in stub_airframe_runtime["constructed"])


async def test_retarget_protection_for_isolation_rebinds_every_agent(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """057-isolated-bead-workspaces: retargeting re-roots every agent's
    protection policy at the workspace and rotates its session (research.md
    R11) — the same close-and-reopen `rotate_for_new_bead` already exercises."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    async with FlySquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        agents = list(squadron._all_agents())
        assert all(a._protection_policy is not None for a in agents)
        assert all(a._protection_policy.root == tmp_path.resolve() for a in agents)

        await squadron.retarget_protection_for_isolation(workspace)

        assert all(a._protection_policy is not None for a in agents)
        assert all(a._protection_policy.root == workspace.resolve() for a in agents)
        # Every agent rotated its session so Layer 1's gate rebuilds
        # against the new policy immediately (Agent.rebind_protection's
        # own contract — it doesn't reopen on its own).
        for runtime in stub_airframe_runtime["constructed"]:
            assert len(runtime.sessions) == 2

        await squadron.retarget_protection_for_isolation(None)
        assert all(a._protection_policy.root == tmp_path.resolve() for a in agents)
        for runtime in stub_airframe_runtime["constructed"]:
            assert len(runtime.sessions) == 3


async def test_close_tears_down_all_runtimes(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """Squadron.close() calls runtime.close() on every agent."""
    async with FlySquadron(cwd=tmp_path, config=config_with_agents):
        pass
    close_counts = [r.close_calls for r in stub_airframe_runtime["constructed"]]
    assert all(c >= 1 for c in close_counts)


async def test_bead_context_tags_propagate_through_gather(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """``bead_context`` stamps tags visible to concurrent tasks underneath."""
    import asyncio

    from maverick.agents.context import current_tags

    async with FlySquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        seen: dict[str, dict[str, str]] = {}

        async def capture(name: str) -> None:
            await asyncio.sleep(0)
            seen[name] = current_tags()

        with squadron.bead_context(bead_id="b-7", complexity="simple"):
            await asyncio.gather(capture("a"), capture("b"))

    assert seen["a"] == {"bead_id": "b-7", "complexity": "simple"}
    assert seen["b"] == {"bead_id": "b-7", "complexity": "simple"}
