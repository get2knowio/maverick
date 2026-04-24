"""GenerateFlightPlanWorkflow — PRD to flight plan conversion pipeline."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from maverick.agents.tools import PLANNER_TOOLS
from maverick.exceptions import WorkflowError
from maverick.flight.models import FlightPlan, Scope, SuccessCriterion
from maverick.logging import get_logger
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.generate_flight_plan.constants import (
    BRIEFING,
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
        # Steps 2-5: xoscar supervisor handles briefing, generation,
        # validation, and writing via supervisor-driven message routing.
        # ------------------------------------------------------------------
        result = await self._generate_with_xoscar(
            prd_content=prd_content,
            name=name,
            plan_dir=plan_dir,
            skip_briefing=skip_briefing,
        )
        return GenerateFlightPlanResult(
            flight_plan_path=result.get("flight_plan_path", str(target_file)),
            name=name,
            success_criteria_count=result.get("success_criteria_count", 0),
            validation_passed=result.get("validation_passed", True),
            briefing_generated=result.get("briefing_path") is not None,
        ).to_dict()

    async def _generate_with_supervisor(
        self,
        *,
        prd_content: str,
        name: str,
        plan_dir: Path,
        skip_briefing: bool,
    ) -> Any:
        """Generate flight plan using actor-mailbox supervisor."""
        import shutil as _shutil

        from acp.schema import McpServerStdio

        from maverick.workflows.fly_beads.session_registry import (
            BeadSessionRegistry,
        )
        from maverick.workflows.generate_flight_plan.actors.briefing import (
            BriefingActor,
        )
        from maverick.workflows.generate_flight_plan.actors.generator import (
            GeneratorActor,
        )
        from maverick.workflows.generate_flight_plan.actors.synthesis import (
            SynthesisActor,
        )
        from maverick.workflows.generate_flight_plan.actors.validator import (
            PlanValidatorActor,
        )
        from maverick.workflows.generate_flight_plan.actors.writer import (
            PlanWriterActor,
        )
        from maverick.workflows.generate_flight_plan.supervisor import (
            PlanSupervisor,
        )

        session_registry = BeadSessionRegistry(bead_id="plan")

        # Create inbox directory
        inbox_dir = plan_dir / ".inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)

        _maverick_bin = _shutil.which("maverick") or "maverick"

        def _mcp_config(tool_name: str, agent_name: str) -> McpServerStdio:
            return McpServerStdio(
                name="supervisor-inbox",
                command=_maverick_bin,
                args=[
                    "serve-inbox",
                    "--tools",
                    tool_name,
                    "--output",
                    str(inbox_dir / f"{agent_name}-inbox.json"),
                ],
                env=[],
            )

        from maverick.workflows.base import StepType

        briefing_agents = {
            "scopist": ("submit_scope", "briefing_scopist"),
            "codebase_analyst": ("submit_analysis", "briefing_codebase_analyst"),
            "criteria_writer": ("submit_criteria", "briefing_criteria_writer"),
            "contrarian": ("submit_challenge", "briefing_contrarian"),
        }

        actors: dict[str, Any] = {}

        for agent_name, (tool_name, step_name) in briefing_agents.items():
            config = self.resolve_step_config(
                step_name=step_name,
                step_type=StepType.PYTHON,
                agent_name=agent_name,
            )
            actors[agent_name] = BriefingActor(
                actor_name=agent_name,
                mcp_tool_name=tool_name,
                session_registry=session_registry,
                cwd=Path.cwd(),
                config=config,
                allowed_tools=list(PLANNER_TOOLS),
                inbox_path=inbox_dir / f"{agent_name}-inbox.json",
                mcp_server_config=_mcp_config(tool_name, agent_name),
            )

        gen_config = self.resolve_step_config(
            step_name="generate",
            step_type=StepType.PYTHON,
            agent_name="flight_plan_generator",
        )
        actors["generator"] = GeneratorActor(
            session_registry=session_registry,
            cwd=Path.cwd(),
            config=gen_config,
            allowed_tools=list(PLANNER_TOOLS),
            inbox_path=inbox_dir / "generator-inbox.json",
            mcp_server_config=_mcp_config("submit_flight_plan", "generator"),
        )

        actors["synthesis"] = SynthesisActor(plan_name=name)
        actors["plan_validator"] = PlanValidatorActor()
        actors["plan_writer"] = PlanWriterActor(output_dir=plan_dir)

        supervisor = PlanSupervisor(
            actors=actors,
            prd_content=prd_content,
            plan_name=name,
            skip_briefing=skip_briefing,
        )

        await self.emit_output(
            BRIEFING,
            "Generating flight plan with actor-mailbox supervisor",
            level="info",
        )

        outcome = await supervisor.process()
        session_registry.close_all()

        if not outcome.success:
            from maverick.exceptions import WorkflowError

            raise WorkflowError(
                f"Plan generation failed: {outcome.error}",
                workflow_name="generate-flight-plan",
            )

        await self.emit_output(
            GENERATE,
            f"Generated {outcome.success_criteria_count} success criteria "
            f"({outcome.duration_seconds:.0f}s)",
            level="success",
        )

        return outcome

    async def _generate_with_xoscar(
        self,
        *,
        prd_content: str,
        name: str,
        plan_dir: Path,
        skip_briefing: bool,
    ) -> dict[str, Any]:
        """Generate flight plan using the xoscar actor system.

        Creates a single ``PlanSupervisor`` which spawns its own
        briefing agents, generator, validator, and writer in
        ``__post_create__``. The workflow consumes progress events
        via the ``@xo.generator`` ``run()`` drain helper.
        """
        import xoscar as xo

        from maverick.actors.xoscar.plan_supervisor import PlanInputs, PlanSupervisor
        from maverick.actors.xoscar.pool import actor_pool
        from maverick.types import StepType as _StepType

        cwd = str(Path.cwd())

        # Resolve provider labels so the Rich Live briefing table shows
        # the right provider/model per agent.
        provider_labels: dict[str, str] = {}
        if not skip_briefing:
            for step_name, agent_name, label in (
                ("briefing_scopist", "scopist", "Scopist"),
                (
                    "briefing_codebase_analyst",
                    "codebase_analyst",
                    "Codebase Analyst",
                ),
                (
                    "briefing_criteria_writer",
                    "criteria_writer",
                    "Criteria Writer",
                ),
                ("briefing_contrarian", "contrarian", "Contrarian"),
            ):
                config = self.resolve_step_config(
                    step_name, _StepType.PYTHON, agent_name=agent_name
                )
                provider_labels[label] = self._resolve_display_label_for_config(config)

        # Generator config drives the agent session used for plan generation.
        gen_config = self.resolve_step_config(
            "generate",
            _StepType.PYTHON,
            agent_name="flight_plan_generator",
        )

        supervisor_inputs = PlanInputs(
            cwd=cwd,
            plan_name=name,
            prd_content=prd_content,
            output_dir=str(plan_dir),
            config=gen_config,
            skip_briefing=skip_briefing,
            provider_labels=provider_labels,
        )

        async with actor_pool() as (_pool, address):
            supervisor = await xo.create_actor(
                PlanSupervisor,
                supervisor_inputs,
                address=address,
                uid="plan-supervisor",
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
                f"Plan generation failed: "
                f"{result.get('error', 'unknown') if result else 'no result'}",
                workflow_name="generate-flight-plan",
            )

        await self.emit_output(
            GENERATE,
            f"Generated {result.get('success_criteria_count', 0)} success criteria",
            level="success",
        )

        return result
