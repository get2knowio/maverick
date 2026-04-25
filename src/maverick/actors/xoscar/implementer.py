"""xoscar ImplementerActor — agent actor with its own MCP inbox.

Owns two MCP tools:

* ``submit_implementation`` — forwarded to supervisor as
  ``implementation_ready``.
* ``submit_fix_result`` — forwarded to supervisor as
  ``fix_result_ready``.

Supervisor calls ``new_bead`` between beads to rotate the ACP session,
then ``send_implement`` / ``send_fix`` to drive ACP prompts. Per-phase
errors surface via ``prompt_error`` on the supervisor.

Tool transport: shared :class:`AgentToolGateway` HTTP server (one per
workflow run, owned by the actor pool). The actor still owns its schemas,
handler, session state, and ACP executor — only MCP transport lives in
shared infrastructure.
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
from maverick.actors.xoscar._agentic import AgenticActorMixin
from maverick.actors.xoscar._agentic import extract_text_output as _extract_text_output
from maverick.actors.xoscar.messages import (
    FlyFixRequest,
    ImplementRequest,
    NewBeadRequest,
    PromptError,
)
from maverick.logging import get_logger
from maverick.tools.agent_inbox.models import (
    SubmitFixResultPayload,
    SubmitImplementationPayload,
    SupervisorToolPayloadError,
    parse_supervisor_tool_payload,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)

IMPLEMENTER_MCP_TOOLS: tuple[str, ...] = ("submit_implementation", "submit_fix_result")
IMPLEMENTER_PROMPT_TIMEOUT_SECONDS = 1800


class ImplementerActor(AgenticActorMixin, xo.Actor):
    """Implements bead work and addresses fix requests."""

    mcp_tools: ClassVar[tuple[str, ...]] = IMPLEMENTER_MCP_TOOLS

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str,
        config: StepConfig | dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        if not cwd:
            raise ValueError("ImplementerActor requires 'cwd'")
        self._supervisor_ref = supervisor_ref
        self._cwd = cwd
        self._step_config = load_step_config(config)

    async def __post_create__(self) -> None:
        self._actor_tag = f"implementer[{self.uid.decode()}]"
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
                "implementer.cleanup_failed",
                actor=self._actor_tag,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Supervisor → agent surface
    # ------------------------------------------------------------------

    async def new_bead(self, request: NewBeadRequest) -> None:
        """Rotate the ACP session so the next prompt starts clean."""
        try:
            await self._new_session()
        except Exception as exc:  # noqa: BLE001
            await self._supervisor_ref.prompt_error(
                PromptError(
                    phase="new_bead",
                    error=str(exc),
                    unit_id=request.bead_id,
                )
            )

    async def send_implement(self, request: ImplementRequest) -> None:
        await self._run_prompt(
            request.prompt,
            phase="implement",
            tool_name="submit_implementation",
            bead_id=request.bead_id,
        )

    async def send_fix(self, request: FlyFixRequest) -> None:
        await self._run_prompt(
            request.prompt,
            phase="fix",
            tool_name="submit_fix_result",
            bead_id=request.bead_id,
        )

    async def _run_prompt(
        self,
        prompt_text: str,
        *,
        phase: str,
        tool_name: str,
        bead_id: str,
    ) -> None:
        """Self-nudge contract: returns once ``tool_name`` has been
        delivered to the supervisor, OR routes a ``PromptError`` if
        both the original prompt and the nudge skip the tool.
        """
        logger.debug("implementer.phase_starting", phase=phase, bead_id=bead_id)

        async def _failure(error_str: str) -> None:
            await self._report_implementer_failure(
                error_str, phase=phase, bead_id=bead_id
            )

        await self._run_with_self_nudge(
            expected_tool=tool_name,
            run_prompt=lambda: self._send_prompt(
                prompt_text, phase=phase, tool_name=tool_name
            ),
            run_nudge=lambda: self._send_nudge_prompt(tool_name, phase=phase),
            on_failure=_failure,
            log_prefix="implementer",
        )

    async def _report_implementer_failure(
        self, error_str: str, *, phase: str, bead_id: str
    ) -> None:
        from maverick.exceptions.quota import is_quota_error

        quota = is_quota_error(error_str)
        logger.debug(
            "implementer.phase_failed",
            phase=phase,
            bead_id=bead_id,
            error=error_str,
        )
        await self._supervisor_ref.prompt_error(
            PromptError(
                phase=phase,
                error=error_str,
                quota_exhausted=quota,
                unit_id=bead_id,
            )
        )

    # ------------------------------------------------------------------
    # MCP gateway → agent inbox
    # ------------------------------------------------------------------

    @xo.no_lock
    async def on_tool_call(self, tool: str, args: dict[str, Any]) -> str:
        try:
            payload = parse_supervisor_tool_payload(tool, args)
        except (SupervisorToolPayloadError, ValueError) as exc:
            await self._supervisor_ref.payload_parse_error(tool, str(exc))
            return "error"

        if isinstance(payload, SubmitImplementationPayload):
            await self._supervisor_ref.implementation_ready(payload)
        elif isinstance(payload, SubmitFixResultPayload):
            await self._supervisor_ref.fix_result_ready(payload)
        else:
            await self._supervisor_ref.payload_parse_error(
                tool, f"Implementer has no handler for tool {tool!r}"
            )
            return "error"
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
                    "implementer.cancel_after_submit_failed",
                    actor=self._actor_tag,
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # ACP plumbing
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
            step_name="implement",
            agent_name="implementer",
            cwd=cwd,
            allowed_tools=step_allowed_tools(self._step_config),
            mcp_servers=[self.mcp_server_config()],
        )

    async def _send_prompt(self, prompt_text: str, *, phase: str, tool_name: str) -> None:
        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        prompt_text = (
            f"{prompt_text}\n\n## REQUIRED: Submit via tool call\n"
            f"You MUST call the `{tool_name}` tool with your results."
        )

        result = await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(self._step_config, IMPLEMENTER_PROMPT_TIMEOUT_SECONDS),
            step_name=phase,
            agent_name="implementer",
        )
        self._record_last_response(_extract_text_output(result))

    async def _send_nudge_prompt(self, expected_tool: str, *, phase: str) -> None:
        """Re-prompt the same session asking the agent to call its tool.

        Quotes the agent's previous text response so the LLM is forced
        to convert that work into a tool call rather than repeating the
        same refusal.
        """
        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        previous = self._get_last_response()
        if previous:
            preview = previous if len(previous) <= 1500 else previous[:1500] + "…"
            quoted = (
                f"\n\nYour previous turn produced this text instead of a "
                f"tool call:\n\n---\n{preview}\n---\n\n"
                f"Convert that work into a single `{expected_tool}` tool "
                "call. Do NOT refuse — even a partial result should be "
                "submitted via the tool."
            )
        else:
            quoted = ""

        prompt_text = (
            f"Your previous turn finished without calling `{expected_tool}`. "
            "You MUST submit your result via that MCP tool — text-only "
            f"responses are dropped by the supervisor.{quoted}"
        )

        result = await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(self._step_config, IMPLEMENTER_PROMPT_TIMEOUT_SECONDS),
            step_name=f"{phase}_nudge",
            agent_name="implementer",
        )
        self._record_last_response(_extract_text_output(result))
