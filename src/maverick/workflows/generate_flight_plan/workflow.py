"""GenerateFlightPlanWorkflow — PRD to flight plan conversion pipeline."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Any

from maverick.exceptions import WorkflowError
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

        # Check if executor supports multi-turn (actor-mailbox path)
        _can_use_supervisor = (
            self._step_executor is not None
            and hasattr(self._step_executor, "create_session")
        )

        if _can_use_supervisor:
            outcome = await self._generate_with_supervisor(
                prd_content=prd_content,
                name=name,
                plan_dir=plan_dir,
                skip_briefing=skip_briefing,
            )
            result = GenerateFlightPlanResult(
                flight_plan_path=outcome.flight_plan_path,
                name=name,
                success_criteria_count=outcome.success_criteria_count,
                validation_passed=outcome.validation_passed,
                briefing_generated=outcome.briefing_path is not None,
            )
            return result.to_dict()

        # ------------------------------------------------------------------
        # Legacy path: Step 2: Pre-Flight Briefing Room (optional)
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

            await self.emit_step_started(BRIEFING, step_type=StepType.AGENT)

            briefing_prompt = build_preflight_briefing_prompt(prd_content)

            try:
                # Parallel: Scopist + CodebaseAnalyst + CriteriaWriter
                scopist_result, analyst_result, criteria_result = await asyncio.gather(
                    self.execute_agent(
                        step_name=BRIEFING_SCOPIST,
                        agent_name="scopist",
                        label="Scopist",
                        prompt=briefing_prompt,
                        output_schema=ScopistBrief,
                        parent_step=BRIEFING,
                    ),
                    self.execute_agent(
                        step_name=BRIEFING_CODEBASE_ANALYST,
                        agent_name="codebase_analyst",
                        label="CodebaseAnalyst",
                        prompt=briefing_prompt,
                        output_schema=CodebaseAnalystBrief,
                        parent_step=BRIEFING,
                    ),
                    self.execute_agent(
                        step_name=BRIEFING_CRITERIA_WRITER,
                        agent_name="criteria_writer",
                        label="CriteriaWriter",
                        prompt=briefing_prompt,
                        output_schema=CriteriaWriterBrief,
                        parent_step=BRIEFING,
                    ),
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
                contrarian_result = await self.execute_agent(
                    step_name=BRIEFING_CONTRARIAN,
                    agent_name="preflight_contrarian",
                    label="Contrarian",
                    prompt=contrarian_prompt,
                    output_schema=PreFlightContrarianBrief,
                    parent_step=BRIEFING,
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
        await self.emit_step_started(GENERATE, step_type=StepType.AGENT)

        prompt = _build_generate_prompt(
            prd_content, name, today, briefing_content=briefing_content
        )

        try:
            executor_result = await self.execute_agent(
                step_name=GENERATE,
                agent_name="flight_plan_generator",
                label="FlightPlanGenerator",
                prompt=prompt,
                output_schema=FlightPlanOutput,
                timeout=600,
            )
        except OutputSchemaValidationError:
            await self.emit_step_failed(
                GENERATE, "Agent output failed schema validation"
            )
            raise
        except Exception as exc:
            await self.emit_step_failed(GENERATE, str(exc))
            raise

        flight_plan_output = executor_result.output
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

    async def _generate_with_supervisor(
        self,
        *,
        prd_content: str,
        name: str,
        plan_dir: Path,
        skip_briefing: bool,
    ) -> Any:
        """Generate flight plan using actor-mailbox supervisor."""
        import sys as _sys

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

        def _mcp_config(tool_name: str, agent_name: str) -> McpServerStdio:
            return McpServerStdio(
                name="supervisor-inbox",
                command=_sys.executable,
                args=[
                    "-m", "maverick.tools.supervisor_inbox.server",
                    "--tools", tool_name,
                    "--output", str(inbox_dir / f"{agent_name}-inbox.json"),
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
                executor=self._step_executor,
                cwd=Path.cwd(),
                config=config,
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
            executor=self._step_executor,
            cwd=Path.cwd(),
            config=gen_config,
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
