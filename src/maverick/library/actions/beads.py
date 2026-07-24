"""Bead-creation and lifecycle actions for workflows.

Every action takes an explicit ``cwd`` so workflows preserve workspace
isolation (CLAUDE.md Architectural Guardrail 7). Workflows resolve
``cwd`` from the active workspace (``ws_cwd``) and thread it through
every call. Defaulting to ``Path.cwd()`` here would silently route bd
writes to whatever directory the maverick CLI was launched in,
bypassing the workspace and producing the kind of duplicate-epic /
project-id-mismatch bugs the airframe migration cleanup
removed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.library.actions.types import (
    BeadCreationResult,
    DependencyWiringResult,
    MarkBeadCompleteResult,
    RemediationBeadsResult,
    SelectNextBeadResult,
)
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.beads.client import BeadClient
    from maverick.workflows.spec_chain.models import AnalyzeFinding

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


def _build_remediation_description(finding: AnalyzeFinding) -> str:
    return (
        f"## Finding\n\n{finding.title}\n\n"
        f"## Category\n\n{finding.category}\n\n"
        f"## Severity Hint\n\n{finding.severity_hint}\n\n"
        f"## Location\n\n{finding.location}\n\n"
        f"## Summary\n\n{finding.summary}\n"
    )


async def _existing_remediation_fingerprints(client: BeadClient) -> set[str]:
    from maverick.workflows.spec_chain.constants import (
        KEY_FINDING_FINGERPRINT,
        SPEC_REMEDIATION_LABEL,
    )

    try:
        candidates = await client.query("type=task")
    except Exception as exc:  # noqa: BLE001 — best-effort idempotency probe
        logger.warning("spec_remediation_fingerprint_query_failed", error=str(exc))
        return set()

    fingerprints: set[str] = set()
    for candidate in candidates:
        try:
            details = await client.show(candidate.id)
        except Exception as exc:  # noqa: BLE001 — one bad bead must not sink the scan
            logger.debug(
                "spec_remediation_fingerprint_show_failed", bead_id=candidate.id, error=str(exc)
            )
            continue
        if SPEC_REMEDIATION_LABEL in (details.labels or []):
            fingerprint = (details.state or {}).get(KEY_FINDING_FINGERPRINT)
            if fingerprint:
                fingerprints.add(fingerprint)
    return fingerprints


async def create_remediation_beads(
    findings: Sequence[AnalyzeFinding],
    *,
    cwd: Path | str,
) -> RemediationBeadsResult:
    """Create one standalone ``spec-remediation`` bead per analyze finding (R6).

    Beads are created unparented (the feature's epic doesn't exist until
    ``refuel --speckit`` runs) and idempotent per
    ``finding_fingerprint`` — re-running analyze never duplicates a bead
    for the same finding. Best-effort per finding (Principle IV): one
    finding's bd failure is logged and excluded from the result, never
    raised, so it can't sink the others or the analyze step itself.

    Args:
        findings: Analyze findings to convert into remediation beads.
        cwd: Workspace directory whose ``.beads/`` receives the writes.
            Required — see module docstring.

    Returns:
        RemediationBeadsResult.
    """
    from maverick.beads.client import BeadClient
    from maverick.beads.models import BeadCategory, BeadDefinition, BeadType
    from maverick.workflows.spec_chain.constants import (
        KEY_FINDING_FINGERPRINT,
        KEY_REMEDIATION_SOURCE,
        KEY_SPECKIT_FEATURE,
        REMEDIATION_SOURCE_ANALYZE,
        SPEC_REMEDIATION_LABEL,
    )

    if not findings:
        return RemediationBeadsResult(
            created_bead_ids=(), skipped_duplicate_fingerprints=(), errors=()
        )

    client = BeadClient(cwd=Path(cwd))
    existing_fingerprints = await _existing_remediation_fingerprints(client)

    created_ids: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for finding in findings:
        if finding.fingerprint in existing_fingerprints:
            skipped.append(finding.fingerprint)
            continue
        try:
            definition = BeadDefinition(
                title=f"Spec remediation: {finding.title[:150]}",
                bead_type=BeadType.TASK,
                # Advisory by design — severity_hint lives in the
                # description, not priority (FR-012: findings never block).
                priority=2,
                category=BeadCategory.CLEANUP,
                description=_build_remediation_description(finding),
                labels=[SPEC_REMEDIATION_LABEL],
            )
            created = await client.create_bead(definition, parent_id=None)
            await client.set_state(
                created.bd_id,
                {
                    KEY_SPECKIT_FEATURE: finding.feature_dir,
                    KEY_REMEDIATION_SOURCE: REMEDIATION_SOURCE_ANALYZE,
                    KEY_FINDING_FINGERPRINT: finding.fingerprint,
                },
                reason="spec-chain analyze finding",
            )
            created_ids.append(created.bd_id)
            existing_fingerprints.add(finding.fingerprint)
        except Exception as exc:  # noqa: BLE001 — one finding's failure must not sink the rest
            logger.warning(
                "spec_remediation_bead_creation_failed", title=finding.title, error=str(exc)
            )
            errors.append(f"{finding.title}: {exc}")

    return RemediationBeadsResult(
        created_bead_ids=tuple(created_ids),
        skipped_duplicate_fingerprints=tuple(skipped),
        errors=tuple(errors),
    )


async def adopt_remediation_bead(
    client: BeadClient,
    *,
    bead_id: str,
    epic_id: str,
) -> None:
    """Adopt a standalone ``spec-remediation`` bead under *epic_id* (R6).

    Fallback primitive: no ``bd update --parent`` exists (verified
    against T001's research — no live ``bd`` install to confirm a real
    parent-reassignment command, and ``BeadClient`` exposes no such
    method today). Wires a ``DISCOVERED_FROM`` dependency edge from the
    epic (provenance/grouping only — does not affect readiness, unlike
    ``BLOCKS``) plus the ``adopted_by_epic`` state stamp that callers use
    for the idempotency check ("already adopted" — see
    ``SpeckitRefuelWorkflow``'s post-ingest adoption step).

    Args:
        client: BeadClient bound to the user's checkout.
        bead_id: The remediation bead to adopt.
        epic_id: The epic to adopt it under.

    Raises:
        Exception: Any bd-layer failure — callers isolate per-bead
            failures (Principle IV); this primitive itself does not.
    """
    from maverick.beads.models import BeadDependency, DependencyType
    from maverick.workflows.spec_chain.constants import KEY_ADOPTED_BY_EPIC

    await client.add_dependency(
        BeadDependency(
            blocker_id=epic_id,
            blocked_id=bead_id,
            dep_type=DependencyType.DISCOVERED_FROM,
        )
    )
    await client.set_state(
        bead_id,
        {KEY_ADOPTED_BY_EPIC: epic_id},
        reason=f"adopted under epic {epic_id}",
    )
