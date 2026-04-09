"""RefuelMaverickWorkflow — flight plan decomposition pipeline."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from maverick.briefing.models import (
    ContrarianBrief,
    NavigatorBrief,
    ReconBrief,
    StructuralistBrief,
)
from maverick.briefing.serializer import serialize_briefing
from maverick.briefing.synthesis import synthesize_briefing
from maverick.exceptions import WorkflowError
from maverick.executor.errors import OutputSchemaValidationError
from maverick.flight.loader import FlightPlanFile
from maverick.flight.serializer import serialize_work_unit
from maverick.library.actions.beads import create_beads, wire_dependencies
from maverick.library.actions.cross_plan_deps import (
    resolve_plan_epic_ids,
    wire_cross_plan_dependencies,
)
from maverick.library.actions.decompose import (
    SCCoverageError,
    build_detail_prompt,
    build_outline_prompt,
    convert_specs_to_work_units,
    gather_codebase_context,
    merge_outline_and_details,
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
    DECOMPOSE_DETAIL,
    DECOMPOSE_OUTLINE,
    DERIVE_VERIFICATION,
    DETAIL_BATCH_SIZE,
    GATHER_CONTEXT,
    MAX_DECOMPOSE_ATTEMPTS,
    PARSE_FLIGHT_PLAN,
    VALIDATE,
    WIRE_CROSS_PLAN_DEPS,
    WIRE_DEPS,
    WORKFLOW_NAME,
    WRITE_WORK_UNITS,
)
from maverick.workflows.refuel_maverick.models import (
    DecompositionOutline,
    DecompositionOutput,
    DetailBatchOutput,
    RefuelMaverickResult,
)

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
        # ------------------------------------------------------------------
        # Step 2.8: Derive verification properties from acceptance criteria
        # ------------------------------------------------------------------
        # A dedicated agent reads the flight plan's success criteria plus
        # the codebase context and produces executable test assertions.
        # These become the deterministic spec compliance gate during fly.
        verification_properties = getattr(
            flight_plan, "verification_properties", ""
        )
        _derive_vp = (
            not verification_properties
            and self._step_executor is not None
            and not dry_run
            and len(flight_plan.success_criteria) > 0
            and len(codebase_context.files) > 0
        )
        if _derive_vp:
            await self.emit_step_started(DERIVE_VERIFICATION)
            try:
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
                    + "\n".join(
                        f"- {f.path}" for f in codebase_context.files
                    )
                    + "\n"
                )
                try:
                    vp_result = await self._step_executor.execute(
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
                        fp_text = await asyncio.to_thread(
                            flight_plan_path.read_text, "utf-8"
                        )
                        if "\n## Verification Properties" not in fp_text:
                            fp_text += (
                                "\n\n## Verification Properties\n\n"
                                + verification_properties
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
                logger.warning(
                    "derive_verification_failed", error=str(exc)
                )
                await self.emit_output(
                    DERIVE_VERIFICATION,
                    f"Verification derivation failed (non-fatal): {exc}",
                    level="warning",
                )
            await self.emit_step_completed(DERIVE_VERIFICATION)

        # Re-read raw content in case VP was appended
        import contextlib

        with contextlib.suppress(Exception):
            raw_content = await asyncio.to_thread(
                flight_plan_path.read_text, "utf-8"
            )

        briefing_doc = None
        briefing_path_str: str | None = None

        if not skip_briefing:
            from maverick.agents.briefing.prompts import (
                build_briefing_prompt,
                build_contrarian_prompt,
            )

            await self.emit_step_started(BRIEFING, step_type=StepType.AGENT)

            briefing_prompt = build_briefing_prompt(
                raw_content,
                codebase_context,
                open_bead_context=open_bead_result,
            )

            try:
                # Parallel: Navigator + Structuralist + Recon
                nav_result, struct_result, recon_result = await asyncio.gather(
                    self.execute_agent(
                        step_name=BRIEFING_NAVIGATOR,
                        agent_name="navigator",
                        label="Navigator",
                        prompt=briefing_prompt,
                        output_schema=NavigatorBrief,
                        parent_step=BRIEFING,
                    ),
                    self.execute_agent(
                        step_name=BRIEFING_STRUCTURALIST,
                        agent_name="structuralist",
                        label="Structuralist",
                        prompt=briefing_prompt,
                        output_schema=StructuralistBrief,
                        parent_step=BRIEFING,
                    ),
                    self.execute_agent(
                        step_name=BRIEFING_RECON,
                        agent_name="recon",
                        label="Recon",
                        prompt=briefing_prompt,
                        output_schema=ReconBrief,
                        parent_step=BRIEFING,
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
                contrarian_result = await self.execute_agent(
                    step_name=BRIEFING_CONTRARIAN,
                    agent_name="contrarian",
                    label="Contrarian",
                    prompt=contrarian_prompt,
                    output_schema=ContrarianBrief,
                    parent_step=BRIEFING,
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
        # Steps 3-4: Decompose + Validate (with retry on validation failure)
        #
        # Two-pass chunked decomposition:
        #   3a. Outline pass: structural skeleton (IDs, tasks, deps, file scopes)
        #   3b. Detail pass: instructions, acceptance criteria, verification
        #       (batched to stay within output token limits)
        #   4.  Validate: dependency graph + SC coverage
        #
        # If validation fails (e.g. uncovered SCs), the error is fed back
        # to the outline prompt and the decomposer retries.
        # ------------------------------------------------------------------
        decomposition: DecompositionOutput | None = None
        coverage_warnings: list[str] = []
        validation_feedback: str | None = None

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

        # Check if executor supports multi-turn sessions (actor-mailbox path)
        _can_use_supervisor = (
            self._step_executor is not None
            and hasattr(self._step_executor, "create_session")
        )

        if _can_use_supervisor:
            decomposition = await self._decompose_with_supervisor(
                flight_plan=flight_plan,
                raw_content=raw_content,
                codebase_context=codebase_context,
                briefing_doc=briefing_doc,
                runway_context_text=runway_context_text,
                run_dir=run_dir,
            )
        else:
            # --- Legacy decompose retry loop ---
            pass  # fall through to existing for-loop below

        if not _can_use_supervisor:
            pass  # marker

        for attempt in range(1, MAX_DECOMPOSE_ATTEMPTS + 1):
            if _can_use_supervisor:
                break  # skip legacy loop — supervisor already ran
            await self.emit_step_started(DECOMPOSE, step_type=StepType.AGENT)

            # --- 3a: Outline pass ---
            outline_prompt = build_outline_prompt(
                raw_content,
                codebase_context,
                briefing=briefing_doc,
                runway_context=runway_context_text,
            )
            if validation_feedback:
                outline_prompt += (
                    f"\n\n## PREVIOUS ATTEMPT FAILED VALIDATION\n"
                    f"Your previous decomposition was rejected:\n"
                    f"{validation_feedback}\n\n"
                    f"Fix these issues in your new decomposition."
                )

            try:
                outline_result = await self.execute_agent(
                    step_name=DECOMPOSE_OUTLINE,
                    agent_name="decomposer",
                    label=f"Decomposer (outline, attempt {attempt}/"
                    f"{MAX_DECOMPOSE_ATTEMPTS})",
                    prompt=outline_prompt,
                    output_schema=DecompositionOutline,
                    timeout=600,
                )
            except OutputSchemaValidationError:
                await self.emit_step_failed(
                    DECOMPOSE, "Outline pass failed schema validation"
                )
                raise
            except Exception as exc:
                await self.emit_step_failed(DECOMPOSE, str(exc))
                raise

            outline: DecompositionOutline | None = outline_result.output
            if outline is None:
                raise WorkflowError("Outline pass completed but produced no output")

            unit_count = len(outline.work_units)
            await self.emit_output(
                DECOMPOSE,
                f"Outline: {unit_count} work units identified",
            )

            # --- 3b: Detail pass (batched) ---
            all_ids = [wu.id for wu in outline.work_units]
            batches: list[list[str]] = [
                all_ids[i : i + DETAIL_BATCH_SIZE]
                for i in range(0, len(all_ids), DETAIL_BATCH_SIZE)
            ]
            outline_json = outline.model_dump_json(indent=2)

            detail_outputs: list[DetailBatchOutput] = []

            async def _run_detail_batch(
                batch_ids: list[str], label_prefix: str
            ) -> list[DetailBatchOutput]:
                """Run a detail batch with file-based output + binary-split retry."""
                import json as _json

                from maverick.exceptions.agent import MalformedResponseError

                # Create file path for decomposer to write JSON to
                detail_dir = run_dir / "decompose-output"
                detail_dir.mkdir(parents=True, exist_ok=True)
                batch_file = detail_dir / f"detail-{'_'.join(batch_ids[:3])}.json"
                batch_file.unlink(missing_ok=True)

                detail_prompt = build_detail_prompt(
                    raw_content,
                    outline_json,
                    batch_ids,
                    output_file_path=str(batch_file),
                    verification_properties=getattr(
                        flight_plan, "verification_properties", ""
                    ),
                )
                try:
                    detail_result = await self.execute_agent(
                        step_name=DECOMPOSE_DETAIL,
                        agent_name="decomposer",
                        label=label_prefix,
                        prompt=detail_prompt,
                        output_schema=DetailBatchOutput,
                        output_file_path=str(batch_file),
                        timeout=600,
                    )
                    if isinstance(detail_result.output, DetailBatchOutput):
                        return [detail_result.output]
                    raise WorkflowError(
                        f"{label_prefix} completed but no output file"
                        f" or parseable text produced"
                    )
                except (
                    OutputSchemaValidationError,
                    MalformedResponseError,
                    WorkflowError,
                    Exception,
                ) as exc:
                    # File fallback failed — proceed with binary split
                    # only for parse errors, not quota/network errors
                    if not isinstance(
                        exc,
                        (
                            OutputSchemaValidationError,
                            MalformedResponseError,
                        ),
                    ):
                        raise
                    if len(batch_ids) <= 1:
                        raise  # Can't split a single unit further
                    # Binary split: retry each half separately
                    mid = len(batch_ids) // 2
                    left_ids, right_ids = batch_ids[:mid], batch_ids[mid:]
                    await self.emit_output(
                        DECOMPOSE,
                        f"Detail batch truncated ({len(batch_ids)} units),"
                        f" splitting into {len(left_ids)}+{len(right_ids)}",
                        level="warning",
                    )
                    left = await _run_detail_batch(
                        left_ids, f"{label_prefix} [L]"
                    )
                    right = await _run_detail_batch(
                        right_ids, f"{label_prefix} [R]"
                    )
                    return left + right

            for batch_idx, batch_ids in enumerate(batches):
                batch_label = f"Decomposer (detail {batch_idx + 1}/{len(batches)})"
                try:
                    batch_results = await _run_detail_batch(
                        batch_ids, batch_label
                    )
                    detail_outputs.extend(batch_results)
                except Exception as exc:
                    await self.emit_step_failed(DECOMPOSE, str(exc))
                    raise

            # --- Merge outline + details ---
            try:
                decomposition = merge_outline_and_details(outline, detail_outputs)
            except ValueError as exc:
                await self.emit_step_failed(DECOMPOSE, str(exc))
                raise WorkflowError(
                    f"Failed to merge outline and detail passes: {exc}"
                ) from exc

            await self.emit_output(
                DECOMPOSE,
                f"Decomposed into {len(decomposition.work_units)} work units"
                f" ({len(batches)} detail batch(es))",
            )
            if decomposition.rationale:
                first_sentence = decomposition.rationale.split(". ")[0].rstrip(".")
                await self.emit_output(
                    DECOMPOSE,
                    f"Rationale: {first_sentence}",
                    level="info",
                )
            await self.emit_step_completed(
                DECOMPOSE,
                output={
                    "work_unit_count": len(decomposition.work_units),
                    "rationale": decomposition.rationale,
                },
            )

            # --- Step 4: Validate ---
            await self.emit_step_started(VALIDATE)
            try:
                # Extract SC ref IDs from the flight plan text.
                # Success criteria may use "SC-B1-default: ..." prefix
                # format, which we extract via regex.
                import re as _re

                _sc_prefix_re = _re.compile(r"^(SC-[\w-]+):\s+")
                sc_refs: list[str] = []
                for sc in flight_plan.success_criteria:
                    m = _sc_prefix_re.match(sc.text)
                    if m:
                        sc_refs.append(m.group(1))

                coverage_warnings = validate_decomposition(
                    specs=decomposition.work_units,
                    success_criteria_count=len(flight_plan.success_criteria),
                    expected_sc_refs=sc_refs if sc_refs else None,
                )
            except SCCoverageError as exc:
                if attempt < MAX_DECOMPOSE_ATTEMPTS:
                    # Build enriched feedback with the actual SC text so
                    # the decomposer knows *what* each missing criterion says,
                    # not just its reference number.
                    feedback_lines = [str(exc), ""]
                    for gap in exc.gaps:
                        # gap format: "SC-017 not explicitly covered …"
                        ref = gap.split(" ", 1)[0]  # "SC-017"
                        try:
                            idx = int(ref.split("-")[1]) - 1  # 0-based
                            sc_text = flight_plan.success_criteria[idx].text
                            feedback_lines.append(f"- {ref}: {sc_text}")
                        except (IndexError, ValueError):
                            feedback_lines.append(f"- {ref}: (could not resolve text)")
                    feedback_lines.append(
                        "\nEnsure every criterion above has at least one "
                        "work-unit acceptance criterion with a matching trace_ref."
                    )
                    validation_feedback = "\n".join(feedback_lines)
                    await self.emit_output(
                        VALIDATE,
                        f"Validation failed (attempt {attempt}/"
                        f"{MAX_DECOMPOSE_ATTEMPTS}): {exc}",
                        level="warning",
                    )
                    await self.emit_step_failed(VALIDATE, str(exc))
                    continue
                # Final attempt — propagate the failure
                await self.emit_step_failed(VALIDATE, str(exc))
                raise WorkflowError(str(exc)) from exc
            except ValueError as exc:
                # Structural errors (circular deps, dangling refs) — no retry
                await self.emit_step_failed(VALIDATE, str(exc))
                raise WorkflowError(str(exc)) from exc

            # Validation passed — break out of retry loop
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
            break  # Success — exit retry loop
        else:
            # Loop exhausted without break (should not reach here due to raise above)
            raise WorkflowError(
                f"Decomposition failed after {MAX_DECOMPOSE_ATTEMPTS} attempts"
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
            # Write to BOTH plans/ (reusable) and runs/ (execution context)
            run_wu_dir = run_dir / "work-units"
            await asyncio.to_thread(
                run_wu_dir.mkdir, parents=True, exist_ok=True
            )
            for wu in work_units:
                filename = f"{wu.sequence:03d}-{wu.id}.md"
                content = serialize_work_unit(wu)
                # Plans directory (reusable artifact)
                file_path = work_units_dir / filename
                await asyncio.to_thread(
                    file_path.write_text, content, "utf-8"
                )
                # Run directory (execution context)
                run_file_path = run_wu_dir / filename
                await asyncio.to_thread(
                    run_file_path.write_text, content, "utf-8"
                )
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

                # Wire cross-epic dependencies: new epic is blocked by
                # any existing open epics. This serializes epic execution
                # so fly processes them in order.
                try:
                    all_beads = await _bead_client.query(
                        "type=epic AND status=open"
                    )
                    existing_epics = [
                        b for b in all_beads
                        if b.id != new_epic_id
                    ]
                    for existing in existing_epics:
                        await _bead_client.add_dependency(
                            BeadDependency(
                                blocker_id=existing.id,
                                blocked_id=new_epic_id,
                            )
                        )
                        logger.info(
                            "cross_epic_dep_wired",
                            blocker=existing.id,
                            blocked=new_epic_id,
                        )
                    if existing_epics:
                        await self.emit_output(
                            CREATE_BEADS,
                            f"Wired {len(existing_epics)} cross-epic "
                            f"dependency(ies) — new epic waits for "
                            f"existing work to complete",
                        )
                except Exception as exc:
                    logger.warning(
                        "cross_epic_dep_failed",
                        epic_id=new_epic_id,
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
            run_id=run_id,
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

    async def _decompose_with_supervisor(
        self,
        *,
        flight_plan: Any,
        raw_content: str,
        codebase_context: str,
        briefing_doc: Any,
        runway_context_text: str,
        run_dir: Path | None,
    ) -> Any:
        """Decompose using actor-mailbox supervisor.

        Replaces the retry loop with persistent-session decomposer
        that receives targeted fix requests instead of full redos.

        Returns a DecompositionOutput (same type as the legacy loop).
        """
        from maverick.workflows.refuel_maverick.models import (
            DecompositionOutput,
            WorkUnitSpec,
        )

        import asyncio

        from thespian.actors import ActorSystem

        from maverick.actors.bead_creator import BeadCreatorActor
        from maverick.actors.decomposer import DecomposerActor
        from maverick.actors.refuel_supervisor import RefuelSupervisorActor
        from maverick.actors.validator import ValidatorActor

        await self.emit_step_started(DECOMPOSE, step_type=StepType.AGENT)

        # Build initial payload
        initial_payload = {
            "flight_plan_content": raw_content,
            "codebase_context": codebase_context,
            "briefing": briefing_doc,
            "runway_context": runway_context_text or None,
            "verification_properties": getattr(
                flight_plan, "verification_properties", ""
            ),
        }

        await self.emit_output(
            DECOMPOSE,
            "Decomposing with Thespian actor system",
            level="info",
        )

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
                import time; time.sleep(1)
            except Exception:
                pass

        asys = ActorSystem(
            "multiprocTCPBase",
            capabilities={"Admin Port": THESPIAN_PORT},
        )

        # Register atexit handler for crash safety
        def _cleanup_actor_system():
            try:
                asys.shutdown()
            except Exception:
                pass
        atexit.register(_cleanup_actor_system)

        try:
            # Create child actors
            decomposer_addr = asys.createActor(DecomposerActor)
            validator_addr = asys.createActor(ValidatorActor)
            bead_creator_addr = asys.createActor(BeadCreatorActor)

            # Create supervisor with globalName for MCP server discovery
            supervisor_addr = asys.createActor(
                RefuelSupervisorActor,
                globalName="supervisor-inbox",
            )

            # Init child actors
            asys.ask(decomposer_addr, {
                "type": "init",
                "cwd": str(Path.cwd()),
                "mcp_tools": "submit_outline,submit_details,submit_fix",
                "admin_port": THESPIAN_PORT,
            }, timeout=10)

            asys.ask(validator_addr, {
                "type": "init",
                "flight_plan": flight_plan,
            }, timeout=10)

            asys.ask(bead_creator_addr, {
                "type": "init",
                "plan_name": flight_plan.name if hasattr(flight_plan, "name") else "",
                "plan_objective": flight_plan.objective if hasattr(flight_plan, "objective") else "",
            }, timeout=10)

            # Init supervisor with child addresses and config
            asys.ask(supervisor_addr, {
                "type": "init",
                "decomposer_addr": decomposer_addr,
                "validator_addr": validator_addr,
                "bead_creator_addr": bead_creator_addr,
                "initial_payload": initial_payload,
                "config": {"flight_plan": flight_plan},
            }, timeout=10)

            # Start decomposition and wait for result
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: asys.ask(supervisor_addr, "start", timeout=3600),
            )

        finally:
            asys.shutdown()
            atexit.unregister(_cleanup_actor_system)

        if not result or not result.get("success"):
            from maverick.exceptions import WorkflowError

            raise WorkflowError(
                f"Decomposition failed: {result.get('error', 'unknown') if result else 'no result'}",
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
            rationale=f"{len(work_units)} work units via supervisor"
            f" ({fix_rounds} fix rounds)",
        )

        await self.emit_output(
            DECOMPOSE,
            f"Decomposed into {len(work_units)} work units"
            f" ({fix_rounds} fix rounds)",
            level="success",
        )
        await self.emit_step_completed(
            DECOMPOSE,
            {"work_unit_count": len(work_units)},
        )

        return decomposition
