"""GenerateFlightPlanWorkflow — PRD to flight plan conversion pipeline."""

from __future__ import annotations

import asyncio
import time
from datetime import date
from pathlib import Path
from typing import Any

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from maverick.exceptions import WorkflowError
from maverick.executor.config import StepConfig
from maverick.executor.errors import OutputSchemaValidationError
from maverick.flight.models import FlightPlan, Scope, SuccessCriterion
from maverick.flight.serializer import serialize_flight_plan
from maverick.flight.validator import validate_flight_plan_file
from maverick.logging import get_logger
from maverick.types import StepType
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.generate_flight_plan.constants import (
    BRIEFING,
    BRIEFING_CODEBASE_ANALYST,
    BRIEFING_CONTRARIAN,
    BRIEFING_CRITERIA_WRITER,
    BRIEFING_SCOPIST,
    GENERATE,
    READ_PRD,
    VALIDATE,
    WORKFLOW_NAME,
    WRITE_FLIGHT_PLAN,
)
from maverick.workflows.generate_flight_plan.models import (
    FlightPlanOutput,
    GenerateFlightPlanResult,
)

logger = get_logger(__name__)

# Transient errors that warrant retry (API/network errors)
_TRANSIENT_ERRORS = (
    TimeoutError,
    ConnectionError,
    OSError,
)


def _build_generate_prompt(
    prd_content: str,
    name: str,
    today: date,
    briefing_content: str | None = None,
) -> str:
    """Build the prompt for the flight plan generation agent.

    Args:
        prd_content: Raw PRD text content.
        name: Kebab-case flight plan name.
        today: Current date for the flight plan.
        briefing_content: Optional pre-flight briefing Markdown to include.

    Returns:
        Full prompt string for the agent.
    """
    briefing_section = ""
    if briefing_content:
        briefing_section = f"""
## Pre-Flight Briefing

The following briefing was produced by specialist agents that analyzed the PRD
and codebase. Use it to inform your scope, criteria, and constraints — but
apply your own judgment.

{briefing_content}
"""

    return f"""\
Generate a Maverick flight plan from the following PRD.

## Flight Plan Name
{name}

## Today's Date
{today.isoformat()}

## PRD Content

{prd_content}
{briefing_section}
## Output Requirements

Explore the codebase to understand the project structure and reference actual
files and modules in your scope and constraints.

IMPORTANT: Return the JSON object directly in your response text as a fenced
```json ... ``` code block. Do NOT write it to a file. The JSON must have these
exact fields:
- "name": "{name}" (use this exact name)
- "version": "1"
- "objective": A clear, measurable objective paragraph
- "success_criteria": A list of specific, verifiable success criterion strings
- "in_scope": A list of items that are in scope (reference actual project paths)
- "out_of_scope": A list of items explicitly out of scope
- "boundaries": A list of boundary conditions defining the scope limits
- "context": Background context for implementers
- "constraints": A list of technical constraints
- "notes": Any additional notes

Every success criterion must be independently verifiable. Use measurable
language.
"""


def _convert_output_to_flight_plan(
    output: FlightPlanOutput,
    today: date,
) -> FlightPlan:
    """Convert a FlightPlanOutput agent response to a FlightPlan model.

    Args:
        output: Validated agent output.
        today: Current date for the created field.

    Returns:
        FlightPlan model instance ready for serialization.
    """
    return FlightPlan(
        name=output.name,
        version=output.version,
        created=today,
        tags=(),
        objective=output.objective,
        success_criteria=tuple(
            SuccessCriterion(text=sc, checked=False) for sc in output.success_criteria
        ),
        scope=Scope(
            in_scope=tuple(output.in_scope),
            out_of_scope=tuple(output.out_of_scope),
            boundaries=tuple(output.boundaries),
        ),
        context=output.context,
        constraints=tuple(output.constraints),
        notes=output.notes,
    )


class GenerateFlightPlanWorkflow(PythonWorkflow):
    """Workflow that generates a flight plan from a PRD using an AI agent.

    Pipeline:
    1. read_prd - Read PRD file content
    2. generate - Agent reads PRD + explores codebase, produces structured output
    3. validate - Validate the generated flight plan against V1-V9 rules
    4. write_flight_plan - Write the flight plan file to disk

    Args:
        config: Project configuration (MaverickConfig).
        registry: Component registry for action/agent dispatch.
        checkpoint_store: Optional checkpoint persistence backend.
        step_executor: StepExecutor for agent step execution (required for generate).
        workflow_name: Identifier for this workflow instance.
    """

    def __init__(self, **kwargs: Any) -> None:
        if "workflow_name" not in kwargs:
            kwargs["workflow_name"] = WORKFLOW_NAME
        super().__init__(**kwargs)

    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the generate-flight-plan pipeline.

        Args:
            inputs: Workflow inputs. Required: ``prd_content`` (str),
                ``name`` (str), ``output_dir`` (str).

        Returns:
            Output dict matching GenerateFlightPlanResult.to_dict() contract.

        Raises:
            WorkflowError: If required inputs are missing.
        """
        prd_content: str = inputs.get("prd_content", "")
        if not prd_content:
            raise WorkflowError("'prd_content' input is required")
        name: str = inputs.get("name", "")
        if not name:
            raise WorkflowError("'name' input is required")
        output_dir: str = inputs.get("output_dir", ".maverick/plans")
        skip_briefing: bool = inputs.get("skip_briefing", False)

        output_path = Path(output_dir)
        plan_dir = output_path / name
        target_file = plan_dir / "flight-plan.md"
        today = date.today()

        # ------------------------------------------------------------------
        # Step 1: Read PRD
        # ------------------------------------------------------------------
        await self.emit_step_started(READ_PRD)
        prd_lines = prd_content.strip().splitlines()
        prd_size = len(prd_content)
        title_heuristic = prd_lines[0].lstrip("#").strip() if prd_lines else "(empty)"
        await self.emit_output(
            READ_PRD,
            f'PRD: "{title_heuristic}" ({prd_size:,} chars, {len(prd_lines)} lines)',
        )
        await self.emit_step_completed(READ_PRD, output={"prd_size": prd_size})

        # ------------------------------------------------------------------
        # Step 2: Pre-Flight Briefing Room (optional)
        # ------------------------------------------------------------------
        briefing_content: str | None = None
        briefing_generated = False

        if not skip_briefing:
            from maverick.agents.preflight_briefing.prompts import (
                build_preflight_briefing_prompt,
                build_preflight_contrarian_prompt,
            )
            from maverick.preflight_briefing.models import (
                CodebaseAnalystBrief,
                CriteriaWriterBrief,
                PreFlightContrarianBrief,
                ScopistBrief,
            )
            from maverick.preflight_briefing.serializer import (
                serialize_preflight_briefing,
            )
            from maverick.preflight_briefing.synthesis import (
                synthesize_preflight_briefing,
            )

            await self.emit_step_started(BRIEFING)

            if self._step_executor is None:
                raise WorkflowError("step_executor is required for the briefing step")

            briefing_prompt = build_preflight_briefing_prompt(prd_content)

            async def _briefing_event_cb(event: Any) -> None:
                await self._event_queue.put(event)

            try:
                # Parallel: Scopist + CodebaseAnalyst + CriteriaWriter
                # Wrap each agent to emit progress events on completion.
                async def _run_agent(
                    label: str,
                    step_name: str,
                    agent_name: str,
                    prompt: dict[str, Any],
                    output_schema: type[Any],
                ) -> Any:
                    await self.emit_output(
                        BRIEFING, f"\u23f3 {label}...", level="info",
                    )
                    t0 = time.monotonic()
                    result = await self._step_executor.execute(
                        step_name=step_name,
                        agent_name=agent_name,
                        prompt=prompt,
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

                scopist_result, analyst_result, criteria_result = (
                    await asyncio.gather(
                        _run_agent(
                            "Scopist", BRIEFING_SCOPIST,
                            "scopist", briefing_prompt, ScopistBrief,
                        ),
                        _run_agent(
                            "CodebaseAnalyst", BRIEFING_CODEBASE_ANALYST,
                            "codebase_analyst", briefing_prompt,
                            CodebaseAnalystBrief,
                        ),
                        _run_agent(
                            "CriteriaWriter", BRIEFING_CRITERIA_WRITER,
                            "criteria_writer", briefing_prompt,
                            CriteriaWriterBrief,
                        ),
                    )
                )

                if (
                    not scopist_result.output
                    or not analyst_result.output
                    or not criteria_result.output
                ):
                    raise WorkflowError(
                        "One or more briefing agents returned no output"
                    )

                # Sequential: Contrarian reviews all 3
                contrarian_prompt = build_preflight_contrarian_prompt(
                    prd_content,
                    scopist_result.output,
                    analyst_result.output,
                    criteria_result.output,
                )
                await self.emit_output(
                    BRIEFING, "\u23f3 Contrarian...", level="info",
                )
                t0 = time.monotonic()
                contrarian_result = await self._step_executor.execute(
                    step_name=BRIEFING_CONTRARIAN,
                    agent_name="preflight_contrarian",
                    prompt=contrarian_prompt,
                    output_schema=PreFlightContrarianBrief,
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
                briefing_doc = synthesize_preflight_briefing(
                    name,
                    scopist_result.output,
                    analyst_result.output,
                    criteria_result.output,
                    contrarian_result.output,
                )

                briefing_content = serialize_preflight_briefing(briefing_doc)
                briefing_generated = True

            except Exception as exc:
                await self.emit_step_failed(BRIEFING, str(exc))
                raise

            await self.emit_output(
                BRIEFING,
                f"Briefing complete: {len(briefing_doc.key_scope_items)} scope items, "
                f"{len(briefing_doc.key_criteria)} criteria, "
                f"{len(briefing_doc.open_questions)} open questions",
            )
            await self.emit_step_completed(
                BRIEFING,
                output={
                    "key_scope_items": list(briefing_doc.key_scope_items),
                    "key_criteria": list(briefing_doc.key_criteria),
                    "open_questions": list(briefing_doc.open_questions),
                },
            )

        # ------------------------------------------------------------------
        # Step 3: Generate flight plan via agent
        # ------------------------------------------------------------------
        await self.emit_step_started(
            GENERATE,
            step_type=StepType.AGENT,
            agent_name="flight-plan-generator",
            model_id=self._resolve_display_model(),
        )

        prompt = _build_generate_prompt(
            prd_content, name, today, briefing_content=briefing_content
        )

        flight_plan_output: FlightPlanOutput | None = None
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
                            "step_executor is required for the generate step"
                        )

                    async def _event_cb(event: Any) -> None:
                        await self._event_queue.put(event)

                    executor_result = await self._step_executor.execute(
                        step_name=GENERATE,
                        agent_name="flight_plan_generator",
                        prompt=prompt,
                        output_schema=FlightPlanOutput,
                        event_callback=_event_cb,
                        config=StepConfig(timeout=600),
                    )

                    if executor_result.output is None:
                        raise WorkflowError(
                            "Flight plan generator agent returned no output"
                        )

                    flight_plan_output = executor_result.output
        except OutputSchemaValidationError:
            await self.emit_step_failed(
                GENERATE, "Agent output failed schema validation"
            )
            raise
        except Exception as exc:
            await self.emit_step_failed(GENERATE, str(exc))
            raise

        if flight_plan_output is None:
            raise WorkflowError("Generate step completed but produced no output")
        await self.emit_output(
            GENERATE,
            f"Generated {len(flight_plan_output.success_criteria)} success criteria",
        )
        await self.emit_step_completed(
            GENERATE,
            step_type=StepType.AGENT,
        )

        # Convert agent output to FlightPlan model
        flight_plan = _convert_output_to_flight_plan(flight_plan_output, today)

        # ------------------------------------------------------------------
        # Step 3: Write flight plan file
        # ------------------------------------------------------------------
        await self.emit_step_started(WRITE_FLIGHT_PLAN)
        try:
            plan_dir.mkdir(parents=True, exist_ok=True)
            content = serialize_flight_plan(flight_plan)
            target_file.write_text(content, encoding="utf-8")

            # Persist briefing alongside the flight plan
            if briefing_generated and briefing_content:
                briefing_file = plan_dir / "briefing.md"
                briefing_file.write_text(briefing_content, encoding="utf-8")
        except Exception as exc:
            await self.emit_step_failed(WRITE_FLIGHT_PLAN, str(exc))
            raise
        await self.emit_output(
            WRITE_FLIGHT_PLAN,
            f"Wrote flight plan to {target_file}",
        )
        await self.emit_step_completed(WRITE_FLIGHT_PLAN)

        # ------------------------------------------------------------------
        # Step 4: Validate generated flight plan
        # ------------------------------------------------------------------
        await self.emit_step_started(VALIDATE)
        validation_passed = True
        try:
            issues = validate_flight_plan_file(target_file)
            if issues:
                validation_passed = False
                for issue in issues:
                    await self.emit_output(
                        VALIDATE,
                        f"[{issue.location}] {issue.message}",
                        level="warning",
                    )
                await self.emit_output(
                    VALIDATE,
                    f"{len(issues)} validation issue(s) found (non-blocking)",
                    level="warning",
                )
            else:
                await self.emit_output(
                    VALIDATE,
                    "Flight plan passes all V1-V9 validation checks",
                    level="success",
                )
        except Exception as exc:
            validation_passed = False
            await self.emit_output(
                VALIDATE,
                f"Validation error: {exc}",
                level="warning",
            )
        await self.emit_step_completed(VALIDATE, output={"passed": validation_passed})

        # ------------------------------------------------------------------
        # Final result
        # ------------------------------------------------------------------
        result = GenerateFlightPlanResult(
            flight_plan_path=str(target_file),
            name=name,
            success_criteria_count=len(flight_plan_output.success_criteria),
            validation_passed=validation_passed,
            briefing_generated=briefing_generated,
        )
        return result.to_dict()
