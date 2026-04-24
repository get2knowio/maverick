"""RefuelMaverickWorkflow — flight plan decomposition pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from maverick.exceptions import WorkflowError
from maverick.flight.loader import FlightPlanFile
from maverick.flight.serializer import serialize_work_unit
from maverick.library.actions.beads import create_beads, wire_dependencies
from maverick.library.actions.cross_plan_deps import (
    resolve_plan_epic_ids,
    wire_cross_plan_dependencies,
)
from maverick.library.actions.decompose import (
    convert_specs_to_work_units,
    gather_codebase_context,
)
from maverick.library.actions.open_bead_analysis import (
    OpenBeadAnalysisResult,
    analyze_open_beads,
)
from maverick.logging import get_logger
from maverick.types import StepType
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.refuel_maverick.constants import (
    ANALYZE_OPEN_BEADS,
    BRIEFING,
    CREATE_BEADS,
    DECOMPOSE,
    DERIVE_VERIFICATION,
    DETAIL_SESSION_MAX_TURNS,
    FIX_SESSION_MAX_TURNS,
    GATHER_CONTEXT,
    PARSE_FLIGHT_PLAN,
    WIRE_CROSS_PLAN_DEPS,
    WIRE_DEPS,
    WORKFLOW_NAME,
    WRITE_WORK_UNITS,
)
from maverick.workflows.refuel_maverick.models import RefuelMaverickResult

logger = get_logger(__name__)

#: Bumped when the on-disk cache layout changes so stale caches with
#: the old schema get invalidated instead of silently misinterpreted.
BRIEFING_CACHE_SCHEMA_VERSION = 1
OUTLINE_CACHE_SCHEMA_VERSION = 1


def _briefing_cache_key(
    flight_plan_content: str,
    codebase_context: Any,
    briefing_prompt: str,
) -> str:
    """Stable fingerprint of every input the briefing reasoned about.

    Changing any of ``flight_plan_content``, ``codebase_context`` (even
    whitespace inside gathered files), or ``briefing_prompt`` drifts the
    hash and invalidates the cache. Trimmed to 16 hex chars — collisions
    on a local cache file are not a threat model we care about, and the
    shorter key keeps log lines scannable.
    """
    h = hashlib.sha256()
    h.update(flight_plan_content.encode("utf-8"))
    h.update(b"\x00")
    h.update(json.dumps(codebase_context, default=str, sort_keys=True).encode("utf-8"))
    h.update(b"\x00")
    h.update(briefing_prompt.encode("utf-8"))
    return h.hexdigest()[:16]


def _outline_cache_key(
    flight_plan_content: str,
    verification_properties: str,
    briefing_payloads: dict[str, Any] | None,
) -> str:
    """Stable fingerprint of the outline's inputs.

    The outline is seeded from the briefing + flight plan + verification
    properties, so any of those changing must invalidate the outline.
    """
    h = hashlib.sha256()
    h.update(flight_plan_content.encode("utf-8"))
    h.update(b"\x00")
    h.update(verification_properties.encode("utf-8"))
    h.update(b"\x00")
    h.update(json.dumps(briefing_payloads or {}, default=str, sort_keys=True).encode("utf-8"))
    return h.hexdigest()[:16]


class RefuelMaverickWorkflow(PythonWorkflow):
    """Workflow that decomposes a Maverick Flight Plan into work units and beads.

    Pipeline:
    1. parse_flight_plan - Parse flight plan file via FlightPlanFile.aload()
    2. gather_context - Read in-scope files from codebase
    3. decompose - Agent decomposes flight plan into work units (via StepExecutor)
    4. validate - Validate dependency graph (acyclic), unique IDs, SC coverage
    5. write_work_units - Write work unit files to .maverick/plans/<name>/
    6. create_beads - Create epic + task beads via BeadClient
    7. wire_deps - Wire bead dependencies from depends_on fields

    Args:
        config: Project configuration (MaverickConfig).
        registry: Component registry for action/agent dispatch.
        checkpoint_store: Optional checkpoint persistence backend.
        workflow_name: Identifier for this workflow instance.
    """

    def __init__(self, **kwargs: Any) -> None:
        if "workflow_name" not in kwargs:
            kwargs["workflow_name"] = WORKFLOW_NAME
        super().__init__(**kwargs)

    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the refuel-maverick pipeline with post-run audit report.

        Delegates to :meth:`_run_impl` and writes a ``RefuelReport`` to the
        run directory regardless of success or failure — mirroring the
        fly workflow's per-bead ``fly-report.json`` audit artifact
        (PATTERNS.md §13).
        """
        import time as _time
        from datetime import UTC, datetime

        from maverick.workflows.refuel_maverick.refuel_report import (
            RefuelReport,
            write_refuel_report,
        )

        ctx: dict[str, Any] = {}
        started_at = datetime.now(tz=UTC).isoformat()
        start_time = _time.monotonic()
        error_msg: str | None = None
        try:
            return await self._run_impl(inputs, ctx=ctx)
        except Exception as exc:
            error_msg = str(exc)
            raise
        finally:
            run_id = ctx.get("run_id", "unknown")
            run_dir = ctx.get("run_dir", Path.cwd() / ".maverick" / "runs" / run_id)
            report = RefuelReport(
                plan_name=ctx.get("plan_name", ""),
                flight_plan_path=inputs.get("flight_plan_path", ""),
                run_id=run_id,
                outcome="refueled" if error_msg is None else "failed",
                started_at=started_at,
                completed_at=datetime.now(tz=UTC).isoformat(),
                duration_seconds=_time.monotonic() - start_time,
                skip_briefing=bool(inputs.get("skip_briefing", False)),
                phases_completed=[r.name for r in self._step_results if r.success],
                work_units_count=ctx.get("work_units_count", 0),
                fix_rounds=ctx.get("fix_rounds", 0),
                epic_id=ctx.get("epic_id"),
                work_bead_ids=ctx.get("bead_ids", []),
                error=error_msg,
            )
            try:
                await write_refuel_report(report, run_dir)
            except Exception as write_exc:
                logger.warning("refuel_report.write_failed", error=str(write_exc))

    async def _run_impl(self, inputs: dict[str, Any], *, ctx: dict[str, Any]) -> dict[str, Any]:
        """Execute the refuel-maverick pipeline.

        Args:
            inputs: Workflow inputs. Required: ``flight_plan_path`` (str).
            ctx: Accumulator dict written by the impl as phase state becomes
                known (plan_name, run_id, run_dir, work_units_count,
                fix_rounds, epic_id, bead_ids). Consumed by ``_run`` to
                build the post-run ``RefuelReport`` on both success and
                failure paths.

        Returns:
            Output dict matching RefuelMaverickResult.to_dict() contract.

        Raises:
            WorkflowError: If ``flight_plan_path`` is not provided in inputs.
        """
        flight_plan_path_str: str = inputs.get("flight_plan_path", "")
        if not flight_plan_path_str:
            raise WorkflowError("'flight_plan_path' input is required")
        skip_briefing: bool = bool(inputs.get("skip_briefing", False))

        flight_plan_path = Path(flight_plan_path_str)

        # Generate run_id and create run directory
        import uuid as _uuid

        from maverick.runway.run_metadata import RunMetadata, write_metadata

        run_id = _uuid.uuid4().hex[:8]
        run_dir = Path.cwd() / ".maverick" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        ctx["run_id"] = run_id
        ctx["run_dir"] = run_dir

        # ------------------------------------------------------------------
        # Step 1: Parse flight plan
        # ------------------------------------------------------------------
        await self.emit_step_started(PARSE_FLIGHT_PLAN, display_label="Parsing flight plan")
        try:
            flight_plan = await FlightPlanFile.aload(flight_plan_path)
        except Exception as exc:
            await self.emit_step_failed(PARSE_FLIGHT_PLAN, str(exc))
            raise
        await self.emit_output(
            PARSE_FLIGHT_PLAN,
            f'Parsed flight plan "{flight_plan.name}" '
            f"({len(flight_plan.success_criteria)} success criteria, "
            f"{len(flight_plan.scope.in_scope)} in-scope files)",
        )
        await self.emit_step_completed(PARSE_FLIGHT_PLAN, output=flight_plan.to_dict())
        ctx["plan_name"] = flight_plan.name

        # Write initial run metadata
        run_meta = RunMetadata(
            run_id=run_id,
            plan_name=flight_plan.name,
            status="refueling",
        )
        write_metadata(run_dir, run_meta)

        # ------------------------------------------------------------------
        # Step 2: Gather codebase context
        # ------------------------------------------------------------------
        await self.emit_step_started(GATHER_CONTEXT, display_label="Gathering context")
        try:
            plan_dir = flight_plan_path.parent
            cwd = plan_dir.parent.parent.parent if plan_dir.name else None
            codebase_context = await gather_codebase_context(
                in_scope=flight_plan.scope.in_scope,
                cwd=cwd,
            )
        except Exception as exc:
            await self.emit_step_failed(GATHER_CONTEXT, str(exc))
            raise

        total_scope = len(flight_plan.scope.in_scope)
        found_count = len(codebase_context.files)
        missing_count = len(codebase_context.missing_files)
        size_kb = codebase_context.total_size // 1024

        if missing_count > 0 and found_count == 0:
            summary = f"Greenfield project — {total_scope} in-scope files (none exist yet)"
        elif missing_count > 0:
            summary = (
                f"{found_count} of {total_scope} files ({size_kb}KB), "
                f"{missing_count} not found yet"
            )
        else:
            summary = f"{found_count} files ({size_kb}KB)"
        await self.emit_output(GATHER_CONTEXT, summary)
        await self.emit_step_completed(
            GATHER_CONTEXT,
            output={
                "file_count": len(codebase_context.files),
                "missing_count": len(codebase_context.missing_files),
                "total_size": codebase_context.total_size,
            },
        )

        # ------------------------------------------------------------------
        # Step 2.5: Read raw flight plan content (used by briefing + decompose)
        # ------------------------------------------------------------------
        try:
            raw_content = await asyncio.to_thread(flight_plan_path.read_text, "utf-8")
        except Exception as exc:
            raise WorkflowError(f"Cannot read flight plan: {exc}") from exc

        # ------------------------------------------------------------------
        # Step 2.6: Analyze open beads for cross-plan context (non-fatal)
        # ------------------------------------------------------------------
        open_bead_result: OpenBeadAnalysisResult | None = None

        if not skip_briefing:
            await self.emit_step_started(ANALYZE_OPEN_BEADS, display_label="Checking open beads")
            try:
                open_bead_result = await analyze_open_beads(
                    new_plan_in_scope=flight_plan.scope.in_scope,
                    cwd=cwd,
                )
                if open_bead_result.open_epics:
                    await self.emit_output(
                        ANALYZE_OPEN_BEADS,
                        f"Found {len(open_bead_result.open_epics)} open epics, "
                        f"{open_bead_result.overlap_count} file overlaps",
                    )
                else:
                    await self.emit_output(
                        ANALYZE_OPEN_BEADS,
                        "No open epics found",
                    )
                await self.emit_step_completed(
                    ANALYZE_OPEN_BEADS,
                    output=open_bead_result.to_dict(),
                )
            except Exception as exc:
                logger.warning("analyze_open_beads_failed", error=str(exc))
                await self.emit_output(
                    ANALYZE_OPEN_BEADS,
                    f"Skipped (non-fatal): {exc}",
                    level="warning",
                )
                await self.emit_step_completed(ANALYZE_OPEN_BEADS)

        # ------------------------------------------------------------------
        # Step 2b: Briefing Room (optional)
        # ------------------------------------------------------------------
        # ------------------------------------------------------------------
        # Step 2.8: Derive verification properties from acceptance criteria
        # ------------------------------------------------------------------
        # A dedicated agent reads the flight plan's success criteria plus
        # the codebase context and produces executable test assertions.
        # These become the deterministic spec compliance gate during fly.
        verification_properties = getattr(flight_plan, "verification_properties", "")
        _derive_vp = (
            not verification_properties
            and len(flight_plan.success_criteria) > 0
            and len(codebase_context.files) > 0
        )
        if _derive_vp:
            await self.emit_step_started(
                DERIVE_VERIFICATION, display_label="Deriving verification"
            )
            try:
                from maverick.executor import create_default_executor

                _vp_executor = create_default_executor()
                sc_text = "\n".join(
                    f"SC-{i + 1:03d}: {sc.text}"
                    for i, sc in enumerate(flight_plan.success_criteria)
                )
                vp_prompt = (
                    "You are a verification property writer. Read the "
                    "success criteria below and the codebase context, "
                    "then write executable test assertions for each "
                    "criterion that specifies a testable behavior.\n\n"
                    "RULES:\n"
                    "- Reference actual types/functions from the codebase\n"
                    "- Use exact expected values from the criteria\n"
                    "- Each test function must be named verify_scNNN\n"
                    "- Skip structural or subjective criteria\n"
                    "- Output ONE fenced code block with all tests\n\n"
                    f"## Success Criteria\n\n{sc_text}\n\n"
                    f"## Codebase Files\n\n"
                    + "\n".join(f"- {f.path}" for f in codebase_context.files)
                    + "\n"
                )
                try:
                    vp_result = await _vp_executor.execute(
                        step_name=DERIVE_VERIFICATION,
                        agent_name="flight_plan_generator",
                        prompt=vp_prompt,
                    )
                except Exception as vp_exec_err:
                    logger.debug(
                        "vp_executor_failed",
                        error=str(vp_exec_err),
                    )
                    vp_result = None
                if vp_result and vp_result.output:
                    vp_text = str(vp_result.output)
                    if "verify_" in vp_text:
                        verification_properties = vp_text
                        # Write to flight plan file
                        fp_text = await asyncio.to_thread(flight_plan_path.read_text, "utf-8")
                        if "\n## Verification Properties" not in fp_text:
                            fp_text += (
                                "\n\n## Verification Properties\n\n" + verification_properties
                            )
                            await asyncio.to_thread(
                                flight_plan_path.write_text,
                                fp_text,
                                "utf-8",
                            )
                        # Also save to run dir
                        vp_path = run_dir / "verification-properties.txt"
                        await asyncio.to_thread(
                            vp_path.write_text,
                            verification_properties,
                            "utf-8",
                        )
                        await self.emit_output(
                            DERIVE_VERIFICATION,
                            f"Derived verification properties "
                            f"({verification_properties.count('verify_')}"
                            f" tests)",
                        )
            except Exception as exc:
                logger.warning("derive_verification_failed", error=str(exc))
                await self.emit_output(
                    DERIVE_VERIFICATION,
                    f"Verification derivation failed (non-fatal): {exc}",
                    level="warning",
                )
            await self.emit_step_completed(DERIVE_VERIFICATION)

        # Re-read raw content in case VP was appended
        try:
            raw_content = await asyncio.to_thread(flight_plan_path.read_text, "utf-8")
        except OSError as exc:
            logger.warning(
                "refuel.flight_plan_reread_failed",
                path=str(flight_plan_path),
                error=str(exc),
            )

        # Retrieve runway context so the decomposer can learn from past runs
        runway_context_text: str | None = None
        try:
            from maverick.library.actions.runway import retrieve_runway_context

            runway_result = await retrieve_runway_context(
                title=flight_plan.name,
                description=raw_content[:500],
                epic_id="",
                max_passages=5,
                max_context_chars=3000,
                cwd=str(Path.cwd()),
            )
            if runway_result.context_text:
                runway_context_text = runway_result.context_text
        except Exception as exc:
            logger.warning("refuel_runway_context_failed", error=str(exc))

        # ------------------------------------------------------------------
        # Steps 2b-4: Briefing + Decompose + Validate via xoscar supervisor
        # ------------------------------------------------------------------
        decomposition = await self._run_with_xoscar(
            flight_plan=flight_plan,
            raw_content=raw_content,
            codebase_context=codebase_context,
            open_bead_result=open_bead_result,
            runway_context_text=runway_context_text,
            run_dir=run_dir,
            skip_briefing=skip_briefing,
            ctx=ctx,
        )
        briefing_path_str: str | None = None
        suggested_deps: tuple[str, ...] = ()
        if decomposition is not None:
            ctx["work_units_count"] = len(decomposition.work_units)

        # ------------------------------------------------------------------
        # Step 5: Write work units
        # ------------------------------------------------------------------
        await self.emit_step_started(WRITE_WORK_UNITS, display_label="Writing work units")

        if decomposition is None:
            raise WorkflowError("Decomposition loop exited without producing a result")

        # Determine output directory (colocated with flight plan)
        work_units_dir = Path.cwd() / ".maverick" / "plans" / flight_plan.name

        # Convert specs to WorkUnit models
        work_units = convert_specs_to_work_units(
            specs=decomposition.work_units,
            flight_plan_name=flight_plan.name,
        )

        written = 0
        try:
            # Clear existing work unit files (preserve briefing.md)
            await asyncio.to_thread(work_units_dir.mkdir, parents=True, exist_ok=True)
            for existing in work_units_dir.glob("[0-9][0-9][0-9]-*.md"):
                existing.unlink()

            # Write work unit files using {sequence:03d}-{id}.md naming
            # Write to BOTH plans/ (reusable) and runs/ (execution context)
            run_wu_dir = run_dir / "work-units"
            await asyncio.to_thread(run_wu_dir.mkdir, parents=True, exist_ok=True)
            for wu in work_units:
                filename = f"{wu.sequence:03d}-{wu.id}.md"
                content = serialize_work_unit(wu)
                # Plans directory (reusable artifact)
                file_path = work_units_dir / filename
                await asyncio.to_thread(file_path.write_text, content, "utf-8")
                # Run directory (execution context)
                run_file_path = run_wu_dir / filename
                await asyncio.to_thread(run_file_path.write_text, content, "utf-8")
                written += 1
        except Exception as exc:
            await self.emit_step_failed(WRITE_WORK_UNITS, str(exc))
            raise

        await self.emit_output(
            WRITE_WORK_UNITS,
            f"Wrote {written} work unit files to {work_units_dir}",
        )
        await self.emit_step_completed(
            WRITE_WORK_UNITS,
            output={
                "written": written,
                "directory": str(work_units_dir),
            },
        )

        # ------------------------------------------------------------------
        # Steps 6-7: Create beads and wire deps
        # ------------------------------------------------------------------
        bead_result = None
        wire_result = None

        # Step 6: Create beads
        await self.emit_step_started(CREATE_BEADS, display_label="Creating beads")
        try:
            # Build epic and work definitions
            epic_definition = {
                "title": flight_plan.name,
                "bead_type": "epic",
                "priority": 1,
                "category": "foundation",
                "description": flight_plan.objective,
                "phase_names": [],
                "task_ids": [wu.id for wu in work_units],
            }
            work_definitions = [
                {
                    "title": wu.id if len(wu.task) > 200 else wu.task[:200],
                    "bead_type": "task",
                    "priority": 2,
                    "category": "user_story",
                    "description": (wu.instructions[:500] if wu.instructions else wu.task),
                    "phase_names": [],
                    "user_story_id": wu.id,
                    "task_ids": [wu.id],
                }
                for wu in work_units
            ]

            bead_result = await create_beads(
                epic_definition=epic_definition,
                work_definitions=work_definitions,
                dry_run=False,
            )
        except Exception as exc:
            await self.emit_step_failed(CREATE_BEADS, str(exc))
            raise

        # Update run metadata with epic ID
        if bead_result.epic:
            run_meta.epic_id = bead_result.epic["bd_id"]
            run_meta.status = "refueled"
            write_metadata(run_dir, run_meta)
            ctx["epic_id"] = bead_result.epic["bd_id"]
            ctx["bead_ids"] = [b["bd_id"] for b in bead_result.work_beads if b.get("bd_id")]

        # Attach flight_plan_name to the epic for downstream lookup,
        # and wire cross-epic dependencies so new epics wait for
        # existing open epics to complete first.
        if bead_result.epic:
            from maverick.beads.client import BeadClient
            from maverick.beads.models import BeadDependency

            _bead_client = BeadClient(cwd=Path.cwd())
            new_epic_id = bead_result.epic["bd_id"]

            try:
                await _bead_client.set_state(
                    new_epic_id,
                    {"flight_plan_name": flight_plan.name},
                    reason="refuel: link epic to flight plan",
                )
            except Exception as exc:
                logger.warning(
                    "set_flight_plan_state_failed",
                    epic_id=new_epic_id,
                    error=str(exc),
                )

            # Wire cross-epic dependency: new epic is blocked by the
            # most recent existing open epic (the tail of the chain).
            # This serializes epics without creating redundant fan-in
            # dependencies — if A→B already exists, C only needs B→C.
            try:
                all_beads = await _bead_client.query("type=epic AND status=open")
                existing_epics = [b for b in all_beads if b.id != new_epic_id]
                if existing_epics:
                    # Use the last one (most recently created = tail)
                    tail_epic = existing_epics[-1]
                    await _bead_client.add_dependency(
                        BeadDependency(
                            blocker_id=tail_epic.id,
                            blocked_id=new_epic_id,
                        )
                    )
                    logger.info(
                        "cross_epic_dep_wired",
                        blocker=tail_epic.id,
                        blocked=new_epic_id,
                    )
                    await self.emit_output(
                        CREATE_BEADS,
                        f"New epic blocked by {tail_epic.id} "
                        f"— tasks start when prior epic completes",
                    )
            except Exception as exc:
                logger.warning(
                    "cross_epic_dep_failed",
                    epic_id=new_epic_id,
                    error=str(exc),
                )

        if bead_result.errors:
            for error in bead_result.errors:
                await self.emit_output(
                    CREATE_BEADS,
                    error,
                    level="error",
                )
            raise WorkflowError(f"Failed to create {len(bead_result.errors)} beads")

        await self.emit_output(
            CREATE_BEADS,
            f"Created epic: {flight_plan.name}",
        )
        await self.emit_output(
            CREATE_BEADS,
            f"Created {len(bead_result.work_beads)} task beads",
        )
        await self.emit_step_completed(CREATE_BEADS, output=bead_result.to_dict())

        # Step 7: Wire dependencies
        await self.emit_step_started(WIRE_DEPS, display_label="Wiring dependencies")
        dep_pairs: list[list[str]] = []
        for wu in work_units:
            for dep_id in wu.depends_on:
                dep_pairs.append([wu.id, dep_id])
        extracted_deps = json.dumps(dep_pairs) if dep_pairs else ""

        try:
            wire_result = await wire_dependencies(
                work_definitions=work_definitions,
                created_map=bead_result.created_map,
                tasks_content=f"# Flight Plan: {flight_plan.name}\n",
                extracted_deps=extracted_deps,
                dry_run=False,
            )
        except Exception as exc:
            await self.emit_step_failed(WIRE_DEPS, str(exc))
            raise

        await self.emit_output(
            WIRE_DEPS,
            f"Wired {len(wire_result.dependencies)} dependencies",
        )
        await self.emit_step_completed(WIRE_DEPS, output=wire_result.to_dict())

        # ------------------------------------------------------------------
        # Step 8: Wire cross-plan epic dependencies
        # ------------------------------------------------------------------
        cross_plan_result = None

        # Merge explicit depends_on_plans with suggested cross-plan deps
        all_plan_deps: set[str] = set(flight_plan.depends_on_plans)
        if suggested_deps:
            all_plan_deps.update(suggested_deps)
        # Remove self-reference
        all_plan_deps.discard(flight_plan.name)

        if all_plan_deps and bead_result and bead_result.epic:
            await self.emit_step_started(
                WIRE_CROSS_PLAN_DEPS,
                display_label="Wiring cross-plan dependencies",
            )
            try:
                # Resolve plan names to epic bd_ids
                resolved, resolve_errors = await resolve_plan_epic_ids(
                    plan_names=tuple(sorted(all_plan_deps)),
                    cwd=cwd,
                )

                for err in resolve_errors:
                    await self.emit_output(
                        WIRE_CROSS_PLAN_DEPS,
                        err,
                        level="warning",
                    )

                if resolved:
                    dep_epic_ids = [r.epic_bd_id for r in resolved]
                    cross_plan_result = await wire_cross_plan_dependencies(
                        new_epic_bd_id=bead_result.epic["bd_id"],
                        dependency_epic_ids=dep_epic_ids,
                        cwd=cwd,
                    )
                    await self.emit_output(
                        WIRE_CROSS_PLAN_DEPS,
                        f"Wired {cross_plan_result.wired_count} cross-plan epic dependencies",
                    )
                    for err in cross_plan_result.errors:
                        await self.emit_output(
                            WIRE_CROSS_PLAN_DEPS,
                            err,
                            level="error",
                        )
                else:
                    await self.emit_output(
                        WIRE_CROSS_PLAN_DEPS,
                        "No cross-plan dependencies resolved",
                        level="warning",
                    )

                await self.emit_step_completed(
                    WIRE_CROSS_PLAN_DEPS,
                    output=cross_plan_result.to_dict() if cross_plan_result else {},
                )
            except Exception as exc:
                await self.emit_step_failed(WIRE_CROSS_PLAN_DEPS, str(exc))
                logger.warning("wire_cross_plan_deps_failed", error=str(exc))

        # ------------------------------------------------------------------
        # Return final output
        # ------------------------------------------------------------------
        result = RefuelMaverickResult(
            work_units_written=written,
            work_units_dir=str(work_units_dir),
            run_id=run_id,
            epic=bead_result.epic if bead_result else None,
            work_beads=bead_result.work_beads if bead_result else (),
            dependencies=wire_result.dependencies if wire_result else (),
            errors=bead_result.errors if bead_result else (),
            coverage_warnings=(),
            briefing_path=briefing_path_str,
            cross_plan_deps=(
                tuple(rp.to_dict() for rp in cross_plan_result.resolved_plans)
                if cross_plan_result
                else ()
            ),
            cross_plan_dep_errors=(cross_plan_result.errors if cross_plan_result else ()),
            suggested_cross_plan_deps=suggested_deps,
            open_bead_overlap_count=(open_bead_result.overlap_count if open_bead_result else 0),
        )
        return result.to_dict()

    async def _run_with_xoscar(
        self,
        *,
        flight_plan: Any,
        raw_content: str,
        codebase_context: Any,
        open_bead_result: Any,
        runway_context_text: str | None,
        run_dir: Path | None,
        skip_briefing: bool = False,
        ctx: dict[str, Any] | None = None,
    ) -> Any:
        """Run briefing + decomposition via xoscar supervisor.

        Creates briefing actors (Navigator, Structuralist, Recon, Contrarian)
        and decomposer actors in the same ActorSystem. The supervisor
        orchestrates: briefing → decompose → validate.

        Returns a DecompositionOutput.
        """

        from maverick.agents.briefing.prompts import build_briefing_prompt
        from maverick.workflows.refuel_maverick.models import (
            DecompositionOutput,
            WorkUnitSpec,
        )

        # Build briefing prompt (needed by supervisor for agent dispatch)
        briefing_prompt = build_briefing_prompt(
            raw_content,
            codebase_context,
            open_bead_context=open_bead_result,
        )

        # Check for cached briefing from a previous run
        import json as _json

        plan_dir = Path.cwd() / ".maverick" / "plans" / flight_plan.name
        briefing_cache_path = plan_dir / "refuel-briefing.json"
        outline_cache_path = plan_dir / "refuel-outline.json"
        detail_cache_dir = plan_dir / "refuel-details"
        cached_briefing: dict[str, Any] | None = None
        cached_outline: dict[str, Any] | None = None
        cached_details: dict[str, dict[str, Any]] = {}

        verification_properties = getattr(flight_plan, "verification_properties", "")
        briefing_key = _briefing_cache_key(raw_content, codebase_context, briefing_prompt)

        if not skip_briefing and briefing_cache_path.is_file():
            try:
                raw_cache = _json.loads(briefing_cache_path.read_text(encoding="utf-8"))
                # Support legacy caches written before the keyed-envelope
                # format: those are a flat {agent: payload} dict. Treat
                # them as absent so the hash gets written next time.
                if (
                    isinstance(raw_cache, dict)
                    and raw_cache.get("schema_version") == BRIEFING_CACHE_SCHEMA_VERSION
                    and isinstance(raw_cache.get("payloads"), dict)
                ):
                    if raw_cache.get("cache_key") == briefing_key:
                        cached_briefing = raw_cache["payloads"]
                        skip_briefing = True
                        logger.info(
                            "refuel.briefing_cache_hit",
                            path=str(briefing_cache_path),
                            agents=list(cached_briefing.keys()),
                            cache_key=briefing_key,
                        )
                        await self.emit_output(
                            "refuel",
                            "Using cached briefing from previous run",
                            level="info",
                        )
                    else:
                        logger.info(
                            "refuel.briefing_cache_invalidated",
                            path=str(briefing_cache_path),
                            reason="key_mismatch",
                            expected=briefing_key,
                            actual=raw_cache.get("cache_key"),
                        )
                else:
                    logger.info(
                        "refuel.briefing_cache_invalidated",
                        path=str(briefing_cache_path),
                        reason="legacy_or_malformed_envelope",
                    )
            except (OSError, _json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "refuel.briefing_cache_invalid",
                    path=str(briefing_cache_path),
                    error=str(exc),
                )
                cached_briefing = None

        # The outline key depends on the briefing that produced it, so
        # compute it from whatever briefing we'll actually run with
        # (cached or the about-to-be-produced None placeholder).
        outline_key = _outline_cache_key(raw_content, verification_properties, cached_briefing)

        if outline_cache_path.is_file():
            try:
                raw_outline = _json.loads(outline_cache_path.read_text(encoding="utf-8"))
                if (
                    isinstance(raw_outline, dict)
                    and raw_outline.get("schema_version") == OUTLINE_CACHE_SCHEMA_VERSION
                    and isinstance(raw_outline.get("payload"), dict)
                ):
                    if raw_outline.get("cache_key") == outline_key:
                        cached_outline = raw_outline["payload"]
                        unit_count = len(cached_outline.get("work_units", []))
                        logger.info(
                            "refuel.outline_cache_hit",
                            path=str(outline_cache_path),
                            unit_count=unit_count,
                            cache_key=outline_key,
                        )
                        await self.emit_output(
                            "refuel",
                            f"Using cached outline from previous run ({unit_count} work units)",
                            level="info",
                        )
                    else:
                        logger.info(
                            "refuel.outline_cache_invalidated",
                            path=str(outline_cache_path),
                            reason="key_mismatch",
                            expected=outline_key,
                            actual=raw_outline.get("cache_key"),
                        )
                else:
                    logger.info(
                        "refuel.outline_cache_invalidated",
                        path=str(outline_cache_path),
                        reason="legacy_or_malformed_envelope",
                    )
            except (OSError, _json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "refuel.outline_cache_invalid",
                    path=str(outline_cache_path),
                    error=str(exc),
                )
                cached_outline = None

        # Per-unit detail cache — one JSON file per unit. A resumed run
        # picks up where it left off instead of re-generating details
        # that already succeeded.
        if detail_cache_dir.is_dir():
            for detail_file in detail_cache_dir.glob("*.json"):
                try:
                    detail = _json.loads(detail_file.read_text(encoding="utf-8"))
                    if isinstance(detail, dict) and detail.get("id"):
                        cached_details[detail["id"]] = detail
                except (OSError, _json.JSONDecodeError, ValueError) as exc:
                    logger.warning(
                        "refuel.detail_cache_invalid",
                        path=str(detail_file),
                        error=str(exc),
                    )
            if cached_details:
                await self.emit_output(
                    "refuel",
                    f"Loaded {len(cached_details)} cached detail(s) from previous run",
                    level="info",
                )

        initial_payload = {
            "flight_plan_content": raw_content,
            "codebase_context": codebase_context,
            "briefing": cached_briefing,  # pre-populated if cached, else filled by supervisor
            "briefing_prompt": briefing_prompt,
            "runway_context": runway_context_text or None,
            "verification_properties": getattr(flight_plan, "verification_properties", ""),
            "outline": cached_outline,  # pre-populated if cached, else produced by decomposer
            "cached_details": cached_details,  # keyed by unit_id; empty dict if none
        }

        # Provider labels for briefing agents are still useful for the
        # Rich Live display the supervisor emits; compute them here so
        # the supervisor doesn't need access to ``resolve_step_config``.
        provider_labels: dict[str, str] = {}
        if not skip_briefing:
            for agent_name in ("navigator", "structuralist", "recon", "contrarian"):
                config = self.resolve_step_config(
                    BRIEFING,
                    StepType.PYTHON,
                    agent_name=agent_name,
                )
                label = agent_name.replace("_", " ").title()
                provider_labels[label] = self._resolve_display_label_for_config(config)

        decompose_config = self.resolve_step_config(
            DECOMPOSE,
            StepType.PYTHON,
            agent_name="decomposer",
        )

        import xoscar as xo

        from maverick.actors.xoscar.pool import actor_pool
        from maverick.actors.xoscar.refuel_supervisor import (
            RefuelInputs,
            RefuelSupervisor,
        )

        DECOMPOSER_POOL_SIZE = 4

        supervisor_inputs = RefuelInputs(
            cwd=str(Path.cwd()),
            flight_plan=flight_plan,
            initial_payload=initial_payload,
            config=decompose_config,
            decomposer_pool_size=DECOMPOSER_POOL_SIZE - 1,
            skip_briefing=skip_briefing,
            provider_labels=provider_labels,
            detail_session_max_turns=DETAIL_SESSION_MAX_TURNS,
            fix_session_max_turns=FIX_SESSION_MAX_TURNS,
            briefing_cache_path=str(briefing_cache_path),
            outline_cache_path=str(outline_cache_path),
            detail_cache_dir=str(detail_cache_dir),
            briefing_cache_key=briefing_key,
            briefing_cache_schema_version=BRIEFING_CACHE_SCHEMA_VERSION,
            outline_cache_key_inputs={
                "flight_plan_content": raw_content,
                "verification_properties": verification_properties,
            },
            outline_cache_schema_version=OUTLINE_CACHE_SCHEMA_VERSION,
        )

        async with actor_pool() as (_pool, address):
            supervisor = await xo.create_actor(
                RefuelSupervisor,
                supervisor_inputs,
                address=address,
                uid="refuel-supervisor",
            )
            try:
                result = await self._drain_xoscar_supervisor(supervisor)
            finally:
                try:
                    await xo.destroy_actor(supervisor)
                except Exception:  # noqa: BLE001 — teardown must not raise
                    pass

        if not result or not result.get("success"):
            from maverick.exceptions import WorkflowError

            raise WorkflowError(
                f"Decomposition failed: {result.get('error', 'unknown') if result else 'no result'}",  # noqa: E501
                workflow_name="refuel-maverick",
            )

        # Convert specs to DecompositionOutput
        work_units = []
        for spec in result.get("specs", []):
            if isinstance(spec, WorkUnitSpec):
                work_units.append(spec)
            elif isinstance(spec, dict):
                work_units.append(WorkUnitSpec.model_validate(spec))

        fix_rounds = result.get("fix_rounds", 0)
        if ctx is not None:
            ctx["fix_rounds"] = fix_rounds

        decomposition = DecompositionOutput(
            work_units=work_units,
            rationale=f"{len(work_units)} work units via supervisor ({fix_rounds} fix rounds)",
        )

        await self.emit_output(
            DECOMPOSE,
            f"Decomposed into {len(work_units)} work units ({fix_rounds} fix rounds)",
            level="success",
        )
        await self.emit_step_completed(
            DECOMPOSE,
            {"work_unit_count": len(work_units)},
        )

        return decomposition
