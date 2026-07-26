"""RefuelMaverickWorkflow — flight plan decomposition pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maverick.exceptions import WorkflowError
from maverick.flight.loader import FlightPlanFile
from maverick.flight.serializer import serialize_work_unit
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
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.refuel_maverick.constants import (
    ANALYZE_OPEN_BEADS,
    COMMIT_OUTPUT,
    CREATE_BEADS,
    DECOMPOSE,
    DERIVE_VERIFICATION,
    GATHER_CONTEXT,
    PARSE_FLIGHT_PLAN,
    WIRE_CROSS_PLAN_DEPS,
    WORKFLOW_NAME,
    WRITE_WORK_UNITS,
)
from maverick.workflows.refuel_maverick.models import RefuelMaverickResult

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _SyntheticBeadResult:
    """Adopts the supervisor's bead-creation outputs into the shape the
    downstream workflow code expects (cross-plan dep wiring, the final
    :class:`RefuelMaverickResult`). Replaces the result the deleted
    in-workflow ``create_beads`` call used to produce."""

    epic: dict[str, Any] | None
    work_beads: tuple[dict[str, Any], ...]
    created_map: dict[str, str]
    dependencies: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SyntheticWireResult:
    """Stand-in for the deleted in-workflow ``wire_dependencies`` result.
    Carries only the field downstream consumers read."""

    dependencies: tuple[dict[str, Any], ...]


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
    3. decompose - Agent decomposes flight plan into work units
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

        # Validate cwd before entering _run_impl so the finally block
        # can rely on ctx["cwd"] being populated even on early failure.
        cwd_input = inputs.get("cwd")
        if not cwd_input:
            raise WorkflowError("'cwd' input is required")

        ctx: dict[str, Any] = {"cwd": Path(cwd_input)}
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
            ctx_cwd: Path = ctx["cwd"]
            run_dir = ctx.get("run_dir", ctx_cwd / ".maverick" / "runs" / run_id)
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
        auto_commit: bool = bool(inputs.get("auto_commit", False))
        # ``ctx["cwd"]`` was validated + set by ``_run`` before this
        # call, so we can rely on it directly.
        ws_cwd: Path = ctx["cwd"]

        flight_plan_path = Path(flight_plan_path_str)

        # Generate run_id and create run directory (inside workspace).
        import uuid as _uuid

        from maverick.runway.run_metadata import RunMetadata, write_metadata

        run_id = _uuid.uuid4().hex[:8]
        run_dir = ws_cwd / ".maverick" / "runs" / run_id
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
                from maverick.agents.personas import VerificationPropertiesAgent
                from maverick.config import load_config
                from maverick.runtime.agent_factory import runtime_for_agent

                config = load_config()
                runtime, _ = runtime_for_agent("generate", agents_config=config.agents)
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
                    "- Skip structural or subjective criteria\n\n"
                    f"## Success Criteria\n\n{sc_text}\n\n"
                    f"## Codebase Files\n\n"
                    + "\n".join(f"- {f.path}" for f in codebase_context.files)
                    + "\n"
                )
                try:
                    async with VerificationPropertiesAgent(
                        runtime=runtime, cwd=str(ws_cwd)
                    ) as agent:
                        vp_text = await agent.derive(vp_prompt)
                except Exception as vp_exec_err:
                    logger.debug(
                        "vp_executor_failed",
                        error=str(vp_exec_err),
                    )
                    vp_text = ""
                if vp_text:
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
                cwd=str(ws_cwd),
            )
            if runway_result.context_text:
                runway_context_text = runway_result.context_text
        except Exception as exc:
            logger.warning("refuel_runway_context_failed", error=str(exc))

        # ------------------------------------------------------------------
        # Steps 2b-4: Briefing + Decompose + Validate — driven by the
        # Burr application built around the RefuelSquadron.
        # ------------------------------------------------------------------
        decomposition = await self._run_decomposition(
            flight_plan=flight_plan,
            raw_content=raw_content,
            codebase_context=codebase_context,
            open_bead_result=open_bead_result,
            runway_context_text=runway_context_text,
            skip_briefing=skip_briefing,
            ctx=ctx,
            ws_cwd=ws_cwd,
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

        # Determine output directory (colocated with flight plan in workspace)
        work_units_dir = ws_cwd / ".maverick" / "plans" / flight_plan.name

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

        # Phase 1 observability: surface the complexity distribution so users
        # can see what the decomposer produced before deciding whether to
        # trust per-tier model routing in Phase 2. Counts are advisory only —
        # ``complexity`` is not yet wired into model selection.
        from collections import Counter

        complexity_counts: Counter[str] = Counter(
            str(wu.complexity or "unclassified") for wu in work_units
        )
        # Stable display order: trivial → simple → moderate → complex → unclassified.
        _order = ["trivial", "simple", "moderate", "complex", "unclassified"]
        breakdown = ", ".join(
            f"{complexity_counts[k]} {k}" for k in _order if complexity_counts.get(k, 0) > 0
        )
        if breakdown:
            await self.emit_output(
                WRITE_WORK_UNITS,
                f"Complexity distribution: {breakdown}",
            )

        await self.emit_step_completed(
            WRITE_WORK_UNITS,
            output={
                "written": written,
                "directory": str(work_units_dir),
                "complexity_distribution": dict(complexity_counts),
            },
        )

        # ------------------------------------------------------------------
        # Steps 6-7: Consume the supervisor's bead-creation outputs.
        #
        # The Burr graph's ``create_beads`` action already created the
        # epic + work beads and wired ``depends_on`` deps inside the same
        # call. Re-running bead creation here would fabricate a duplicate
        # epic with identical children — that was the historical bug.
        # Instead, we adopt the graph's outputs from ``ctx`` (stashed in
        # :meth:`_run_decomposition`) and only run the post-creation
        # bookkeeping the graph doesn't own (run-meta update,
        # ``flight_plan_name`` state attachment, cross-epic dep wiring).
        # ------------------------------------------------------------------
        supervisor_epic: dict[str, Any] | None = ctx.get("supervisor_epic")
        supervisor_epic_id: str = ctx.get("supervisor_epic_id", "") or ""
        supervisor_work_beads: list[dict[str, Any]] = list(ctx.get("supervisor_work_beads") or ())
        supervisor_created_map: dict[str, str] = dict(ctx.get("supervisor_created_map") or {})
        supervisor_dependencies: list[dict[str, Any]] = list(
            ctx.get("supervisor_dependencies") or ()
        )

        await self.emit_step_started(CREATE_BEADS, display_label="Recording bead creation")

        if not supervisor_epic_id:
            await self.emit_step_failed(
                CREATE_BEADS,
                "supervisor returned no epic_id; bead creation must have failed",
            )
            raise WorkflowError("Supervisor produced no epic; aborting refuel")

        if not supervisor_epic:
            # Synthesize a minimal epic dict so downstream consumers
            # (cross-plan deps, RefuelMaverickResult) keep their
            # ``epic["bd_id"]`` access pattern. The supervisor returns
            # the full dict in the happy path; this fallback handles
            # older cached supervisor payloads.
            supervisor_epic = {"bd_id": supervisor_epic_id, "title": flight_plan.name}

        run_meta.epic_id = supervisor_epic_id
        run_meta.status = "refueled"
        write_metadata(run_dir, run_meta)
        ctx["epic_id"] = supervisor_epic_id
        ctx["bead_ids"] = [
            b["bd_id"] for b in supervisor_work_beads if isinstance(b, dict) and b.get("bd_id")
        ]

        # Attach flight_plan_name to the epic for downstream lookup,
        # and wire cross-epic dependencies so new epics wait for
        # existing open epics to complete first.
        from maverick.beads.client import BeadClient
        from maverick.beads.models import BeadDependency

        _bead_client = BeadClient(cwd=ws_cwd)

        try:
            await _bead_client.set_state(
                supervisor_epic_id,
                {"flight_plan_name": flight_plan.name},
                reason="refuel: link epic to flight plan",
            )
        except Exception as exc:
            logger.warning(
                "set_flight_plan_state_failed",
                epic_id=supervisor_epic_id,
                error=str(exc),
            )

        # Wire cross-epic dependency: new epic is blocked by the most
        # recent existing open epic (the tail of the chain). Serializes
        # epics without redundant fan-in dependencies — if A→B already
        # exists, C only needs B→C.
        try:
            all_beads = await _bead_client.query("type=epic AND status=open")
            existing_epics = [b for b in all_beads if b.id != supervisor_epic_id]
            if existing_epics:
                tail_epic = existing_epics[-1]
                await _bead_client.add_dependency(
                    BeadDependency(
                        blocker_id=tail_epic.id,
                        blocked_id=supervisor_epic_id,
                    )
                )
                logger.info(
                    "cross_epic_dep_wired",
                    blocker=tail_epic.id,
                    blocked=supervisor_epic_id,
                )
                await self.emit_output(
                    CREATE_BEADS,
                    f"New epic blocked by {tail_epic.id} — tasks start when prior epic completes",
                )
        except Exception as exc:
            logger.warning(
                "cross_epic_dep_failed",
                epic_id=supervisor_epic_id,
                error=str(exc),
            )

        await self.emit_output(
            CREATE_BEADS,
            f"Adopted supervisor epic {supervisor_epic_id}: {flight_plan.name}",
        )
        await self.emit_output(
            CREATE_BEADS,
            f"Adopted {len(supervisor_work_beads)} supervisor-created task beads "
            f"({len(supervisor_dependencies)} deps wired by supervisor)",
        )
        await self.emit_step_completed(
            CREATE_BEADS,
            output={
                "epic": supervisor_epic,
                "work_beads": supervisor_work_beads,
                "created_map": supervisor_created_map,
                "dependencies": supervisor_dependencies,
                "deps_wired": ctx.get("supervisor_deps_wired", 0),
                "errors": [],
            },
        )

        # The legacy WIRE_DEPS step (Step 7) was redundant: ``BeadCreatorActor``
        # already invoked ``wire_dependencies`` against ``self._extract_deps()``
        # before returning, so re-running it here only re-wrote the same edges.
        # Synthesize a stand-in result the rest of the workflow expects.
        bead_result = _SyntheticBeadResult(
            epic=supervisor_epic,
            work_beads=tuple(supervisor_work_beads),
            created_map=supervisor_created_map,
            dependencies=tuple(supervisor_dependencies),
            errors=(),
        )
        wire_result = _SyntheticWireResult(
            dependencies=tuple(supervisor_dependencies),
        )

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
        # Step 9 (optional): Auto-commit refuel artifacts
        # ------------------------------------------------------------------
        # Mirrors fly's ``--auto-commit``: when set, snapshot the
        # working directory so the user can pivot directly to ``maverick
        # fly`` without the snapshot step tripping on refuel's own
        # output (.maverick/plans, .beads/issues.jsonl, etc.). Failure
        # here is non-fatal — refuel itself succeeded.
        if auto_commit:
            from maverick.library.actions.jj import jj_snapshot_changes

            await self.emit_step_started(COMMIT_OUTPUT, display_label="Committing refuel output")
            try:
                snap = await jj_snapshot_changes(
                    message=f"chore: refuel {flight_plan.name}",
                )
                if snap.success and snap.committed:
                    sha_preview = (snap.commit_sha or "")[:8]
                    await self.emit_output(
                        COMMIT_OUTPUT,
                        f"Committed refuel output ({sha_preview})",
                    )
                    if snap.warning:
                        await self.emit_output(COMMIT_OUTPUT, snap.warning, level="warning")
                    await self.emit_step_completed(
                        COMMIT_OUTPUT,
                        {"committed": True, "commit_sha": snap.commit_sha},
                    )
                elif snap.success and not snap.committed:
                    await self.emit_output(
                        COMMIT_OUTPUT,
                        "Working directory clean — nothing to commit",
                    )
                    await self.emit_step_completed(COMMIT_OUTPUT, {"committed": False})
                else:
                    await self.emit_output(
                        COMMIT_OUTPUT,
                        snap.error or "commit failed",
                        level="error",
                    )
                    await self.emit_step_completed(
                        COMMIT_OUTPUT,
                        {"committed": False, "error": snap.error},
                    )
            except Exception as exc:
                await self.emit_step_failed(COMMIT_OUTPUT, str(exc))
                logger.warning("auto_commit_failed", error=str(exc))

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

    async def _run_decomposition(
        self,
        *,
        flight_plan: Any,
        raw_content: str,
        codebase_context: Any,
        open_bead_result: Any,
        runway_context_text: str | None,
        skip_briefing: bool = False,
        ctx: dict[str, Any] | None = None,
        ws_cwd: Path,
    ) -> Any:
        """Run briefing + decomposition via Burr.

        Kept as its own method rather than inlined into :meth:`_run` only
        to keep that method readable; there is no alternative driver to
        select between.
        """
        from maverick.agents.briefing.prompts import build_briefing_prompt
        from maverick.burr import BurrWorkflowDriver
        from maverick.events import ProgressEvent
        from maverick.squadron.refuel import RefuelSquadron
        from maverick.workflows.fly_beads.workflow import _cost_sink_for_cwd
        from maverick.workflows.refuel_maverick.burr_graph import (
            REFUEL_TERMINAL_ACTIONS,
            build_refuel_application,
        )
        from maverick.workflows.refuel_maverick.models import (
            DecompositionOutput,
            WorkUnitSpec,
        )

        briefing_prompt = build_briefing_prompt(
            raw_content,
            codebase_context,
            open_bead_context=open_bead_result,
        )

        # Extract success-criteria refs from the FlightPlan so the
        # validator can check coverage.
        sc_refs: tuple[str, ...] = tuple(
            (getattr(sc, "id", None) or getattr(sc, "description", "") or "")
            for sc in (getattr(flight_plan, "success_criteria", ()) or ())
        )
        sc_count = len(sc_refs)
        plan_name = str(getattr(flight_plan, "name", "") or "")
        plan_objective = str(getattr(flight_plan, "objective", "") or "")

        cost_sink = _cost_sink_for_cwd(ws_cwd)
        async with RefuelSquadron(
            cwd=ws_cwd,
            config=self._config,
            cost_sink=cost_sink,
            decomposer_pool_cap=self._config.parallel.decomposer_pool_size,
        ) as squadron:
            # ``decomposer_tiers`` is resolved from config inside the
            # squadron; nothing to thread here.
            event_queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
            # Per-plan refuel cache under
            # ``<cwd>/.maverick/plans/<plan>/refuel-cache/`` so a
            # later resume can read the raw artifacts. The actions
            # treat ``cache_dir`` as advisory — empty disables writes
            # and any OSError is swallowed with a warning.
            cache_dir = (
                str(ws_cwd / ".maverick" / "plans" / plan_name / "refuel-cache")
                if plan_name
                else ""
            )
            app = build_refuel_application(
                squadron=squadron,
                event_queue=event_queue,
                raw_content=raw_content,
                briefing_prompt=briefing_prompt,
                codebase_context=codebase_context,
                open_bead_context=open_bead_result,
                runway_context_text=runway_context_text,
                plan_name=plan_name,
                plan_objective=plan_objective,
                cwd=str(ws_cwd),
                skip_briefing=skip_briefing,
                provider_labels={},
                max_briefing_agents=self._config.parallel.max_briefing_agents,
                decomposer_pool_size=self._config.parallel.decomposer_pool_size,
                success_criteria_count=sc_count,
                expected_sc_refs=sc_refs,
                cache_dir=cache_dir,
            )
            driver = BurrWorkflowDriver(
                app,
                halt_after=REFUEL_TERMINAL_ACTIONS,
                event_queue=event_queue,
            )
            async for evt in driver.events():
                await self._event_queue.put(evt)
            _, _result, state = driver.result

        # Materialize WorkUnitSpec objects + assemble the
        # DecompositionOutput the caller expects.
        work_units: list[WorkUnitSpec] = []
        for spec in state.get("specs") or ():
            if isinstance(spec, WorkUnitSpec):
                work_units.append(spec)
            elif isinstance(spec, dict):
                work_units.append(WorkUnitSpec.model_validate(spec))

        fix_rounds = state.get("fix_rounds", 0)
        if ctx is not None:
            ctx["fix_rounds"] = fix_rounds
            ctx["supervisor_epic"] = state.get("epic")
            ctx["supervisor_epic_id"] = state.get("epic_id", "")
            ctx["supervisor_work_beads"] = list(state.get("work_beads") or ())
            ctx["supervisor_created_map"] = dict(state.get("created_map") or {})
            ctx["supervisor_dependencies"] = list(state.get("dependencies") or ())
            ctx["supervisor_deps_wired"] = state.get("deps_wired", 0)

        decomposition = DecompositionOutput(
            work_units=work_units,
            rationale=(f"{len(work_units)} work units via burr ({fix_rounds} fix rounds)"),
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
