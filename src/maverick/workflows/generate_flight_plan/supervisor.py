"""PlanSupervisor — fan-out/fan-in routing for flight plan generation.

Routes messages between briefing agents (parallel), contrarian
(sequential), synthesis (deterministic), generator, validator,
and writer actors.

The fan-out/fan-in pattern: 3 briefing agents run in parallel,
the supervisor collects results as they arrive, and routes to the
contrarian only when all 3 have reported.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maverick.logging import get_logger
from maverick.tools.supervisor_inbox.models import (
    SubmitChallengePayload,
    SubmitFlightPlanPayload,
    SupervisorInboxPayload,
    dump_supervisor_payload,
    parse_supervisor_tool_payload,
)
from maverick.workflows.fly_beads.actors.protocol import (
    Actor,
    Message,
    MessageType,
)
from maverick.workflows.generate_flight_plan.markdown import (
    render_flight_plan_markdown,
)

logger = get_logger(__name__)


@dataclass
class PlanOutcome:
    """Result of the plan generation supervisor."""

    success: bool = False
    flight_plan_path: str = ""
    briefing_path: str | None = None
    success_criteria_count: int = 0
    validation_passed: bool = False
    message_log: list[Message] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: str | None = None


class PlanSupervisor:
    """Routes messages for flight plan generation.

    Handles the fan-out/fan-in pattern: 3 parallel briefing agents
    → contrarian → synthesis → generator → validate → write.

    Since Phase 1 is sequential, the 3 parallel agents are dispatched
    via asyncio.gather on their actor.receive() calls.
    """

    def __init__(
        self,
        *,
        actors: dict[str, Actor],
        prd_content: str,
        plan_name: str,
        skip_briefing: bool = False,
    ) -> None:
        self._actors = actors
        self._prd_content = prd_content
        self._plan_name = plan_name
        self._skip_briefing = skip_briefing
        self._message_log: list[Message] = []
        self._sequence: int = 0

        # Collected briefing results
        self._briefs: dict[str, SupervisorInboxPayload] = {}
        self._briefing_markdown: str = ""
        self._flight_plan_data: SubmitFlightPlanPayload | None = None

    async def process(self) -> PlanOutcome:
        """Main supervisor loop."""
        t0 = time.monotonic()

        try:
            if self._skip_briefing:
                # Go straight to generator
                await self._run_generator()
            else:
                # Fan-out briefing
                await self._run_briefing_parallel()
                # Contrarian
                await self._run_contrarian()
                # Synthesis
                await self._run_synthesis()
                # Generator
                await self._run_generator()

            # Validate
            await self._run_validation()
            # Write
            result = await self._run_writer()

        except Exception as exc:
            logger.error("plan_supervisor.error", error=str(exc))
            elapsed = time.monotonic() - t0
            return PlanOutcome(
                success=False,
                message_log=list(self._message_log),
                duration_seconds=elapsed,
                error=str(exc),
            )

        elapsed = time.monotonic() - t0
        return PlanOutcome(
            success=True,
            flight_plan_path=result.get("flight_plan_path", ""),
            briefing_path=result.get("briefing_path"),
            success_criteria_count=(
                len(self._flight_plan_data.success_criteria) if self._flight_plan_data else 0
            ),
            validation_passed=True,
            message_log=list(self._message_log),
            duration_seconds=elapsed,
        )

    async def _run_briefing_parallel(self) -> None:
        """Run 3 briefing agents sequentially.

        ACP supports one session at a time per connection, so we
        run briefing agents sequentially rather than in parallel.
        Each agent gets its own session with its own MCP server.
        """
        from maverick.agents.preflight_briefing.prompts import (
            build_preflight_briefing_prompt,
        )

        briefing_prompt = build_preflight_briefing_prompt(self._prd_content)

        for agent_name in ["scopist", "codebase_analyst", "criteria_writer"]:
            actor = self._actors.get(agent_name)
            if actor is None:
                continue

            msg = self._make_message(
                MessageType.BRIEFING_REQUEST,
                sender="supervisor",
                recipient=agent_name,
                payload={"prompt": briefing_prompt},
            )
            self._message_log.append(msg)

            try:
                responses = await actor.receive(msg)
                for r in responses:
                    r = self._stamp(r)
                    self._message_log.append(r)
                    tool_name = {
                        "scopist": "submit_scope",
                        "codebase_analyst": "submit_analysis",
                        "criteria_writer": "submit_criteria",
                    }[agent_name]
                    self._briefs[agent_name] = parse_supervisor_tool_payload(
                        tool_name,
                        r.payload,
                    )
            except Exception as exc:
                logger.warning(
                    "plan_supervisor.briefing_agent_failed",
                    agent=agent_name,
                    error=str(exc),
                )

        logger.info(
            "plan_supervisor.briefing_complete",
            agents_responded=len(self._briefs),
        )

    async def _run_contrarian(self) -> None:
        """Sequential: contrarian reviews all 3 briefing results."""
        from maverick.agents.preflight_briefing.prompts import (
            build_preflight_contrarian_prompt,
        )

        contrarian = self._actors.get("contrarian")
        if contrarian is None:
            return

        prompt = build_preflight_contrarian_prompt(
            self._prd_content,
            (
                dump_supervisor_payload(self._briefs["scopist"])
                if "scopist" in self._briefs
                else {}
            ),
            (
                dump_supervisor_payload(self._briefs["codebase_analyst"])
                if "codebase_analyst" in self._briefs
                else {}
            ),
            (
                dump_supervisor_payload(self._briefs["criteria_writer"])
                if "criteria_writer" in self._briefs
                else {}
            ),
        )

        msg = self._make_message(
            MessageType.BRIEFING_REQUEST,
            sender="supervisor",
            recipient="contrarian",
            payload={"prompt": prompt},
        )
        self._message_log.append(msg)

        responses = await contrarian.receive(msg)
        for r in responses:
            r = self._stamp(r)
            self._message_log.append(r)
            parsed = parse_supervisor_tool_payload("submit_challenge", r.payload)
            if isinstance(parsed, SubmitChallengePayload):
                self._briefs["contrarian"] = parsed

    async def _run_synthesis(self) -> None:
        """Deterministic: merge 4 briefs into briefing document."""
        synthesis = self._actors.get("synthesis")
        if synthesis is None:
            return

        msg = self._make_message(
            MessageType.SYNTHESIS_REQUEST,
            sender="supervisor",
            recipient="synthesis",
            payload={
                "scopist": (
                    dump_supervisor_payload(self._briefs["scopist"])
                    if "scopist" in self._briefs
                    else None
                ),
                "analyst": (
                    dump_supervisor_payload(self._briefs["codebase_analyst"])
                    if "codebase_analyst" in self._briefs
                    else None
                ),
                "criteria": (
                    dump_supervisor_payload(self._briefs["criteria_writer"])
                    if "criteria_writer" in self._briefs
                    else None
                ),
                "contrarian": (
                    dump_supervisor_payload(self._briefs["contrarian"])
                    if "contrarian" in self._briefs
                    else None
                ),
            },
        )
        self._message_log.append(msg)

        responses = await synthesis.receive(msg)
        for r in responses:
            r = self._stamp(r)
            self._message_log.append(r)
            self._briefing_markdown = r.payload.get("briefing_markdown", "")

    async def _run_generator(self) -> None:
        """Generate the flight plan."""
        generator = self._actors.get("generator")
        if generator is None:
            raise ValueError("No generator actor configured")

        # Build prompt with PRD + briefing
        parts = [f"## PRD Content\n\n{self._prd_content}"]
        if self._briefing_markdown:
            parts.append(f"## Pre-Flight Briefing\n\n{self._briefing_markdown}")
        prompt = "\n\n".join(parts)

        msg = self._make_message(
            MessageType.GENERATE_PLAN_REQUEST,
            sender="supervisor",
            recipient="generator",
            payload={"prompt": prompt},
        )
        self._message_log.append(msg)

        responses = await generator.receive(msg)
        for r in responses:
            r = self._stamp(r)
            self._message_log.append(r)
            parsed = parse_supervisor_tool_payload("submit_flight_plan", r.payload)
            if isinstance(parsed, SubmitFlightPlanPayload):
                self._flight_plan_data = parsed

    async def _run_validation(self) -> None:
        """Validate the flight plan."""
        validator = self._actors.get("plan_validator")
        if validator is None or self._flight_plan_data is None:
            return

        msg = self._make_message(
            MessageType.VALIDATE_PLAN_REQUEST,
            sender="supervisor",
            recipient="plan_validator",
            payload={
                "flight_plan": dump_supervisor_payload(self._flight_plan_data),
                "plan_name": self._plan_name,
                "prd_content": self._prd_content,
            },
        )
        self._message_log.append(msg)

        responses = await validator.receive(msg)
        for r in responses:
            r = self._stamp(r)
            self._message_log.append(r)

    async def _run_writer(self) -> dict[str, Any]:
        """Write flight plan and briefing to disk."""
        writer = self._actors.get("plan_writer")
        if writer is None:
            return {}

        msg = self._make_message(
            MessageType.WRITE_PLAN_REQUEST,
            sender="supervisor",
            recipient="plan_writer",
            payload={
                "flight_plan_markdown": (
                    render_flight_plan_markdown(
                        plan_name=self._plan_name,
                        prd_content=self._prd_content,
                        flight_plan=self._flight_plan_data,
                    )
                    if self._flight_plan_data is not None
                    else ""
                ),
                "briefing_markdown": self._briefing_markdown,
                "plan_name": self._plan_name,
            },
        )
        self._message_log.append(msg)

        responses = await writer.receive(msg)
        for r in responses:
            r = self._stamp(r)
            self._message_log.append(r)
            return r.payload
        return {}

    # ------------------------------------------------------------------
    # Message helpers
    # ------------------------------------------------------------------

    def _make_message(
        self,
        msg_type: MessageType,
        *,
        sender: str,
        recipient: str,
        payload: dict[str, Any] | None = None,
    ) -> Message:
        self._sequence += 1
        return Message(
            msg_type=msg_type,
            sender=sender,
            recipient=recipient,
            payload=payload or {},
            sequence=self._sequence,
        )

    def _stamp(self, message: Message) -> Message:
        self._sequence += 1
        return Message(
            msg_type=message.msg_type,
            sender=message.sender,
            recipient=message.recipient,
            payload=message.payload,
            sequence=self._sequence,
            in_reply_to=message.in_reply_to,
        )
