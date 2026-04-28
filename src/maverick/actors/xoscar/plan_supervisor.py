"""xoscar PlanSupervisor — async-native plan-generation orchestrator.

State machine:

    briefing (3 parallel: scopist + analyst + criteria)
      → contrarian (after the first three land)
      → generator
      → validator (non-blocking)
      → writer
      → done

Agent-owned MCP inbox: each briefing actor forwards its typed payload
to a dedicated supervisor method (``scope_ready``, ``analysis_ready``,
``criteria_ready``, ``challenge_ready``). The generator forwards to
``flight_plan_ready``. Deterministic actors (``PlanValidatorActor``,
``PlanWriterActor``) return typed results via ordinary RPC.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import xoscar as xo

from maverick.actors.xoscar.briefing import BriefingActor
from maverick.actors.xoscar.generator import GeneratorActor
from maverick.actors.xoscar.messages import (
    BriefingRequest,
    GenerateRequest,
    PlanValidateRequest,
    PromptError,
    WritePlanRequest,
)
from maverick.actors.xoscar.plan_validator import PlanValidatorActor
from maverick.actors.xoscar.plan_writer import PlanWriterActor
from maverick.events import (
    AgentCompleted,
    AgentStarted,
    ProgressEvent,
    StepCompleted,
    StepOutput,
    StepStarted,
)
from maverick.logging import get_logger
from maverick.tools.agent_inbox.models import (
    SubmitAnalysisPayload,
    SubmitChallengePayload,
    SubmitCriteriaPayload,
    SubmitFlightPlanPayload,
    SubmitScopePayload,
    SupervisorInboxPayload,
    dump_supervisor_payload,
)
from maverick.types import StepType

logger = get_logger(__name__)

_SOURCE = "plan-supervisor"

# (agent_name, display_label, mcp_tool, supervisor_forward_method)
#
# Agent names match the long-form keys used in maverick.yaml (under
# ``actors.plan.<name>`` / ``agents.<name>``) so per-agent provider/model
# overrides resolve correctly. The display labels remain human-readable.
PLAN_BRIEFING_CONFIG: tuple[tuple[str, str, str, str], ...] = (
    ("scopist", "Scopist", "submit_scope", "scope_ready"),
    ("codebase_analyst", "Codebase Analyst", "submit_analysis", "analysis_ready"),
    ("criteria_writer", "Criteria Writer", "submit_criteria", "criteria_ready"),
    ("contrarian", "Contrarian", "submit_challenge", "challenge_ready"),
)
PARALLEL_PLAN_BRIEFING_NAMES: tuple[str, ...] = (
    "scopist",
    "codebase_analyst",
    "criteria_writer",
)


@dataclass(frozen=True)
class PlanInputs:
    """Construction payload for ``PlanSupervisor``."""

    cwd: str
    plan_name: str
    prd_content: str
    output_dir: str
    config: Any = None
    skip_briefing: bool = False
    provider_labels: dict[str, str] = field(default_factory=dict)
    # Per-agent ACP StepConfig keyed by agent_name (e.g. "scopist",
    # "codebase_analyst", "criteria_writer", "contrarian"). The workflow
    # resolves these via ``actors.plan.<agent_name>`` /
    # ``steps.briefing_<name>`` / ``agents.<name>``. Missing entries fall
    # back to ``config`` (the generator's StepConfig) so older callers
    # remain compatible.
    briefing_configs: dict[str, Any] = field(default_factory=dict)
    # Cap on how many briefing agents may be in-flight concurrently
    # (scopist/codebase_analyst/criteria_writer during the parallel
    # phase). Default 3 matches legacy behaviour. Setting to 1 runs them
    # sequentially.
    max_briefing_agents: int = 3


class PlanSupervisor(xo.Actor):
    """Orchestrates PRD → flight-plan generation."""

    def __init__(self, inputs: PlanInputs) -> None:
        super().__init__()
        if not inputs.cwd:
            raise ValueError("PlanSupervisor requires 'cwd'")
        if not inputs.plan_name:
            raise ValueError("PlanSupervisor requires 'plan_name'")
        if not inputs.output_dir:
            raise ValueError("PlanSupervisor requires 'output_dir'")
        self._inputs = inputs

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __post_create__(self) -> None:
        self._event_queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        self._done = False
        self._terminal_result: dict[str, Any] | None = None
        self._driver_task: asyncio.Task[None] | None = None

        self._briefs: dict[str, SupervisorInboxPayload] = {}
        self._briefing_markdown: str = ""
        self._flight_plan: SubmitFlightPlanPayload | None = None
        self._briefing_start_times: dict[str, float] = {}

        self_ref = self.ref()

        # --- Briefing actors ---
        # Per-agent StepConfig from ``inputs.briefing_configs`` lets each
        # briefing actor run on its own provider/model (e.g. scopist on
        # gemini, codebase_analyst on opencode). When a config is missing
        # for an agent, fall back to ``inputs.config`` (the generator's
        # config) — same shape as before this field was added.
        self._briefing_actors: dict[str, xo.ActorRef] = {}
        if not self._inputs.skip_briefing:
            for agent_name, _label, mcp_tool, forward_method in PLAN_BRIEFING_CONFIG:
                actor_config = self._inputs.briefing_configs.get(agent_name, self._inputs.config)
                self._briefing_actors[agent_name] = await xo.create_actor(
                    BriefingActor,
                    self_ref,
                    agent_name=agent_name,
                    mcp_tool=mcp_tool,
                    forward_method=forward_method,
                    cwd=self._inputs.cwd,
                    config=actor_config,
                    address=self.address,
                    uid=f"{self.uid.decode()}:briefing-{agent_name}",
                )

        # --- Generator, validator, writer ---
        self._generator = await xo.create_actor(
            GeneratorActor,
            self_ref,
            cwd=self._inputs.cwd,
            config=self._inputs.config,
            address=self.address,
            uid=f"{self.uid.decode()}:generator",
        )
        self._validator = await xo.create_actor(
            PlanValidatorActor,
            address=self.address,
            uid=f"{self.uid.decode()}:plan-validator",
        )
        self._writer = await xo.create_actor(
            PlanWriterActor,
            output_dir=self._inputs.output_dir,
            address=self.address,
            uid=f"{self.uid.decode()}:plan-writer",
        )

    async def __pre_destroy__(self) -> None:
        refs: list[xo.ActorRef] = [
            *self._briefing_actors.values(),
            self._generator,
            self._validator,
            self._writer,
        ]
        for ref in refs:
            try:
                await xo.destroy_actor(ref)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "plan_supervisor.destroy_child_failed",
                    uid=getattr(ref, "uid", "?"),
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # Workflow entry point
    # ------------------------------------------------------------------

    @xo.generator
    async def run(self) -> AsyncGenerator[ProgressEvent, None]:
        self._driver_task = asyncio.create_task(self._drive())
        try:
            while True:
                evt = await self._event_queue.get()
                if evt is None:
                    break
                yield evt
        finally:
            if self._driver_task and not self._driver_task.done():
                self._driver_task.cancel()
                try:
                    await self._driver_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    async def _drive(self) -> None:
        try:
            if self._briefing_actors and not self._inputs.skip_briefing:
                await self._run_briefing_phase()
                await self._synthesize_briefing_markdown()
            await self._run_generator_phase()
            await self._run_validation_phase()
            await self._run_write_phase()
        except Exception as exc:  # noqa: BLE001
            logger.exception("plan_supervisor.drive_failed", error=str(exc))
            await self._emit_output(
                "plan",
                f"Plan generation failed: {exc}",
                level="error",
            )
            self._mark_done({"success": False, "error": str(exc)})

    # ------------------------------------------------------------------
    # Briefing phase
    # ------------------------------------------------------------------

    async def _run_briefing_phase(self) -> None:
        import time as _time

        from maverick.agents.preflight_briefing.prompts import (
            build_preflight_briefing_prompt,
        )

        await self._emit_phase_started("briefing", "Briefing")
        briefing_start = _time.monotonic()
        prompt = build_preflight_briefing_prompt(self._inputs.prd_content)

        for agent_name, label, _tool, _method in PLAN_BRIEFING_CONFIG[:3]:
            await self._emit_agent_started(
                "briefing", label, self._inputs.provider_labels.get(label, "")
            )
            self._briefing_start_times[label] = _time.monotonic()
            _ = agent_name

        # Cap concurrent briefings at parallel.max_briefing_agents (default
        # 3 = legacy fan-out). Each briefing is its own claude-agent-acp
        # subprocess; lower this on resource-constrained hosts.
        sem = asyncio.Semaphore(max(1, self._inputs.max_briefing_agents))

        async def _bounded_send(name: str) -> None:
            async with sem:
                await self._briefing_actors[name].send_briefing(
                    BriefingRequest(agent_name=name, prompt=prompt)
                )

        await asyncio.gather(
            *[
                _bounded_send(name)
                for name in PARALLEL_PLAN_BRIEFING_NAMES
                if name in self._briefing_actors
            ]
        )
        # ``_record_brief`` keys ``_briefs`` by the role-name derived
        # from the forward_method ("scope_ready" → "scope"), not by the
        # agent name (scopist / analyst / criteria). Translate for the
        # missing-check so we're comparing the same thing we stored.
        missing = [
            agent_name
            for agent_name, _label, _tool, method in PLAN_BRIEFING_CONFIG[:3]
            if method.removesuffix("_ready") not in self._briefs
        ]
        # Each BriefingActor self-nudges if its agent finishes without
        # calling its tool, then routes a prompt_error if the nudge also
        # fails. Bail if the workflow was already marked done so the
        # driver surfaces the recorded failure.
        if self._done:
            return
        if missing:
            raise RuntimeError(
                f"Briefing actor returned without delivering and without "
                f"reporting a prompt_error — actor contract violation: "
                f"{sorted(missing)}"
            )

        if "contrarian" in self._briefing_actors:
            await self._run_contrarian_phase()
            if self._done:
                return

        elapsed_ms = int((_time.monotonic() - briefing_start) * 1000)
        await self._emit_phase_completed("briefing", "Briefing", elapsed_ms)

    async def _run_contrarian_phase(self) -> None:
        import time as _time

        await self._emit_agent_started(
            "briefing",
            "Contrarian",
            self._inputs.provider_labels.get("Contrarian", ""),
        )
        self._briefing_start_times["Contrarian"] = _time.monotonic()

        scope_json = json.dumps(
            dump_supervisor_payload(self._briefs["scope"]) if "scope" in self._briefs else {},
            indent=2,
        )
        analysis_json = json.dumps(
            dump_supervisor_payload(self._briefs["analysis"])
            if "analysis" in self._briefs
            else {},
            indent=2,
        )
        criteria_json = json.dumps(
            dump_supervisor_payload(self._briefs["criteria"])
            if "criteria" in self._briefs
            else {},
            indent=2,
        )

        prompt = (
            f"## PRD Content\n\n{self._inputs.prd_content}\n\n"
            f"## Scopist Analysis\n\n```json\n{scope_json}\n```\n\n"
            f"## Codebase Analysis\n\n```json\n{analysis_json}\n```\n\n"
            f"## Success Criteria\n\n```json\n{criteria_json}\n```\n\n"
            f"Challenge these analyses. Identify risks, blind spots, "
            f"and missing considerations."
        )
        await self._briefing_actors["contrarian"].send_briefing(
            BriefingRequest(agent_name="contrarian", prompt=prompt)
        )
        if "challenge" not in self._briefs and not self._done:
            raise RuntimeError(
                "Contrarian briefing returned without delivering and "
                "without reporting a prompt_error — actor contract violation"
            )

    async def _synthesize_briefing_markdown(self) -> None:
        from maverick.preflight_briefing.serializer import serialize_briefs_to_markdown

        self._briefing_markdown = serialize_briefs_to_markdown(
            self._inputs.plan_name,
            scope=(
                dump_supervisor_payload(self._briefs["scope"]) if "scope" in self._briefs else None
            ),
            analysis=(
                dump_supervisor_payload(self._briefs["analysis"])
                if "analysis" in self._briefs
                else None
            ),
            criteria=(
                dump_supervisor_payload(self._briefs["criteria"])
                if "criteria" in self._briefs
                else None
            ),
            challenge=(
                dump_supervisor_payload(self._briefs["challenge"])
                if "challenge" in self._briefs
                else None
            ),
        )

    # ------------------------------------------------------------------
    # Generator / validate / write
    # ------------------------------------------------------------------

    async def _run_generator_phase(self) -> None:
        await self._emit_output("plan", "Sending briefing to flight-plan generator")
        parts = [f"## PRD Content\n\n{self._inputs.prd_content}"]
        if self._briefing_markdown:
            parts.append(f"## Pre-Flight Briefing\n\n{self._briefing_markdown}")
        prompt = "\n\n".join(parts)
        await self._generator.send_generate(GenerateRequest(prompt=prompt))
        if self._flight_plan is None:
            raise RuntimeError("Generator did not submit a flight plan payload")

    async def _run_validation_phase(self) -> None:
        if self._flight_plan is None:
            raise RuntimeError("Validation ran without a flight plan payload")
        result = await self._validator.validate(
            PlanValidateRequest(
                flight_plan=dump_supervisor_payload(self._flight_plan),
                plan_name=self._inputs.plan_name,
                prd_content=self._inputs.prd_content,
            )
        )
        if not result.passed:
            await self._emit_output(
                "plan",
                f"Validation warnings ({len(result.warnings)}); continuing to write",
                level="warning",
                metadata={"warning_count": len(result.warnings)},
            )
        else:
            await self._emit_output("plan", "Validation passed", level="success")

    async def _run_write_phase(self) -> None:
        if self._flight_plan is None:
            raise RuntimeError("Write ran without a flight plan payload")

        from maverick.workflows.generate_flight_plan.markdown import (
            render_flight_plan_markdown,
        )

        flight_plan_md = render_flight_plan_markdown(
            plan_name=self._inputs.plan_name,
            prd_content=self._inputs.prd_content,
            flight_plan=self._flight_plan,
        )
        result = await self._writer.write(
            WritePlanRequest(
                flight_plan_markdown=flight_plan_md,
                briefing_markdown=self._briefing_markdown,
            )
        )
        sc_count = len(self._flight_plan.success_criteria)
        await self._emit_output(
            "plan",
            f"Flight plan written ({sc_count} success criteria)",
            level="success",
            metadata={"success_criteria_count": sc_count},
        )
        self._mark_done(
            {
                "success": True,
                "flight_plan_path": result.flight_plan_path,
                "briefing_path": result.briefing_path,
                "success_criteria_count": sc_count,
                "validation_passed": True,
            }
        )

    # ------------------------------------------------------------------
    # Typed domain methods (called by agent actors)
    # ------------------------------------------------------------------

    @xo.no_lock
    async def scope_ready(self, payload: SubmitScopePayload) -> None:
        await self._record_brief("scope", "Scopist", payload)

    @xo.no_lock
    async def analysis_ready(self, payload: SubmitAnalysisPayload) -> None:
        await self._record_brief("analysis", "Codebase Analyst", payload)

    @xo.no_lock
    async def criteria_ready(self, payload: SubmitCriteriaPayload) -> None:
        await self._record_brief("criteria", "Criteria Writer", payload)

    @xo.no_lock
    async def challenge_ready(self, payload: SubmitChallengePayload) -> None:
        await self._record_brief("challenge", "Contrarian", payload)

    async def _record_brief(self, key: str, label: str, payload: SupervisorInboxPayload) -> None:
        import time as _time

        self._briefs[key] = payload
        elapsed = _time.monotonic() - self._briefing_start_times.get(label, 0)
        await self._emit_agent_completed("briefing", label, elapsed)

    @xo.no_lock
    async def flight_plan_ready(self, payload: SubmitFlightPlanPayload) -> None:
        self._flight_plan = payload
        sc_count = len(payload.success_criteria)
        await self._emit_output(
            "plan",
            f"Flight plan generated ({sc_count} success criteria); validating",
            level="success",
            metadata={"success_criteria_count": sc_count},
        )

    @xo.no_lock
    async def prompt_error(self, error: PromptError) -> None:
        await self._emit_output(
            "plan",
            f"{error.phase} prompt failed: {error.error}",
            level="error",
            metadata={"phase": error.phase, "quota": error.quota_exhausted},
        )
        self._mark_done(
            {
                "success": False,
                "error": error.error,
                "phase": error.phase,
                "quota_exhausted": error.quota_exhausted,
            }
        )

    @xo.no_lock
    async def payload_parse_error(self, tool: str, message: str) -> None:
        await self._emit_output(
            "plan",
            f"Tool {tool!r} payload rejected: {message}",
            level="warning",
        )

    # ------------------------------------------------------------------
    # Event bus
    # ------------------------------------------------------------------

    async def _emit(self, event: ProgressEvent) -> None:
        await self._event_queue.put(event)

    async def _emit_output(
        self,
        step_name: str,
        message: str,
        *,
        level: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._emit(
            StepOutput(
                step_name=step_name,
                message=message,
                display_label="",
                level=level,  # type: ignore[arg-type]
                source=_SOURCE,
                metadata=metadata,
            )
        )

    async def _emit_phase_started(self, step_name: str, display_label: str) -> None:
        await self._emit(
            StepStarted(
                step_name=step_name,
                step_type=StepType.PYTHON,
                display_label=display_label,
            )
        )

    async def _emit_phase_completed(
        self, step_name: str, display_label: str, duration_ms: int
    ) -> None:
        await self._emit(
            StepCompleted(
                step_name=step_name,
                step_type=StepType.PYTHON,
                success=True,
                duration_ms=duration_ms,
                display_label=display_label,
            )
        )

    async def _emit_agent_started(
        self, step_name: str, agent_name: str, provider: str = ""
    ) -> None:
        await self._emit(
            AgentStarted(step_name=step_name, agent_name=agent_name, provider=provider)
        )

    async def _emit_agent_completed(
        self, step_name: str, agent_name: str, duration_seconds: float
    ) -> None:
        await self._emit(
            AgentCompleted(
                step_name=step_name,
                agent_name=agent_name,
                duration_seconds=duration_seconds,
            )
        )

    def _mark_done(self, result: dict[str, Any] | None) -> None:
        self._terminal_result = result
        self._done = True
        self._event_queue.put_nowait(None)

    @xo.no_lock
    async def get_terminal_result(self) -> dict[str, Any] | None:
        return self._terminal_result
