"""xoscar BriefingActor — generic one-shot briefing agent.

Used by both refuel (navigator/structuralist/recon/contrarian) and plan
(scopist/analyst/criteria/contrarian) workflows. Each instance owns one
MCP tool and forwards the parsed payload to a single typed method on
the supervisor (``forward_method`` passed at construction).

Per Design Decision #3, the MCP subprocess targets this actor's own uid
rather than a shared supervisor-inbox uid.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import xoscar as xo
from acp.schema import McpServerStdio

from maverick.actors.step_config import (
    load_step_config,
    step_allowed_tools,
    step_config_with_timeout,
)
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


class BriefingActor(xo.Actor):
    """One briefing agent with its own ACP session and MCP inbox.

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

    async def __post_create__(self) -> None:
        self._actor_tag = f"briefing[{self._agent_name}:{self.uid.decode()}]"
        self._executor: Any = None
        self._session_id: str | None = None

    async def __pre_destroy__(self) -> None:
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
        supervisor via this actor's own ``on_tool_call``."""
        from maverick.exceptions.quota import is_quota_error

        logger.debug(
            "briefing.prompt_starting",
            actor=self._actor_tag,
            tool=self._mcp_tool,
        )
        try:
            await self._send_prompt(request)
            logger.debug(
                "briefing.prompt_completed",
                actor=self._actor_tag,
                tool=self._mcp_tool,
            )
        except Exception as exc:  # noqa: BLE001 — route all errors to the supervisor
            error_str = str(exc)
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
    # MCP subprocess → agent inbox
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
        return "ok"

    # ------------------------------------------------------------------
    # ACP plumbing (internal)
    # ------------------------------------------------------------------

    async def _ensure_executor(self) -> None:
        if self._executor is None:
            from maverick.executor import create_default_executor

            self._executor = create_default_executor()

    async def _new_session(self) -> None:
        await self._ensure_executor()

        maverick_bin = shutil.which("maverick") or str(Path(sys.executable).parent / "maverick")
        mcp_config = McpServerStdio(
            name="agent-inbox",
            command=maverick_bin,
            args=[
                "serve-inbox",
                "--tools",
                self._mcp_tool,
                "--inbox-address",
                self.address,
                "--inbox-uid",
                self.uid.decode(),
            ],
            env=[],
        )

        cwd = Path(self._cwd)
        self._session_id = await self._executor.create_session(
            provider=self._step_config.provider if self._step_config else None,
            config=self._step_config,
            step_name=f"briefing_{self._agent_name}",
            agent_name=self._agent_name,
            cwd=cwd,
            allowed_tools=step_allowed_tools(self._step_config),
            mcp_servers=[mcp_config],
            one_shot_tools=[self._mcp_tool],
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
            f"{self._mcp_tool} tool call."
        )

        await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(self._step_config, BRIEFING_TIMEOUT_SECONDS),
            step_name=f"briefing_{self._agent_name}",
            agent_name=self._agent_name,
        )
