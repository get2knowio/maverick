"""Tests for dependency-edge derivation (maverick.speckit.build)."""

from __future__ import annotations

import pytest

from maverick.speckit.build import derive_dependency_edges
from maverick.speckit.errors import SpeckitValidationError
from maverick.speckit.models import SpeckitPhase, SpeckitTask


def _task(
    task_id: str,
    *,
    phase_number: int,
    parallel: bool = False,
    story_id: str | None = None,
    explicit_deps: tuple[str, ...] = (),
    line_number: int = 1,
) -> SpeckitTask:
    return SpeckitTask(
        task_id=task_id,
        description=f"do {task_id}",
        completed=False,
        parallel=parallel,
        story_id=story_id,
        phase_number=phase_number,
        explicit_deps=explicit_deps,
        line_number=line_number,
    )


class TestIntraPhaseChain:
    def test_serial_chain_of_non_parallel_tasks(self) -> None:
        phase = SpeckitPhase(
            number=1,
            title="Setup",
            tasks=(
                _task("T001", phase_number=1),
                _task("T002", phase_number=1),
                _task("T003", phase_number=1),
            ),
        )
        edges = derive_dependency_edges((phase,))
        assert ("T001", "T002") in edges
        assert ("T002", "T003") in edges

    def test_parallel_tasks_have_no_implicit_intra_phase_deps(self) -> None:
        phase = SpeckitPhase(
            number=1,
            title="Setup",
            tasks=(
                _task("T001", phase_number=1, parallel=True),
                _task("T002", phase_number=1, parallel=True),
            ),
        )
        edges = derive_dependency_edges((phase,))
        assert edges == ()

    def test_phase_barrier_is_transitive_across_serial_chain(self) -> None:
        """Only sinks/sources need connecting — the barrier is a valid
        execution order thanks to transitivity through the chains."""
        phase1 = SpeckitPhase(
            number=1,
            title="Setup",
            tasks=(_task("T001", phase_number=1), _task("T002", phase_number=1)),
        )
        phase2 = SpeckitPhase(
            number=2,
            title="Next",
            tasks=(_task("T003", phase_number=2), _task("T004", phase_number=2)),
        )
        edges = derive_dependency_edges((phase1, phase2))
        # sink of phase 1 is T002 (last in chain); source of phase 2 is T003.
        assert ("T002", "T003") in edges
        # T001 already reaches T003 transitively via T001->T002->T003.
        assert ("T001", "T003") not in edges

    def test_parallel_tasks_are_both_sinks_and_sources_for_barrier(self) -> None:
        phase1 = SpeckitPhase(
            number=1,
            title="Setup",
            tasks=(_task("T001", phase_number=1, parallel=True),),
        )
        phase2 = SpeckitPhase(
            number=2,
            title="Next",
            tasks=(_task("T002", phase_number=2, parallel=True),),
        )
        edges = derive_dependency_edges((phase1, phase2))
        assert ("T001", "T002") in edges


class TestExplicitDeps:
    def test_explicit_dep_edge_added(self) -> None:
        phase = SpeckitPhase(
            number=1,
            title="Setup",
            tasks=(
                _task("T001", phase_number=1, parallel=True),
                _task("T002", phase_number=1, parallel=True, explicit_deps=("T001",)),
            ),
        )
        edges = derive_dependency_edges((phase,))
        assert ("T001", "T002") in edges


class TestTopologicalValidity:
    def test_full_edge_set_is_a_valid_execution_order(self) -> None:
        """Build a Kahn's-algorithm topological sort from the derived
        edges and verify it recovers a valid tasks.md-consistent order."""
        phase1 = SpeckitPhase(
            number=1,
            title="Setup",
            tasks=(
                _task("T001", phase_number=1),
                _task("T002", phase_number=1, parallel=True),
                _task("T003", phase_number=1, parallel=True),
            ),
        )
        phase2 = SpeckitPhase(
            number=2,
            title="Next",
            tasks=(_task("T004", phase_number=2),),
        )
        edges = derive_dependency_edges((phase1, phase2))

        all_ids = {"T001", "T002", "T003", "T004"}
        indegree = dict.fromkeys(all_ids, 0)
        adjacency: dict[str, list[str]] = {i: [] for i in all_ids}
        for a, b in edges:
            adjacency[a].append(b)
            indegree[b] += 1

        ready = [i for i in all_ids if indegree[i] == 0]
        order: list[str] = []
        while ready:
            node = ready.pop()
            order.append(node)
            for nxt in adjacency[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)

        assert set(order) == all_ids
        assert order.index("T001") < order.index("T004")
        assert order.index("T002") < order.index("T004")
        assert order.index("T003") < order.index("T004")


class TestStoryDeps:
    def test_story_dep_not_duplicated_when_already_reachable(self) -> None:
        phase1 = SpeckitPhase(
            number=1,
            title="US1",
            tasks=(_task("T001", phase_number=1, story_id="US1"),),
        )
        phase2 = SpeckitPhase(
            number=2,
            title="US2",
            tasks=(_task("T002", phase_number=2, story_id="US2"),),
        )
        edges = derive_dependency_edges((phase1, phase2), story_deps=(("US2", "US1"),))
        assert edges == (("T001", "T002"),)

    def test_story_dep_adds_edge_when_stories_interleaved_in_same_phase(self) -> None:
        phase = SpeckitPhase(
            number=1,
            title="Mixed",
            tasks=(
                _task("T001", phase_number=1, parallel=True, story_id="US1"),
                _task("T002", phase_number=1, parallel=True, story_id="US2"),
            ),
        )
        edges = derive_dependency_edges((phase,), story_deps=(("US2", "US1"),))
        assert ("T001", "T002") in edges


class TestCycleDetection:
    def test_cycle_from_explicit_deps_raises(self) -> None:
        phase = SpeckitPhase(
            number=1,
            title="Setup",
            tasks=(
                _task("T001", phase_number=1, parallel=True, explicit_deps=("T002",)),
                _task("T002", phase_number=1, parallel=True, explicit_deps=("T001",)),
            ),
        )
        with pytest.raises(SpeckitValidationError) as exc_info:
            derive_dependency_edges((phase,))
        assert exc_info.value.cycle


class TestDeltaEdgeResolution:
    def test_edges_resolve_through_existing_task_map_and_drop_completed_blockers(self) -> None:
        from maverick.speckit.build import _resolve_delta_edges

        edges = (("T001", "T002"), ("T003", "T004"), ("T005", "T004"))
        resolved = _resolve_delta_edges(
            edges,
            completed_ids={"T003"},
            existing_task_map={"T001": "bead-abc"},
            new_task_ids={"T002", "T004"},
        )
        # T001->T002: T002 is new, T001 resolves to its bead ID.
        assert ("bead-abc", "T002") in resolved
        # T003->T004: T003 is completed -> dropped.
        assert not any(blocker == "T003" for blocker, _blocked in resolved)
        # T005->T004: T005 is neither completed nor existing -> passes through
        # as a bare task ID (resolved via created_map once T005 itself is created).
        assert ("T005", "T004") in resolved
