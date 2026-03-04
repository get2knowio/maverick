"""RefuelMaverickWorkflow — flight plan decomposition pipeline."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from maverick.exceptions import WorkflowError
from maverick.executor.errors import OutputSchemaValidationError
from maverick.flight.loader import FlightPlanFile
from maverick.flight.serializer import serialize_work_unit
from maverick.library.actions.beads import create_beads, wire_dependencies
from maverick.library.actions.decompose import (
    build_decomposition_prompt,
    convert_specs_to_work_units,
    gather_codebase_context,
    validate_decomposition,
)
from maverick.logging import get_logger
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.refuel_maverick.constants import (
    CREATE_BEADS,
    DECOMPOSE,
    GATHER_CONTEXT,
    PARSE_FLIGHT_PLAN,
    VALIDATE,
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
    5. write_work_units - Write work unit files to .maverick/work-units/<name>/
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
            # .maverick/flight-plans/<name>.md, so parent.parent yields the repo root.
            # If the flight plan is at the filesystem root (parent.name is empty),
            # fall back to None (which gather_codebase_context resolves to Path.cwd()).
            fp_parent = flight_plan_path.parent
            cwd = fp_parent.parent if fp_parent.name else None
            codebase_context = await gather_codebase_context(
                in_scope=flight_plan.scope.in_scope,
                cwd=cwd,
            )
        except Exception as exc:
            await self.emit_step_failed(GATHER_CONTEXT, str(exc))
            raise

        for missing in codebase_context.missing_files:
            await self.emit_output(
                GATHER_CONTEXT, f"File not found: {missing}", level="warning"
            )

        size_kb = codebase_context.total_size // 1024
        await self.emit_output(
            GATHER_CONTEXT,
            f"Gathered context ({len(codebase_context.files)} files, {size_kb}KB)",
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
        # Step 3: Decompose via agent (with retry)
        # ------------------------------------------------------------------
        await self.emit_step_started(DECOMPOSE)

        # Read the raw flight plan content for the prompt
        try:
            raw_content = await asyncio.to_thread(flight_plan_path.read_text, "utf-8")
        except Exception as exc:
            await self.emit_step_failed(DECOMPOSE, str(exc))
            raise

        prompt = build_decomposition_prompt(raw_content, codebase_context)

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

        # Determine output directory
        work_units_dir = Path.cwd() / ".maverick" / "work-units" / flight_plan.name

        # Convert specs to WorkUnit models
        work_units = convert_specs_to_work_units(
            specs=decomposition.work_units,
            flight_plan_name=flight_plan.name,
        )

        written = 0
        try:
            # Clear existing directory
            if work_units_dir.exists():
                await asyncio.to_thread(shutil.rmtree, work_units_dir)
            await asyncio.to_thread(work_units_dir.mkdir, parents=True, exist_ok=True)

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
        )
        return result.to_dict()
