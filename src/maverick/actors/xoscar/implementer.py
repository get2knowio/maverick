"""xoscar ImplementerActor — agent actor with its own MCP inbox.

Owns two MCP tools:

* ``submit_implementation`` — forwarded to supervisor as
  ``implementation_ready``.
* ``submit_fix_result`` — forwarded to supervisor as
  ``fix_result_ready``.

Supervisor calls ``new_bead`` between beads to rotate the ACP session,
then ``send_implement`` / ``send_fix`` to drive ACP prompts. Per-phase
errors surface via ``prompt_error`` on the supervisor.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import xoscar as xo
from acp.schema import McpServerStdio

from maverick.actors._step_config import (
    load_step_config,
    step_allowed_tools,
    step_config_with_timeout,
)
from maverick.actors.xoscar.messages import (
    FlyFixRequest,
    ImplementRequest,
    NewBeadRequest,
    PromptError,
)
from maverick.logging import get_logger
from maverick.tools.supervisor_inbox.models import (
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


class ImplementerActor(xo.Actor):
    """Implements bead work and addresses fix requests."""

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str,
        config: StepConfig | dict[str, Any] | None = None,
    ) -> None:
        if not cwd:
            raise ValueError("ImplementerActor requires 'cwd'")
        self._supervisor_ref = supervisor_ref
        self._cwd = cwd
        self._step_config = load_step_config(config)
        self._mcp_tools_csv = ",".join(IMPLEMENTER_MCP_TOOLS)

    async def __post_create__(self) -> None:
        self._actor_tag = f"implementer[{self.uid}]"
        self._executor: Any = None
        self._session_id: str | None = None

    async def __pre_destroy__(self) -> None:
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
        from maverick.exceptions.quota import is_quota_error

        logger.debug("implementer.phase_starting", phase=phase, bead_id=bead_id)
        try:
            await self._send_prompt(prompt_text, phase=phase, tool_name=tool_name)
            logger.debug("implementer.phase_completed", phase=phase, bead_id=bead_id)
        except Exception as exc:  # noqa: BLE001
            error_str = str(exc)
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
    # MCP subprocess → agent inbox
    # ------------------------------------------------------------------

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
        return "ok"

    # ------------------------------------------------------------------
    # ACP plumbing
    # ------------------------------------------------------------------

    async def _ensure_executor(self) -> None:
        if self._executor is None:
            from maverick.executor import create_default_executor

            self._executor = create_default_executor()

    async def _new_session(self) -> None:
        await self._ensure_executor()

        maverick_bin = shutil.which("maverick") or str(
            Path(sys.executable).parent / "maverick"
        )
        mcp_config = McpServerStdio(
            name="agent-inbox",
            command=maverick_bin,
            args=[
                "serve-inbox",
                "--tools",
                self._mcp_tools_csv,
                "--inbox-address",
                self.address,
                "--inbox-uid",
                self.uid,
            ],
            env=[],
        )

        cwd = Path(self._cwd)
        self._session_id = await self._executor.create_session(
            provider=self._step_config.provider if self._step_config else None,
            config=self._step_config,
            step_name="implement",
            agent_name="implementer",
            cwd=cwd,
            allowed_tools=step_allowed_tools(self._step_config),
            mcp_servers=[mcp_config],
        )

    async def _send_prompt(
        self, prompt_text: str, *, phase: str, tool_name: str
    ) -> None:
        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        prompt_text = (
            f"{prompt_text}\n\n## REQUIRED: Submit via tool call\n"
            f"You MUST call the `{tool_name}` tool with your results."
        )

        await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(
                self._step_config, IMPLEMENTER_PROMPT_TIMEOUT_SECONDS
            ),
            step_name=phase,
            agent_name="implementer",
        )
