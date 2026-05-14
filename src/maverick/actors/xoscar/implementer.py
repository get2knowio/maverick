"""xoscar ImplementerActor — thin shell over :class:`CodingAgent`.

Same supervisor-facing contract as before: supervisors call
``new_bead`` between beads, then ``send_implement`` / ``send_fix``;
errors surface via ``prompt_error``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import xoscar as xo

from maverick.actors.step_config import load_step_config
from maverick.actors.xoscar.messages import (
    FlyFixRequest,
    ImplementRequest,
    NewBeadRequest,
    PromptError,
)
from maverick.agents.coding import CodingAgent
from maverick.logging import get_logger
from maverick.runtime.opencode import (
    OpenCodeError,
    cost_sink_for,
    opencode_handle_for,
    tier_overrides_for,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)


class ImplementerActor(xo.Actor):
    """Implements bead work and addresses fix requests via OpenCode."""

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
        self._agent: CodingAgent | None = None

    async def __post_create__(self) -> None:
        self._agent = self._make_agent()
        await self._agent.open()

    def _make_agent(self) -> CodingAgent:
        """Factory hook — override in tests to inject a stubbed agent."""
        pool_address: str = self.address
        return CodingAgent(
            handle=opencode_handle_for(pool_address),
            cwd=self._cwd,
            step_config=self._step_config,
            tier_overrides=tier_overrides_for(pool_address),
            cost_sink=cost_sink_for(pool_address),
            tag=f"implementer[{self.uid.decode()}]",
        )

    async def __pre_destroy__(self) -> None:
        if self._agent is not None:
            await self._agent.close()

    # ------------------------------------------------------------------
    # Supervisor → agent surface
    # ------------------------------------------------------------------

    async def new_bead(self, request: NewBeadRequest) -> None:
        """Rotate the OpenCode session so the next prompt starts clean."""
        assert self._agent is not None
        try:
            await self._agent.rotate_session()
        except Exception as exc:  # noqa: BLE001 — bubble through supervisor
            await self._report_prompt_error(
                phase="new_bead", error=str(exc), bead_id=request.bead_id
            )

    @xo.no_lock
    async def send_implement(self, request: ImplementRequest) -> None:
        assert self._agent is not None
        logger.debug("implementer.phase_starting", phase="implement", bead_id=request.bead_id)
        try:
            payload = await self._agent.implement(request.prompt, bead_id=request.bead_id)
        except OpenCodeError as exc:
            await self._report_prompt_error(
                phase="implement", error=str(exc), bead_id=request.bead_id
            )
            return
        except Exception as exc:  # noqa: BLE001 — supervisor decides retry policy
            await self._report_prompt_error(
                phase="implement", error=str(exc), bead_id=request.bead_id
            )
            return
        await self._supervisor_ref.implementation_ready(payload)

    @xo.no_lock
    async def send_fix(self, request: FlyFixRequest) -> None:
        assert self._agent is not None
        logger.debug("implementer.phase_starting", phase="fix", bead_id=request.bead_id)
        try:
            payload = await self._agent.fix(request.prompt, bead_id=request.bead_id)
        except OpenCodeError as exc:
            await self._report_prompt_error(phase="fix", error=str(exc), bead_id=request.bead_id)
            return
        except Exception as exc:  # noqa: BLE001 — supervisor decides retry policy
            await self._report_prompt_error(phase="fix", error=str(exc), bead_id=request.bead_id)
            return
        await self._supervisor_ref.fix_result_ready(payload)

    async def _report_prompt_error(self, *, phase: str, error: str, bead_id: str) -> None:
        from maverick.exceptions.quota import is_quota_error, is_transient_error

        logger.debug("implementer.phase_failed", phase=phase, bead_id=bead_id, error=error)
        await self._supervisor_ref.prompt_error(
            PromptError(
                phase=phase,
                error=error,
                quota_exhausted=is_quota_error(error),
                transient=is_transient_error(error),
                unit_id=bead_id,
            )
        )
