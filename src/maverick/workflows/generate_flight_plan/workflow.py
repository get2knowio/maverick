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
        # Steps 2-5: Thespian actor system handles briefing, generation,
        # validation, and writing via supervisor-driven message routing.
        # ------------------------------------------------------------------
        result = await self._generate_with_thespian(
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

    async def _generate_with_thespian(
        self,
        *,
        prd_content: str,
        name: str,
        plan_dir: Path,
        skip_briefing: bool,
    ) -> dict[str, Any]:
        """Generate flight plan using Thespian actor system.

        Creates actors for parallel briefing, contrarian, generator,
        validator, and writer. The supervisor routes messages.
        """
        import atexit
        import socket

        from thespian.actors import ActorSystem

        from maverick.actors.briefing import BriefingActor
        from maverick.actors.generator import GeneratorActor
        from maverick.actors.plan_supervisor import PlanSupervisorActor
        from maverick.actors.plan_validator import PlanValidatorActor
        from maverick.actors.plan_writer import PlanWriterActor

        THESPIAN_PORT = 19500

        # Clean up stale admin
        def _port_in_use(port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(("127.0.0.1", port)) == 0

        if _port_in_use(THESPIAN_PORT):
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

        def _cleanup():
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

        atexit.register(_cleanup)

        try:
            cwd = str(Path.cwd())

            # Create briefing actors (4 instances of BriefingActor)
            scopist = asys.createActor(BriefingActor)
            analyst = asys.createActor(BriefingActor)
            criteria = asys.createActor(BriefingActor)
            contrarian = asys.createActor(BriefingActor)

            # Init each with its MCP tool
            for addr, tool in [
                (scopist, "submit_scope"),
                (analyst, "submit_analysis"),
                (criteria, "submit_criteria"),
                (contrarian, "submit_challenge"),
            ]:
                asys.ask(
                    addr,
                    {
                        "type": "init",
                        "mcp_tool": tool,
                        "admin_port": THESPIAN_PORT,
                        "cwd": cwd,
                    },
                    timeout=10,
                )

            # Create generator
            gen = asys.createActor(GeneratorActor)
            asys.ask(
                gen,
                {
                    "type": "init",
                    "admin_port": THESPIAN_PORT,
                    "cwd": cwd,
                },
                timeout=10,
            )

            # Create deterministic actors
            validator = asys.createActor(PlanValidatorActor)
            writer = asys.createActor(PlanWriterActor)
            asys.ask(
                writer,
                {
                    "type": "init",
                    "output_dir": str(plan_dir),
                },
                timeout=10,
            )

            # Create supervisor
            supervisor = asys.createActor(
                PlanSupervisorActor,
                globalName="supervisor-inbox",
            )
            # Resolve provider/model label for CLI display
            from maverick.types import StepType as _StepType

            _resolved = self.resolve_step_config("briefing", _StepType.PYTHON)
            _prov = _resolved.provider or self._resolve_display_provider() or "default"
            _mod = _resolved.model_id or self._resolve_display_model() or "default"
            _label = f"{_prov}/{_mod}"
            _provider_labels = {
                "Scopist": _label,
                "Codebase Analyst": _label,
                "Criteria Writer": _label,
                "Contrarian": _label,
            }

            asys.ask(
                supervisor,
                {
                    "type": "init",
                    "prd_content": prd_content,
                    "plan_name": name,
                    "skip_briefing": skip_briefing,
                    "scopist_addr": scopist,
                    "analyst_addr": analyst,
                    "criteria_addr": criteria,
                    "contrarian_addr": contrarian,
                    "generator_addr": gen,
                    "validator_addr": validator,
                    "writer_addr": writer,
                    "provider_labels": _provider_labels,
                },
                timeout=10,
            )

            # Start and drain events
            asys.tell(supervisor, "start")
            result = await self._drain_supervisor_events(
                asys=asys,
                supervisor=supervisor,
                poll_interval=0.25,
                hard_timeout_seconds=3600.0,
            )

        finally:
            asys.shutdown()
            atexit.unregister(_cleanup)

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
