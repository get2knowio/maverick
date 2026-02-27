"""Dependency resolver for Work Unit execution ordering.

Provides :func:`resolve_execution_order` which accepts a list of
:class:`~maverick.flight.models.WorkUnit` instances and returns an
:class:`~maverick.flight.models.ExecutionOrder` describing topologically
sorted :class:`~maverick.flight.models.ExecutionBatch` instances.

Algorithm overview:

1. Check for duplicate Work Unit IDs (raises
   :class:`~maverick.flight.errors.WorkUnitDependencyError`).  Then build an
   ID-to-unit lookup map and validate that all ``depends_on`` IDs reference
   known units (raises :exc:`WorkUnitDependencyError` with ``missing_id`` set).
2. DFS topological sort with explicit ``in_stack`` tracking for cycle
   detection (raises :exc:`WorkUnitDependencyError` with ``cycle`` set).
3. Compute the dependency *level* for each unit:
   ``level = max(dep_levels) + 1``, or ``0`` when the unit has no deps.
4. Group units by level into ordered tiers.
5. Within each tier, further group by ``parallel_group``.  Units that share
   the same non-``None`` ``parallel_group`` are placed in a single
   :class:`ExecutionBatch` with that group label.  Units whose
   ``parallel_group`` is ``None`` are collected into a single ungrouped
   batch for their tier.
"""

from __future__ import annotations

from collections import defaultdict

from maverick.flight.errors import WorkUnitDependencyError
from maverick.flight.models import ExecutionBatch, ExecutionOrder, WorkUnit
from maverick.logging import get_logger

logger = get_logger(__name__)


def resolve_execution_order(units: list[WorkUnit]) -> ExecutionOrder:
    """Resolve dependency order using topological sort.

    Groups units by ``parallel_group`` within each dependency tier so that
    independent work can be executed concurrently.

    Args:
        units: List of :class:`WorkUnit` instances to order.

    Returns:
        :class:`ExecutionOrder` with topologically sorted
        :class:`ExecutionBatch` instances.

    Raises:
        WorkUnitDependencyError: If a circular dependency is detected
            (``cycle`` attribute holds the cycle IDs) or a referenced
            dependency ID is not present in ``units`` (``missing_id``
            attribute holds the unknown ID).
    """
    if not units:
        logger.debug("resolve_execution_order.empty_input")
        return ExecutionOrder(batches=())

    # --- 1. Build lookup and validate deps -----------------------------------

    # Check for duplicate IDs before building the map.
    seen_ids: dict[str, int] = {}
    for u in units:
        seen_ids[u.id] = seen_ids.get(u.id, 0) + 1
    duplicates = [uid for uid, count in seen_ids.items() if count > 1]
    if duplicates:
        raise WorkUnitDependencyError(
            f"Duplicate work unit IDs: {', '.join(sorted(duplicates))}",
        )

    unit_map: dict[str, WorkUnit] = {u.id: u for u in units}

    for unit in units:
        for dep_id in unit.depends_on:
            if dep_id not in unit_map:
                raise WorkUnitDependencyError(
                    f"Work unit '{unit.id}' depends on unknown unit '{dep_id}'",
                    missing_id=dep_id,
                )

    # --- 2. DFS topological sort with cycle detection -----------------------

    visited: set[str] = set()
    in_stack: set[str] = set()
    path: list[str] = []
    topo_order: list[str] = []

    def _visit(uid: str) -> None:
        if uid in in_stack:
            # Extract the exact cycle from the DFS path.
            start = path.index(uid)
            cycle = path[start:] + [uid]
            raise WorkUnitDependencyError(
                f"Circular dependency detected involving '{uid}': {' -> '.join(cycle)}",
                cycle=cycle,
            )
        if uid in visited:
            return

        in_stack.add(uid)
        path.append(uid)
        for dep_id in unit_map[uid].depends_on:
            _visit(dep_id)
        path.pop()
        in_stack.remove(uid)
        visited.add(uid)
        topo_order.append(uid)

    for uid in unit_map:
        _visit(uid)

    logger.debug(
        "resolve_execution_order.topo_order",
        order=topo_order,
    )

    # --- 3. Assign dependency levels ----------------------------------------

    levels: dict[str, int] = {}
    for uid in topo_order:  # topo_order is deps-before-dependents
        deps = unit_map[uid].depends_on
        if deps:
            levels[uid] = max(levels[dep] for dep in deps) + 1
        else:
            levels[uid] = 0

    # --- 4. Group by level into tiers ----------------------------------------

    level_groups: dict[int, list[WorkUnit]] = defaultdict(list)
    for uid in topo_order:
        level_groups[levels[uid]].append(unit_map[uid])

    # --- 5. Within each tier, group by parallel_group ------------------------

    batches: list[ExecutionBatch] = []
    for level in sorted(level_groups):
        tier_units = level_groups[level]

        # Collect ungrouped units first; then each distinct parallel_group.
        pg_groups: dict[str | None, list[WorkUnit]] = defaultdict(list)
        for u in tier_units:
            pg_groups[u.parallel_group].append(u)

        for pg, pg_units in pg_groups.items():
            batches.append(ExecutionBatch(units=tuple(pg_units), parallel_group=pg))

    logger.debug(
        "resolve_execution_order.batches_built",
        batch_count=len(batches),
    )

    return ExecutionOrder(batches=tuple(batches))
