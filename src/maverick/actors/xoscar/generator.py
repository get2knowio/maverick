"""xoscar GeneratorActor — flight-plan generation agent.

Owns one MCP tool: ``submit_flight_plan``. The supervisor passes the
composite PRD + briefing prompt via ``send_generate``; the agent
submits the structured plan via ``submit_flight_plan`` → supervisor's
``flight_plan_ready`` method.

Tool transport: this actor uses the shared :class:`AgentToolGateway`
HTTP server (one per workflow run, owned by the actor pool). The actor
itself still owns its schema list, on_tool_call handler, ACP session
state, and ACP executor — only the MCP transport lives in shared
infrastructure.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import xoscar as xo

from maverick.actors.step_config import (
    load_step_config,
    step_allowed_tools,
    step_config_with_timeout,
)
from maverick.actors.xoscar._agentic import (
    AgenticActorMixin,
    build_tool_required_nudge_prompt,
    build_tool_required_prompt,
)
from maverick.actors.xoscar._agentic import (
    extract_text_output as _extract_text_output,
)
from maverick.actors.xoscar.messages import GenerateRequest, PromptError
from maverick.logging import get_logger
from maverick.tools.agent_inbox.models import (
    SubmitFlightPlanPayload,
    SupervisorToolPayloadError,
    parse_supervisor_tool_payload,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)

GENERATOR_MCP_TOOL = "submit_flight_plan"
GENERATOR_PROMPT_TIMEOUT_SECONDS = 1200


class GeneratorActor(AgenticActorMixin, xo.Actor):
    """Generates flight plan from PRD + briefing context."""

    mcp_tools: ClassVar[tuple[str, ...]] = (GENERATOR_MCP_TOOL,)

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str,
        config: StepConfig | dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        if not cwd:
            raise ValueError("GeneratorActor requires 'cwd'")
        self._supervisor_ref = supervisor_ref
        self._cwd = cwd
        self._step_config = load_step_config(config)

    async def __post_create__(self) -> None:
        self._actor_tag = f"generator[{self.uid.decode()}]"
        self._executor: Any = None
        self._session_id: str | None = None
        await self._register_with_gateway()

    async def __pre_destroy__(self) -> None:
        await self._unregister_from_gateway()
        if self._executor is None:
            return
        try:
            await self._executor.cleanup()
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "generator.cleanup_failed",
                actor=self._actor_tag,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Supervisor → agent
    # ------------------------------------------------------------------

    async def send_generate(self, request: GenerateRequest) -> None:
        """Run the flight-plan generation prompt.

        Self-nudge contract (see AgenticActorMixin._run_with_self_nudge):
        returns once ``submit_flight_plan`` has been delivered to the
        supervisor's ``flight_plan_ready``, OR routes a ``PromptError``
        if both attempts skip the tool.
        """
        logger.debug("generator.prompt_starting")
        await self._run_with_self_nudge(
            expected_tool=GENERATOR_MCP_TOOL,
            run_prompt=lambda: self._send_prompt(request.prompt),
            run_nudge=lambda: self._send_nudge_prompt(),
            on_failure=self._report_generator_failure,
            log_prefix="generator",
        )

    async def _report_generator_failure(self, error_str: str) -> None:
        from maverick.exceptions.quota import is_quota_error

        logger.debug("generator.prompt_failed", error=error_str)
        await self._supervisor_ref.prompt_error(
            PromptError(
                phase="generate",
                error=error_str,
                quota_exhausted=is_quota_error(error_str),
            )
        )

    # ------------------------------------------------------------------
    # MCP gateway → agent inbox
    # ------------------------------------------------------------------

    @xo.no_lock
    async def on_tool_call(self, tool: str, args: dict[str, Any]) -> str:
        if tool != GENERATOR_MCP_TOOL:
            await self._supervisor_ref.payload_parse_error(
                tool,
                f"Generator advertises {GENERATOR_MCP_TOOL!r}, got {tool!r}",
            )
            return "error"
        try:
            payload = parse_supervisor_tool_payload(tool, args)
        except (SupervisorToolPayloadError, ValueError) as exc:
            await self._supervisor_ref.payload_parse_error(tool, str(exc))
            return "error"
        if not isinstance(payload, SubmitFlightPlanPayload):
            await self._supervisor_ref.payload_parse_error(
                tool, f"Unexpected payload type for {tool!r}"
            )
            return "error"
        await self._supervisor_ref.flight_plan_ready(payload)
        self._mark_tool_delivered(tool)
        await self._end_turn()
        return "ok"

    async def _end_turn(self) -> None:
        """Cancel the current ACP turn after a successful MCP submission."""
        if self._session_id and self._executor is not None:
            try:
                await self._executor.cancel_session(self._session_id)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "generator.cancel_after_submit_failed",
                    actor=self._actor_tag,
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # ACP plumbing
    # ------------------------------------------------------------------

    async def _ensure_executor(self) -> None:
        if self._executor is None:
            self._executor = await self._build_quota_aware_executor()

    async def _new_session(self) -> None:
        await self._ensure_executor()

        cwd = Path(self._cwd)
        self._session_id = await self._executor.create_session(
            provider=self._step_config.provider if self._step_config else None,
            config=self._step_config,
            step_name="generate",
            agent_name="flight_plan_generator",
            cwd=cwd,
            allowed_tools=step_allowed_tools(self._step_config),
            mcp_servers=[self.mcp_server_config()],
        )

    async def _send_prompt(self, raw_prompt: str) -> None:
        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        prompt_text = build_tool_required_prompt(
            expected_tool=GENERATOR_MCP_TOOL,
            user_content=raw_prompt,
            user_content_label="PRD and briefing",
            role_intro=(
                "You are a flight plan generator. DO NOT read files from "
                "the filesystem. DO NOT explore the codebase. DO NOT "
                "write code. Your sole output is a single call to "
                f"`{GENERATOR_MCP_TOOL}` with these fields: objective "
                "(one-line summary), success_criteria (array of "
                "{description, verification}), in_scope, out_of_scope, "
                "constraints, context (markdown), tags."
            ),
        )

        result = await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(self._step_config, GENERATOR_PROMPT_TIMEOUT_SECONDS),
            step_name="generate",
            agent_name="flight_plan_generator",
        )
        accumulated = _extract_text_output(result)
        self._record_last_response(accumulated)
        logger.debug(
            "generator.result",
            success=getattr(result, "success", None),
            text_len=len(accumulated),
            output_type=type(getattr(result, "output", None)).__name__,
            output_preview=accumulated[:500],
        )

    async def _send_nudge_prompt(self) -> None:
        """Re-prompt the same session asking the agent to call its tool.

        Re-uses the existing ACP session so the agent has full
        conversation context. Quotes the agent's previous text response
        so the LLM is forced to convert that work into a tool call
        rather than repeating the same refusal.
        """
        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        prompt_text = build_tool_required_nudge_prompt(
            expected_tool=GENERATOR_MCP_TOOL,
            previous_response=self._get_last_response(),
            empty_result_guidance=("Submit even a partial plan rather than refusing."),
        )

        result = await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(self._step_config, GENERATOR_PROMPT_TIMEOUT_SECONDS),
            step_name="generate_nudge",
            agent_name="flight_plan_generator",
        )
        self._record_last_response(_extract_text_output(result))
