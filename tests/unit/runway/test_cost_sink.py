"""Tests for the cost-telemetry → runway sink wiring.

Covers:

* :class:`CostEntry` round-trip through ``append_cost_entry`` /
  ``get_cost_entries`` with optional filters.
* ``make_cost_sink`` returns an async closure that accepts both
  :class:`CostEntry` instances and dict-shaped records.
* The mixin's ``_record_cost`` flushes to a registered sink and stays
  silent when none is registered.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from maverick.runway.models import CostEntry
from maverick.runway.store import RunwayStore, make_cost_sink

# ---------------------------------------------------------------------------
# RunwayStore.append_cost_entry / get_cost_entries
# ---------------------------------------------------------------------------


@pytest.fixture
async def initialized_store(tmp_path: Path) -> RunwayStore:
    store = RunwayStore(tmp_path / "runway")
    await store.initialize()
    return store


async def test_append_and_read_round_trip(initialized_store: RunwayStore) -> None:
    entry = CostEntry(
        actor="reviewer[fly-supervisor:reviewer]",
        tier="review",
        provider_id="openrouter",
        model_id="anthropic/claude-haiku-4.5",
        cost_usd=0.0123,
        input_tokens=1000,
        output_tokens=200,
        cache_read_tokens=50,
        cache_write_tokens=10,
        finish="tool-calls",
        bead_id="bd-1",
    )
    await initialized_store.append_cost_entry(entry)
    entries = await initialized_store.get_cost_entries()
    assert len(entries) == 1
    assert entries[0].model_id == "anthropic/claude-haiku-4.5"
    assert entries[0].cost_usd == pytest.approx(0.0123)


async def test_filters_by_bead_actor_tier(initialized_store: RunwayStore) -> None:
    for actor, tier, bead in (
        ("reviewer[a]", "review", "bd-1"),
        ("reviewer[b]", "review", "bd-2"),
        ("implementer[a]", "implement", "bd-1"),
    ):
        await initialized_store.append_cost_entry(CostEntry(actor=actor, tier=tier, bead_id=bead))

    by_bead = await initialized_store.get_cost_entries(bead_id="bd-1")
    assert {e.actor for e in by_bead} == {"reviewer[a]", "implementer[a]"}

    by_actor = await initialized_store.get_cost_entries(actor="reviewer[b]")
    assert [e.bead_id for e in by_actor] == ["bd-2"]

    by_tier = await initialized_store.get_cost_entries(tier="implement")
    assert [e.actor for e in by_tier] == ["implementer[a]"]


async def test_limit_returns_most_recent(initialized_store: RunwayStore) -> None:
    for i in range(5):
        await initialized_store.append_cost_entry(CostEntry(actor="x", bead_id=f"bd-{i}"))
    entries = await initialized_store.get_cost_entries(limit=2)
    # ``get_cost_entries`` returns the *last* N — newest at the tail.
    assert [e.bead_id for e in entries] == ["bd-3", "bd-4"]


# ---------------------------------------------------------------------------
# make_cost_sink
# ---------------------------------------------------------------------------


async def test_sink_appends_cost_entry_instance(initialized_store: RunwayStore) -> None:
    sink = make_cost_sink(initialized_store)
    await sink(CostEntry(actor="x", tier="review", bead_id="b1"))
    entries = await initialized_store.get_cost_entries()
    assert [e.actor for e in entries] == ["x"]


async def test_sink_tolerates_dict_input(initialized_store: RunwayStore) -> None:
    """Defensive — actor mixin always sends CostEntry, but accept dicts too."""
    sink = make_cost_sink(initialized_store)
    payload: dict[str, Any] = {"actor": "y", "tier": "implement", "bead_id": "b2"}
    await sink(payload)
    entries = await initialized_store.get_cost_entries()
    assert [e.actor for e in entries] == ["y"]


# ---------------------------------------------------------------------------
# Agent._emit_cost → sink wiring
# ---------------------------------------------------------------------------


def _stub_cost() -> Any:
    from airframe.cost import CostRecord

    return CostRecord(
        provider_id="openrouter",
        model_id="anthropic/claude-haiku-4.5",
        cost_usd=0.0042,
        input_tokens=100,
        output_tokens=20,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="tool-calls",
    )


def _stub_runtime() -> Any:
    from unittest.mock import AsyncMock, MagicMock

    runtime = MagicMock()
    runtime.label = "stub"
    runtime.reset = AsyncMock()
    runtime.close = AsyncMock()
    return runtime


async def test_agent_flushes_to_injected_sink(
    initialized_store: RunwayStore, tmp_path: Path
) -> None:
    """_emit_cost calls the constructor-injected sink, appending to runway."""
    import asyncio

    from maverick.agents.base import Agent
    from maverick.agents.context import tagged

    sink = make_cost_sink(initialized_store)

    class _BareAgent(Agent):
        provider_tier = "review"  # type: ignore[assignment]

    agent = _BareAgent(runtime=_stub_runtime(), cwd="/tmp", cost_sink=sink)

    with tagged(bead_id="bd-test"):
        agent._emit_cost(_stub_cost())

    await asyncio.sleep(0)
    await asyncio.sleep(0.05)

    entries = await initialized_store.get_cost_entries()
    assert len(entries) == 1
    e = entries[0]
    assert e.actor == "_BareAgent"
    assert e.tier == "review"
    assert e.bead_id == "bd-test"
    assert e.cost_usd == pytest.approx(0.0042)
    assert e.model_id == "anthropic/claude-haiku-4.5"


async def test_cost_entry_without_active_tags_has_empty_bead_id(
    initialized_store: RunwayStore, tmp_path: Path
) -> None:
    """Outside any ``tagged()`` block, bead_id falls back to the empty string."""
    import asyncio

    from maverick.agents.base import Agent

    sink = make_cost_sink(initialized_store)

    class _BareAgent(Agent):
        provider_tier = "review"  # type: ignore[assignment]

    agent = _BareAgent(runtime=_stub_runtime(), cwd="/tmp", cost_sink=sink)

    agent._emit_cost(_stub_cost())

    await asyncio.sleep(0)
    await asyncio.sleep(0.05)

    entries = await initialized_store.get_cost_entries()
    assert len(entries) == 1
    assert entries[0].bead_id == ""


async def test_agent_no_sink_skips_silently(tmp_path: Path) -> None:
    """When no sink is injected, _emit_cost only logs (doesn't crash)."""
    from maverick.agents.base import Agent

    class _BareAgent(Agent):
        provider_tier = "review"  # type: ignore[assignment]

    agent = _BareAgent(runtime=_stub_runtime(), cwd="/tmp")  # no cost_sink
    agent._emit_cost(_stub_cost())
    assert agent._cost_sink is None
