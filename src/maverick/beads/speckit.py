"""Generate beads from SpecKit specification directories.

Parses a SpecKit spec directory's ``tasks.md`` into coarse-grained beads
by classifying phases, grouping them, extracting context, and wiring
dependencies via the ``bd`` CLI.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

from maverick.beads.client import BeadClient
from maverick.beads.models import (
    BeadCategory,
    BeadDefinition,
    BeadDependency,
    BeadGenerationResult,
    BeadType,
    CreatedBead,
    DependencyType,
)
from maverick.exceptions.beads import SpecKitParseError
from maverick.logging import get_logger
from maverick.models.implementation import Task, TaskFile

logger = get_logger(__name__)

# =============================================================================
# Phase Classification
# =============================================================================

# Keywords that indicate a foundation/setup phase
_FOUNDATION_KEYWORDS = frozenset(
    {
        "setup",
        "foundational",
        "foundation",
        "infrastructure",
        "prerequisites",
        "blocking",
    }
)

# Keywords that indicate a cleanup/polish phase
_CLEANUP_KEYWORDS = frozenset(
    {
        "polish",
        "cross-cutting",
        "cleanup",
        "finalize",
        "finalise",
    }
)

# Regex for user story phase names like "User Story 3" or "US2"
_USER_STORY_PATTERN = re.compile(r"user\s+story\s+(\d+)", re.IGNORECASE)
_US_SHORT_PATTERN = re.compile(r"\bUS(\d+)\b", re.IGNORECASE)

# Regex for inter-story dependencies in the dependency section
_STORY_DEP_PATTERN = re.compile(
    r"US(\d+).*?Depends\s+(?:only\s+)?on\s+((?:US\d+(?:\s*,\s*)?)+)",
    re.IGNORECASE,
)
_US_REF_PATTERN = re.compile(r"US(\d+)", re.IGNORECASE)


class PhaseCategory(str, Enum):
    """Classification of a tasks.md phase."""

    FOUNDATION = "foundation"
    USER_STORY = "user_story"
    CLEANUP = "cleanup"


def classify_phase(
    phase_name: str,
    phase_index: int,
    total_phases: int,
) -> PhaseCategory:
    """Classify a phase by its name and position.

    Classification precedence:
    1. Regex match for "User Story N" -> USER_STORY
    2. Foundation keywords -> FOUNDATION
    3. Cleanup keywords -> CLEANUP
    4. Positional heuristic (first 2 = FOUNDATION, last = CLEANUP) when >3 phases
    5. Default -> USER_STORY

    Args:
        phase_name: Name of the phase from the tasks.md header.
        phase_index: Zero-based position of this phase among all phases.
        total_phases: Total number of phases.

    Returns:
        The classified PhaseCategory.
    """
    name_lower = phase_name.lower()

    # 1. Explicit user story reference
    if _USER_STORY_PATTERN.search(name_lower):
        return PhaseCategory.USER_STORY

    # 2. Foundation keywords
    if any(kw in name_lower for kw in _FOUNDATION_KEYWORDS):
        return PhaseCategory.FOUNDATION

    # 3. Cleanup keywords
    if any(kw in name_lower for kw in _CLEANUP_KEYWORDS):
        return PhaseCategory.CLEANUP

    # 4. Positional heuristic (only when >3 phases)
    if total_phases > 3:
        if phase_index < 2:
            return PhaseCategory.FOUNDATION
        if phase_index == total_phases - 1:
            return PhaseCategory.CLEANUP

    # 5. Default
    return PhaseCategory.USER_STORY


# =============================================================================
# Phase Aggregation
# =============================================================================


def _extract_user_story_id(phase_name: str) -> str | None:
    """Extract user story ID from a phase name.

    Args:
        phase_name: Phase name like "Phase 3: User Story 1 - Basic Greeting".

    Returns:
        User story ID like "US1", or None.
    """
    match = _USER_STORY_PATTERN.search(phase_name)
    if match:
        return f"US{match.group(1)}"

    # Also check for US shorthand in phase name
    match = _US_SHORT_PATTERN.search(phase_name)
    if match:
        return f"US{match.group(1)}"

    return None


def _extract_story_title(phase_name: str) -> str:
    """Extract a clean title from a user story phase name.

    Strips phase numbering and "User Story N" prefix, keeping the
    descriptive part.

    Args:
        phase_name: Phase name like "Phase 3: User Story 1 - Basic Greeting".

    Returns:
        Clean title like "Basic Greeting".
    """
    # Remove "Phase N:" prefix
    title = re.sub(r"^Phase\s+\d+\s*:\s*", "", phase_name, flags=re.IGNORECASE)
    # Remove "User Story N -" or "User Story N:" prefix
    title = re.sub(
        r"User\s+Story\s+\d+\s*[-:]\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    # Remove priority markers like "(Priority: P1)"
    title = re.sub(r"\(Priority:\s*P\d+\)", "", title, flags=re.IGNORECASE)
    # Remove emoji and extra whitespace
    title = re.sub(r"[^\w\s\-/&,.]", "", title)
    title = title.strip(" -:")
    return title or phase_name


def group_phases_into_beads(
    phases: dict[str, list[Task]],
) -> list[BeadDefinition]:
    """Group classified phases into bead definitions.

    - All FOUNDATION phases merge into a single "Foundation" bead.
    - Each USER_STORY phase becomes one bead.
    - All CLEANUP phases merge into a single "Cleanup" bead.

    Args:
        phases: Phase name -> task list mapping from TaskFile.

    Returns:
        Ordered list of BeadDefinitions.
    """
    phase_names = list(phases.keys())
    total = len(phase_names)

    foundation_phases: list[str] = []
    story_phases: list[str] = []
    cleanup_phases: list[str] = []

    for idx, name in enumerate(phase_names):
        category = classify_phase(name, idx, total)
        if category == PhaseCategory.FOUNDATION:
            foundation_phases.append(name)
        elif category == PhaseCategory.CLEANUP:
            cleanup_phases.append(name)
        else:
            story_phases.append(name)

    beads: list[BeadDefinition] = []
    priority = 1  # Clamped to 0-4 (bd's P0-P4 range) when assigned

    # Foundation bead (merged)
    if foundation_phases:
        all_task_ids = [t.id for name in foundation_phases for t in phases[name]]
        beads.append(
            BeadDefinition(
                title="Foundation",
                bead_type=BeadType.TASK,
                priority=min(priority, 4),
                category=BeadCategory.FOUNDATION,
                phase_names=foundation_phases,
                task_ids=all_task_ids,
            )
        )
        priority += 1

    # Story beads (one per phase)
    for name in story_phases:
        tasks = phases[name]
        us_id = _extract_user_story_id(name)
        title = _extract_story_title(name)
        beads.append(
            BeadDefinition(
                title=title,
                bead_type=BeadType.TASK,
                priority=min(priority, 4),
                category=BeadCategory.USER_STORY,
                phase_names=[name],
                user_story_id=us_id,
                task_ids=[t.id for t in tasks],
            )
        )
        priority += 1

    # Cleanup bead (merged)
    if cleanup_phases:
        all_task_ids = [t.id for name in cleanup_phases for t in phases[name]]
        beads.append(
            BeadDefinition(
                title="Cleanup",
                bead_type=BeadType.TASK,
                priority=min(priority, 4),
                category=BeadCategory.CLEANUP,
                phase_names=cleanup_phases,
                task_ids=all_task_ids,
            )
        )

    return beads


# =============================================================================
# Context Extraction
# =============================================================================


class SpecKitContextExtractor:
    """Extract bead descriptions from SpecKit spec directories.

    Since specs are in-repo, descriptions use file references and key
    excerpts rather than being fully self-contained.

    Args:
        spec_dir: Path to the spec directory.
        task_file: Parsed TaskFile.
    """

    def __init__(self, spec_dir: Path, task_file: TaskFile) -> None:
        self._spec_dir = spec_dir
        self._task_file = task_file

    def build_epic_description(self) -> str:
        """Build description for the epic bead.

        Includes spec summary, file listing, and task counts.

        Returns:
            Markdown-formatted epic description.
        """
        parts: list[str] = []

        # Spec directory reference
        parts.append(f"**Spec directory**: `{self._spec_dir}`\n")

        # List spec files
        spec_files = sorted(self._spec_dir.iterdir())
        if spec_files:
            parts.append("**Spec files**:")
            for f in spec_files:
                if f.is_file():
                    parts.append(f"- `{f.name}`")
                elif f.is_dir():
                    parts.append(f"- `{f.name}/`")
            parts.append("")

        # Task summary
        total_tasks = len(self._task_file.tasks)
        total_phases = len(self._task_file.phases)
        pending = len(self._task_file.pending_tasks)
        completed = len(self._task_file.completed_tasks)
        parts.append(
            f"**Tasks**: {total_tasks} total across {total_phases} phases "
            f"({completed} completed, {pending} pending)"
        )

        return "\n".join(parts)

    def build_bead_description(self, definition: BeadDefinition) -> str:
        """Build description for a work bead.

        Includes file references, task list, and checkpoint conditions
        extracted from the tasks.md content.

        Args:
            definition: The bead definition to build description for.

        Returns:
            Markdown-formatted bead description.
        """
        parts: list[str] = []

        # Phase references
        parts.append("**Phases**: " + ", ".join(definition.phase_names))
        parts.append("")

        # Task list
        if definition.task_ids:
            parts.append("**Tasks**:")
            for task_id in definition.task_ids:
                task = self._find_task(task_id)
                if task:
                    status = "x" if task.status.value == "completed" else " "
                    parts.append(f"- [{status}] {task.id} {task.description}")
            parts.append("")

        # Extract checkpoint conditions from the tasks.md content
        checkpoints = self._extract_checkpoints(definition.phase_names)
        if checkpoints:
            parts.append("**Checkpoints**:")
            for checkpoint in checkpoints:
                parts.append(f"- {checkpoint}")
            parts.append("")

        # Spec file reference
        parts.append(f"**Spec directory**: `{self._spec_dir}`")

        return "\n".join(parts)

    def _find_task(self, task_id: str) -> Task | None:
        """Find a task by ID in the task file."""
        for task in self._task_file.tasks:
            if task.id == task_id:
                return task
        return None

    def _extract_checkpoints(self, phase_names: list[str]) -> list[str]:
        """Extract checkpoint lines from tasks.md for the given phases.

        Looks for lines starting with "**Checkpoint**:" in the raw content
        that appear within the relevant phase sections.

        Args:
            phase_names: Phase names to extract checkpoints for.

        Returns:
            List of checkpoint descriptions.
        """
        checkpoints: list[str] = []
        try:
            content = self._task_file.path.read_text(encoding="utf-8")
        except OSError:
            return checkpoints

        lines = content.split("\n")
        in_relevant_phase = False

        for line in lines:
            stripped = line.strip()
            # Check for phase header
            if stripped.startswith("## "):
                phase_name = stripped[3:].strip()
                in_relevant_phase = any(pn in phase_name for pn in phase_names)
                continue

            # Extract checkpoint lines
            if in_relevant_phase and "**Checkpoint**:" in stripped:
                # Remove the **Checkpoint**: prefix
                checkpoint_text = re.sub(
                    r"\*\*Checkpoint\*\*:\s*",
                    "",
                    stripped,
                )
                if checkpoint_text:
                    checkpoints.append(checkpoint_text)

        return checkpoints


# =============================================================================
# Dependency Computation
# =============================================================================


def _compute_dependencies(
    beads: list[BeadDefinition],
    created_map: dict[str, CreatedBead],
    tasks_content: str,
) -> list[BeadDependency]:
    """Compute dependencies between created beads.

    Rules:
    - Foundation blocks all story beads.
    - All story beads block cleanup.
    - Inter-story deps parsed from the dependency section of tasks.md.

    Args:
        beads: Ordered list of bead definitions.
        created_map: Mapping from bead title to CreatedBead.
        tasks_content: Raw tasks.md content for parsing inter-story deps.

    Returns:
        List of BeadDependency objects.
    """
    deps: list[BeadDependency] = []

    # Identify beads by category (skip any that failed creation)
    foundation_bead = next(
        (
            created_map[b.title]
            for b in beads
            if b.category == BeadCategory.FOUNDATION and b.title in created_map
        ),
        None,
    )
    cleanup_bead = next(
        (
            created_map[b.title]
            for b in beads
            if b.category == BeadCategory.CLEANUP and b.title in created_map
        ),
        None,
    )
    story_beads = [
        (b, created_map[b.title])
        for b in beads
        if b.category == BeadCategory.USER_STORY and b.title in created_map
    ]

    # Foundation blocks all story beads (stories depend on foundation)
    if foundation_bead:
        for _def, created in story_beads:
            deps.append(
                BeadDependency(
                    blocker_id=foundation_bead.bd_id,
                    blocked_id=created.bd_id,
                    dep_type=DependencyType.BLOCKS,
                )
            )

    # All story beads block cleanup (cleanup depends on stories)
    if cleanup_bead:
        for _def, created in story_beads:
            deps.append(
                BeadDependency(
                    blocker_id=created.bd_id,
                    blocked_id=cleanup_bead.bd_id,
                    dep_type=DependencyType.BLOCKS,
                )
            )

    # Parse inter-story dependencies from tasks.md
    us_to_bead: dict[str, CreatedBead] = {}
    for bead_def, created in story_beads:
        if bead_def.user_story_id:
            us_to_bead[bead_def.user_story_id] = created

    for match in _STORY_DEP_PATTERN.finditer(tasks_content):
        target_us = f"US{match.group(1)}"
        dep_refs_str = match.group(2)
        source_refs = _US_REF_PATTERN.findall(dep_refs_str)

        target_bead = us_to_bead.get(target_us)
        if not target_bead:
            continue

        for source_num in source_refs:
            source_us = f"US{source_num}"
            source_bead = us_to_bead.get(source_us)
            if source_bead and source_bead.bd_id != target_bead.bd_id:
                deps.append(
                    BeadDependency(
                        blocker_id=source_bead.bd_id,
                        blocked_id=target_bead.bd_id,
                        dep_type=DependencyType.BLOCKS,
                    )
                )

    # Foundation blocks cleanup directly (if no stories)
    if foundation_bead and cleanup_bead and not story_beads:
        deps.append(
            BeadDependency(
                blocker_id=foundation_bead.bd_id,
                blocked_id=cleanup_bead.bd_id,
                dep_type=DependencyType.BLOCKS,
            )
        )

    return deps


# =============================================================================
# Orchestrator
# =============================================================================


async def generate_beads_from_speckit(
    spec_dir: Path,
    client: BeadClient,
    *,
    dry_run: bool = False,
) -> BeadGenerationResult:
    """Generate beads from a SpecKit specification directory.

    Orchestrates the full pipeline:
    1. Parse tasks.md
    2. Classify and group phases into bead definitions
    3. Enrich definitions with extracted context
    4. Create epic bead
    5. Create work beads as children
    6. Wire dependencies
    7. Sync

    Args:
        spec_dir: Path to the spec directory containing tasks.md.
        client: BeadClient for bd CLI operations.
        dry_run: If True, return definitions without calling bd.

    Returns:
        BeadGenerationResult with created beads and any errors.

    Raises:
        SpecKitParseError: If spec_dir or tasks.md is invalid.
    """
    spec_dir = spec_dir.resolve()
    tasks_path = spec_dir / "tasks.md"

    if not spec_dir.is_dir():
        raise SpecKitParseError(
            f"Spec directory does not exist: {spec_dir}",
            spec_dir=spec_dir,
        )

    if not tasks_path.is_file():
        raise SpecKitParseError(
            f"tasks.md not found in {spec_dir}",
            spec_dir=spec_dir,
        )

    # 1. Parse tasks.md
    logger.info("parsing_tasks", spec_dir=str(spec_dir))
    task_file = await TaskFile.parse_async(tasks_path)

    if not task_file.phases:
        raise SpecKitParseError(
            f"No phases found in {tasks_path}",
            spec_dir=spec_dir,
        )

    # 2. Classify and group phases
    bead_definitions = group_phases_into_beads(task_file.phases)
    logger.info(
        "phases_grouped",
        total_beads=len(bead_definitions),
        phases=len(task_file.phases),
    )

    # 3. Enrich definitions with context
    extractor = SpecKitContextExtractor(spec_dir, task_file)

    # Build epic definition
    epic_title = spec_dir.name
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

    # Dry run: return definitions without creating beads
    if dry_run:
        logger.info("dry_run_complete", beads=len(enriched_definitions) + 1)
        return BeadGenerationResult(
            epic=CreatedBead(bd_id="dry-run-epic", definition=epic_definition),
            work_beads=[
                CreatedBead(bd_id=f"dry-run-{i}", definition=d)
                for i, d in enumerate(enriched_definitions)
            ],
        )

    # 4. Create epic bead
    errors: list[str] = []
    try:
        epic = await client.create_bead(epic_definition)
    except Exception as e:
        logger.error("epic_creation_failed", error=str(e))
        return BeadGenerationResult(errors=[f"Epic creation failed: {e}"])

    # 5. Create work beads as children
    created_map: dict[str, CreatedBead] = {}
    work_beads: list[CreatedBead] = []

    for defn in enriched_definitions:
        try:
            created = await client.create_bead(defn, parent_id=epic.bd_id)
            created_map[defn.title] = created
            work_beads.append(created)
        except Exception as e:
            error_msg = f"Failed to create bead '{defn.title}': {e}"
            logger.error("bead_creation_failed", title=defn.title, error=str(e))
            errors.append(error_msg)

    # 6. Wire dependencies
    tasks_content = tasks_path.read_text(encoding="utf-8")
    dependencies = _compute_dependencies(
        enriched_definitions, created_map, tasks_content
    )

    wired_deps: list[BeadDependency] = []
    for dep in dependencies:
        try:
            await client.add_dependency(dep)
            wired_deps.append(dep)
        except Exception as e:
            error_msg = (
                f"Failed to wire: {dep.blocked_id} blocked-by {dep.blocker_id}: {e}"
            )
            logger.error(
                "dependency_wiring_failed",
                blocker_id=dep.blocker_id,
                blocked_id=dep.blocked_id,
                error=str(e),
            )
            errors.append(error_msg)

    # 7. Sync
    try:
        await client.sync()
    except Exception as e:
        error_msg = f"Failed to sync beads: {e}"
        logger.warning("sync_failed", error=str(e))
        errors.append(error_msg)

    result = BeadGenerationResult(
        epic=epic,
        work_beads=work_beads,
        dependencies=wired_deps,
        errors=errors,
    )

    logger.info(
        "generation_complete",
        total_beads=result.total_beads,
        dependencies=len(wired_deps),
        errors=len(errors),
        success=result.success,
    )

    return result
