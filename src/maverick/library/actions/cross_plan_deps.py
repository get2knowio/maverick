"""Cross-flight-plan dependency resolution and wiring.

Resolves flight plan names to epic bead IDs via ``bd`` state metadata,
then wires epic-to-epic dependencies so later plans are blocked by
earlier plans they depend on.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ResolvedPlanDep:
    """A resolved plan name -> epic bd_id mapping."""

    plan_name: str
    epic_bd_id: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {"plan_name": self.plan_name, "epic_bd_id": self.epic_bd_id}


@dataclass(frozen=True, slots=True)
class CrossPlanDependencyResult:
    """Result of resolving and wiring cross-plan epic dependencies."""

    wired_count: int
    resolved_plans: tuple[ResolvedPlanDep, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "wired_count": self.wired_count,
            "resolved_plans": [rp.to_dict() for rp in self.resolved_plans],
            "errors": list(self.errors),
        }


async def resolve_plan_epic_ids(
    plan_names: tuple[str, ...] | list[str],
    cwd: Path | None = None,
) -> tuple[list[ResolvedPlanDep], list[str]]:
    """Resolve flight plan names to their epic bd_ids.

    Queries all epics via ``bd query type=epic``, then for each epic checks
    ``bd show <id>`` to read ``state.flight_plan_name`` metadata.

    Args:
        plan_names: Flight plan names to resolve.
        cwd: Working directory for bd commands.

    Returns:
        Tuple of (resolved deps, error messages for unresolved plans).
    """
    from maverick.beads.client import BeadClient

    if not plan_names:
        return [], []

    client = BeadClient(cwd=cwd or Path.cwd())

    # Query all epics
    try:
        epics = await client.query("type=epic")
    except Exception as exc:
        return [], [f"Failed to query epics: {exc}"]

    # Build mapping: flight_plan_name -> epic_bd_id
    plan_to_epic: dict[str, str] = {}
    for epic in epics:
        try:
            details = await client.show(epic.id)
            fp_name = details.state.get("flight_plan_name", "")
            if fp_name:
                plan_to_epic[fp_name] = epic.id
        except Exception:
            logger.debug("show_epic_failed", epic_id=epic.id)

    # Resolve requested plan names
    resolved: list[ResolvedPlanDep] = []
    errors: list[str] = []
    for name in plan_names:
        epic_id = plan_to_epic.get(name)
        if epic_id:
            resolved.append(ResolvedPlanDep(plan_name=name, epic_bd_id=epic_id))
        else:
            errors.append(f"Flight plan '{name}' not found in any epic's state metadata")

    return resolved, errors


async def wire_cross_plan_dependencies(
    new_epic_bd_id: str,
    dependency_epic_ids: list[str],
    cwd: Path | None = None,
    dry_run: bool = False,
) -> CrossPlanDependencyResult:
    """Wire epic-to-epic dependencies: new_epic blocked-by each dependency epic.

    Args:
        new_epic_bd_id: BD ID of the newly created epic.
        dependency_epic_ids: BD IDs of epics that must complete first.
        cwd: Working directory for bd commands.
        dry_run: If True, compute without calling bd.

    Returns:
        CrossPlanDependencyResult with wired count and any errors.
    """
    from maverick.beads.client import BeadClient
    from maverick.beads.models import BeadDependency, DependencyType

    if not dependency_epic_ids:
        return CrossPlanDependencyResult(wired_count=0, resolved_plans=(), errors=())

    resolved: list[ResolvedPlanDep] = []
    errors: list[str] = []
    wired = 0

    if dry_run:
        return CrossPlanDependencyResult(
            wired_count=len(dependency_epic_ids),
            resolved_plans=tuple(
                ResolvedPlanDep(plan_name="(dry-run)", epic_bd_id=eid)
                for eid in dependency_epic_ids
            ),
            errors=(),
        )

    client = BeadClient(cwd=cwd or Path.cwd())

    for dep_epic_id in dependency_epic_ids:
        dep = BeadDependency(
            blocker_id=dep_epic_id,
            blocked_id=new_epic_bd_id,
            dep_type=DependencyType.BLOCKS,
        )
        try:
            await client.add_dependency(dep)
            resolved.append(ResolvedPlanDep(plan_name="", epic_bd_id=dep_epic_id))
            wired += 1
        except Exception as exc:
            errors.append(f"Failed to wire epic {new_epic_bd_id} blocked-by {dep_epic_id}: {exc}")

    return CrossPlanDependencyResult(
        wired_count=wired,
        resolved_plans=tuple(resolved),
        errors=tuple(errors),
    )
