"""xoscar BriefingActor — OpenCode-backed generic briefing agent.

Used by both refuel (navigator/structuralist/recon/contrarian) and plan
(scopist/analyst/criteria/contrarian) workflows. Each instance owns one
result schema (looked up at construction time from the legacy mcp_tool
name) and forwards the parsed payload to a single typed method on the
supervisor (``forward_method`` passed at construction).

The legacy MCP-gateway path is gone — OpenCode's StructuredOutput tool
forces the model to return the typed payload on the first turn, so the
self-nudge loop and JSON-in-text fallback are no longer needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import xoscar as xo
from pydantic import BaseModel

from maverick.actors.step_config import load_step_config
from maverick.actors.xoscar.messages import BriefingRequest, PromptError
from maverick.actors.xoscar.opencode_mixin import OpenCodeAgentMixin
from maverick.logging import get_logger
from maverick.payloads import (
    SUPERVISOR_TOOL_PAYLOAD_MODELS,
)
from maverick.runtime.opencode import OpenCodeError

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)

BRIEFING_TIMEOUT_SECONDS = 1200

# Map the in-process agent label to the bundled OpenCode persona file.
# Both refuel briefings (navigator/structuralist/recon/contrarian) and
# pre-flight briefings (scopist/codebase_analyst/criteria_writer/
# preflight_contrarian) flow through this actor; the .md files live at
# ``runtime/opencode/profile/agents/maverick.<persona>.md``. The
# refuel/contrarian and preflight/contrarian roles share an
# ``agent_name`` of "contrarian" / "preflight_contrarian" already, so
# the map is a straight identity with one alias.
_OPENCODE_AGENT_MAP: dict[str, str] = {
    "navigator": "maverick.navigator",
    "structuralist": "maverick.structuralist",
    "recon": "maverick.recon",
    "contrarian": "maverick.contrarian",
    "scopist": "maverick.scopist",
    "codebase_analyst": "maverick.codebase-analyst",
    "criteria_writer": "maverick.criteria-writer",
    "preflight_contrarian": "maverick.preflight-contrarian",
}


class BriefingActor(OpenCodeAgentMixin, xo.Actor):
    """One briefing agent backed by OpenCode HTTP + structured output.

    Constructor params:

    * ``supervisor_ref`` — supervisor's ActorRef.
    * ``agent_name`` — logical name ("navigator", "scopist", etc.); used
      in logs and as the OpenCode agent label.
    * ``mcp_tool`` — legacy tool name (e.g., ``"submit_navigator_brief"``);
      used here only to look up the result schema.
    * ``forward_method`` — supervisor method to call with the parsed payload.
    * ``cwd`` — working directory.
    * ``config`` — optional ``StepConfig`` override.

    The instance overrides :attr:`result_model` from the class default to
    match the per-instance schema lookup; the mixin still treats it as
    the per-call default schema.
    """

    # Will be replaced per-instance in __init__; the class-level default
    # is BaseModel so type checkers see a valid type.
    result_model: ClassVar[type[BaseModel]] = BaseModel
    provider_tier: ClassVar[str] = "briefing"

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
        # Per-instance schema — used by _send_structured below.
        self._schema: type[BaseModel] = schema

    async def __post_create__(self) -> None:
        self._actor_tag = f"briefing[{self._agent_name}:{self.uid.decode()}]"
        await self._opencode_post_create()

    def _opencode_agent_name(self) -> str | None:
        """Map ``self._agent_name`` to the bundled persona label.

        Returns ``None`` (server default) for any unmapped name so an
        unknown role surfaces as a missing-persona warning in OpenCode
        logs rather than silently routing to the wrong system prompt.
        """
        return _OPENCODE_AGENT_MAP.get(self._agent_name)

    async def __pre_destroy__(self) -> None:
        await self._opencode_pre_destroy()

    # ------------------------------------------------------------------
    # Supervisor → agent surface
    # ------------------------------------------------------------------

    @xo.no_lock
    async def send_briefing(self, request: BriefingRequest) -> None:
        """Run the briefing prompt and forward the typed payload."""
        logger.debug(
            "briefing.prompt_starting",
            actor=self._actor_tag,
            tool=self._mcp_tool,
            agent=self._opencode_agent_name(),
        )
        # The persona's system prompt now lives in the bundled
        # ``maverick.<agent_name>`` markdown file, loaded by OpenCode
        # via ``OPENCODE_CONFIG_DIR``. Send only the per-bead user
        # prompt here; the role/voice text used to be in Python is now
        # in the .md frontmatter.
        prompt = (
            "If your analysis surfaces no findings (e.g. greenfield project "
            "with no existing code), set empty arrays / minimal required "
            "fields rather than refusing.\n\n"
            "# Briefing input\n\n"
            f"{request.prompt}"
        )
        try:
            payload = await self._send_structured(
                prompt,
                schema=self._schema,
                timeout=BRIEFING_TIMEOUT_SECONDS,
                agent=self._opencode_agent_name(),
            )
        except OpenCodeError as exc:
            await self._report_briefing_failure(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — supervisor decides retry policy
            await self._report_briefing_failure(str(exc))
            return

        # xoscar's __getattr__ returns an ActorRefMethod proxy regardless of
        # whether the method exists; the failure surfaces only on call. We
        # rely on the supervisor being correctly wired by its constructor —
        # forward-method mismatches are a programmer error, not a runtime
        # failure mode worth handling silently.
        forward = getattr(self._supervisor_ref, self._forward_method)
        await forward(payload)

    async def _report_briefing_failure(self, error: str) -> None:
        from maverick.exceptions.quota import is_quota_error, is_transient_error

        quota = is_quota_error(error)
        transient = is_transient_error(error)
        logger.debug(
            "briefing.prompt_failed",
            actor=self._actor_tag,
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
