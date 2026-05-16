"""xoscar DecomposerActor — thin shell over :class:`DecomposerAgent`.

Three phases — ``send_outline``, ``send_detail``, ``send_fix`` — each
returning a typed payload to a different supervisor method
(``outline_ready``, ``detail_ready``, ``fix_ready``). Session-mode
rotation lives inside the agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import xoscar as xo
from pydantic import BaseModel

from maverick.actors.step_config import load_step_config
from maverick.actors.xoscar.messages import (
    DecomposerContext,
    DetailRequest,
    FixRequest,
    NudgeRequest,
    OutlineRequest,
    PromptError,
)
from maverick.agents.decomposer import DecomposerAgent
from maverick.logging import get_logger
from maverick.payloads import (
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitOutlinePayload,
)
from maverick.runtime.opencode import (
    AgentRuntimeError,
    cost_sink_for,
    opencode_handle_for,
    tier_overrides_for,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)


class DecomposerActor(xo.Actor):
    """Sends structured prompts for decomposition phases."""

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str,
        config: StepConfig | dict[str, Any] | None = None,
        role: str = "primary",
        detail_session_max_turns: int = 5,
        fix_session_max_turns: int = 1,
        agent: DecomposerAgent | None = None,
    ) -> None:
        super().__init__()
        if not cwd:
            raise ValueError("DecomposerActor requires 'cwd'")
        self._supervisor_ref = supervisor_ref
        self._cwd = cwd
        self._step_config = load_step_config(config)
        self._role = role
        self._detail_session_max_turns = detail_session_max_turns
        self._fix_session_max_turns = fix_session_max_turns
        # Pre-built agent provided by the squadron (Pattern D) or test
        # harness. When None, ``_make_agent`` falls back to constructing
        # one from the legacy pool registries.
        self._injected_agent = agent
        self._agent: DecomposerAgent | None = None

    async def __post_create__(self) -> None:
        self._agent = self._make_agent()
        await self._agent.open()

    def _make_agent(self) -> DecomposerAgent:
        """Return the injected agent or fall back to legacy pool registries."""
        if self._injected_agent is not None:
            return self._injected_agent
        pool_address: str = self.address
        return DecomposerAgent(
            handle=opencode_handle_for(pool_address),
            cwd=self._cwd,
            role=self._role,
            detail_session_max_turns=self._detail_session_max_turns,
            fix_session_max_turns=self._fix_session_max_turns,
            step_config=self._step_config,
            tier_overrides=tier_overrides_for(pool_address),
            cost_sink=cost_sink_for(pool_address),
            tag=f"decomposer[{self._role}:{self.uid.decode()}]",
        )

    async def __pre_destroy__(self) -> None:
        # Squadron owns the lifecycle of injected agents; the actor only
        # closes agents it constructed itself via the legacy fallback.
        if self._agent is not None and self._injected_agent is None:
            await self._agent.close()

    # ------------------------------------------------------------------
    # Supervisor → agent surface
    # ------------------------------------------------------------------

    async def set_context(self, context: DecomposerContext) -> None:
        """Broadcast context for the upcoming detail phase."""
        assert self._agent is not None
        await self._agent.set_context(
            outline_json=context.outline_json,
            flight_plan_content=context.flight_plan_content,
            verification_properties=context.verification_properties,
        )

    @xo.no_lock
    async def send_outline(self, request: OutlineRequest) -> None:
        """Run the outline prompt, forward :class:`SubmitOutlinePayload`."""
        assert self._agent is not None
        logger.debug("decomposer.phase_starting", phase="outline")
        try:
            payload = await self._agent.outline(
                flight_plan_content=request.flight_plan_content,
                codebase_context=request.codebase_context,
                briefing=request.briefing,
                runway_context=request.runway_context,
                validation_feedback=request.validation_feedback,
            )
        except AgentRuntimeError as exc:
            await self._report_failure(str(exc), phase="outline", unit_id=None)
            return
        except Exception as exc:  # noqa: BLE001
            await self._report_failure(str(exc), phase="outline", unit_id=None)
            return
        await self._supervisor_ref.outline_ready(payload)

    @xo.no_lock
    async def send_detail(self, request: DetailRequest) -> None:
        """Run a detail-pass prompt for one or more units."""
        assert self._agent is not None
        unit_id = request.unit_ids[0] if request.unit_ids else None
        logger.debug("decomposer.phase_starting", phase="detail", unit_id=unit_id)
        try:
            payload = await self._agent.detail(unit_ids=request.unit_ids)
        except AgentRuntimeError as exc:
            await self._report_failure(str(exc), phase="detail", unit_id=unit_id)
            return
        except Exception as exc:  # noqa: BLE001
            await self._report_failure(str(exc), phase="detail", unit_id=unit_id)
            return
        await self._supervisor_ref.detail_ready(payload)

    @xo.no_lock
    async def send_fix(self, request: FixRequest) -> None:
        """Run the fix-pass prompt, forward :class:`SubmitFixPayload`."""
        assert self._agent is not None
        logger.debug("decomposer.phase_starting", phase="fix")
        try:
            payload = await self._agent.fix(
                coverage_gaps=request.coverage_gaps,
                overloaded=request.overloaded,
                outline_json=request.outline_json or None,
                details_json=request.details_json or None,
                verification_properties=request.verification_properties or None,
            )
        except AgentRuntimeError as exc:
            await self._report_failure(str(exc), phase="fix", unit_id=None)
            return
        except Exception as exc:  # noqa: BLE001
            await self._report_failure(str(exc), phase="fix", unit_id=None)
            return
        await self._supervisor_ref.fix_ready(payload)

    @xo.no_lock
    async def send_nudge(self, request: NudgeRequest) -> None:
        """Re-prompt when the supervisor rejected a previous payload."""
        assert self._agent is not None
        try:
            payload: BaseModel = await self._agent.nudge(
                expected_tool=request.expected_tool,
                unit_id=request.unit_id,
                reason=request.reason,
            )
        except AgentRuntimeError as exc:
            await self._report_failure(str(exc), phase="nudge", unit_id=request.unit_id)
            return
        except Exception as exc:  # noqa: BLE001
            await self._report_failure(str(exc), phase="nudge", unit_id=request.unit_id)
            return

        if isinstance(payload, SubmitOutlinePayload):
            await self._supervisor_ref.outline_ready(payload)
        elif isinstance(payload, SubmitDetailsPayload):
            await self._supervisor_ref.detail_ready(payload)
        elif isinstance(payload, SubmitFixPayload):
            await self._supervisor_ref.fix_ready(payload)
        else:
            await self._supervisor_ref.payload_parse_error(
                request.expected_tool,
                f"DecomposerActor nudge produced unexpected {type(payload).__name__}",
            )

    async def _report_failure(self, error: str, *, phase: str, unit_id: str | None) -> None:
        from maverick.exceptions.quota import is_quota_error, is_transient_error

        logger.debug("decomposer.phase_failed", phase=phase, unit_id=unit_id, error=error)
        await self._supervisor_ref.prompt_error(
            PromptError(
                phase=phase,
                error=error,
                quota_exhausted=is_quota_error(error),
                transient=is_transient_error(error),
                unit_id=unit_id,
            )
        )
