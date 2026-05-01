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
# OpenCodeAgentMixin._record_cost → sink wiring
# ---------------------------------------------------------------------------


async def test_mixin_flushes_to_registered_sink(
    initialized_store: RunwayStore, tmp_path: Path
) -> None:
    """_record_cost calls the pool-scoped sink, which appends to runway."""
    from maverick.actors.xoscar.opencode_mixin import OpenCodeAgentMixin
    from maverick.actors.xoscar.pool import create_pool
    from maverick.runtime.opencode import (
        ProviderModel,
        SendResult,
        cost_sink_for,
        register_cost_sink,
        unregister_cost_sink,
    )

    pool, address = await create_pool()
    sink = make_cost_sink(initialized_store)
    register_cost_sink(address, sink)
    try:
        # cost_sink_for returns the sink we registered.
        assert cost_sink_for(address) is sink

        # Build a stripped-down mixin that exposes _record_cost without
        # going through a full actor — we just need the pool address.
        class _Bare(OpenCodeAgentMixin):
            def __init__(self) -> None:
                self.address = address  # type: ignore[assignment]
                self._actor_tag = "test-actor"
                self._validated_bindings = set()
                self._failed_bindings = set()
                self._last_cost_record = None
                self._cost_sink = None
                self._cost_sink_resolved = False
                self._current_bead_id = "bd-test"

            provider_tier = "review"  # type: ignore[assignment]

        actor = _Bare()
        # Build a SendResult with cost info, run cost_record_from_send,
        # then call _record_cost.
        info = {
            "providerID": "openrouter",
            "modelID": "anthropic/claude-haiku-4.5",
            "cost": 0.0042,
            "tokens": {"input": 100, "output": 20, "cache": {"read": 0, "write": 0}},
            "finish": "tool-calls",
        }
        from maverick.runtime.opencode import cost_record_from_send

        result = SendResult(
            message={"info": info},
            text="",
            structured=None,
            valid=False,
            info=info,
        )
        actor._last_cost_record = cost_record_from_send(result)
        actor._record_cost(
            result, binding=ProviderModel("openrouter", "anthropic/claude-haiku-4.5")
        )

        # _record_cost schedules an asyncio.create_task — drain it.
        import asyncio

        # Give the scheduled coroutine a tick to run.
        await asyncio.sleep(0)
        await asyncio.sleep(0.05)

        entries = await initialized_store.get_cost_entries()
        assert len(entries) == 1
        e = entries[0]
        assert e.actor == "test-actor"
        assert e.tier == "review"
        assert e.bead_id == "bd-test"
        assert e.cost_usd == pytest.approx(0.0042)
        assert e.model_id == "anthropic/claude-haiku-4.5"
    finally:
        unregister_cost_sink(address)
        await pool.stop()


async def test_mixin_no_sink_skips_silently(tmp_path: Path) -> None:
    """When no sink is registered, _record_cost only logs (doesn't crash)."""
    from maverick.actors.xoscar.opencode_mixin import OpenCodeAgentMixin
    from maverick.actors.xoscar.pool import create_pool
    from maverick.runtime.opencode import (
        ProviderModel,
        SendResult,
        cost_record_from_send,
    )

    pool, address = await create_pool()
    try:

        class _Bare(OpenCodeAgentMixin):
            def __init__(self) -> None:
                self.address = address  # type: ignore[assignment]
                self._actor_tag = "test"
                self._validated_bindings = set()
                self._failed_bindings = set()
                self._last_cost_record = None
                self._cost_sink = None
                self._cost_sink_resolved = False
                self._current_bead_id = ""

            provider_tier = "review"  # type: ignore[assignment]

        actor = _Bare()
        info = {"providerID": "x", "modelID": "y", "cost": 0.001, "tokens": {}}
        result = SendResult(
            message={"info": info}, text="", structured=None, valid=False, info=info
        )
        actor._last_cost_record = cost_record_from_send(result)
        # Should not raise — sink resolution returns None.
        actor._record_cost(result, binding=ProviderModel("x", "y"))
        assert actor._cost_sink is None
    finally:
        await pool.stop()
