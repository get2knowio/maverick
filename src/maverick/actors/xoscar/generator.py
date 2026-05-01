"""xoscar GeneratorActor — OpenCode-backed flight-plan generator.

Same supervisor-facing contract as the legacy ACP+MCP version:
``send_generate`` runs the prompt and forwards a typed
:class:`SubmitFlightPlanPayload` to the supervisor's
``flight_plan_ready`` method, or routes a :class:`PromptError` on
failure. The transport is now OpenCode HTTP with
``format=json_schema``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import xoscar as xo

from maverick.actors.step_config import load_step_config
from maverick.actors.xoscar.messages import GenerateRequest, PromptError
from maverick.actors.xoscar.opencode_mixin import OpenCodeAgentMixin
from maverick.logging import get_logger
from maverick.runtime.opencode import OpenCodeError
from maverick.tools.agent_inbox.models import SubmitFlightPlanPayload

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)

GENERATOR_PROMPT_TIMEOUT_SECONDS = 1200

_GENERATOR_ROLE_INTRO = (
    "You are a flight plan generator. DO NOT read files from "
    "the filesystem. DO NOT explore the codebase. DO NOT write "
    "code. Your sole output is a single structured response with "
    "these fields: objective (one-line summary), success_criteria "
    "(array of {description, verification}), in_scope, "
    "out_of_scope, constraints, context (markdown), tags."
)


class GeneratorActor(OpenCodeAgentMixin, xo.Actor):
    """Generates a flight plan from PRD + briefing context."""

    result_model: ClassVar[type[SubmitFlightPlanPayload]] = SubmitFlightPlanPayload
    provider_tier: ClassVar[str] = "generate"

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
        await self._opencode_post_create()

    async def __pre_destroy__(self) -> None:
        await self._opencode_pre_destroy()

    # ------------------------------------------------------------------
    # Supervisor → agent
    # ------------------------------------------------------------------

    @xo.no_lock
    async def send_generate(self, request: GenerateRequest) -> None:
        """Run the flight-plan generation prompt and forward the typed payload."""
        logger.debug("generator.prompt_starting")
        prompt = (
            f"{_GENERATOR_ROLE_INTRO}\n\n"
            "# PRD and briefing\n\n"
            f"{request.prompt}"
        )
        try:
            payload = await self._send_structured(
                prompt, timeout=GENERATOR_PROMPT_TIMEOUT_SECONDS
            )
        except OpenCodeError as exc:
            await self._report_prompt_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — supervisor decides retry policy
            await self._report_prompt_error(str(exc))
            return

        if not isinstance(payload, SubmitFlightPlanPayload):
            await self._supervisor_ref.payload_parse_error(
                "submit_flight_plan",
                f"GeneratorActor expected SubmitFlightPlanPayload, "
                f"got {type(payload).__name__}",
            )
            return

        await self._supervisor_ref.flight_plan_ready(payload)

    async def _report_prompt_error(self, error: str) -> None:
        from maverick.exceptions.quota import is_quota_error, is_transient_error

        logger.debug("generator.prompt_failed", error=error)
        await self._supervisor_ref.prompt_error(
            PromptError(
                phase="generate",
                error=error,
                quota_exhausted=is_quota_error(error),
                transient=is_transient_error(error),
            )
        )
