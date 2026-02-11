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
    CheckEpicDoneResult,
    CreateBeadsFromFailuresResult,
    CreateBeadsFromFindingsResult,
    DependencyWiringResult,
    MarkBeadCompleteResult,
    SelectNextBeadResult,
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
    client = BeadClient(cwd=Path.cwd())
    errors: list[str] = []
    wired: list[BeadDependency] = []

    for dep in deps:
        try:
            await client.add_dependency(dep)
            wired.append(dep)
        except Exception as e:
            error_msg = (
                f"Failed to wire: {dep.blocked_id} "
                f"blocked-by {dep.blocker_id}: {e}"
            )
            logger.error(
                "dependency_wiring_failed",
                blocker_id=dep.blocker_id,
                blocked_id=dep.blocked_id,
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


async def select_next_bead(epic_id: str = "") -> SelectNextBeadResult:
    """Select the next ready bead.

    Args:
        epic_id: Epic bead ID to query. When empty, queries any ready bead
            across all epics.

    Returns:
        SelectNextBeadResult with bead info or done=True if none left.
    """
    from maverick.beads.client import BeadClient

    client = BeadClient(cwd=Path.cwd())

    # When epic_id is provided, query by parent; otherwise query all ready beads
    parent = epic_id if epic_id else None
    beads = await client.ready(parent, limit=1)

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

    bead = beads[0]

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

    logger.info(
        "bead_selected",
        bead_id=bead.id,
        title=bead.title,
        priority=bead.priority,
        epic_id=resolved_epic_id,
    )
    return SelectNextBeadResult(
        found=True,
        bead_id=bead.id,
        title=bead.title,
        description=description,
        priority=bead.priority,
        epic_id=resolved_epic_id,
        done=False,
    )


async def mark_bead_complete(
    bead_id: str,
    reason: str = "",
) -> MarkBeadCompleteResult:
    """Close a bead, marking it as complete.

    Args:
        bead_id: ID of the bead to close.
        reason: Optional reason for closing.

    Returns:
        MarkBeadCompleteResult with success status.
    """
    from maverick.beads.client import BeadClient

    client = BeadClient(cwd=Path.cwd())
    try:
        await client.close(bead_id, reason=reason)
        logger.info("bead_completed", bead_id=bead_id)
        return MarkBeadCompleteResult(
            success=True,
            bead_id=bead_id,
            error=None,
        )
    except Exception as e:
        logger.error("bead_close_failed", bead_id=bead_id, error=str(e))
        return MarkBeadCompleteResult(
            success=False,
            bead_id=bead_id,
            error=str(e),
        )


async def check_epic_done(epic_id: str = "") -> CheckEpicDoneResult:
    """Check if there are any remaining ready beads.

    Args:
        epic_id: Epic bead ID to check. When empty, checks for any ready bead
            across all epics.

    Returns:
        CheckEpicDoneResult with done flag and remaining count.
    """
    from maverick.beads.client import BeadClient

    client = BeadClient(cwd=Path.cwd())
    parent = epic_id if epic_id else None
    beads = await client.ready(parent, limit=10)

    done = len(beads) == 0
    logger.info(
        "epic_done_check",
        epic_id=epic_id or "(any)",
        done=done,
        remaining=len(beads),
    )
    return CheckEpicDoneResult(
        done=done,
        remaining_count=len(beads),
    )


# Priority constants for validation failure beads
_PRIORITY_TEST = 1
_PRIORITY_LINT = 3
_PRIORITY_TYPECHECK = 3
_PRIORITY_FORMAT = 4


async def create_beads_from_failures(
    epic_id: str,
    validation_result: dict[str, Any],
    dry_run: bool = False,
) -> CreateBeadsFromFailuresResult:
    """Create fix beads from validation failures.

    Args:
        epic_id: Epic bead ID to create children under.
        validation_result: Validation output dict with ``passed`` and ``stages``.
        dry_run: If True, return synthetic IDs without calling bd.

    Returns:
        CreateBeadsFromFailuresResult with created bead info.
    """
    from maverick.beads.models import BeadCategory, BeadDefinition, BeadType

    if validation_result.get("passed", True):
        return CreateBeadsFromFailuresResult(
            created_count=0,
            bead_ids=(),
            errors=(),
        )

    # The validate step returns stage_results as a dict keyed by stage name,
    # each value being a dict with 'passed', 'output', 'errors', etc.
    stage_results = validation_result.get("stage_results", {})
    failed_stages: list[tuple[str, dict[str, Any]]] = [
        (name, data)
        for name, data in stage_results.items()
        if isinstance(data, dict) and not data.get("passed", True)
    ]

    if not failed_stages:
        return CreateBeadsFromFailuresResult(
            created_count=0,
            bead_ids=(),
            errors=(),
        )

    priority_map = {
        "test": _PRIORITY_TEST,
        "lint": _PRIORITY_LINT,
        "typecheck": _PRIORITY_TYPECHECK,
        "format": _PRIORITY_FORMAT,
    }

    definitions: list[BeadDefinition] = []
    for stage_name, stage_data in failed_stages:
        errors_list = stage_data.get("errors", [])
        output_text = stage_data.get("output", "")
        # Use output as error context when errors list is empty
        error_text = "\n".join(str(e) for e in errors_list[:20]) or output_text

        priority = priority_map.get(stage_name, 3)

        definitions.append(
            BeadDefinition(
                title=f"Fix: {stage_name} validation failures",
                bead_type=BeadType.TASK,
                priority=priority,
                category=BeadCategory.VALIDATION,
                description=(
                    f"Fix {stage_name} validation failures.\n\n"
                    f"Errors:\n{error_text}"
                ),
            )
        )

    if dry_run:
        dry_ids = tuple(f"dry-run-fix-{i}" for i in range(len(definitions)))
        return CreateBeadsFromFailuresResult(
            created_count=len(definitions),
            bead_ids=dry_ids,
            errors=(),
        )

    from maverick.beads.client import BeadClient

    client = BeadClient(cwd=Path.cwd())
    created_ids: list[str] = []
    errors: list[str] = []

    for defn in definitions:
        try:
            created = await client.create_bead(defn, parent_id=epic_id)
            created_ids.append(created.bd_id)
        except Exception as e:
            error_msg = f"Failed to create fix bead '{defn.title}': {e}"
            logger.error("fix_bead_creation_failed", title=defn.title, error=str(e))
            errors.append(error_msg)

    return CreateBeadsFromFailuresResult(
        created_count=len(created_ids),
        bead_ids=tuple(created_ids),
        errors=tuple(errors),
    )


# Priority constants for review finding beads
_PRIORITY_CRITICAL = 1
_PRIORITY_MAJOR = 2
_PRIORITY_MINOR = 4


async def create_beads_from_findings(
    epic_id: str,
    review_result: dict[str, Any],
    dry_run: bool = False,
) -> CreateBeadsFromFindingsResult:
    """Create fix beads from code review findings.

    Args:
        epic_id: Epic bead ID to create children under.
        review_result: Review output dict with ``issues`` and ``recommendation``.
        dry_run: If True, return synthetic IDs without calling bd.

    Returns:
        CreateBeadsFromFindingsResult with created bead info.
    """
    from maverick.beads.models import BeadCategory, BeadDefinition, BeadType

    recommendation = review_result.get("recommendation", "")
    issues = review_result.get("issues", [])

    if not issues or recommendation == "approve":
        return CreateBeadsFromFindingsResult(
            created_count=0,
            bead_ids=(),
            errors=(),
        )

    # Group issues by file
    file_groups: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        file_path = issue.get("file_path", "general")
        file_groups.setdefault(file_path, []).append(issue)

    severity_priority = {
        "critical": _PRIORITY_CRITICAL,
        "major": _PRIORITY_MAJOR,
        "minor": _PRIORITY_MINOR,
    }

    definitions: list[BeadDefinition] = []
    for file_path, file_issues in file_groups.items():
        # Use highest severity in group for priority
        min_priority = min(
            severity_priority.get(issue.get("severity", "minor"), _PRIORITY_MINOR)
            for issue in file_issues
        )
        descriptions = [
            f"- [{issue.get('severity', 'minor')}] {issue.get('description', '')}"
            for issue in file_issues
        ]
        description_text = "\n".join(descriptions)

        definitions.append(
            BeadDefinition(
                title=f"Fix review findings: {file_path}",
                bead_type=BeadType.TASK,
                priority=min_priority,
                category=BeadCategory.REVIEW,
                description=(
                    f"Fix review findings in {file_path}.\n\n"
                    f"Issues:\n{description_text}"
                ),
            )
        )

    if dry_run:
        dry_ids = tuple(f"dry-run-review-{i}" for i in range(len(definitions)))
        return CreateBeadsFromFindingsResult(
            created_count=len(definitions),
            bead_ids=dry_ids,
            errors=(),
        )

    from maverick.beads.client import BeadClient

    client = BeadClient(cwd=Path.cwd())
    created_ids: list[str] = []
    errors: list[str] = []

    for defn in definitions:
        try:
            created = await client.create_bead(defn, parent_id=epic_id)
            created_ids.append(created.bd_id)
        except Exception as e:
            error_msg = f"Failed to create review bead '{defn.title}': {e}"
            logger.error("review_bead_creation_failed", title=defn.title, error=str(e))
            errors.append(error_msg)

    return CreateBeadsFromFindingsResult(
        created_count=len(created_ids),
        bead_ids=tuple(created_ids),
        errors=tuple(errors),
    )
