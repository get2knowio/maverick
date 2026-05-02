"""Bead-creation and lifecycle actions for workflows.

Every action takes an explicit ``cwd`` so workflows preserve workspace
isolation (CLAUDE.md Architectural Guardrail 7). Workflows resolve
``cwd`` from the active workspace (``ws_cwd``) and thread it through
every call. Defaulting to ``Path.cwd()`` here would silently route bd
writes to whatever directory the maverick CLI was launched in,
bypassing the workspace and producing the kind of duplicate-epic /
project-id-mismatch bugs the OpenCode-substrate migration cleanup
removed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maverick.library.actions.types import (
    BeadCreationResult,
    DependencyWiringResult,
    MarkBeadCompleteResult,
    SelectNextBeadResult,
)
from maverick.logging import get_logger

logger = get_logger(__name__)


async def create_beads(
    epic_definition: dict[str, Any],
    work_definitions: list[dict[str, Any]],
    *,
    cwd: Path | str,
    dry_run: bool = False,
) -> BeadCreationResult:
    """Create epic and work beads via the bd CLI.

    Args:
        epic_definition: Serialized BeadDefinition for the epic.
        work_definitions: Serialized BeadDefinitions for work beads.
        cwd: Workspace directory whose ``.beads/`` receives the writes.
            Required — see module docstring.
        dry_run: If True, return synthetic IDs without calling bd.

    Returns:
        BeadCreationResult with created beads and any errors.
    """
    from maverick.beads.client import BeadClient
    from maverick.beads.models import BeadDefinition

    epic_def = BeadDefinition.model_validate(epic_definition)
    work_defs = [BeadDefinition.model_validate(d) for d in work_definitions]

    if dry_run:
        logger.info("dry_run_create", beads=len(work_defs) + 1)
        epic_data = {"bd_id": "dry-run-epic", "title": epic_def.title}
        work_data: list[dict[str, Any]] = []
        created_map: dict[str, str] = {}
        for i, defn in enumerate(work_defs):
            bd_id = f"dry-run-{i}"
            work_data.append({"bd_id": bd_id, "title": defn.title})
            created_map[defn.title] = bd_id
        return BeadCreationResult(
            epic=epic_data,
            work_beads=tuple(work_data),
            created_map=created_map,
            errors=(),
        )

    client = BeadClient(cwd=Path(cwd))
    errors: list[str] = []

    # Create epic
    try:
        epic = await client.create_bead(epic_def)
    except Exception as e:
        logger.debug("epic_creation_failed", error=str(e))
        return BeadCreationResult(
            epic=None,
            work_beads=(),
            created_map={},
            errors=(f"Epic creation failed: {e}",),
        )

    epic_data = {"bd_id": epic.bd_id, "title": epic.definition.title}

    # Create work beads as children
    work_data = []
    created_map = {}
    for defn in work_defs:
        try:
            created = await client.create_bead(defn, parent_id=epic.bd_id)
            work_data.append({"bd_id": created.bd_id, "title": created.definition.title})
            created_map[defn.title] = created.bd_id
        except Exception as e:
            error_msg = f"Failed to create bead '{defn.title}': {e}"
            logger.debug("bead_creation_failed", title=defn.title, error=str(e))
            errors.append(error_msg)

    return BeadCreationResult(
        epic=epic_data,
        work_beads=tuple(work_data),
        created_map=created_map,
        errors=tuple(errors),
    )


async def wire_dependencies(
    work_definitions: list[dict[str, Any]],
    created_map: dict[str, str],
    tasks_content: str,
    extracted_deps: str,
    *,
    cwd: Path | str,
    dry_run: bool = False,
) -> DependencyWiringResult:
    """Compute and wire dependencies between created beads.

    Structural dependencies (foundation->stories, stories->cleanup) are
    deterministic. Inter-story dependencies are parsed from the generator's
    JSON output.

    Args:
        work_definitions: Serialized BeadDefinitions for work beads.
        created_map: Mapping from bead title to bd_id.
        tasks_content: Raw tasks.md content (used for structural dep context).
        extracted_deps: JSON string from DependencyExtractor, e.g.
            '[["US3","US1"],["US7","US1"]]'.
        cwd: Workspace directory whose ``.beads/`` receives the writes.
            Required — see module docstring.
        dry_run: If True, compute dependencies without calling bd.

    Returns:
        DependencyWiringResult with dependencies and any errors.
    """
    from maverick.beads.client import BeadClient
    from maverick.beads.models import (
        BeadCategory,
        BeadDefinition,
        BeadDependency,
        DependencyType,
    )

    work_defs = [BeadDefinition.model_validate(d) for d in work_definitions]

    # Identify beads by category
    foundation_id: str | None = None
    cleanup_id: str | None = None
    story_defs: list[tuple[BeadDefinition, str]] = []

    for defn in work_defs:
        bd_id = created_map.get(defn.title)
        if not bd_id:
            continue
        if defn.category == BeadCategory.FOUNDATION:
            foundation_id = bd_id
        elif defn.category == BeadCategory.CLEANUP:
            cleanup_id = bd_id
        elif defn.category == BeadCategory.USER_STORY:
            story_defs.append((defn, bd_id))

    deps: list[BeadDependency] = []

    # Foundation blocks all story beads (stories depend on foundation)
    if foundation_id:
        for _defn, story_id in story_defs:
            deps.append(
                BeadDependency(
                    blocker_id=foundation_id,
                    blocked_id=story_id,
                    dep_type=DependencyType.BLOCKS,
                )
            )

    # All story beads block cleanup (cleanup depends on stories)
    if cleanup_id:
        for _defn, story_id in story_defs:
            deps.append(
                BeadDependency(
                    blocker_id=story_id,
                    blocked_id=cleanup_id,
                    dep_type=DependencyType.BLOCKS,
                )
            )

    # Foundation blocks cleanup directly if no stories
    if foundation_id and cleanup_id and not story_defs:
        deps.append(
            BeadDependency(
                blocker_id=foundation_id,
                blocked_id=cleanup_id,
                dep_type=DependencyType.BLOCKS,
            )
        )

    # Parse inter-story deps from generator output
    us_to_id: dict[str, str] = {}
    for defn, bd_id in story_defs:
        if defn.user_story_id:
            us_to_id[defn.user_story_id] = bd_id

    try:
        dep_pairs: list[list[str]] = json.loads(extracted_deps) if extracted_deps.strip() else []
    except (json.JSONDecodeError, TypeError):
        logger.warning("invalid_extracted_deps", raw=extracted_deps[:200])
        dep_pairs = []

    for pair in dep_pairs:
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        dependent_us, dependency_us = pair[0], pair[1]
        dependent_id = us_to_id.get(dependent_us)
        dependency_id = us_to_id.get(dependency_us)
        if dependent_id and dependency_id and dependent_id != dependency_id:
            deps.append(
                BeadDependency(
                    blocker_id=dependency_id,
                    blocked_id=dependent_id,
                    dep_type=DependencyType.BLOCKS,
                )
            )

    if dry_run:
        logger.info("dry_run_deps", count=len(deps))
        return DependencyWiringResult(
            dependencies=tuple(d.model_dump(mode="json") for d in deps),
            errors=(),
            success=True,
        )

    # Wire dependencies via bd CLI
    client = BeadClient(cwd=Path(cwd))
    errors: list[str] = []
    wired: list[BeadDependency] = []

    for dep in deps:
        try:
            await client.add_dependency(dep)
            wired.append(dep)
        except Exception as e:
            error_msg = f"Failed to wire: {dep.blocked_id} blocked-by {dep.blocker_id}: {e}"
            logger.debug(
                "dependency_wiring_failed",
                blocker_id=dep.blocker_id,
                blocked_id=dep.blocked_id,
                error=str(e),
            )
            errors.append(error_msg)

    return DependencyWiringResult(
        dependencies=tuple(d.model_dump(mode="json") for d in wired),
        errors=tuple(errors),
        success=len(errors) == 0,
    )


async def select_next_bead(
    epic_id: str = "",
    *,
    cwd: Path | str,
) -> SelectNextBeadResult:
    """Select the next ready bead.

    Args:
        cwd: Workspace directory whose ``.beads/`` is queried. Required —
            see module docstring.
        epic_id: Epic bead ID to query. When empty, queries any ready bead
            across all epics.

    Returns:
        SelectNextBeadResult with bead info or done=True if none left.
    """
    from maverick.beads.client import BeadClient

    client = BeadClient(cwd=Path(cwd))

    # When epic_id is provided, query by parent; otherwise query all ready beads.
    # Fetch more than 1 to allow filtering out human-assigned beads.
    parent = epic_id if epic_id else None
    beads = await client.ready(parent, limit=10)

    if not beads:
        logger.info("no_ready_beads", epic_id=epic_id or "(any)")
        return SelectNextBeadResult(
            found=False,
            bead_id="",
            title="",
            description="",
            priority=0,
            epic_id=epic_id,
            done=True,
        )

    # Skip human-assigned beads — check labels via bd show
    bead = None
    for candidate in beads:
        try:
            details = await client.show(candidate.id)
            labels = details.labels or []
            if "needs-human-review" in labels or "assumption-review" in labels:
                logger.info(
                    "skipping_human_bead",
                    bead_id=candidate.id,
                    labels=labels,
                )
                continue
        except Exception:
            pass
        bead = candidate
        break

    if bead is None:
        logger.info(
            "only_human_beads_remaining",
            epic_id=epic_id or "(any)",
            total_ready=len(beads),
        )
        return SelectNextBeadResult(
            found=False,
            bead_id="",
            title="",
            description="",
            priority=0,
            epic_id=epic_id,
            done=False,
        )

    # Resolve the epic_id from the bead when none was specified
    resolved_epic_id = epic_id or bead.parent_id or ""

    # If the bead lacks a description and we got it from a global query,
    # fetch full details
    description = bead.description
    if not description and not epic_id:
        try:
            details = await client.show(bead.id)
            description = details.description
        except Exception:
            pass

    # Resolve flight_plan_name from epic state metadata
    flight_plan_name = ""
    if resolved_epic_id:
        try:
            epic_details = await client.show(resolved_epic_id)
            flight_plan_name = epic_details.state.get("flight_plan_name", "")
        except Exception:
            pass

    logger.info(
        "bead_selected",
        bead_id=bead.id,
        title=bead.title,
        priority=bead.priority,
        epic_id=resolved_epic_id,
        flight_plan_name=flight_plan_name or "(none)",
    )
    return SelectNextBeadResult(
        found=True,
        bead_id=bead.id,
        title=bead.title,
        description=description,
        priority=bead.priority,
        epic_id=resolved_epic_id,
        done=False,
        flight_plan_name=flight_plan_name,
    )


async def mark_bead_complete(
    bead_id: str,
    *,
    cwd: Path | str,
    reason: str = "",
) -> MarkBeadCompleteResult:
    """Close a bead, marking it as complete.

    Args:
        bead_id: ID of the bead to close.
        cwd: Workspace directory whose ``.beads/`` is updated. Required —
            see module docstring.
        reason: Optional reason for closing.

    Returns:
        MarkBeadCompleteResult with success status.
    """
    from maverick.beads.client import BeadClient

    client = BeadClient(cwd=Path(cwd))
    try:
        await client.close(bead_id, reason=reason)
        logger.info("bead_completed", bead_id=bead_id)
        return MarkBeadCompleteResult(
            success=True,
            bead_id=bead_id,
            error=None,
        )
    except Exception as e:
        logger.debug("bead_close_failed", bead_id=bead_id, error=str(e))
        return MarkBeadCompleteResult(
            success=False,
            bead_id=bead_id,
            error=str(e),
        )


async def defer_bead(
    bead_id: str,
    *,
    cwd: Path | str,
    reason: str = "",
) -> None:
    """Defer a bead so it no longer appears in ``bd ready``.

    Args:
        bead_id: ID of the bead to defer.
        cwd: Workspace directory whose ``.beads/`` is updated. Required —
            see module docstring.
        reason: Reason for deferral (logged, not passed to bd).
    """
    from maverick.runners.command import CommandRunner

    runner = CommandRunner(cwd=Path(cwd))
    await runner.run(["bd", "defer", bead_id])
    logger.info("bead_deferred", bead_id=bead_id, reason=reason)
