"""xoscar ImplementerActor — OpenCode-backed agent actor.

Owns two structured-output payloads:

* ``submit_implementation`` (:class:`SubmitImplementationPayload`) —
  forwarded to the supervisor as ``implementation_ready``.
* ``submit_fix_result`` (:class:`SubmitFixResultPayload`) — forwarded as
  ``fix_result_ready``.

The legacy ACP+MCP-gateway pattern is gone:

* No per-actor MCP tool registration / unregistration.
* No two-turn self-nudge loop. OpenCode's ``StructuredOutput`` tool
  forces the model to return a typed payload on the first turn.
* No JSON-in-text fallback. The runtime layer surfaces classified
  errors instead.
* No per-actor ACP subprocess. The actor pool spawns one OpenCode
  server per workflow run.

Same supervisor-facing contract as before: supervisors call
``new_bead`` between beads, then ``send_implement`` / ``send_fix``;
errors surface via ``prompt_error``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import xoscar as xo
from pydantic import BaseModel

from maverick.actors.step_config import load_step_config
from maverick.actors.xoscar.messages import (
    FlyFixRequest,
    ImplementRequest,
    NewBeadRequest,
    PromptError,
)
from maverick.actors.xoscar.opencode_mixin import OpenCodeAgentMixin
from maverick.logging import get_logger
from maverick.runtime.opencode import OpenCodeError
from maverick.tools.agent_inbox.models import (
    SubmitFixResultPayload,
    SubmitImplementationPayload,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)

IMPLEMENTER_PROMPT_TIMEOUT_SECONDS = 1800


class ImplementerActor(OpenCodeAgentMixin, xo.Actor):
    """Implements bead work and addresses fix requests via OpenCode."""

    # Default schema for implement-phase prompts; the fix phase passes its
    # own schema explicitly to ``_send_structured``.
    result_model: ClassVar[type[BaseModel]] = SubmitImplementationPayload
    provider_tier: ClassVar[str] = "implement"

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
        await self._opencode_post_create()

    async def __pre_destroy__(self) -> None:
        await self._opencode_pre_destroy()

    # ------------------------------------------------------------------
    # Supervisor → agent surface
    # ------------------------------------------------------------------

    async def new_bead(self, request: NewBeadRequest) -> None:
        """Rotate the OpenCode session so the next prompt starts clean."""
        try:
            await self._rotate_session()
        except Exception as exc:  # noqa: BLE001 — bubble through supervisor
            await self._report_prompt_error(
                phase="new_bead", error=str(exc), bead_id=request.bead_id
            )

    @xo.no_lock
    async def send_implement(self, request: ImplementRequest) -> None:
        await self._run_phase(
            request.prompt,
            phase="implement",
            schema=SubmitImplementationPayload,
            bead_id=request.bead_id,
        )

    @xo.no_lock
    async def send_fix(self, request: FlyFixRequest) -> None:
        await self._run_phase(
            request.prompt,
            phase="fix",
            schema=SubmitFixResultPayload,
            bead_id=request.bead_id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _run_phase(
        self,
        prompt_text: str,
        *,
        phase: str,
        schema: type[BaseModel],
        bead_id: str,
    ) -> None:
        logger.debug("implementer.phase_starting", phase=phase, bead_id=bead_id)
        try:
            payload = await self._send_structured(
                prompt_text,
                schema=schema,
                timeout=IMPLEMENTER_PROMPT_TIMEOUT_SECONDS,
            )
        except OpenCodeError as exc:
            await self._report_prompt_error(
                phase=phase, error=str(exc), bead_id=bead_id
            )
            return
        except Exception as exc:  # noqa: BLE001 — supervisor decides retry policy
            await self._report_prompt_error(
                phase=phase, error=str(exc), bead_id=bead_id
            )
            return

        if isinstance(payload, SubmitImplementationPayload):
            await self._supervisor_ref.implementation_ready(payload)
        elif isinstance(payload, SubmitFixResultPayload):
            await self._supervisor_ref.fix_result_ready(payload)
        else:
            await self._supervisor_ref.payload_parse_error(
                schema.__name__,
                f"ImplementerActor expected {schema.__name__}, "
                f"got {type(payload).__name__}",
            )

    async def _report_prompt_error(
        self, *, phase: str, error: str, bead_id: str
    ) -> None:
        from maverick.exceptions.quota import is_quota_error, is_transient_error

        logger.debug(
            "implementer.phase_failed", phase=phase, bead_id=bead_id, error=error
        )
        await self._supervisor_ref.prompt_error(
            PromptError(
                phase=phase,
                error=error,
                quota_exhausted=is_quota_error(error),
                transient=is_transient_error(error),
                unit_id=bead_id,
            )
        )
