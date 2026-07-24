"""SpeckitRefuelWorkflow — deterministic Spec Kit ingestion pipeline.

Bypasses Burr, RefuelSquadron, and the actor stack entirely (research D1):
a plain sequential :class:`PythonWorkflow` that parses tasks.md/spec.md
with a fixed grammar and talks to ``bd`` directly via :class:`BeadClient`.
Zero model invocations unless ``--enrich`` is passed (FR-010).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from typing import Any

from maverick.exceptions import WorkflowError
from maverick.logging import get_logger
from maverick.speckit.build import IngestionPlan, build_ingestion_plan
from maverick.speckit.detect import SUPPORTED_SPECKIT_RANGE, check_template_compatibility
from maverick.speckit.errors import NothingToIngestError, SpeckitError, UnsupportedTemplateError
from maverick.speckit.models import SpeckitFeature
from maverick.speckit.parser import parse_spec_md, parse_tasks_md
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.refuel_speckit.constants import (
    CHAIN_EPIC,
    CHECK_TEMPLATE,
    COMMIT_OUTPUT,
    CREATE_BEADS,
    ENRICH,
    PARSE_ARTIFACTS,
    PLAN_INGESTION,
    RECORD_RUN,
    RESOLVE_FEATURE,
    WIRE_DEPS,
    WORKFLOW_NAME,
)
from maverick.workflows.refuel_speckit.models import SpeckitRefuelResult

logger = get_logger(__name__)

_TASK_ID_RE = re.compile(r"^T\d{3,}$")


def _resolve_bead_id(identifier: str, created_map: dict[str, str]) -> str:
    """Resolve an edge endpoint to a bead ID.

    Edge endpoints are either a Spec Kit task ID (resolved via
    *created_map*, populated by this run's own bead creation) or an
    already-resolved bead ID from a prior run (delta edges) — passed
    through unchanged.
    """
    if _TASK_ID_RE.match(identifier) and identifier in created_map:
        return created_map[identifier]
    return identifier


class SpeckitRefuelWorkflow(PythonWorkflow):
    """Deterministic Spec Kit ingestion: parse tasks.md, create beads, wire deps.

    Args:
        config: Project configuration (MaverickConfig).
        checkpoint_store: Optional checkpoint persistence backend.
        workflow_name: Identifier for this workflow instance.
    """

    def __init__(self, **kwargs: Any) -> None:
        if "workflow_name" not in kwargs:
            kwargs["workflow_name"] = WORKFLOW_NAME
        super().__init__(**kwargs)

    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the Spec Kit ingestion pipeline.

        Args:
            inputs: Required: ``feature_dir`` (str, already resolved by the
                CLI), ``cwd`` (str). Optional: ``dry_run`` (bool),
                ``enrich`` (bool), ``auto_commit`` (bool).

        Returns:
            Output dict matching :meth:`SpeckitRefuelResult.to_dict`.
        """
        feature_dir_str: str = inputs.get("feature_dir", "")
        cwd_str: str = inputs.get("cwd", "")
        if not feature_dir_str:
            raise WorkflowError("'feature_dir' input is required")
        if not cwd_str:
            raise WorkflowError("'cwd' input is required")

        cwd = Path(cwd_str)
        dry_run: bool = bool(inputs.get("dry_run", False))
        enrich: bool = bool(inputs.get("enrich", False))
        auto_commit: bool = bool(inputs.get("auto_commit", False))
        warnings: list[str] = []

        # ------------------------------------------------------------
        # Step 1: Resolve feature
        # ------------------------------------------------------------
        await self.emit_step_started(RESOLVE_FEATURE, display_label="Resolving feature")
        feature_dir = Path(feature_dir_str)
        if not (feature_dir / "spec.md").is_file() or not (feature_dir / "tasks.md").is_file():
            await self.emit_step_failed(
                RESOLVE_FEATURE, f"{feature_dir} is not a Spec Kit feature directory"
            )
            raise SpeckitError(f"{feature_dir} is missing spec.md and/or tasks.md")
        feature_name = feature_dir.name
        await self.emit_output(RESOLVE_FEATURE, f"Using Spec Kit feature: {feature_dir}")
        await self.emit_step_completed(RESOLVE_FEATURE, output={"feature_dir": str(feature_dir)})

        # ------------------------------------------------------------
        # Step 2: Check template compatibility
        # ------------------------------------------------------------
        await self.emit_step_started(CHECK_TEMPLATE, display_label="Checking template version")
        compat = check_template_compatibility(cwd)
        if compat.status == "unsupported":
            await self.emit_step_failed(
                CHECK_TEMPLATE,
                f"unsupported template version {compat.vendored_version}, "
                f"supported: {compat.supported_range}",
            )
            raise UnsupportedTemplateError(
                f"unsupported template version {compat.vendored_version}, "
                f"supported: {compat.supported_range}",
                found_version=compat.vendored_version or "",
                supported_range=compat.supported_range,
            )
        if compat.status == "unknown":
            msg = (
                "Spec Kit template version unknown "
                f"(supported range: {SUPPORTED_SPECKIT_RANGE}) — proceeding structurally"
            )
            warnings.append(msg)
            await self.emit_output(CHECK_TEMPLATE, msg, level="warning")
        await self.emit_step_completed(CHECK_TEMPLATE, output={"status": compat.status})

        # ------------------------------------------------------------
        # Step 3: Parse artifacts
        # ------------------------------------------------------------
        await self.emit_step_started(PARSE_ARTIFACTS, display_label="Parsing Spec Kit artifacts")
        try:
            tasks_content = await asyncio.to_thread(
                (feature_dir / "tasks.md").read_text, encoding="utf-8"
            )
            spec_content = await asyncio.to_thread(
                (feature_dir / "spec.md").read_text, encoding="utf-8"
            )
        except OSError as exc:
            await self.emit_step_failed(PARSE_ARTIFACTS, str(exc))
            raise SpeckitError(f"failed to read Spec Kit artifacts: {exc}") from exc

        phases, story_deps = parse_tasks_md(tasks_content, file=str(feature_dir / "tasks.md"))
        parsed_spec = parse_spec_md(spec_content, file=str(feature_dir / "spec.md"))
        feature = SpeckitFeature(
            feature_dir=feature_dir,
            feature_name=feature_name,
            spec=parsed_spec,
            phases=phases,
            story_deps=story_deps,
            has_plan=(feature_dir / "plan.md").is_file(),
        )
        total_tasks = sum(len(p.tasks) for p in phases)
        await self.emit_output(
            PARSE_ARTIFACTS,
            f"Parsed {len(phases)} phases, {total_tasks} tasks",
        )
        await self.emit_step_completed(
            PARSE_ARTIFACTS, output={"phase_count": len(phases), "task_count": total_tasks}
        )

        # ------------------------------------------------------------
        # Delta lookup: find an existing open epic for this feature.
        # ------------------------------------------------------------
        from maverick.beads.client import BeadClient

        client = BeadClient(cwd=cwd)
        existing_epic_id, existing_task_map = await self._find_existing_epic(client, feature_name)

        # ------------------------------------------------------------
        # Step 4: Plan ingestion
        # ------------------------------------------------------------
        await self.emit_step_started(PLAN_INGESTION, display_label="Planning ingestion")
        try:
            plan, plan_warnings = build_ingestion_plan(
                feature,
                existing_epic_id=existing_epic_id,
                existing_task_map=existing_task_map,
            )
        except NothingToIngestError as exc:
            await self.emit_step_failed(PLAN_INGESTION, str(exc))
            raise
        warnings.extend(plan_warnings)
        for w in plan_warnings:
            await self.emit_output(PLAN_INGESTION, w, level="warning")
        await self.emit_output(
            PLAN_INGESTION,
            f"{len(plan.new_tasks)} new, {len(plan.skipped_completed)} completed, "
            f"{len(plan.skipped_existing)} already ingested",
        )
        await self.emit_step_completed(
            PLAN_INGESTION,
            output={
                "new_tasks": len(plan.new_tasks),
                "skipped_completed": len(plan.skipped_completed),
                "skipped_existing": len(plan.skipped_existing),
                "edges": len(plan.edges),
            },
        )

        delta_run = existing_epic_id is not None

        # Delta no-op: nothing new to create, but not an error.
        if not plan.new_tasks:
            await self.emit_step_started(RECORD_RUN, display_label="Recording run")
            if not dry_run and existing_epic_id:
                await self._record_run(cwd, feature_name, existing_epic_id, "refueled")
            await self.emit_output(
                RECORD_RUN,
                f"No new tasks to ingest for {feature_name} (epic {existing_epic_id} up to date).",
            )
            await self.emit_step_completed(RECORD_RUN, output={"created": 0})
            result = SpeckitRefuelResult(
                feature_name=feature_name,
                epic_id=existing_epic_id or "",
                skipped_completed=plan.skipped_completed,
                skipped_existing=plan.skipped_existing,
                delta_run=delta_run,
                dry_run=dry_run,
                warnings=tuple(warnings),
            )
            return result.to_dict()

        # ------------------------------------------------------------
        # Step 5 (optional): Enrichment
        # ------------------------------------------------------------
        enriched = False
        if enrich:
            plan, enrich_warning = await self._run_enrichment(plan, cwd=cwd)
            if enrich_warning:
                warnings.append(enrich_warning)
            else:
                enriched = True

        # ------------------------------------------------------------
        # Step 6: Create beads
        # ------------------------------------------------------------
        await self.emit_step_started(CREATE_BEADS, display_label="Creating beads")
        created_map: dict[str, str] = {}
        epic_id: str
        if dry_run:
            epic_id = existing_epic_id or "dry-run-epic"
            for i, pb in enumerate(plan.new_tasks):
                created_map[pb.task_id] = f"dry-run-{i}"
        else:
            if plan.epic is not None:
                try:
                    created_epic = await client.create_bead(plan.epic.definition)
                except Exception as exc:
                    await self.emit_step_failed(CREATE_BEADS, str(exc))
                    raise SpeckitError(f"epic creation failed: {exc}") from exc
                epic_id = created_epic.bd_id
            else:
                epic_id = existing_epic_id or ""

            for pb in plan.new_tasks:
                try:
                    created = await client.create_bead(pb.definition, parent_id=epic_id)
                except Exception as exc:
                    await self.emit_step_failed(
                        CREATE_BEADS,
                        f"bead creation failed after creating {list(created_map.values())}: {exc}",
                    )
                    raise SpeckitError(
                        f"bead creation failed partway through (created: "
                        f"{list(created_map.values())}): {exc}"
                    ) from exc
                created_map[pb.task_id] = created.bd_id

        await self.emit_output(
            CREATE_BEADS,
            f"{'Would create' if dry_run else 'Created'} epic {epic_id} + "
            f"{len(plan.new_tasks)} task beads",
        )
        if dry_run:
            for pb in plan.new_tasks:
                blockers = [blocker for blocker, blocked in plan.edges if blocked == pb.task_id]
                blocker_text = ", ".join(blockers) if blockers else "none"
                phase = pb.state.get("speckit_phase", "?")
                parallel_marker = " [P]" if pb.state.get("speckit_parallel") == "true" else ""
                await self.emit_output(
                    CREATE_BEADS,
                    f"{pb.task_id}: {pb.definition.title}{parallel_marker} "
                    f"(phase {phase}, blocked by: {blocker_text})",
                )
            if plan.skipped_completed:
                await self.emit_output(
                    CREATE_BEADS,
                    f"Skipped (completed): {', '.join(plan.skipped_completed)}",
                )
            if plan.skipped_existing:
                await self.emit_output(
                    CREATE_BEADS,
                    f"Skipped (already ingested): {', '.join(plan.skipped_existing)}",
                )
            await self.emit_output(CREATE_BEADS, "Dry run — no beads created.")
        await self.emit_step_completed(
            CREATE_BEADS, output={"epic_id": epic_id, "created": list(created_map.values())}
        )

        # ------------------------------------------------------------
        # Step 7: Provenance state (skipped on dry-run)
        # ------------------------------------------------------------
        if not dry_run:
            if plan.epic is not None:
                await client.set_state(epic_id, plan.epic.state)
            for pb in plan.new_tasks:
                await client.set_state(created_map[pb.task_id], pb.state)

        # ------------------------------------------------------------
        # Step 8: Wire dependencies
        # ------------------------------------------------------------
        await self.emit_step_started(WIRE_DEPS, display_label="Wiring dependencies")
        wired_count = 0
        if not dry_run:
            from maverick.beads.models import BeadDependency

            for blocker, blocked in plan.edges:
                blocker_id = _resolve_bead_id(blocker, created_map)
                blocked_id = _resolve_bead_id(blocked, created_map)
                try:
                    await client.add_dependency(
                        BeadDependency(blocker_id=blocker_id, blocked_id=blocked_id)
                    )
                    wired_count += 1
                except Exception as exc:
                    logger.warning(
                        "speckit_dependency_wiring_failed",
                        blocker_id=blocker_id,
                        blocked_id=blocked_id,
                        error=str(exc),
                    )
                    warnings.append(f"failed to wire {blocker_id} -> {blocked_id}: {exc}")
        else:
            wired_count = len(plan.edges)
        await self.emit_output(WIRE_DEPS, f"Wired {wired_count} dependency edges")
        await self.emit_step_completed(WIRE_DEPS, output={"wired": wired_count})

        # ------------------------------------------------------------
        # Step 9: Chain epic behind existing open epics (fresh runs only)
        # ------------------------------------------------------------
        if plan.epic is not None and not dry_run:
            await self.emit_step_started(CHAIN_EPIC, display_label="Chaining epic")
            chained_behind = await self._chain_epic(client, epic_id)
            if chained_behind:
                await self.emit_output(
                    CHAIN_EPIC,
                    f"New epic blocked by {chained_behind} — "
                    "tasks start when prior epic completes",
                )
            await self.emit_step_completed(CHAIN_EPIC, output={"blocked_by": chained_behind})

        # ------------------------------------------------------------
        # Step 10: Record run metadata (skipped on dry-run)
        # ------------------------------------------------------------
        if not dry_run:
            await self._record_run(cwd, feature_name, epic_id, "refueled")

        # ------------------------------------------------------------
        # Step 11 (optional): Auto-commit
        # ------------------------------------------------------------
        if auto_commit and not dry_run:
            await self._commit_output(feature_name)

        result = SpeckitRefuelResult(
            feature_name=feature_name,
            epic_id=epic_id,
            created_bead_ids=tuple(created_map.values()),
            skipped_completed=plan.skipped_completed,
            skipped_existing=plan.skipped_existing,
            edge_count=wired_count,
            delta_run=delta_run,
            dry_run=dry_run,
            enriched=enriched,
            warnings=tuple(warnings),
        )
        return result.to_dict()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _find_existing_epic(
        self,
        client: Any,
        feature_name: str,
    ) -> tuple[str | None, dict[str, str]]:
        """Find the open epic (if any) whose ``speckit_feature`` state matches.

        Returns:
            ``(epic_id, existing_task_map)`` — both empty/None on a fresh run.

        Raises:
            SpeckitError: More than one open epic claims this feature (corrupt state).
        """
        try:
            epics = await client.query("type=epic AND status=open")
        except Exception as exc:
            logger.debug("speckit_epic_query_failed", error=str(exc))
            return None, {}

        matches = []
        for epic_summary in epics:
            try:
                details = await client.show(epic_summary.id)
            except Exception:
                continue
            if details.state.get("speckit_feature") == feature_name:
                matches.append(details)

        if not matches:
            return None, {}
        if len(matches) > 1:
            ids = ", ".join(d.id for d in matches)
            raise SpeckitError(f"multiple open epics claim speckit_feature={feature_name}: {ids}")

        epic_details = matches[0]
        existing_task_map: dict[str, str] = {}
        try:
            children = await client.children(epic_details.id)
        except Exception:
            children = []
        for child in children:
            try:
                child_details = await client.show(child.id)
            except Exception:
                continue
            task_id = child_details.state.get("speckit_task_id")
            if task_id:
                existing_task_map[task_id] = child.id

        return epic_details.id, existing_task_map

    async def _chain_epic(self, client: Any, new_epic_id: str) -> str | None:
        """Chain *new_epic_id* behind the tail of existing open epics.

        Tail selection is deterministic: open epics are sorted by their
        ``speckit_feature`` NNN prefix (epics without one — flight-plan
        runs — sort after all NNN-prefixed epics, in bd's own query
        order) instead of relying on unspecified ``bd query`` ordering
        (research R8). Additionally wires ``blocks`` edges from any open
        high-severity assumption entries owned by earlier specs onto the
        new epic, so refuel-time chaining catches entries recorded before
        this spec existed (the other temporal order is handled at
        recording time by ``ledger.next_chained_epic``).
        """
        from maverick.assumptions.ledger import open_high_entries_before
        from maverick.assumptions.models import nnn_prefix
        from maverick.beads.models import BeadDependency, DependencyType

        try:
            all_beads = await client.query("type=epic AND status=open")
        except Exception as exc:
            logger.warning("speckit_chain_epic_query_failed", error=str(exc))
            all_beads = []
        existing_epics = [b for b in all_beads if b.id != new_epic_id]

        tail_epic_id: str | None = None
        if existing_epics:
            ordered: list[tuple[tuple[int, int], Any]] = []
            for idx, epic in enumerate(existing_epics):
                prefix: int | None = None
                try:
                    details = await client.show(epic.id)
                    prefix = nnn_prefix(details.state.get("speckit_feature", ""))
                except Exception:
                    prefix = None
                sort_key = (0, prefix) if prefix is not None else (1, idx)
                ordered.append((sort_key, epic))
            ordered.sort(key=lambda pair: pair[0])
            tail_epic_id = ordered[-1][1].id
            try:
                await client.add_dependency(
                    BeadDependency(blocker_id=tail_epic_id, blocked_id=new_epic_id)
                )
            except Exception as exc:
                logger.warning("speckit_chain_epic_failed", error=str(exc))
                tail_epic_id = None

        try:
            blocking_entries = await open_high_entries_before(client, epic_id=new_epic_id)
        except Exception as exc:
            logger.warning("speckit_chain_epic_assumption_query_failed", error=str(exc))
            blocking_entries = ()
        for entry in blocking_entries:
            try:
                await client.add_dependency(
                    BeadDependency(
                        blocker_id=entry.bead_id,
                        blocked_id=new_epic_id,
                        dep_type=DependencyType.BLOCKS,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "speckit_chain_epic_assumption_block_failed",
                    entry_id=entry.bead_id,
                    error=str(exc),
                )

        return tail_epic_id

    async def _record_run(self, cwd: Path, feature_name: str, epic_id: str, status: str) -> None:
        from maverick.runway.run_metadata import RunMetadata, write_metadata

        run_id = uuid.uuid4().hex[:8]
        run_dir = cwd / ".maverick" / "runs" / run_id
        meta = RunMetadata(
            run_id=run_id,
            plan_name=feature_name,
            epic_id=epic_id,
            status=status,
        )
        await asyncio.to_thread(write_metadata, run_dir, meta)

    async def _commit_output(self, feature_name: str) -> None:
        from maverick.library.actions.jj import jj_snapshot_changes

        await self.emit_step_started(COMMIT_OUTPUT, display_label="Committing refuel output")
        try:
            snap = await jj_snapshot_changes(message=f"chore: refuel {feature_name} (speckit)")
            if snap.success and snap.committed:
                sha_preview = (snap.commit_sha or "")[:8]
                await self.emit_output(COMMIT_OUTPUT, f"Committed refuel output ({sha_preview})")
                await self.emit_step_completed(
                    COMMIT_OUTPUT, {"committed": True, "commit_sha": snap.commit_sha}
                )
            elif snap.success:
                await self.emit_output(
                    COMMIT_OUTPUT, "Working directory clean — nothing to commit"
                )
                await self.emit_step_completed(COMMIT_OUTPUT, {"committed": False})
            else:
                await self.emit_output(COMMIT_OUTPUT, snap.error or "commit failed", level="error")
                await self.emit_step_completed(
                    COMMIT_OUTPUT, {"committed": False, "error": snap.error}
                )
        except Exception as exc:
            await self.emit_step_failed(COMMIT_OUTPUT, str(exc))
            logger.warning("speckit_auto_commit_failed", error=str(exc))

    async def _run_enrichment(
        self,
        plan: IngestionPlan,
        *,
        cwd: Path,
    ) -> tuple[IngestionPlan, str | None]:
        """Attach model-supplied verification commands to new task beads.

        Runs a single batched call so cost stays O(1) per run (research
        D9). Any failure degrades to a warning — ingestion proceeds
        unenriched (FR-011). Nothing here imports agent/runtime
        machinery unless this method actually runs (FR-010).

        Returns:
            ``(plan, warning)`` — *plan* is unchanged (with augmented
            ``## Verification`` sections) on success, or the original
            *plan* plus a warning message on failure.
        """
        await self.emit_step_started(ENRICH, display_label="Enriching verification commands")
        applied = 0
        try:
            from maverick.agents.personas import SpeckitEnrichmentAgent
            from maverick.config import load_config
            from maverick.runtime.agent_factory import runtime_for_agent
            from maverick.speckit.enrichment import (
                apply_enrichment,
                build_enrichment_prompt,
                parse_enrichment_response,
            )

            config = load_config()
            runtime, _ = runtime_for_agent("generate", agents_config=config.agents)
            prompt = build_enrichment_prompt(plan.new_tasks)
            async with SpeckitEnrichmentAgent(runtime=runtime, cwd=str(cwd)) as agent:
                response_text = await agent.enrich(prompt)
            commands_by_task = parse_enrichment_response(response_text)
            enriched_plan = apply_enrichment(plan, commands_by_task)
            # Count tasks that actually received commands — a model may
            # return commands for only a subset of the requested task IDs.
            applied = sum(1 for pb in plan.new_tasks if commands_by_task.get(pb.task_id))
        except Exception as exc:
            logger.warning("speckit_enrichment_failed", error=str(exc))
            warning = f"enrichment failed (non-fatal): {exc}"
            await self.emit_output(ENRICH, warning, level="warning")
            await self.emit_step_completed(ENRICH, output={"enriched": False})
            return plan, warning

        await self.emit_output(ENRICH, f"Enriched {applied} of {len(plan.new_tasks)} task beads")
        await self.emit_step_completed(ENRICH, output={"enriched": True, "applied": applied})
        return enriched_plan, None


__all__ = ["SpeckitRefuelWorkflow"]
