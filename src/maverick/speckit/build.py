"""IngestionPlan builder: bead definitions, dependency edges, delta filtering.

See ``specs/048-speckit-refuel-ingestion/data-model.md`` "Ingestion-plan
layer" and ``research.md`` D3/D13 for the rules this module implements.

Edge identifier convention: an edge endpoint is either a Spec Kit task ID
(``T\\d{3,}``, still to be resolved to a bead ID once the workflow creates
it) or an already-resolved ``bd`` bead ID for a previously ingested task
(delta runs). ``bd`` bead IDs never collide with the ``T\\d{3,}`` pattern,
so callers can tell them apart with a single regex check.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from maverick.beads.models import BeadCategory, BeadDefinition, BeadType
from maverick.speckit.errors import NothingToIngestError, SpeckitValidationError
from maverick.speckit.models import SpeckitFeature, SpeckitPhase, SpeckitTask

#: Sentinel task_id for the epic's PlannedBead (data-model.md).
EPIC_TASK_ID = "EPIC"

_MAX_TITLE_LENGTH = 490
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_COMMAND_PREFIXES = ("rg ", "grep ", "cargo ", "make ")


class PlannedBead(BaseModel):
    """Intent to create one bead as part of an ingestion run."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(description="Source task ID; EPIC_TASK_ID for the epic")
    definition: BeadDefinition
    state: dict[str, str] = Field(default_factory=dict)


class IngestionPlan(BaseModel):
    """Complete, validated, side-effect-free description of one ingestion run.

    The dry-run rendering and the real run consume this same object —
    parity by construction (SC-005).
    """

    model_config = ConfigDict(frozen=True)

    feature: SpeckitFeature
    epic: PlannedBead | None = None
    existing_epic_id: str | None = None
    new_tasks: tuple[PlannedBead, ...] = ()
    skipped_completed: tuple[str, ...] = ()
    skipped_existing: tuple[str, ...] = ()
    edges: tuple[tuple[str, str], ...] = ()
    existing_task_map: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Dependency edge derivation
# ---------------------------------------------------------------------------


def _serial_chain_edges(phase: SpeckitPhase) -> list[tuple[str, str]]:
    """Rule 1: each non-[P] task depends on the nearest preceding non-[P] task."""
    edges: list[tuple[str, str]] = []
    prev: str | None = None
    for task in phase.tasks:
        if not task.parallel:
            if prev is not None:
                edges.append((prev, task.task_id))
            prev = task.task_id
    return edges


def _phase_sources(phase: SpeckitPhase, chain_edges: list[tuple[str, str]]) -> list[str]:
    """Tasks in *phase* with no intra-phase (chain) blocker."""
    blocked = {b for _a, b in chain_edges}
    return [t.task_id for t in phase.tasks if t.task_id not in blocked]


def _phase_sinks(phase: SpeckitPhase, chain_edges: list[tuple[str, str]]) -> list[str]:
    """Tasks in *phase* with no intra-phase (chain) dependent."""
    blockers = {a for a, _b in chain_edges}
    return [t.task_id for t in phase.tasks if t.task_id not in blockers]


def _story_endpoints(ids: set[str], intra_edges: list[tuple[str, str]], *, want: str) -> list[str]:
    """Sinks/sources of a story's own task set, restricted to edges internal to it."""
    if want == "sink":
        blockers = {a for a, _b in intra_edges}
        return [i for i in ids if i not in blockers]
    blocked = {b for _a, b in intra_edges}
    return [i for i in ids if i not in blocked]


def _reachable_from(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        for nxt in adjacency.get(node, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def _detect_cycle(edges: list[tuple[str, str]]) -> tuple[str, ...]:
    """Return the node sequence of a cycle if one exists, else an empty tuple."""
    adjacency: dict[str, list[str]] = {}
    nodes: set[str] = set()
    for a, b in edges:
        adjacency.setdefault(a, []).append(b)
        nodes.add(a)
        nodes.add(b)

    white, gray, black = 0, 1, 2
    color: dict[str, int] = {}
    path: list[str] = []

    def visit(node: str) -> tuple[str, ...] | None:
        color[node] = gray
        path.append(node)
        for nxt in adjacency.get(node, ()):
            state = color.get(nxt, white)
            if state == gray:
                cycle_start = path.index(nxt)
                return tuple(path[cycle_start:])
            if state == white:
                result = visit(nxt)
                if result:
                    return result
        color[node] = black
        path.pop()
        return None

    for node in nodes:
        if color.get(node, white) == white:
            result = visit(node)
            if result:
                return result
    return ()


def derive_dependency_edges(
    phases: tuple[SpeckitPhase, ...],
    story_deps: tuple[tuple[str, str], ...] = (),
) -> tuple[tuple[str, str], ...]:
    """Derive ``(blocker_task_id, blocked_task_id)`` edges from tasks.md structure.

    Implements the four edge rules from data-model.md "Derived dependency
    edges": intra-phase serial chains, explicit ``depends on`` notes, the
    phase barrier (sinks x sources, transitively covered by the chains),
    and story-level dependencies added only where not already implied.

    Args:
        phases: Ordered phases (as parsed by :func:`maverick.speckit.parser.parse_tasks_md`).
        story_deps: ``(dependent_story, blocker_story)`` pairs.

    Returns:
        Deduplicated edges in first-derived order.

    Raises:
        SpeckitValidationError: The derived graph contains a cycle (E06).
    """
    edges: list[tuple[str, str]] = []
    phase_chain_edges: dict[int, list[tuple[str, str]]] = {}

    for phase in phases:
        chain = _serial_chain_edges(phase)
        phase_chain_edges[phase.number] = chain
        edges.extend(chain)
        for task in phase.tasks:
            for dep in task.explicit_deps:
                edges.append((dep, task.task_id))

    for i in range(len(phases) - 1):
        p, p_next = phases[i], phases[i + 1]
        sinks = _phase_sinks(p, phase_chain_edges[p.number])
        sources = _phase_sources(p_next, phase_chain_edges[p_next.number])
        for sink in sinks:
            for source in sources:
                edges.append((sink, source))

    if story_deps:
        story_tasks: dict[str, list[SpeckitTask]] = {}
        for phase in phases:
            for task in phase.tasks:
                if task.story_id:
                    story_tasks.setdefault(task.story_id, []).append(task)

        adjacency: dict[str, set[str]] = {}
        for a, b in edges:
            adjacency.setdefault(a, set()).add(b)

        for dependent_story, blocker_story in story_deps:
            blocker_tasks = story_tasks.get(blocker_story, [])
            dependent_tasks = story_tasks.get(dependent_story, [])
            if not blocker_tasks or not dependent_tasks:
                continue
            blocker_ids = {t.task_id for t in blocker_tasks}
            dependent_ids = {t.task_id for t in dependent_tasks}
            intra_blocker_edges = [
                (a, b) for a, b in edges if a in blocker_ids and b in blocker_ids
            ]
            intra_dependent_edges = [
                (a, b) for a, b in edges if a in dependent_ids and b in dependent_ids
            ]
            story_sinks = _story_endpoints(blocker_ids, intra_blocker_edges, want="sink")
            story_sources = _story_endpoints(dependent_ids, intra_dependent_edges, want="source")
            for blocker_id in story_sinks:
                reachable = _reachable_from(blocker_id, adjacency)
                for dependent_id in story_sources:
                    if dependent_id in reachable or dependent_id == blocker_id:
                        continue
                    edges.append((blocker_id, dependent_id))
                    adjacency.setdefault(blocker_id, set()).add(dependent_id)

    cycle = _detect_cycle(edges)
    if cycle:
        raise SpeckitValidationError(
            f"dependency cycle detected: {' -> '.join(cycle)}",
            cycle=cycle,
        )

    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[str, str]] = []
    for edge in edges:
        if edge not in seen:
            seen.add(edge)
            deduped.append(edge)
    return tuple(deduped)


def _resolve_delta_edges(
    edges: tuple[tuple[str, str], ...],
    *,
    completed_ids: set[str],
    existing_task_map: dict[str, str],
    new_task_ids: set[str],
) -> tuple[tuple[str, str], ...]:
    """Restrict edges to those blocking a new task; resolve/drop the blocker side."""
    resolved: list[tuple[str, str]] = []
    for blocker, blocked in edges:
        if blocked not in new_task_ids:
            continue
        if blocker in completed_ids:
            continue
        resolved_blocker = existing_task_map.get(blocker, blocker)
        resolved.append((resolved_blocker, blocked))
    return tuple(resolved)


# ---------------------------------------------------------------------------
# Bead content assembly (contracts/bead-encoding.md)
# ---------------------------------------------------------------------------


def _truncate_title(text: str, limit: int = _MAX_TITLE_LENGTH) -> str:
    return text if len(text) <= limit else text[:limit]


def _extract_verbatim_commands(text: str) -> tuple[str, ...]:
    """Best-effort extraction of backtick-quoted rg/grep/cargo/make commands."""
    commands = []
    for match in _INLINE_CODE_RE.findall(text):
        stripped = match.strip()
        if stripped.startswith(_COMMAND_PREFIXES):
            commands.append(stripped)
    return tuple(commands)


def _build_verification_lines(task: SpeckitTask, feature: SpeckitFeature) -> list[str]:
    lines = [f"rg --files -g '{path}'" for path in task.file_paths]
    lines.extend(_extract_verbatim_commands(task.description))
    if not lines:
        # Fallback: confirm the source feature directory itself exists —
        # a trivially-true but non-empty check (D8: never leave the AC-check
        # gate with nothing to run).
        #
        # The glob must name the directory's *contents*. Globbing the bare
        # feature name matches nothing (no file is called "001-greet-cli";
        # the directory is "specs/001-greet-cli/"), which turned this
        # supposedly-trivial check into an AC gate no fix could close — and
        # the fixer closed it by fabricating a file with that exact name.
        lines.append(f"rg --files -g 'specs/{feature.feature_name}/*'")
    return lines


def _build_task_description(
    task: SpeckitTask,
    phase: SpeckitPhase,
    feature: SpeckitFeature,
) -> str:
    context_bits = [f"Phase {phase.number}: {phase.title}"]
    if task.story_id:
        context_bits.append(f"Story {task.story_id}")
    if task.parallel:
        context_bits.append("parallel-eligible")

    lines = [
        "## Task",
        f"{task.description} ({', '.join(context_bits)})",
        "",
        "## Acceptance Criteria",
        f"- {task.description}",
    ]
    if task.story_id:
        for scenario in feature.spec.story_scenarios.get(task.story_id, ()):
            lines.append(f"- {scenario}")

    if task.file_paths:
        lines.extend(["", "## File Scope"])
        lines.extend(f"- {path}" for path in task.file_paths)

    lines.extend(["", "## Verification"])
    lines.extend(f"- {cmd}" for cmd in _build_verification_lines(task, feature))

    return "\n".join(lines)


def _build_task_planned_bead(
    task: SpeckitTask,
    phase: SpeckitPhase,
    feature: SpeckitFeature,
) -> PlannedBead:
    title = _truncate_title(f"{task.task_id}: {task.description}")
    definition = BeadDefinition(
        title=title,
        bead_type=BeadType.TASK,
        priority=2,
        category=BeadCategory.USER_STORY,
        description=_build_task_description(task, phase, feature),
        phase_names=[phase.title],
        user_story_id=task.story_id,
        task_ids=[task.task_id],
        labels=["speckit"],
    )
    return PlannedBead(
        task_id=task.task_id,
        definition=definition,
        state={
            "speckit_task_id": task.task_id,
            "speckit_phase": str(task.phase_number),
            "speckit_parallel": "true" if task.parallel else "false",
        },
    )


def _build_epic_description(feature: SpeckitFeature) -> str:
    lines = [f"{feature.spec.title or feature.feature_name} — ingested from Spec Kit."]
    if feature.spec.success_criteria:
        lines.extend(["", "## Success Criteria"])
        lines.extend(f"- {sc}" for sc in feature.spec.success_criteria)
    lines.extend(["", "## Source", f"- specs/{feature.feature_name}/"])
    return "\n".join(lines)


def _build_epic_planned_bead(feature: SpeckitFeature) -> PlannedBead:
    title = _truncate_title(feature.spec.title or feature.feature_name)
    all_task_ids = [task.task_id for phase in feature.phases for task in phase.tasks]
    definition = BeadDefinition(
        title=title,
        bead_type=BeadType.EPIC,
        priority=1,
        category=BeadCategory.USER_STORY,
        description=_build_epic_description(feature),
        phase_names=[phase.title for phase in feature.phases],
        task_ids=all_task_ids,
        labels=["speckit"],
    )
    return PlannedBead(
        task_id=EPIC_TASK_ID,
        definition=definition,
        state={"speckit_feature": feature.feature_name},
    )


# ---------------------------------------------------------------------------
# Ingestion plan
# ---------------------------------------------------------------------------


def build_ingestion_plan(
    feature: SpeckitFeature,
    *,
    existing_epic_id: str | None = None,
    existing_task_map: dict[str, str] | None = None,
) -> tuple[IngestionPlan, tuple[str, ...]]:
    """Build a fully validated :class:`IngestionPlan` from a parsed feature.

    All validation (unique IDs already enforced by the parser; explicit
    deps resolve; acyclic dependency graph) completes before this
    function returns — no ``bd`` write may occur before that (FR-015).

    Args:
        feature: The parsed Spec Kit feature.
        existing_epic_id: Set on delta runs (an open epic already exists
            for this feature). ``None`` on a fresh run.
        existing_task_map: ``task_id -> bead_id`` for previously ingested
            tasks (delta runs only).

    Returns:
        A two-tuple of ``(plan, warnings)``.

    Raises:
        NothingToIngestError: Every task in the feature is already
            completed (E07 — first-run only; a delta no-op where all
            *remaining* tasks are already ingested is not an error).
        SpeckitValidationError: Duplicate IDs, unknown dep refs, or a
            dependency cycle.
    """
    existing_task_map = dict(existing_task_map or {})
    warnings: list[str] = []

    all_pairs = [(phase, task) for phase in feature.phases for task in phase.tasks]
    total_count = len(all_pairs)
    completed_pairs = [(phase, task) for phase, task in all_pairs if task.completed]
    open_pairs = [(phase, task) for phase, task in all_pairs if not task.completed]

    if not open_pairs:
        raise NothingToIngestError(
            f"nothing to ingest for {feature.feature_name}: all {total_count} "
            "tasks are already completed",
            completed_count=len(completed_pairs),
            total_count=total_count,
        )

    skipped_completed = tuple(task.task_id for _phase, task in completed_pairs)
    skipped_existing = tuple(
        task.task_id for _phase, task in open_pairs if task.task_id in existing_task_map
    )
    new_pairs = [
        (phase, task) for phase, task in open_pairs if task.task_id not in existing_task_map
    ]

    # Full-graph validation (rules 1-4 + acyclicity) regardless of delta status.
    derived_edges = derive_dependency_edges(feature.phases, feature.story_deps)

    for _phase, task in all_pairs:
        if task.story_id and task.story_id not in feature.spec.story_scenarios:
            warnings.append(
                f"task {task.task_id} labeled {task.story_id}, but spec.md has no "
                "matching User Story section — scenarios omitted"
            )

    if not new_pairs:
        return (
            IngestionPlan(
                feature=feature,
                epic=None,
                existing_epic_id=existing_epic_id,
                new_tasks=(),
                skipped_completed=skipped_completed,
                skipped_existing=skipped_existing,
                edges=(),
                existing_task_map=existing_task_map,
            ),
            tuple(warnings),
        )

    completed_ids = {task.task_id for _phase, task in completed_pairs}
    new_task_ids = {task.task_id for _phase, task in new_pairs}
    resolved_edges = _resolve_delta_edges(
        derived_edges,
        completed_ids=completed_ids,
        existing_task_map=existing_task_map,
        new_task_ids=new_task_ids,
    )

    new_tasks = tuple(_build_task_planned_bead(task, phase, feature) for phase, task in new_pairs)

    epic: PlannedBead | None = None
    if existing_epic_id is None:
        epic = _build_epic_planned_bead(feature)
        if not feature.spec.success_criteria:
            warnings.append(
                f"{feature.feature_name}: spec.md has no Success Criteria section "
                "— epic description omits it"
            )

    plan = IngestionPlan(
        feature=feature,
        epic=epic,
        existing_epic_id=existing_epic_id,
        new_tasks=new_tasks,
        skipped_completed=skipped_completed,
        skipped_existing=skipped_existing,
        edges=resolved_edges,
        existing_task_map=existing_task_map,
    )
    return plan, tuple(warnings)


__all__ = [
    "EPIC_TASK_ID",
    "IngestionPlan",
    "PlannedBead",
    "build_ingestion_plan",
    "derive_dependency_edges",
]
