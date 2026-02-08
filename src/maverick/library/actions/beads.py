"""Bead generation actions for DSL workflow execution.

Actions that wrap the beads library for use in YAML workflow steps.
Each action receives and returns JSON-serializable dicts/primitives.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from maverick.library.actions.types import (
    BeadCreationResult,
    DependencyWiringResult,
    SpecKitParseResult,
)
from maverick.logging import get_logger

logger = get_logger(__name__)

# Regex for extracting the dependency section from tasks.md
_DEP_SECTION_PATTERN = re.compile(
    r"#+\s*(?:User\s+Story\s+)?Dependencies\s*\n(.*?)(?=\n#+\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)


async def parse_speckit(spec_dir: str) -> SpecKitParseResult:
    """Parse a SpecKit spec directory into bead definitions.

    Args:
        spec_dir: Path to the spec directory containing tasks.md.

    Returns:
        SpecKitParseResult with epic/work definitions and dependency section.

    Raises:
        RuntimeError: If spec_dir or tasks.md is invalid or has no phases.
    """
    from maverick.beads.models import BeadCategory, BeadDefinition, BeadType
    from maverick.beads.speckit import (
        SpecKitContextExtractor,
        group_phases_into_beads,
    )
    from maverick.models.implementation import TaskFile

    spec_path = Path(spec_dir).resolve()
    tasks_path = spec_path / "tasks.md"

    if not spec_path.is_dir():
        raise RuntimeError(f"Spec directory does not exist: {spec_path}")

    if not tasks_path.is_file():
        raise RuntimeError(f"tasks.md not found in {spec_path}")

    # Parse tasks.md
    logger.info("parsing_tasks", spec_dir=str(spec_path))
    task_file = await TaskFile.parse_async(tasks_path)

    if not task_file.phases:
        raise RuntimeError(f"No phases found in {tasks_path}")

    # Classify and group phases
    bead_definitions = group_phases_into_beads(task_file.phases)
    logger.info(
        "phases_grouped",
        total_beads=len(bead_definitions),
        phases=len(task_file.phases),
    )

    # Build context
    extractor = SpecKitContextExtractor(spec_path, task_file)

    # Build epic definition
    epic_title = spec_path.name
    epic_description = extractor.build_epic_description()
    epic_definition = BeadDefinition(
        title=epic_title,
        bead_type=BeadType.EPIC,
        priority=1,
        category=BeadCategory.FOUNDATION,
        description=epic_description,
        phase_names=list(task_file.phases.keys()),
        task_ids=[t.id for t in task_file.tasks],
    )

    # Enrich work bead definitions with descriptions
    enriched_definitions: list[BeadDefinition] = []
    for defn in bead_definitions:
        description = extractor.build_bead_description(defn)
        enriched = BeadDefinition(
            title=defn.title,
            bead_type=defn.bead_type,
            priority=defn.priority,
            category=defn.category,
            description=description,
            phase_names=defn.phase_names,
            user_story_id=defn.user_story_id,
            task_ids=defn.task_ids,
        )
        enriched_definitions.append(enriched)

    # Read tasks content and extract dependency section
    tasks_content = tasks_path.read_text(encoding="utf-8")
    dep_match = _DEP_SECTION_PATTERN.search(tasks_content)
    dependency_section = dep_match.group(1).strip() if dep_match else ""

    return SpecKitParseResult(
        epic_definition=epic_definition.model_dump(mode="json"),
        work_definitions=tuple(d.model_dump(mode="json") for d in enriched_definitions),
        tasks_content=tasks_content,
        dependency_section=dependency_section,
    )


async def create_beads(
    epic_definition: dict[str, Any],
    work_definitions: list[dict[str, Any]],
    dry_run: bool = False,
) -> BeadCreationResult:
    """Create epic and work beads via the bd CLI.

    Args:
        epic_definition: Serialized BeadDefinition for the epic.
        work_definitions: Serialized BeadDefinitions for work beads.
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

    client = BeadClient(cwd=Path.cwd())
    errors: list[str] = []

    # Create epic
    try:
        epic = await client.create_bead(epic_def)
    except Exception as e:
        logger.error("epic_creation_failed", error=str(e))
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
            work_data.append(
                {"bd_id": created.bd_id, "title": created.definition.title}
            )
            created_map[defn.title] = created.bd_id
        except Exception as e:
            error_msg = f"Failed to create bead '{defn.title}': {e}"
            logger.error("bead_creation_failed", title=defn.title, error=str(e))
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

    # Foundation blocks all story beads
    if foundation_id:
        for _defn, story_id in story_defs:
            deps.append(
                BeadDependency(
                    from_id=foundation_id,
                    to_id=story_id,
                    dep_type=DependencyType.BLOCKS,
                )
            )

    # All story beads block cleanup
    if cleanup_id:
        for _defn, story_id in story_defs:
            deps.append(
                BeadDependency(
                    from_id=story_id,
                    to_id=cleanup_id,
                    dep_type=DependencyType.BLOCKS,
                )
            )

    # Foundation blocks cleanup directly if no stories
    if foundation_id and cleanup_id and not story_defs:
        deps.append(
            BeadDependency(
                from_id=foundation_id,
                to_id=cleanup_id,
                dep_type=DependencyType.BLOCKS,
            )
        )

    # Parse inter-story deps from generator output
    us_to_id: dict[str, str] = {}
    for defn, bd_id in story_defs:
        if defn.user_story_id:
            us_to_id[defn.user_story_id] = bd_id

    try:
        dep_pairs: list[list[str]] = (
            json.loads(extracted_deps) if extracted_deps.strip() else []
        )
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
                    from_id=dependency_id,
                    to_id=dependent_id,
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
    client = BeadClient(cwd=Path.cwd())
    errors: list[str] = []
    wired: list[BeadDependency] = []

    for dep in deps:
        try:
            await client.add_dependency(dep)
            wired.append(dep)
        except Exception as e:
            error_msg = f"Failed to wire dependency {dep.from_id} -> {dep.to_id}: {e}"
            logger.error(
                "dependency_wiring_failed",
                from_id=dep.from_id,
                to_id=dep.to_id,
                error=str(e),
            )
            errors.append(error_msg)

    # Sync
    try:
        await client.sync()
    except Exception as e:
        error_msg = f"Failed to sync beads: {e}"
        logger.warning("sync_failed", error=str(e))
        errors.append(error_msg)

    return DependencyWiringResult(
        dependencies=tuple(d.model_dump(mode="json") for d in wired),
        errors=tuple(errors),
        success=len(errors) == 0,
    )
