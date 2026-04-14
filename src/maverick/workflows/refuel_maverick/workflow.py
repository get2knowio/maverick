"""RefuelMaverickWorkflow — flight plan decomposition pipeline."""

from __future__ import annotations

import asyncio
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
    GATHER_CONTEXT,
    MAX_DECOMPOSE_ATTEMPTS,
    PARSE_FLIGHT_PLAN,
    WIRE_CROSS_PLAN_DEPS,
    WIRE_DEPS,
    WORKFLOW_NAME,
    WRITE_WORK_UNITS,
)
from maverick.workflows.refuel_maverick.models import RefuelMaverickResult

logger = get_logger(__name__)


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

        # Generate run_id and create run directory
        import uuid as _uuid

        from maverick.runway.run_metadata import RunMetadata, write_metadata

        run_id = _uuid.uuid4().hex[:8]
        run_dir = Path.cwd() / ".maverick" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

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
        await self.emit_step_started(GATHER_CONTEXT)
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
        # ------------------------------------------------------------------
        # Step 2.8: Derive verification properties from acceptance criteria
        # ------------------------------------------------------------------
        # A dedicated agent reads the flight plan's success criteria plus
        # the codebase context and produces executable test assertions.
        # These become the deterministic spec compliance gate during fly.
        verification_properties = getattr(flight_plan, "verification_properties", "")
        _derive_vp = (
            not verification_properties
            and not dry_run
            and len(flight_plan.success_criteria) > 0
            and len(codebase_context.files) > 0
        )
        if _derive_vp:
            await self.emit_step_started(DERIVE_VERIFICATION)
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
        # Steps 2b-4: Briefing + Decompose + Validate via Thespian actor system
        # ------------------------------------------------------------------
        decomposition = await self._run_with_thespian(
            flight_plan=flight_plan,
            raw_content=raw_content,
            codebase_context=codebase_context,
            open_bead_result=open_bead_result,
            runway_context_text=runway_context_text,
            run_dir=run_dir,
            skip_briefing=skip_briefing,
        )
        briefing_path_str: str | None = None
        suggested_deps: tuple[str, ...] = ()

        # ------------------------------------------------------------------
        # Step 5: Write work units
        # ------------------------------------------------------------------
        await self.emit_step_started(WRITE_WORK_UNITS)

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
            dry_run=dry_run,
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

    async def _run_with_thespian(
        self,
        *,
        flight_plan: Any,
        raw_content: str,
        codebase_context: Any,
        open_bead_result: Any,
        runway_context_text: str | None,
        run_dir: Path | None,
        skip_briefing: bool = False,
    ) -> Any:
        """Run briefing + decomposition via Thespian actor system.

        Creates briefing actors (Navigator, Structuralist, Recon, Contrarian)
        and decomposer actors in the same ActorSystem. The supervisor
        orchestrates: briefing → decompose → validate.

        Returns a DecompositionOutput.
        """

        from thespian.actors import ActorSystem

        from maverick.actors.bead_creator import BeadCreatorActor
        from maverick.actors.briefing import BriefingActor
        from maverick.actors.decomposer import DecomposerActor
        from maverick.actors.refuel_supervisor import RefuelSupervisorActor
        from maverick.actors.validator import ValidatorActor
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

        initial_payload = {
            "flight_plan_content": raw_content,
            "codebase_context": codebase_context,
            "briefing": None,  # populated by supervisor after briefing
            "briefing_prompt": briefing_prompt,
            "runway_context": runway_context_text or None,
            "verification_properties": getattr(flight_plan, "verification_properties", ""),
        }

        # Start Thespian actor system on a known port.
        # Use a fixed port so the MCP server subprocess can connect.
        # Clean up any stale admin from a previous crashed run.
        import atexit
        import socket

        THESPIAN_PORT = 19500

        def _port_in_use(port: int) -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(("127.0.0.1", port)) == 0

        if _port_in_use(THESPIAN_PORT):
            logger.warning(
                "refuel.stale_admin_detected",
                port=THESPIAN_PORT,
                msg="Shutting down stale Thespian admin",
            )
            try:
                stale = ActorSystem(
                    "multiprocTCPBase",
                    capabilities={"Admin Port": THESPIAN_PORT},
                )
                stale.shutdown()
                import time

                time.sleep(1)
            except Exception:
                pass

        asys = ActorSystem(
            "multiprocTCPBase",
            capabilities={"Admin Port": THESPIAN_PORT},
        )

        # Register atexit handler for crash safety.
        # Suppress root logger during shutdown to avoid noisy ACP
        # errors from child processes being killed mid-prompt.
        def _cleanup_actor_system():
            import logging as _logging

            _root = _logging.getLogger()
            _prev = _root.level
            _root.setLevel(_logging.CRITICAL)
            try:
                asys.shutdown()
            except Exception:
                pass
            finally:
                _root.setLevel(_prev)

        atexit.register(_cleanup_actor_system)

        try:
            # Create child actors — primary decomposer handles outline + fixes,
            # pool members handle detail pass in parallel.
            DECOMPOSER_POOL_SIZE = 4
            decomposer_addr = asys.createActor(DecomposerActor)
            decomposer_pool = [
                asys.createActor(DecomposerActor) for _ in range(DECOMPOSER_POOL_SIZE - 1)
            ]
            validator_addr = asys.createActor(ValidatorActor)
            bead_creator_addr = asys.createActor(BeadCreatorActor)

            # Create briefing actors (one per agent role)
            briefing_actors: dict[str, Any] = {}
            if not skip_briefing:
                _briefing_agents = {
                    "navigator": ("maverick.briefing.models", "NavigatorBrief"),
                    "structuralist": ("maverick.briefing.models", "StructuralistBrief"),
                    "recon": ("maverick.briefing.models", "ReconBrief"),
                    "contrarian": ("maverick.briefing.models", "ContrarianBrief"),
                }
                for agent_name, (schema_mod, schema_cls) in _briefing_agents.items():
                    addr = asys.createActor(BriefingActor)
                    asys.ask(
                        addr,
                        {
                            "type": "init",
                            "agent_name": agent_name,
                            "schema_module": schema_mod,
                            "schema_class": schema_cls,
                            "cwd": str(Path.cwd()),
                        },
                        timeout=10,
                    )
                    briefing_actors[agent_name] = addr

            # Resolve provider/model label for CLI display
            _resolved = self.resolve_step_config(BRIEFING, StepType.PYTHON)
            _prov = _resolved.provider or self._resolve_display_provider() or "default"
            _mod = _resolved.model_id or self._resolve_display_model() or "default"
            _label = f"{_prov}/{_mod}"
            provider_labels = {
                "Navigator": _label,
                "Structuralist": _label,
                "Recon": _label,
                "Contrarian": _label,
            }

            # Create supervisor with globalName for MCP server discovery
            supervisor_addr = asys.createActor(
                RefuelSupervisorActor,
                globalName="supervisor-inbox",
            )

            # Init all decomposer actors (primary + pool)
            decomposer_init = {
                "type": "init",
                "cwd": str(Path.cwd()),
                "mcp_tools": "submit_outline,submit_details,submit_fix",
                "admin_port": THESPIAN_PORT,
            }
            asys.ask(decomposer_addr, decomposer_init, timeout=10)
            for pool_addr in decomposer_pool:
                asys.ask(pool_addr, decomposer_init, timeout=10)

            asys.ask(
                validator_addr,
                {
                    "type": "init",
                    "flight_plan": flight_plan,
                },
                timeout=10,
            )

            asys.ask(
                bead_creator_addr,
                {
                    "type": "init",
                    "plan_name": flight_plan.name if hasattr(flight_plan, "name") else "",
                    "plan_objective": flight_plan.objective
                    if hasattr(flight_plan, "objective")
                    else "",  # noqa: E501
                },
                timeout=10,
            )

            # Init supervisor with child addresses and config
            asys.ask(
                supervisor_addr,
                {
                    "type": "init",
                    "decomposer_addr": decomposer_addr,
                    "decomposer_pool": decomposer_pool,
                    "validator_addr": validator_addr,
                    "bead_creator_addr": bead_creator_addr,
                    "briefing_actors": briefing_actors,
                    "provider_labels": provider_labels,
                    "skip_briefing": skip_briefing,
                    "initial_payload": initial_payload,
                    "config": {"flight_plan": flight_plan},
                },
                timeout=10,
            )

            # Start decomposition (fire-and-drain)
            asys.tell(supervisor_addr, "start")

            # Scale timeout: briefing (~10min parallel + ~10min contrarian)
            # + outline (~10min) + parallel detail waves (~10min each)
            # + up to 3 validation/fix rounds (~10min each).
            sc_count = len(flight_plan.success_criteria)
            estimated_units = max(1, int(sc_count * 1.5))
            detail_waves = max(
                1, (estimated_units + DECOMPOSER_POOL_SIZE - 1) // DECOMPOSER_POOL_SIZE
            )
            briefing_phases = 2 if not skip_briefing else 0  # parallel + contrarian
            drain_timeout = 600.0 * (briefing_phases + 1 + detail_waves + MAX_DECOMPOSE_ATTEMPTS)
            result = await self._drain_supervisor_events(
                asys=asys,
                supervisor=supervisor_addr,
                poll_interval=0.25,
                hard_timeout_seconds=drain_timeout,
            )

        finally:
            asys.shutdown()
            atexit.unregister(_cleanup_actor_system)

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
