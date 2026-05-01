"""xoscar DecomposerActor — OpenCode-backed decomposition agent.

Three phases — ``send_outline``, ``send_detail``, ``send_fix`` — each
returning a typed payload to a different supervisor method
(``outline_ready``, ``detail_ready``, ``fix_ready``). The
``StructuredOutput`` tool forces the model to comply on the first turn,
so the legacy two-turn self-nudge loop and JSON-in-text fallback are
gone.

Session-mode rotation (``_ensure_mode_session``) is preserved: detail
and fix phases reuse the same OpenCode session across multiple turns to
keep the seeded context (flight plan + outline JSON) cached, rotating
when the mode changes or the per-mode turn budget is exhausted.

Two roles:

* ``primary`` — outline + detail + fix.
* ``pool`` — detail-only worker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

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
from maverick.actors.xoscar.opencode_mixin import OpenCodeAgentMixin
from maverick.logging import get_logger
from maverick.runtime.opencode import OpenCodeError
from maverick.tools.agent_inbox.models import (
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitOutlinePayload,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)


DETAIL_TIMEOUT_SECONDS = 1200
DEFAULT_PROMPT_TIMEOUT_SECONDS = 1800


class DecomposerActor(OpenCodeAgentMixin, xo.Actor):
    """Sends structured prompts for decomposition phases."""

    # Outline is the most common entry; subclassed phases pass their own
    # schema explicitly via ``_send_structured(schema=...)``.
    result_model: ClassVar[type[BaseModel]] = SubmitOutlinePayload
    provider_tier: ClassVar[str] = "decompose"

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str,
        config: StepConfig | dict[str, Any] | None = None,
        role: str = "primary",
        detail_session_max_turns: int = 5,
        fix_session_max_turns: int = 1,
    ) -> None:
        super().__init__()
        if not cwd:
            raise ValueError("DecomposerActor requires 'cwd'")
        self._supervisor_ref = supervisor_ref
        self._cwd = cwd
        self._step_config = load_step_config(config)
        self._role = role
        self._detail_session_max_turns = max(1, int(detail_session_max_turns))
        self._fix_session_max_turns = max(1, int(fix_session_max_turns))

        # Session-mode bookkeeping (preserved from the legacy actor so we
        # keep the seeded prompt-cache benefit across detail turns).
        self._session_mode: str | None = None
        self._session_turns_in_mode = 0

        # Seeded-context for detail / fix prompts.
        self._detail_outline_json: str = "{}"
        self._detail_flight_plan: str = ""
        self._detail_verification: str = ""
        self._detail_seed_stale = True

        self._fix_outline_json: str = '{"work_units": []}'
        self._fix_details_json: str = '{"details": []}'
        self._fix_verification: str = ""
        self._fix_seed_stale = True

    async def __post_create__(self) -> None:
        self._actor_tag = f"decomposer[{self._role}:{self.uid.decode()}]"
        await self._opencode_post_create()

    async def __pre_destroy__(self) -> None:
        await self._opencode_pre_destroy()

    # ------------------------------------------------------------------
    # Supervisor → agent surface
    # ------------------------------------------------------------------

    async def set_context(self, context: DecomposerContext) -> None:
        """Broadcast context for the upcoming detail phase."""
        self._detail_outline_json = context.outline_json
        self._detail_flight_plan = context.flight_plan_content
        self._detail_verification = context.verification_properties
        self._detail_seed_stale = True

    @xo.no_lock
    async def send_outline(self, request: OutlineRequest) -> None:
        """Run the outline prompt, forward :class:`SubmitOutlinePayload`."""
        prompt = await self._build_outline_prompt(request)
        payload = await self._run_phase(
            prompt,
            phase="outline",
            schema=SubmitOutlinePayload,
            mode="outline",
            seed_stale=True,
            max_turns=1,
            timeout=DEFAULT_PROMPT_TIMEOUT_SECONDS,
        )
        if payload is None:
            return
        if isinstance(payload, SubmitOutlinePayload):
            await self._supervisor_ref.outline_ready(payload)
        else:
            await self._supervisor_ref.payload_parse_error(
                "submit_outline",
                f"DecomposerActor expected SubmitOutlinePayload, got {type(payload).__name__}",
            )

    @xo.no_lock
    async def send_detail(self, request: DetailRequest) -> None:
        """Run a detail-pass prompt for one or more units."""
        unit_id = request.unit_ids[0] if request.unit_ids else None
        prompt, refreshed_seed = await self._build_detail_prompt(request)
        payload = await self._run_phase(
            prompt,
            phase="detail",
            schema=SubmitDetailsPayload,
            mode="detail",
            seed_stale=refreshed_seed,
            max_turns=self._detail_session_max_turns,
            timeout=DETAIL_TIMEOUT_SECONDS,
            unit_id=unit_id,
        )
        if payload is None:
            return
        if isinstance(payload, SubmitDetailsPayload):
            await self._supervisor_ref.detail_ready(payload)
        else:
            await self._supervisor_ref.payload_parse_error(
                "submit_details",
                f"DecomposerActor expected SubmitDetailsPayload, got {type(payload).__name__}",
            )
        # The detail-mode seed has been delivered with this turn; future
        # turns within the same session reuse it.
        self._detail_seed_stale = False
        if self._session_mode == "detail":
            self._session_turns_in_mode += 1

    @xo.no_lock
    async def send_fix(self, request: FixRequest) -> None:
        """Run the fix-pass prompt, forward :class:`SubmitFixPayload`."""
        self._fix_outline_json = request.outline_json or self._fix_outline_json
        self._fix_details_json = request.details_json or self._fix_details_json
        self._fix_verification = request.verification_properties or self._fix_verification
        prompt, refreshed_seed = await self._build_fix_prompt(request)
        payload = await self._run_phase(
            prompt,
            phase="fix",
            schema=SubmitFixPayload,
            mode="fix",
            seed_stale=refreshed_seed,
            max_turns=self._fix_session_max_turns,
            timeout=DEFAULT_PROMPT_TIMEOUT_SECONDS,
        )
        if payload is None:
            return
        if isinstance(payload, SubmitFixPayload):
            await self._supervisor_ref.fix_ready(payload)
        else:
            await self._supervisor_ref.payload_parse_error(
                "submit_fix",
                f"DecomposerActor expected SubmitFixPayload, got {type(payload).__name__}",
            )
        self._fix_seed_stale = False
        if self._session_mode == "fix":
            self._session_turns_in_mode += 1

    @xo.no_lock
    async def send_nudge(self, request: NudgeRequest) -> None:
        """Re-prompt when the supervisor rejected a previous payload."""
        prompt = self._build_nudge_prompt(request)
        # Pick the schema matching the expected tool.
        schema_map: dict[str, type[BaseModel]] = {
            "submit_outline": SubmitOutlinePayload,
            "submit_details": SubmitDetailsPayload,
            "submit_fix": SubmitFixPayload,
        }
        schema = schema_map.get(request.expected_tool, SubmitOutlinePayload)
        try:
            payload = await self._send_structured(
                prompt, schema=schema, timeout=DEFAULT_PROMPT_TIMEOUT_SECONDS
            )
        except OpenCodeError as exc:
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

    # ------------------------------------------------------------------
    # Phase runner
    # ------------------------------------------------------------------

    async def _run_phase(
        self,
        prompt: str,
        *,
        phase: str,
        schema: type[BaseModel],
        mode: str,
        seed_stale: bool,
        max_turns: int,
        timeout: int,
        unit_id: str | None = None,
    ) -> BaseModel | None:
        """Drive the structured send and route failures to ``prompt_error``."""
        logger.debug(
            "decomposer.phase_starting",
            phase=phase,
            unit_id=unit_id,
            mode=mode,
            seed_stale=seed_stale,
            max_turns=max_turns,
        )
        await self._maybe_rotate_session(mode=mode, seed_stale=seed_stale, max_turns=max_turns)
        try:
            return await self._send_structured(prompt, schema=schema, timeout=timeout)
        except OpenCodeError as exc:
            await self._report_failure(str(exc), phase=phase, unit_id=unit_id)
            return None
        except Exception as exc:  # noqa: BLE001 — supervisor decides retry policy
            await self._report_failure(str(exc), phase=phase, unit_id=unit_id)
            return None

    async def _maybe_rotate_session(self, *, mode: str, seed_stale: bool, max_turns: int) -> None:
        """Rotate the OpenCode session when the mode changes or the budget is hit."""
        if self._session_id is None:
            self._session_mode = mode
            self._session_turns_in_mode = 0
            return
        if (
            self._session_mode != mode
            or self._session_turns_in_mode >= max(1, max_turns)
            or seed_stale
        ):
            reason = (
                "mode_change"
                if self._session_mode != mode
                else "turn_limit"
                if self._session_turns_in_mode >= max(1, max_turns)
                else "seed_stale"
            )
            logger.info(
                "decomposer.session_rotated",
                actor=self._actor_tag,
                role=self._role,
                mode=mode,
                reason=reason,
                previous_session=self._session_id,
                previous_mode=self._session_mode,
                previous_turns=self._session_turns_in_mode,
                max_turns=max_turns,
            )
            await self._rotate_session()
            self._session_mode = mode
            self._session_turns_in_mode = 0

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

    # ------------------------------------------------------------------
    # Prompt builders (delegate to the existing decompose helpers)
    # ------------------------------------------------------------------

    async def _build_outline_prompt(self, request: OutlineRequest) -> str:
        from maverick.library.actions.decompose import build_outline_prompt

        body = build_outline_prompt(
            request.flight_plan_content,
            request.codebase_context,
            briefing=request.briefing,
            runway_context=request.runway_context,
        )
        if request.validation_feedback:
            body += (
                "\n\n## PREVIOUS ATTEMPT FAILED VALIDATION\n"
                f"{request.validation_feedback}\n"
                "Fix these issues in your new decomposition."
            )
        return (
            "You are the decomposer's outline pass.\n\n"
            "# Decomposition input (flight plan + briefing)\n\n"
            f"{body}"
        )

    async def _build_detail_prompt(self, request: DetailRequest) -> tuple[str, bool]:
        from maverick.library.actions.decompose import (
            build_detail_seed_prompt,
            build_detail_turn_prompt,
        )

        unit_ids = list(request.unit_ids)
        # Always include the seed when the cache is stale; the session
        # rotation logic below decides whether the in-session cache hits.
        needs_seed = self._detail_seed_stale or self._session_mode != "detail"
        prompt_parts: list[str] = []
        if needs_seed:
            prompt_parts.append(
                build_detail_seed_prompt(
                    flight_plan_content=self._detail_flight_plan,
                    outline_json=self._detail_outline_json,
                    verification_properties=self._detail_verification,
                )
            )
        prompt_parts.append(build_detail_turn_prompt(unit_ids=unit_ids))
        body = "\n\n".join(prompt_parts)
        return (
            "You are the decomposer's detail pass.\n\n"
            "# Decomposition input (outline + details turn)\n\n"
            f"{body}",
            needs_seed,
        )

    async def _build_fix_prompt(self, request: FixRequest) -> tuple[str, bool]:
        from maverick.library.actions.decompose import (
            build_fix_seed_prompt,
            build_fix_turn_prompt,
        )

        needs_seed = self._fix_seed_stale or self._session_mode != "fix"
        prompt_parts: list[str] = []
        if needs_seed:
            prompt_parts.append(
                build_fix_seed_prompt(
                    outline_json=self._fix_outline_json,
                    details_json=self._fix_details_json,
                    verification_properties=self._fix_verification,
                )
            )
        prompt_parts.append(
            build_fix_turn_prompt(
                coverage_gaps=list(request.coverage_gaps),
                overloaded=list(request.overloaded),
            )
        )
        body = "\n\n".join(prompt_parts)
        return (
            "You are the decomposer's fix pass. Submit the COMPLETE updated "
            "work_units and details, not just the changes.\n\n"
            "# Decomposition input (fix turn)\n\n"
            f"{body}",
            needs_seed,
        )

    def _build_nudge_prompt(self, request: NudgeRequest) -> str:
        guidance: list[str] = []
        if request.expected_tool == "submit_details" and request.unit_id:
            guidance.append(f"Provide a complete entry for `{request.unit_id}`.")
        else:
            guidance.append("Submit even partial results rather than refusing.")
        if request.reason:
            guidance.append(f"Reason: {request.reason}")
        return (
            f"Re-submit your previous response with the corrected payload.\n\n{' '.join(guidance)}"
        )
