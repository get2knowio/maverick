"""GenerateFlightPlanWorkflow — PRD to flight plan conversion pipeline."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from maverick.exceptions import WorkflowError
from maverick.flight.models import FlightPlan, Scope, SuccessCriterion
from maverick.logging import get_logger
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.generate_flight_plan.constants import (
    GENERATE,
    READ_PRD,
    WORKFLOW_NAME,
)
from maverick.workflows.generate_flight_plan.models import (
    FlightPlanOutput,
    GenerateFlightPlanResult,
)

logger = get_logger(__name__)


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
        # The workflow's ``cwd`` is required (Guardrail 7) — the CLI
        # command resolves ``Path.cwd()`` at the entry boundary and
        # threads it through inputs.
        cwd_input: str | None = inputs.get("cwd")
        if not cwd_input:
            raise WorkflowError("'cwd' input is required")

        output_path = Path(output_dir)
        plan_dir = output_path / name
        target_file = plan_dir / "flight-plan.md"

        # ------------------------------------------------------------------
        # Step 1: Read PRD
        # ------------------------------------------------------------------
        await self.emit_step_started(READ_PRD, display_label="Reading PRD")
        prd_lines = prd_content.strip().splitlines()
        prd_size = len(prd_content)
        title_heuristic = prd_lines[0].lstrip("#").strip() if prd_lines else "(empty)"
        await self.emit_output(
            READ_PRD,
            f'PRD: "{title_heuristic}" ({prd_size:,} chars, {len(prd_lines)} lines)',
        )
        await self.emit_step_completed(READ_PRD, output={"prd_size": prd_size})

        # ------------------------------------------------------------------
        # Steps 2-5: briefing, generation, validation, and writing —
        # driven by the Burr application built around the PlanSquadron.
        # ------------------------------------------------------------------
        result = await self._generate_plan(
            prd_content=prd_content,
            name=name,
            plan_dir=plan_dir,
            skip_briefing=skip_briefing,
            cwd=cwd_input,
        )
        return GenerateFlightPlanResult(
            flight_plan_path=result.get("flight_plan_path", str(target_file)),
            name=name,
            success_criteria_count=result.get("success_criteria_count", 0),
            validation_passed=result.get("validation_passed", True),
            briefing_generated=result.get("briefing_path") is not None,
        ).to_dict()

    async def _generate_plan(
        self,
        *,
        prd_content: str,
        name: str,
        plan_dir: Path,
        skip_briefing: bool,
        cwd: str,
    ) -> dict[str, Any]:
        """Run briefing → generation → validation → write via Burr.

        Kept as its own method rather than inlined into :meth:`_run` only
        to keep that method readable; there is no alternative driver to
        select between.
        """
        import asyncio

        from maverick.burr import BurrWorkflowDriver
        from maverick.events import ProgressEvent
        from maverick.squadron.plan import PlanSquadron
        from maverick.types import StepType as _StepType
        from maverick.workflows.fly_beads.workflow import _cost_sink_for_cwd
        from maverick.workflows.generate_flight_plan.burr_graph import (
            PLAN_TERMINAL_ACTIONS,
            build_plan_application,
        )

        provider_labels: dict[str, str] = {}
        if not skip_briefing:
            for step_name, agent_name, label in (
                ("briefing_scopist", "scopist", "Scopist"),
                ("briefing_codebase_analyst", "codebase_analyst", "Codebase Analyst"),
                ("briefing_criteria_writer", "criteria_writer", "Criteria Writer"),
                ("briefing_contrarian", "contrarian", "Contrarian"),
            ):
                config = self.resolve_step_config(
                    step_name, _StepType.PYTHON, agent_name=agent_name
                )
                provider_labels[label] = self._resolve_display_label_for_config(config)

        cost_sink = _cost_sink_for_cwd(Path(cwd))
        async with PlanSquadron(
            cwd=Path(cwd), config=self._config, cost_sink=cost_sink
        ) as squadron:
            event_queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
            app = build_plan_application(
                squadron=squadron,
                event_queue=event_queue,
                prd_content=prd_content,
                plan_name=name,
                output_dir=str(plan_dir),
                skip_briefing=skip_briefing,
                provider_labels=provider_labels,
                max_briefing_agents=self._config.parallel.max_briefing_agents,
            )
            driver = BurrWorkflowDriver(
                app,
                halt_after=PLAN_TERMINAL_ACTIONS,
                event_queue=event_queue,
            )
            async for evt in driver.events():
                await self._event_queue.put(evt)
            _, _result, state = driver.result

        # 056-context-file-protection T025: drain + persist, one
        # end-of-run warning when non-empty.
        #
        # This workflow has no run-metadata concept of its own, so there is
        # no run id to reuse. A random one would put the artifact in a
        # directory holding nothing else and named after nothing — the user
        # is told to read a file they cannot find. Derive a stable id from
        # the plan name instead (``name`` already names a directory under
        # ``output_dir``, so it is filesystem-safe), matching ``land``'s
        # fixed ``"land"`` fallback. The directory carries no
        # ``metadata.json``, so ``find_latest_run``/``find_run_for_epic``
        # skip it and refuel's "Next:" hint is unaffected.
        from maverick.protection.records import drain_and_report

        run_id = f"plan-{name}"
        blocked = await drain_and_report(
            getattr(squadron, "block_collector", None),
            cwd=Path(cwd),
            run_id=run_id,
            workflow=WORKFLOW_NAME,
        )
        if blocked:
            await self.emit_output(
                GENERATE,
                f"{len(blocked)} context-file protection event(s) — see "
                f".maverick/runs/{run_id}/protection-blocks.json",
                level="warning",
            )

        flight_plan_path = state.get("flight_plan_path")
        if not flight_plan_path:
            raise WorkflowError(
                "Burr plan workflow exited without producing a flight plan path",
                workflow_name="generate-flight-plan",
            )

        flight_plan_dict = state.get("flight_plan") or {}
        sc_count = len(flight_plan_dict.get("success_criteria") or ())

        await self.emit_output(
            GENERATE,
            f"Generated {sc_count} success criteria",
            level="success",
        )

        return {
            "success": True,
            "flight_plan_path": flight_plan_path,
            "briefing_path": state.get("briefing_path"),
            "success_criteria_count": sc_count,
            "validation_passed": bool(state.get("validation_passed", True)),
        }
