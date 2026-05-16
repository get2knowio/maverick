"""Tests for :class:`maverick.squadron.refuel.RefuelSquadron` +
:class:`maverick.squadron.decomposer_pool.DecomposerAgentPool`.

Pattern D path: airframe runtimes constructed via
:func:`runtime_for_agent`. The shared :func:`stub_airframe_runtime`
fixture in ``conftest.py`` patches :func:`airframe.runtime_for` so
no real adapter SDK is touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from maverick.agents.decomposer import DecomposerAgent
from maverick.config import MaverickConfig
from maverick.squadron.decomposer_pool import DecomposerAgentPool
from maverick.squadron.refuel import RefuelSquadron


# ---------------------------------------------------------------------------
# RefuelSquadron
# ---------------------------------------------------------------------------


async def test_refuel_squadron_builds_generator_and_pool(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    async with RefuelSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        assert squadron.generator is not None
        assert isinstance(squadron.decomposer_pool, DecomposerAgentPool)
        # Pool starts empty.
        assert squadron.decomposer_pool.total_live == 0
    # Generator constructs one runtime at startup.
    assert len(stub_airframe_runtime["constructed"]) == 1


async def test_decomposer_pool_acquire_spawns_under_cap(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    async with RefuelSquadron(
        cwd=tmp_path, config=config_with_agents, decomposer_pool_cap=2
    ) as squadron:
        a1 = await squadron.decomposer_pool.acquire("simple")
        assert isinstance(a1, DecomposerAgent)
        assert squadron.decomposer_pool.total_live == 1
        a2 = await squadron.decomposer_pool.acquire("complex")
        assert isinstance(a2, DecomposerAgent)
        assert squadron.decomposer_pool.total_live == 2
    # 1 generator + 2 decomposers = 3 runtimes built.
    assert len(stub_airframe_runtime["constructed"]) == 3


async def test_decomposer_pool_release_then_reacquire_reuses_idle(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    async with RefuelSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        a1 = await squadron.decomposer_pool.acquire("simple")
        await squadron.decomposer_pool.release(a1, "simple")
        a2 = await squadron.decomposer_pool.acquire("simple")
    # Same agent reused — only one decomposer runtime constructed despite
    # two acquires.
    assert a1 is a2


async def test_refuel_squadron_requires_agents_config(tmp_path: Path) -> None:
    """An empty ``agents:`` block surfaces as ValueError at open."""
    config = MaverickConfig()
    with pytest.raises(ValueError, match="agents.generate"):
        async with RefuelSquadron(cwd=tmp_path, config=config):
            pass


# ---------------------------------------------------------------------------
# DecomposerAgentPool — directly (no squadron)
# ---------------------------------------------------------------------------


class _FakeDecomposer:
    """Minimal stand-in: tracks closes + set_context calls."""

    def __init__(self, tier: str) -> None:
        self.tier = tier
        self.tag = f"decomposer.pool.{tier}"
        self.closed = False
        self.contexts: list[dict[str, Any]] = []

    async def set_context(self, **kwargs: Any) -> None:
        self.contexts.append(kwargs)

    async def close(self) -> None:
        self.closed = True


async def test_pool_evicts_lru_when_at_cap() -> None:
    spawned: list[_FakeDecomposer] = []

    async def factory(tier: str) -> Any:
        a = _FakeDecomposer(tier)
        spawned.append(a)
        return a

    pool = DecomposerAgentPool(cap=2, factory=factory)  # type: ignore[arg-type]
    a1 = await pool.acquire("simple")
    a2 = await pool.acquire("complex")
    await pool.release(a1, "simple")
    await pool.release(a2, "complex")
    # Pool full + both idle. Acquiring a third (different tier) evicts
    # the LRU idle (a1, oldest released).
    a3 = await pool.acquire("moderate")
    assert pool.total_live == 2
    # The evicted one was closed.
    assert a1.closed is True  # type: ignore[attr-defined]
    # New agent of new tier is spawned.
    assert a3.tier == "moderate"  # type: ignore[attr-defined]


async def test_pool_set_context_broadcasts_and_seeds_new_agents() -> None:
    spawned: list[_FakeDecomposer] = []

    async def factory(tier: str) -> Any:
        a = _FakeDecomposer(tier)
        spawned.append(a)
        return a

    pool = DecomposerAgentPool(cap=4, factory=factory)  # type: ignore[arg-type]
    a1 = await pool.acquire("simple")
    await pool.set_context(
        outline_json="{}",
        flight_plan_content="plan",
        verification_properties="vp",
    )
    # a1 received the broadcast.
    assert len(a1.contexts) == 1  # type: ignore[attr-defined]
    # New agent spawned later also receives the cached context.
    a2 = await pool.acquire("complex")
    assert len(a2.contexts) == 1  # type: ignore[attr-defined]


async def test_pool_teardown_closes_everything() -> None:
    spawned: list[_FakeDecomposer] = []

    async def factory(tier: str) -> Any:
        a = _FakeDecomposer(tier)
        spawned.append(a)
        return a

    pool = DecomposerAgentPool(cap=4, factory=factory)  # type: ignore[arg-type]
    await pool.acquire("simple")
    await pool.acquire("complex")
    await pool.teardown()
    assert pool.total_live == 0
    assert all(a.closed for a in spawned)


async def test_squadron_closes_tracked_briefings(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """Squadron tracks every briefing built and closes them on exit.

    Refuel fans out 4+ briefings per phase; one missed close = leaked
    runtime. The squadron owns lifecycle so callers can't forget.
    """

    class _Schema(BaseModel):
        ok: bool = True

    squadron = RefuelSquadron(cwd=tmp_path, config=config_with_agents)
    async with squadron:
        briefings = [
            squadron.build_briefing_agent(agent_name="navigator", result_model=_Schema),
            squadron.build_briefing_agent(agent_name="structuralist", result_model=_Schema),
            squadron.build_briefing_agent(agent_name="recon", result_model=_Schema),
        ]
        for b in briefings:
            await b.open()
        assert len(squadron._briefings) == 3  # noqa: SLF001

    # After context exit, each briefing's runtime.close() was called.
    # The first runtime constructed is the generator; the next 3 are briefings.
    briefing_runtimes = stub_airframe_runtime["constructed"][1:]
    assert len(briefing_runtimes) == 3
    assert all(r.close_calls >= 1 for r in briefing_runtimes)
