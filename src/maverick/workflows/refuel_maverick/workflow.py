"""RefuelMaverickWorkflow — flight plan decomposition pipeline."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from maverick.briefing.models import (
    ContrarianBrief,
    NavigatorBrief,
    ReconBrief,
    StructuralistBrief,
)
from maverick.briefing.serializer import serialize_briefing
from maverick.briefing.synthesis import synthesize_briefing
from maverick.exceptions import WorkflowError
from maverick.executor.config import StepConfig
from maverick.executor.errors import OutputSchemaValidationError
from maverick.flight.loader import FlightPlanFile
from maverick.flight.serializer import serialize_work_unit
from maverick.library.actions.beads import create_beads, wire_dependencies
from maverick.library.actions.cross_plan_deps import (
    resolve_plan_epic_ids,
    wire_cross_plan_dependencies,
)
from maverick.library.actions.decompose import (
    build_decomposition_prompt,
    convert_specs_to_work_units,
    gather_codebase_context,
    validate_decomposition,
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
    BRIEFING_CONTRARIAN,
    BRIEFING_NAVIGATOR,
    BRIEFING_RECON,
    BRIEFING_STRUCTURALIST,
    CREATE_BEADS,
    DECOMPOSE,
    GATHER_CONTEXT,
    PARSE_FLIGHT_PLAN,
    VALIDATE,
    WIRE_CROSS_PLAN_DEPS,
    WIRE_DEPS,
    WORKFLOW_NAME,
    WRITE_WORK_UNITS,
)
from maverick.workflows.refuel_maverick.models import (
    DecompositionOutput,
    RefuelMaverickResult,
)

logger = get_logger(__name__)

# Transient errors that warrant retry (API/network errors)
_TRANSIENT_ERRORS = (
    TimeoutError,
    ConnectionError,
    OSError,
)


class RefuelMaverickWorkflow(PythonWorkflow):
    """Workflow that decomposes a Maverick Flight Plan into work units and beads.

    Pipeline:
    1. parse_flight_plan - Parse flight plan file via FlightPlanFile.aload()
    2. gather_context - Read in-scope files from codebase
    3. decompose - Agent decomposes flight plan into work units (via StepExecutor)
    4. validate - Validate dependency graph (acyclic), unique IDs, SC coverage
    5. write_work_units - Write work unit files to .maverick/plans/<name>/
    6. create_beads - Create epic + task beads via BeadClient (skipped on dry_run)
    7. wire_deps - Wire bead dependencies from depends_on fields (skipped on dry_run)

    Args:
        config: Project configuration (MaverickConfig).
        registry: Component registry for action/agent dispatch.
        checkpoint_store: Optional checkpoint persistence backend.
        step_executor: StepExecutor for agent step execution (required for decompose).
        workflow_name: Identifier for this workflow instance.
    """

    def __init__(self, **kwargs: Any) -> None:
        if "workflow_name" not in kwargs:
            kwargs["workflow_name"] = WORKFLOW_NAME
        super().__init__(**kwargs)

    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the refuel-maverick pipeline.

        Args:
            inputs: Workflow inputs. Required: ``flight_plan_path`` (str).
                Optional: ``dry_run`` (bool, default False).

        Returns:
            Output dict matching RefuelMaverickResult.to_dict() contract.

        Raises:
            WorkflowError: If ``flight_plan_path`` is not provided in inputs.
        """
        flight_plan_path_str: str = inputs.get("flight_plan_path", "")
        if not flight_plan_path_str:
            raise WorkflowError("'flight_plan_path' input is required")
        dry_run: bool = bool(inputs.get("dry_run", False))
        skip_briefing: bool = bool(inputs.get("skip_briefing", False))

        flight_plan_path = Path(flight_plan_path_str)

        # ------------------------------------------------------------------
        # Step 1: Parse flight plan
        # ------------------------------------------------------------------
        await self.emit_step_started(PARSE_FLIGHT_PLAN)
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

        # ------------------------------------------------------------------
        # Step 2: Gather codebase context
        # ------------------------------------------------------------------
        await self.emit_step_started(GATHER_CONTEXT)
        await self.emit_output(
            GATHER_CONTEXT,
            f"Reading {len(flight_plan.scope.in_scope)} in-scope files...",
        )
        try:
            # Resolve cwd for in-scope file paths. Convention: flight plans live in
            # .maverick/plans/<name>/flight-plan.md, so we need to go up 4 levels
            # (flight-plan.md → <name> → plans → .maverick → repo root).
            # If the flight plan is at the filesystem root (parent.name is empty),
            # fall back to None (which gather_codebase_context resolves to Path.cwd()).
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

        if missing_count > 0 and found_count == 0:
            # All files missing — greenfield project, not an error
            await self.emit_output(
                GATHER_CONTEXT,
                f"Greenfield project \u2014 none of {total_scope} "
                f"in-scope files exist yet",
            )
        elif missing_count > 0:
            # Partial — some files exist, some don't
            await self.emit_output(
                GATHER_CONTEXT,
                f"{missing_count} of {total_scope} in-scope files "
                f"not found (may not exist yet)",
                level="warning",
            )
        size_kb = codebase_context.total_size // 1024
        await self.emit_output(
            GATHER_CONTEXT,
            f"Gathered context ({found_count} files, {size_kb}KB)",
        )
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
        suggested_deps: tuple[str, ...] = ()

        if not skip_briefing:
            await self.emit_step_started(ANALYZE_OPEN_BEADS)
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
        briefing_doc = None
        briefing_path_str: str | None = None

        if not skip_briefing:
            from maverick.agents.briefing.prompts import (
                build_briefing_prompt,
                build_contrarian_prompt,
            )

            await self.emit_step_started(BRIEFING)

            if self._step_executor is None:
                raise WorkflowError("step_executor is required for the briefing step")

            briefing_prompt = build_briefing_prompt(
                raw_content,
                codebase_context,
                open_bead_context=open_bead_result,
            )

            # Create event callback to forward streaming events
            async def _briefing_event_cb(event: Any) -> None:
                await self._event_queue.put(event)

            try:
                # Parallel: Navigator + Structuralist + Recon
                async def _run_briefing_agent(
                    label: str,
                    step_name: str,
                    agent_name: str,
                    output_schema: type[Any],
                ) -> Any:
                    await self.emit_output(
                        BRIEFING,
                        f"\u23f3 {label}...",
                        level="info",
                    )
                    t0 = time.monotonic()
                    result = await self._step_executor.execute(
                        step_name=step_name,
                        agent_name=agent_name,
                        prompt=briefing_prompt,
                        output_schema=output_schema,
                        event_callback=_briefing_event_cb,
                        config=StepConfig(timeout=300),
                    )
                    elapsed = time.monotonic() - t0
                    await self.emit_output(
                        BRIEFING,
                        f"\u2713 {label} ({elapsed:.1f}s)",
                        level="success",
                    )
                    return result

                nav_result, struct_result, recon_result = await asyncio.gather(
                    _run_briefing_agent(
                        "Navigator",
                        BRIEFING_NAVIGATOR,
                        "navigator",
                        NavigatorBrief,
                    ),
                    _run_briefing_agent(
                        "Structuralist",
                        BRIEFING_STRUCTURALIST,
                        "structuralist",
                        StructuralistBrief,
                    ),
                    _run_briefing_agent(
                        "Recon",
                        BRIEFING_RECON,
                        "recon",
                        ReconBrief,
                    ),
                )

                if (
                    not nav_result.output
                    or not struct_result.output
                    or not recon_result.output
                ):
                    raise WorkflowError(
                        "One or more briefing agents returned no output"
                    )

                # Sequential: Contrarian reviews all 3
                contrarian_prompt = build_contrarian_prompt(
                    raw_content,
                    nav_result.output,
                    struct_result.output,
                    recon_result.output,
                )
                await self.emit_output(
                    BRIEFING,
                    "\u23f3 Contrarian...",
                    level="info",
                )
                t0 = time.monotonic()
                contrarian_result = await self._step_executor.execute(
                    step_name=BRIEFING_CONTRARIAN,
                    agent_name="contrarian",
                    prompt=contrarian_prompt,
                    output_schema=ContrarianBrief,
                    event_callback=_briefing_event_cb,
                    config=StepConfig(timeout=300),
                )
                elapsed = time.monotonic() - t0
                await self.emit_output(
                    BRIEFING,
                    f"\u2713 Contrarian ({elapsed:.1f}s)",
                    level="success",
                )

                if not contrarian_result.output:
                    raise WorkflowError("Contrarian agent returned no output")

                # Synthesize (deterministic)
                briefing_doc = synthesize_briefing(
                    flight_plan.name,
                    nav_result.output,
                    struct_result.output,
                    recon_result.output,
                    contrarian_result.output,
                )

                # Write to disk (colocated with flight plan and work units)
                plan_dir = Path.cwd() / ".maverick" / "plans" / flight_plan.name
                await asyncio.to_thread(plan_dir.mkdir, parents=True, exist_ok=True)
                briefing_path = plan_dir / "refuel-briefing.md"
                await asyncio.to_thread(
                    briefing_path.write_text,
                    serialize_briefing(briefing_doc),
                    "utf-8",
                )
                briefing_path_str = str(briefing_path)

            except Exception as exc:
                await self.emit_step_failed(BRIEFING, str(exc))
                raise

            # Extract cross-plan dependency suggestions from recon
            recon_out = recon_result.output
            if recon_out and recon_out.suggested_cross_plan_dependencies:
                suggested_deps = recon_out.suggested_cross_plan_dependencies
                # Remove self-reference
                suggested_deps = tuple(
                    d for d in suggested_deps if d != flight_plan.name
                )
                if suggested_deps:
                    await self.emit_output(
                        BRIEFING,
                        f"Recon suggested {len(suggested_deps)} cross-plan "
                        f"dependencies: {', '.join(suggested_deps)}",
                    )

            await self.emit_output(
                BRIEFING,
                f"Briefing complete: {len(briefing_doc.key_decisions)} decisions, "
                f"{len(briefing_doc.key_risks)} risks, "
                f"{len(briefing_doc.open_questions)} open questions",
            )
            await self.emit_step_completed(
                BRIEFING,
                output={
                    "key_decisions": list(briefing_doc.key_decisions),
                    "key_risks": list(briefing_doc.key_risks),
                    "open_questions": list(briefing_doc.open_questions),
                    "briefing_path": briefing_path_str,
                },
            )

        # ------------------------------------------------------------------
        # Step 3: Decompose via agent (with retry)
        # ------------------------------------------------------------------
        await self.emit_step_started(
            DECOMPOSE,
            step_type=StepType.AGENT,
            provider=self._resolve_display_provider(),
            model_id=self._resolve_display_model(),
        )

        prompt = build_decomposition_prompt(
            raw_content, codebase_context, briefing=briefing_doc
        )

        decomposition: DecompositionOutput | None = None

        # Create event callback to forward streaming events
        async def _event_cb(event: Any) -> None:
            await self._event_queue.put(event)

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception_type(_TRANSIENT_ERRORS),
                reraise=True,
            ):
                with attempt:
                    if self._step_executor is None:
                        raise WorkflowError(
                            "step_executor is required for the decompose step"
                        )

                    executor_result = await self._step_executor.execute(
                        step_name=DECOMPOSE,
                        agent_name="decomposer",
                        prompt=prompt,
                        output_schema=DecompositionOutput,
                        event_callback=_event_cb,
                        config=StepConfig(timeout=600),
                    )

                    if executor_result.output is None:
                        raise WorkflowError("Decomposition agent returned no output")

                    decomposition = executor_result.output
        except OutputSchemaValidationError:
            # Don't retry on schema validation errors
            await self.emit_step_failed(
                DECOMPOSE, "Agent output failed schema validation"
            )
            raise
        except Exception as exc:
            await self.emit_step_failed(DECOMPOSE, str(exc))
            raise

        if decomposition is None:
            raise WorkflowError("Decomposition step completed but produced no output")
        await self.emit_output(
            DECOMPOSE,
            f"Decomposed into {len(decomposition.work_units)} work units",
        )
        if decomposition.rationale:
            # Show first sentence of rationale as a brief summary
            first_sentence = decomposition.rationale.split(". ")[0].rstrip(".")
            await self.emit_output(
                DECOMPOSE, f"Rationale: {first_sentence}", level="info"
            )
        await self.emit_step_completed(
            DECOMPOSE,
            output={
                "work_unit_count": len(decomposition.work_units),
                "rationale": decomposition.rationale,
            },
        )

        # ------------------------------------------------------------------
        # Step 4: Validate
        # ------------------------------------------------------------------
        await self.emit_step_started(VALIDATE)
        try:
            coverage_warnings = validate_decomposition(
                specs=decomposition.work_units,
                success_criteria_count=len(flight_plan.success_criteria),
            )
        except ValueError as exc:
            await self.emit_step_failed(VALIDATE, str(exc))
            raise WorkflowError(str(exc)) from exc

        for warning in coverage_warnings:
            await self.emit_output(VALIDATE, f"Warning: {warning}", level="warning")

        parallel_group_count = len(
            {
                wu.parallel_group
                for wu in decomposition.work_units
                if wu.parallel_group is not None
            }
        )
        await self.emit_output(
            VALIDATE,
            f"Dependency graph is acyclic ({parallel_group_count} parallel groups)",
        )
        await self.emit_step_completed(
            VALIDATE,
            output={
                "coverage_warnings": coverage_warnings,
                "parallel_group_count": parallel_group_count,
            },
        )

        # ------------------------------------------------------------------
        # Step 5: Write work units
        # ------------------------------------------------------------------
        await self.emit_step_started(WRITE_WORK_UNITS)

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
            for wu in work_units:
                filename = f"{wu.sequence:03d}-{wu.id}.md"
                file_path = work_units_dir / filename
                content = serialize_work_unit(wu)
                await asyncio.to_thread(file_path.write_text, content, "utf-8")
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
        # Steps 6-7: Create beads and wire deps (skipped in dry_run)
        # ------------------------------------------------------------------
        bead_result = None
        wire_result = None

        if not dry_run:
            # Step 6: Create beads
            await self.emit_step_started(CREATE_BEADS)
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
                        "title": wu.task,
                        "bead_type": "task",
                        "priority": 2,
                        "category": "user_story",
                        "description": (
                            wu.instructions[:500] if wu.instructions else wu.task
                        ),
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

            # Attach flight_plan_name to the epic for downstream lookup
            if bead_result.epic:
                from maverick.beads.client import BeadClient

                _bead_client = BeadClient(cwd=Path.cwd())
                try:
                    await _bead_client.set_state(
                        bead_result.epic["bd_id"],
                        {"flight_plan_name": flight_plan.name},
                        reason="refuel: link epic to flight plan",
                    )
                except Exception as exc:
                    logger.warning(
                        "set_flight_plan_state_failed",
                        epic_id=bead_result.epic["bd_id"],
                        error=str(exc),
                    )

            await self.emit_output(
                CREATE_BEADS,
                f"Created epic: {flight_plan.name}",
            )
            await self.emit_output(
                CREATE_BEADS,
                f"Created {len(bead_result.work_beads)} task beads",
            )
            if bead_result.errors:
                for error in bead_result.errors:
                    await self.emit_output(
                        CREATE_BEADS,
                        error,
                        level="error",
                    )
                raise WorkflowError(f"Failed to create {len(bead_result.errors)} beads")
            await self.emit_step_completed(CREATE_BEADS, output=bead_result.to_dict())

            # Step 7: Wire dependencies
            await self.emit_step_started(WIRE_DEPS)
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
        # Step 8: Wire cross-plan epic dependencies (skipped in dry_run)
        # ------------------------------------------------------------------
        cross_plan_result = None

        # Merge explicit depends_on_plans with suggested cross-plan deps
        all_plan_deps: set[str] = set(flight_plan.depends_on_plans)
        if suggested_deps:
            all_plan_deps.update(suggested_deps)
        # Remove self-reference
        all_plan_deps.discard(flight_plan.name)

        if all_plan_deps and not dry_run and bead_result and bead_result.epic:
            await self.emit_step_started(WIRE_CROSS_PLAN_DEPS)
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
                        f"Wired {cross_plan_result.wired_count} cross-plan "
                        f"epic dependencies",
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
            epic=bead_result.epic if bead_result else None,
            work_beads=bead_result.work_beads if bead_result else (),
            dependencies=wire_result.dependencies if wire_result else (),
            errors=bead_result.errors if bead_result else (),
            coverage_warnings=tuple(coverage_warnings),
            dry_run=dry_run,
            briefing_path=briefing_path_str,
            cross_plan_deps=(
                tuple(rp.to_dict() for rp in cross_plan_result.resolved_plans)
                if cross_plan_result
                else ()
            ),
            cross_plan_dep_errors=(
                cross_plan_result.errors if cross_plan_result else ()
            ),
            suggested_cross_plan_deps=suggested_deps,
            open_bead_overlap_count=(
                open_bead_result.overlap_count if open_bead_result else 0
            ),
        )
        return result.to_dict()
