"""xoscar BriefingActor — thin shell over :class:`BriefingAgent`.

Used by both refuel (navigator/structuralist/recon/contrarian) and plan
(scopist/analyst/criteria/contrarian) workflows. Each instance owns one
result schema (looked up at construction time from the legacy mcp_tool
name) and forwards the parsed payload to a single typed method on the
supervisor (``forward_method`` passed at construction).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import xoscar as xo

from maverick.actors.step_config import load_step_config
from maverick.actors.xoscar.messages import BriefingRequest, PromptError
from maverick.agents.briefing.agent import BriefingAgent
from maverick.logging import get_logger
from maverick.payloads import SUPERVISOR_TOOL_PAYLOAD_MODELS
from maverick.runtime.opencode import (
    AgentRuntimeError,
    cost_sink_for,
    opencode_handle_for,
    tier_overrides_for,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)


class BriefingActor(xo.Actor):
    """One briefing agent backed by OpenCode HTTP + structured output."""

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
        schema = SUPERVISOR_TOOL_PAYLOAD_MODELS.get(mcp_tool)
        if schema is None:
            raise ValueError(
                f"BriefingActor: unknown payload tool {mcp_tool!r}; "
                "add an entry to SUPERVISOR_TOOL_PAYLOAD_MODELS first."
            )
        self._supervisor_ref = supervisor_ref
        self._agent_name = agent_name
        self._mcp_tool = mcp_tool
        self._forward_method = forward_method
        self._cwd = cwd
        self._step_config = load_step_config(config)
        self._schema = schema
        self._agent: BriefingAgent | None = None

    async def __post_create__(self) -> None:
        self._agent = self._make_agent()
        await self._agent.open()

    def _make_agent(self) -> BriefingAgent:
        """Factory hook — override in tests to inject a stubbed agent."""
        pool_address: str = self.address
        return BriefingAgent(
            handle=opencode_handle_for(pool_address),
            cwd=self._cwd,
            agent_name=self._agent_name,
            result_model=self._schema,
            step_config=self._step_config,
            tier_overrides=tier_overrides_for(pool_address),
            cost_sink=cost_sink_for(pool_address),
            tag=f"briefing[{self._agent_name}:{self.uid.decode()}]",
        )

    async def __pre_destroy__(self) -> None:
        if self._agent is not None:
            await self._agent.close()

    # ------------------------------------------------------------------
    # Supervisor → agent surface
    # ------------------------------------------------------------------

    @xo.no_lock
    async def send_briefing(self, request: BriefingRequest) -> None:
        """Run the briefing prompt and forward the typed payload."""
        assert self._agent is not None
        logger.debug(
            "briefing.prompt_starting",
            agent=self._agent_name,
            tool=self._mcp_tool,
        )
        try:
            payload = await self._agent.brief(request.prompt)
        except AgentRuntimeError as exc:
            await self._report_briefing_failure(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — supervisor decides retry policy
            await self._report_briefing_failure(str(exc))
            return

        # xoscar's __getattr__ returns an ActorRefMethod proxy regardless
        # of whether the method exists; failure surfaces only on call. We
        # rely on the supervisor being correctly wired by its
        # constructor — forward-method mismatches are a programmer error.
        forward = getattr(self._supervisor_ref, self._forward_method)
        await forward(payload)

    async def _report_briefing_failure(self, error: str) -> None:
        from maverick.exceptions.quota import is_quota_error, is_transient_error

        quota = is_quota_error(error)
        transient = is_transient_error(error)
        logger.debug(
            "briefing.prompt_failed",
            agent=self._agent_name,
            tool=self._mcp_tool,
            error=error,
            quota=quota,
            transient=transient,
        )
        await self._supervisor_ref.prompt_error(
            PromptError(
                phase="briefing",
                error=error,
                quota_exhausted=quota,
                transient=transient,
                unit_id=self._agent_name,
            )
        )
