"""xoscar BriefingActor — generic one-shot briefing agent.

Used by both refuel (navigator/structuralist/recon/contrarian) and plan
(scopist/analyst/criteria/contrarian) workflows. Each instance owns one
MCP tool and forwards the parsed payload to a single typed method on
the supervisor (``forward_method`` passed at construction).

Tool transport: shared :class:`AgentToolGateway` HTTP server (one per
workflow run, owned by the actor pool). The actor still owns its schemas,
handler, session state, and ACP executor — only MCP transport lives in
shared infrastructure.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import xoscar as xo

from maverick.actors.step_config import (
    load_step_config,
    step_allowed_tools,
    step_config_with_timeout,
)
from maverick.actors.xoscar._agentic import AgenticActorMixin
from maverick.actors.xoscar._agentic import extract_text_output as _extract_text_output
from maverick.actors.xoscar.messages import BriefingRequest, PromptError
from maverick.logging import get_logger
from maverick.tools.agent_inbox.models import (
    SupervisorToolPayloadError,
    parse_supervisor_tool_payload,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)

BRIEFING_TIMEOUT_SECONDS = 1200


class BriefingActor(AgenticActorMixin, xo.Actor):
    """One briefing agent with its own ACP session and inbox registration.

    Constructor params:

    * ``supervisor_ref`` — the supervisor's ActorRef; the target of
      typed result-forwarding and error-reporting calls.
    * ``agent_name`` — logical name ("navigator", "scopist", etc.);
      used in logs and as the prompt-session ``agent_name`` field.
    * ``mcp_tool`` — the single MCP tool this briefing owns
      (e.g., ``"submit_navigator_brief"``).
    * ``forward_method`` — the supervisor method to call with the parsed
      typed payload (e.g., ``"navigator_brief_ready"``).
    * ``cwd`` — working directory for the ACP subprocess.
    * ``config`` — optional ``StepConfig`` override.
    """

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        agent_name: str,
        mcp_tool: str,
        forward_method: str,
        cwd: str,
        config: StepConfig | dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        if not cwd:
            raise ValueError("BriefingActor requires 'cwd'")
        if not mcp_tool:
            raise ValueError("BriefingActor requires 'mcp_tool'")
        if not forward_method:
            raise ValueError("BriefingActor requires 'forward_method'")
        self._supervisor_ref = supervisor_ref
        self._agent_name = agent_name
        self._mcp_tool = mcp_tool
        self._forward_method = forward_method
        self._cwd = cwd
        self._step_config = load_step_config(config)

    def _mcp_tools(self) -> tuple[str, ...]:
        return (self._mcp_tool,)

    async def __post_create__(self) -> None:
        self._actor_tag = f"briefing[{self._agent_name}:{self.uid.decode()}]"
        self._executor: Any = None
        self._session_id: str | None = None
        await self._register_with_gateway()

    async def __pre_destroy__(self) -> None:
        await self._unregister_from_gateway()
        if self._executor is None:
            return
        try:
            await self._executor.cleanup()
        except Exception as exc:  # noqa: BLE001 — best-effort teardown
            logger.debug(
                "briefing.cleanup_failed",
                actor=self._actor_tag,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Supervisor → agent surface
    # ------------------------------------------------------------------

    async def send_briefing(self, request: BriefingRequest) -> None:
        """Run the briefing prompt. The typed result arrives on the
        supervisor via this actor's own ``on_tool_call``.

        Self-nudge contract (see AgenticActorMixin._run_with_self_nudge):
        returns once the agent's MCP tool has been delivered to the
        supervisor's forward method, OR routes a ``PromptError`` if
        both the initial prompt and the nudge come up empty.
        """
        logger.debug(
            "briefing.prompt_starting",
            actor=self._actor_tag,
            tool=self._mcp_tool,
        )
        await self._run_with_self_nudge(
            expected_tool=self._mcp_tool,
            run_prompt=lambda: self._send_prompt(request),
            run_nudge=lambda: self._send_nudge_prompt(),
            on_failure=self._report_briefing_failure,
            log_prefix="briefing",
        )

    async def _report_briefing_failure(self, error_str: str) -> None:
        """Send a ``PromptError`` to the supervisor for this briefing actor."""
        from maverick.exceptions.quota import is_quota_error

        quota = is_quota_error(error_str)
        logger.debug(
            "briefing.prompt_failed",
            actor=self._actor_tag,
            tool=self._mcp_tool,
            error=error_str,
            quota=quota,
        )
        await self._supervisor_ref.prompt_error(
            PromptError(
                phase="briefing",
                error=error_str,
                quota_exhausted=quota,
                unit_id=self._agent_name,
            )
        )

    # ------------------------------------------------------------------
    # MCP gateway → agent inbox
    # ------------------------------------------------------------------

    @xo.no_lock
    async def on_tool_call(self, tool: str, args: dict[str, Any]) -> str:
        if tool != self._mcp_tool:
            await self._supervisor_ref.payload_parse_error(
                tool,
                f"{self._actor_tag} advertises {self._mcp_tool!r}, got {tool!r}",
            )
            return "error"
        try:
            payload = parse_supervisor_tool_payload(tool, args)
        except (SupervisorToolPayloadError, ValueError) as exc:
            await self._supervisor_ref.payload_parse_error(tool, str(exc))
            return "error"

        forward = getattr(self._supervisor_ref, self._forward_method, None)
        if forward is None:
            await self._supervisor_ref.payload_parse_error(
                tool, f"supervisor has no method {self._forward_method!r}"
            )
            return "error"
        await forward(payload)
        # Mark the tool delivered so send_briefing's self-nudge loop
        # knows the prompt produced a real submission.
        self._mark_tool_delivered(tool)
        # Payload is safely in the supervisor; end the ACP turn so
        # send_briefing returns. If we didn't, the agent would keep
        # generating post-submission wrap-up text and the briefing
        # phase would drag long past the point of no useful work.
        await self._end_turn()
        return "ok"

    async def _end_turn(self) -> None:
        """Cancel the current ACP turn after the MCP submission is
        safely forwarded to the supervisor. Best-effort: a failure to
        cancel is not fatal — the agent will just finish its turn
        naturally."""
        if self._session_id and self._executor is not None:
            try:
                await self._executor.cancel_session(self._session_id)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "briefing.cancel_after_submit_failed",
                    actor=self._actor_tag,
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # ACP plumbing (internal)
    # ------------------------------------------------------------------

    async def _ensure_executor(self) -> None:
        if self._executor is None:
            from maverick.executor import create_default_executor

            self._executor = create_default_executor()

    async def _new_session(self) -> None:
        await self._ensure_executor()

        cwd = Path(self._cwd)
        self._session_id = await self._executor.create_session(
            provider=self._step_config.provider if self._step_config else None,
            config=self._step_config,
            step_name=f"briefing_{self._agent_name}",
            agent_name=self._agent_name,
            cwd=cwd,
            allowed_tools=step_allowed_tools(self._step_config),
            mcp_servers=[self.mcp_server_config()],
        )

    async def _send_prompt(self, request: BriefingRequest) -> None:
        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        prompt_text = request.prompt
        prompt_text += (
            f"\n\n## REQUIRED: Submit via tool call\n"
            f"You MUST call the `{self._mcp_tool}` tool with your "
            f"results. Do NOT put results in a text response — the "
            f"supervisor can only receive your work via the "
            f"{self._mcp_tool} tool call.\n"
            "If your analysis surfaced no findings (e.g. greenfield "
            "project with no existing code), still call the tool with "
            "empty arrays / minimal fields. Do NOT respond with text "
            "saying 'nothing to report' — that is dropped."
        )

        result = await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(self._step_config, BRIEFING_TIMEOUT_SECONDS),
            step_name=f"briefing_{self._agent_name}",
            agent_name=self._agent_name,
        )
        self._record_last_response(_extract_text_output(result))

    async def _send_nudge_prompt(self) -> None:
        """Send a follow-up prompt asking the agent to call its tool.

        Re-uses the same ACP session so the agent has full conversation
        context — the agent already saw the original prompt, the nudge
        just reminds it to deliver via the tool. Quotes the agent's
        previous text response so the LLM is forced to convert it into
        a tool call instead of repeating the same refusal.
        """
        await self._ensure_executor()
        if not self._session_id:
            # Should not happen — _send_prompt would have created one.
            await self._new_session()

        previous = self._get_last_response()
        if previous:
            preview = previous if len(previous) <= 1500 else previous[:1500] + "…"
            quoted = (
                f"\n\nYour previous turn produced this text instead of a "
                f"tool call:\n\n---\n{preview}\n---\n\n"
                f"Convert that work into a single `{self._mcp_tool}` "
                "tool call. If the analysis is 'nothing to report' (e.g. "
                "greenfield project), call the tool with empty arrays — "
                "do NOT refuse."
            )
        else:
            quoted = ""

        prompt_text = (
            f"Your previous turn finished without calling `{self._mcp_tool}`. "
            "You MUST submit your result via that MCP tool — text-only "
            f"responses are dropped by the supervisor.{quoted}"
        )

        result = await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(self._step_config, BRIEFING_TIMEOUT_SECONDS),
            step_name=f"briefing_{self._agent_name}_nudge",
            agent_name=self._agent_name,
        )
        self._record_last_response(_extract_text_output(result))
