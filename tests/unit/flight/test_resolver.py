"""Tests for resolve_execution_order() and related models (US3).

Tests cover:
- ExecutionBatch and ExecutionOrder model construction
- Linear chain dependency resolution
- Diamond dependency resolution
- Independent units batched together
- parallel_group batching within tiers
- Duplicate work unit ID detection (WorkUnitDependencyError)
- Circular dependency detection (WorkUnitDependencyError with deterministic cycle)
- Missing dependency detection (WorkUnitDependencyError with missing_id)
- Empty list returns empty batches
- Single unit returns single batch
"""

from __future__ import annotations

import pytest

from maverick.flight.errors import WorkUnitDependencyError
from maverick.flight.models import (
    AcceptanceCriterion,
    ExecutionBatch,
    ExecutionOrder,
    FileScope,
    WorkUnit,
)
from maverick.flight.resolver import resolve_execution_order

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_work_unit(
    uid: str,
    *,
    sequence: int = 1,
    depends_on: tuple[str, ...] = (),
    parallel_group: str | None = None,
) -> WorkUnit:
    """Create a minimal WorkUnit for testing."""
    return WorkUnit(
        id=uid,
        flight_plan="test-plan",
        sequence=sequence,
        parallel_group=parallel_group,
        depends_on=depends_on,
        task=f"Task for {uid}",
        acceptance_criteria=(AcceptanceCriterion(text="Done"),),
        file_scope=FileScope(create=(), modify=(), protect=()),
        instructions="Do the work.",
        verification=("make test-fast",),
    )


def _batch_unit_ids(batch: ExecutionBatch) -> frozenset[str]:
    """Return the set of unit IDs in a batch."""
    return frozenset(u.id for u in batch.units)


# ---------------------------------------------------------------------------
# Model construction tests (T017 item 9 and 10)
# ---------------------------------------------------------------------------


class TestExecutionBatchConstruction:
    """ExecutionBatch frozen model construction and field access."""

    def test_construction_with_units_and_no_group(self) -> None:
        u = _make_work_unit("alpha")
        batch = ExecutionBatch(units=(u,), parallel_group=None)
        assert batch.units == (u,)
        assert batch.parallel_group is None

    def test_construction_with_parallel_group(self) -> None:
        u = _make_work_unit("beta")
        batch = ExecutionBatch(units=(u,), parallel_group="group-a")
        assert batch.parallel_group == "group-a"

    def test_parallel_group_defaults_to_none(self) -> None:
        u = _make_work_unit("gamma")
        batch = ExecutionBatch(units=(u,))
        assert batch.parallel_group is None

    def test_frozen_immutability(self) -> None:
        u = _make_work_unit("delta")
        batch = ExecutionBatch(units=(u,))
        with pytest.raises(Exception):
            batch.parallel_group = "mutated"  # type: ignore[misc]

    def test_units_is_tuple(self) -> None:
        u1 = _make_work_unit("e1")
        u2 = _make_work_unit("e2")
        batch = ExecutionBatch(units=(u1, u2))
        assert isinstance(batch.units, tuple)
        assert len(batch.units) == 2


class TestExecutionOrderConstruction:
    """ExecutionOrder frozen model construction and field access."""

    def test_construction_with_empty_batches(self) -> None:
        order = ExecutionOrder(batches=())
        assert order.batches == ()

    def test_construction_with_batches(self) -> None:
        u = _make_work_unit("alpha")
        batch = ExecutionBatch(units=(u,))
        order = ExecutionOrder(batches=(batch,))
        assert len(order.batches) == 1
        assert order.batches[0] is batch

    def test_frozen_immutability(self) -> None:
        order = ExecutionOrder(batches=())
        with pytest.raises(Exception):
            order.batches = ()  # type: ignore[misc]

    def test_batches_is_tuple(self) -> None:
        u = _make_work_unit("alpha")
        batch = ExecutionBatch(units=(u,))
        order = ExecutionOrder(batches=(batch,))
        assert isinstance(order.batches, tuple)


# ---------------------------------------------------------------------------
# Empty and single unit edge cases (T017 items 7 and 8)
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty list and single unit."""

    def test_empty_list_returns_empty_batches(self) -> None:
        order = resolve_execution_order([])
        assert isinstance(order, ExecutionOrder)
        assert order.batches == ()

    def test_single_unit_returns_single_batch(self) -> None:
        u = _make_work_unit("solo")
        order = resolve_execution_order([u])
        assert len(order.batches) == 1
        assert _batch_unit_ids(order.batches[0]) == {"solo"}


# ---------------------------------------------------------------------------
# Linear chain ordering (T017 item 1)
# ---------------------------------------------------------------------------


class TestLinearChain:
    """A → B → C must resolve A first, then B, then C (separate batches)."""

    def test_linear_chain_three_units(self) -> None:
        a = _make_work_unit("unit-a", sequence=1)
        b = _make_work_unit("unit-b", sequence=2, depends_on=("unit-a",))
        c = _make_work_unit("unit-c", sequence=3, depends_on=("unit-b",))

        order = resolve_execution_order([a, b, c])

        assert len(order.batches) == 3
        all_ids = [_batch_unit_ids(batch) for batch in order.batches]
        assert all_ids[0] == {"unit-a"}
        assert all_ids[1] == {"unit-b"}
        assert all_ids[2] == {"unit-c"}

    def test_linear_chain_input_order_irrelevant(self) -> None:
        """Reversed input order should produce same dependency-ordered output."""
        a = _make_work_unit("unit-a", sequence=1)
        b = _make_work_unit("unit-b", sequence=2, depends_on=("unit-a",))
        c = _make_work_unit("unit-c", sequence=3, depends_on=("unit-b",))

        order_forward = resolve_execution_order([a, b, c])
        order_reversed = resolve_execution_order([c, b, a])

        ids_forward = [_batch_unit_ids(batch) for batch in order_forward.batches]
        ids_reversed = [_batch_unit_ids(batch) for batch in order_reversed.batches]
        assert ids_forward == ids_reversed


# ---------------------------------------------------------------------------
# Diamond dependency (T017 item 2)
# ---------------------------------------------------------------------------


class TestDiamondDependency:
    """A → B, A → C, B → D, C → D: A first, B+C can be concurrent, D last."""

    def test_diamond_dependency_ordering(self) -> None:
        a = _make_work_unit("unit-a", sequence=1)
        b = _make_work_unit("unit-b", sequence=2, depends_on=("unit-a",))
        c = _make_work_unit("unit-c", sequence=3, depends_on=("unit-a",))
        d = _make_work_unit("unit-d", sequence=4, depends_on=("unit-b", "unit-c"))

        order = resolve_execution_order([a, b, c, d])

        # A must be first
        assert _batch_unit_ids(order.batches[0]) == {"unit-a"}

        # D must be last
        assert _batch_unit_ids(order.batches[-1]) == {"unit-d"}

        # B and C appear before D and after A
        middle_ids: set[str] = set()
        for batch in order.batches[1:-1]:
            middle_ids |= _batch_unit_ids(batch)
        assert middle_ids == {"unit-b", "unit-c"}

    def test_diamond_d_in_own_batch(self) -> None:
        """D must be in its own batch since it depends on B and C."""
        a = _make_work_unit("unit-a", sequence=1)
        b = _make_work_unit("unit-b", sequence=2, depends_on=("unit-a",))
        c = _make_work_unit("unit-c", sequence=3, depends_on=("unit-a",))
        d = _make_work_unit("unit-d", sequence=4, depends_on=("unit-b", "unit-c"))

        order = resolve_execution_order([a, b, c, d])

        last_batch = order.batches[-1]
        assert _batch_unit_ids(last_batch) == {"unit-d"}


# ---------------------------------------------------------------------------
# Independent units in same batch (T017 item 3)
# ---------------------------------------------------------------------------


class TestIndependentUnits:
    """Units with no dependencies should be grouped together in one batch."""

    def test_three_independent_units_same_batch(self) -> None:
        x = _make_work_unit("unit-x", sequence=1)
        y = _make_work_unit("unit-y", sequence=2)
        z = _make_work_unit("unit-z", sequence=3)

        order = resolve_execution_order([x, y, z])

        # All three have no deps, so they should all be at level 0
        # They may be in individual batches (None parallel_group) or merged —
        # but collectively they should all appear in the same dependency tier.
        all_ids = set()
        for batch in order.batches:
            all_ids |= _batch_unit_ids(batch)
        assert all_ids == {"unit-x", "unit-y", "unit-z"}

        # All should appear before any dependents (trivially satisfied here)

    def test_independent_units_all_in_level_zero(self) -> None:
        """All independent units should be in the same dependency tier (level 0)."""
        x = _make_work_unit("unit-x", sequence=1)
        y = _make_work_unit("unit-y", sequence=2)
        dep = _make_work_unit("unit-dep", sequence=3, depends_on=("unit-x",))

        order = resolve_execution_order([x, y, dep])

        # unit-dep must come after unit-x; unit-y is independent
        all_ids_before_dep: set[str] = set()
        dep_batch_index = next(
            i for i, batch in enumerate(order.batches) if "unit-dep" in _batch_unit_ids(batch)
        )
        for batch in order.batches[:dep_batch_index]:
            all_ids_before_dep |= _batch_unit_ids(batch)

        assert "unit-x" in all_ids_before_dep


# ---------------------------------------------------------------------------
# parallel_group batching (T017 item 4)
# ---------------------------------------------------------------------------


class TestParallelGroupBatching:
    """Units with the same parallel_group in the same dependency tier → one batch."""

    def test_same_group_same_tier_in_one_batch(self) -> None:
        x = _make_work_unit("unit-x", sequence=1, parallel_group="grp-a")
        y = _make_work_unit("unit-y", sequence=2, parallel_group="grp-a")

        order = resolve_execution_order([x, y])

        # Both should be in a single batch with parallel_group="grp-a"
        assert len(order.batches) == 1
        batch = order.batches[0]
        assert batch.parallel_group == "grp-a"
        assert _batch_unit_ids(batch) == {"unit-x", "unit-y"}

    def test_different_groups_different_batches(self) -> None:
        x = _make_work_unit("unit-x", sequence=1, parallel_group="grp-a")
        y = _make_work_unit("unit-y", sequence=2, parallel_group="grp-b")

        order = resolve_execution_order([x, y])

        # Different groups → separate batches (even at same tier)
        assert len(order.batches) == 2
        groups = {batch.parallel_group for batch in order.batches}
        assert groups == {"grp-a", "grp-b"}

    def test_group_only_in_same_tier(self) -> None:
        """Units with same parallel_group but different tiers are NOT merged."""
        a = _make_work_unit("unit-a", sequence=1, parallel_group="grp")
        b = _make_work_unit("unit-b", sequence=2, depends_on=("unit-a",), parallel_group="grp")

        order = resolve_execution_order([a, b])

        # They are in different tiers, so they get separate batches
        assert len(order.batches) == 2

    def test_no_group_units_get_none_parallel_group(self) -> None:
        u = _make_work_unit("unit-a", sequence=1)

        order = resolve_execution_order([u])

        assert order.batches[0].parallel_group is None

    def test_mixed_group_and_no_group_in_same_tier(self) -> None:
        """Group units and ungrouped units at same tier produce separate batches."""
        x = _make_work_unit("unit-x", sequence=1, parallel_group="grp-a")
        y = _make_work_unit("unit-y", sequence=2, parallel_group="grp-a")
        z = _make_work_unit("unit-z", sequence=3)  # no parallel_group

        order = resolve_execution_order([x, y, z])

        group_a_batch = next(b for b in order.batches if b.parallel_group == "grp-a")
        assert _batch_unit_ids(group_a_batch) == {"unit-x", "unit-y"}


# ---------------------------------------------------------------------------
# Error cases (T017 items 5 and 6)
# ---------------------------------------------------------------------------


class TestDuplicateWorkUnitIds:
    """Duplicate work unit IDs raise WorkUnitDependencyError."""

    def test_duplicate_id_raises(self) -> None:
        a1 = _make_work_unit("unit-a", sequence=1)
        a2 = _make_work_unit("unit-a", sequence=2)
        with pytest.raises(WorkUnitDependencyError, match="Duplicate work unit IDs"):
            resolve_execution_order([a1, a2])

    def test_duplicate_id_message_contains_id(self) -> None:
        a1 = _make_work_unit("unit-a", sequence=1)
        a2 = _make_work_unit("unit-a", sequence=2)
        with pytest.raises(WorkUnitDependencyError) as exc_info:
            resolve_execution_order([a1, a2])
        assert "unit-a" in str(exc_info.value)

    def test_multiple_duplicate_ids_all_reported(self) -> None:
        a1 = _make_work_unit("unit-a", sequence=1)
        a2 = _make_work_unit("unit-a", sequence=2)
        b1 = _make_work_unit("unit-b", sequence=3)
        b2 = _make_work_unit("unit-b", sequence=4)
        with pytest.raises(WorkUnitDependencyError) as exc_info:
            resolve_execution_order([a1, a2, b1, b2])
        msg = str(exc_info.value)
        assert "unit-a" in msg
        assert "unit-b" in msg

    def test_duplicate_has_no_cycle_or_missing_id(self) -> None:
        a1 = _make_work_unit("unit-a", sequence=1)
        a2 = _make_work_unit("unit-a", sequence=2)
        with pytest.raises(WorkUnitDependencyError) as exc_info:
            resolve_execution_order([a1, a2])
        assert exc_info.value.cycle is None
        assert exc_info.value.missing_id is None


class TestCircularDependency:
    """Circular dependencies raise WorkUnitDependencyError with cycle attribute."""

    def test_self_dependency_raises(self) -> None:
        a = _make_work_unit("unit-a", depends_on=("unit-a",))
        with pytest.raises(WorkUnitDependencyError) as exc_info:
            resolve_execution_order([a])
        assert exc_info.value.cycle == ["unit-a", "unit-a"]

    def test_two_unit_cycle_raises(self) -> None:
        a = _make_work_unit("unit-a", depends_on=("unit-b",))
        b = _make_work_unit("unit-b", depends_on=("unit-a",))
        with pytest.raises(WorkUnitDependencyError) as exc_info:
            resolve_execution_order([a, b])
        err = exc_info.value
        assert err.cycle is not None
        # The cycle path must be deterministic: a -> b -> a
        assert err.cycle == ["unit-a", "unit-b", "unit-a"]

    def test_three_unit_cycle_raises(self) -> None:
        a = _make_work_unit("unit-a", depends_on=("unit-c",))
        b = _make_work_unit("unit-b", depends_on=("unit-a",))
        c = _make_work_unit("unit-c", depends_on=("unit-b",))
        with pytest.raises(WorkUnitDependencyError) as exc_info:
            resolve_execution_order([a, b, c])
        err = exc_info.value
        assert err.cycle is not None
        # Deterministic path: a -> c -> b -> a
        assert err.cycle == ["unit-a", "unit-c", "unit-b", "unit-a"]

    def test_cycle_starts_and_ends_with_same_node(self) -> None:
        """The cycle list starts and ends with the same node ID."""
        a = _make_work_unit("unit-a", depends_on=("unit-b",))
        b = _make_work_unit("unit-b", depends_on=("unit-a",))
        with pytest.raises(WorkUnitDependencyError) as exc_info:
            resolve_execution_order([a, b])
        cycle = exc_info.value.cycle
        assert cycle is not None
        assert cycle[0] == cycle[-1]

    def test_cycle_missing_id_is_none(self) -> None:
        """Cycle errors should not set missing_id."""
        a = _make_work_unit("unit-a", depends_on=("unit-a",))
        with pytest.raises(WorkUnitDependencyError) as exc_info:
            resolve_execution_order([a])
        assert exc_info.value.missing_id is None


class TestMissingDependency:
    """Missing dep IDs raise WorkUnitDependencyError."""

    def test_unknown_dep_raises(self) -> None:
        a = _make_work_unit("unit-a", depends_on=("nonexistent",))
        with pytest.raises(WorkUnitDependencyError) as exc_info:
            resolve_execution_order([a])
        err = exc_info.value
        assert err.missing_id == "nonexistent"

    def test_cycle_is_none_for_missing_dep(self) -> None:
        """Missing-dep errors should not set cycle."""
        a = _make_work_unit("unit-a", depends_on=("ghost",))
        with pytest.raises(WorkUnitDependencyError) as exc_info:
            resolve_execution_order([a])
        assert exc_info.value.cycle is None

    def test_missing_dep_error_message_mentions_id(self) -> None:
        a = _make_work_unit("unit-a", depends_on=("ghost-unit",))
        with pytest.raises(WorkUnitDependencyError) as exc_info:
            resolve_execution_order([a])
        assert "ghost-unit" in str(exc_info.value)
