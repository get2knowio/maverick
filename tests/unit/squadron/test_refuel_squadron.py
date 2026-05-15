"""Tests for :class:`maverick.squadron.refuel.RefuelSquadron` +
:class:`maverick.squadron.decomposer_pool.DecomposerAgentPool`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from maverick.agents.decomposer import DecomposerAgent
from maverick.config import MaverickConfig
from maverick.squadron.decomposer_pool import DecomposerAgentPool
from maverick.squadron.refuel import RefuelSquadron
from tests.unit.agents.conftest import FakeClient, fake_handle, payload_send_result


@pytest.fixture
def fake_squadron_handle(monkeypatch: Any) -> Any:
    handle = fake_handle()

    async def _fake_spawn(*_args: Any, **_kwargs: Any) -> Any:
        return handle

    async def _fake_validate(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("maverick.squadron.base.spawn_opencode_server", _fake_spawn)
    monkeypatch.setattr("maverick.squadron.base.validate_model_id", _fake_validate)
    return handle


@pytest.fixture
def fake_agent_clients(monkeypatch: Any) -> dict[str, FakeClient]:
    clients: dict[str, FakeClient] = {}

    def _build_client(self: Any) -> Any:
        c = FakeClient(send_result=payload_send_result({"approved": True}))
        clients[self.tag] = c
        return c

    monkeypatch.setattr("maverick.agents.base.Agent._build_client", _build_client)
    return clients


# ---------------------------------------------------------------------------
# RefuelSquadron
# ---------------------------------------------------------------------------


async def test_refuel_squadron_builds_generator_and_pool(
    fake_squadron_handle: Any,
    fake_agent_clients: dict[str, FakeClient],
    tmp_path: Path,
) -> None:
    config = MaverickConfig()
    async with RefuelSquadron(cwd=tmp_path, config=config) as squadron:
        assert squadron.generator is not None
        assert isinstance(squadron.decomposer_pool, DecomposerAgentPool)
        # Pool starts empty.
        assert squadron.decomposer_pool.total_live == 0


async def test_decomposer_pool_acquire_spawns_under_cap(
    fake_squadron_handle: Any,
    fake_agent_clients: dict[str, FakeClient],
    tmp_path: Path,
) -> None:
    config = MaverickConfig()
    async with RefuelSquadron(cwd=tmp_path, config=config, decomposer_pool_cap=2) as squadron:
        a1 = await squadron.decomposer_pool.acquire("simple")
        assert isinstance(a1, DecomposerAgent)
        assert squadron.decomposer_pool.total_live == 1
        a2 = await squadron.decomposer_pool.acquire("complex")
        assert isinstance(a2, DecomposerAgent)
        assert squadron.decomposer_pool.total_live == 2


async def test_decomposer_pool_release_then_reacquire_reuses_idle(
    fake_squadron_handle: Any,
    fake_agent_clients: dict[str, FakeClient],
    tmp_path: Path,
) -> None:
    config = MaverickConfig()
    async with RefuelSquadron(cwd=tmp_path, config=config) as squadron:
        a1 = await squadron.decomposer_pool.acquire("simple")
        await squadron.decomposer_pool.release(a1, "simple")
        a2 = await squadron.decomposer_pool.acquire("simple")
    # Same agent reused.
    assert a1 is a2


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
    fake_squadron_handle: Any,
    fake_agent_clients: dict[str, FakeClient],
    tmp_path: Path,
) -> None:
    """Squadron tracks every briefing built and closes them on exit.

    Pre-3.3 the caller had to remember to call ``await agent.close()``
    on each briefing. Refuel fans out 4+ briefings per phase; one
    missed close = leaked HTTP client. Now the squadron owns lifecycle.
    """
    from pydantic import BaseModel

    class _Schema(BaseModel):
        ok: bool = True

    config = MaverickConfig()
    squadron = RefuelSquadron(cwd=tmp_path, config=config)
    async with squadron:
        briefings = [
            squadron.build_briefing_agent(agent_name="navigator", result_model=_Schema),
            squadron.build_briefing_agent(agent_name="structuralist", result_model=_Schema),
            squadron.build_briefing_agent(agent_name="recon", result_model=_Schema),
        ]
        # Open them so they have client state worth closing.
        for b in briefings:
            await b.open()
        # Squadron now tracks all 3.
        assert len(squadron._briefings) == 3  # noqa: SLF001

    # After context exit each agent's client got closed.
    # (The fake client tags closed via .closed = True in conftest.)
    for b in briefings:
        # Even if no send happened (lazy client build), close() is safe.
        assert b._client is None or b._client.closed  # noqa: SLF001
