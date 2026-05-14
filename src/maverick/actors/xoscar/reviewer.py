"""xoscar ReviewerActor — thin shell over :class:`ReviewerAgent`.

Per-bead review + epic-aggregate review. Two instances run per workflow
(correctness + completeness lenses) and the supervisor merges payloads.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import xoscar as xo

from maverick.actors.step_config import load_step_config
from maverick.actors.xoscar.messages import (
    AggregateReviewRequest,
    NewBeadRequest,
    PromptError,
    ReviewRequest,
)
from maverick.agents.reviewer import (
    AGGREGATE_REVIEW_TIMEOUT_SECONDS,
    REVIEW_PROMPT_TIMEOUT_SECONDS,
    ReviewerAgent,
    ReviewKind,
)
from maverick.logging import get_logger
from maverick.payloads import SubmitReviewPayload
from maverick.runtime.opencode import (
    OpenCodeError,
    cost_sink_for,
    opencode_handle_for,
    tier_overrides_for,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)


__all__ = [
    "AGGREGATE_REVIEW_TIMEOUT_SECONDS",
    "REVIEW_PROMPT_TIMEOUT_SECONDS",
    "ReviewerActor",
]


class ReviewerActor(xo.Actor):
    """Reviewer (correctness or completeness lens)."""

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str,
        config: StepConfig | dict[str, Any] | None = None,
        opencode_agent: str = "maverick.correctness-reviewer",
        review_kind: ReviewKind = "correctness",
    ) -> None:
        super().__init__()
        if not cwd:
            raise ValueError("ReviewerActor requires 'cwd'")
        if review_kind not in ("correctness", "completeness"):
            raise ValueError(
                f"ReviewerActor 'review_kind' must be 'correctness' or "
                f"'completeness', got {review_kind!r}"
            )
        self._supervisor_ref = supervisor_ref
        self._cwd = cwd
        self._step_config = load_step_config(config)
        self._opencode_agent_name = opencode_agent
        self._review_kind: ReviewKind = review_kind
        self._agent: ReviewerAgent | None = None

    async def __post_create__(self) -> None:
        self._agent = self._make_agent()
        await self._agent.open()

    def _make_agent(self) -> ReviewerAgent:
        """Factory hook — override in tests to inject a stubbed agent."""
        pool_address: str = self.address
        return ReviewerAgent(
            handle=opencode_handle_for(pool_address),
            cwd=self._cwd,
            review_kind=self._review_kind,
            opencode_agent=self._opencode_agent_name,
            step_config=self._step_config,
            tier_overrides=tier_overrides_for(pool_address),
            cost_sink=cost_sink_for(pool_address),
            tag=f"reviewer[{self.uid.decode()}]",
        )

    async def __pre_destroy__(self) -> None:
        if self._agent is not None:
            await self._agent.close()

    # ------------------------------------------------------------------
    # Supervisor → agent surface
    # ------------------------------------------------------------------

    async def new_bead(self, request: NewBeadRequest) -> None:
        """Rotate the OpenCode session for a new bead."""
        assert self._agent is not None
        try:
            await self._agent.rotate_session()
        except Exception as exc:  # noqa: BLE001 — bubble through supervisor
            await self._supervisor_ref.prompt_error(
                PromptError(
                    phase="new_bead",
                    error=str(exc),
                    unit_id=request.bead_id,
                )
            )

    @xo.no_lock
    async def send_review(self, request: ReviewRequest) -> None:
        """Run a per-bead review and forward typed payload."""
        from maverick.agents.context import tagged

        assert self._agent is not None
        logger.debug(
            "reviewer.review_starting",
            bead_id=request.bead_id,
            review_kind=self._review_kind,
        )
        try:
            with tagged(bead_id=request.bead_id):
                payload = await self._agent.review(
                    bead_description=request.bead_description,
                    work_unit_md=request.work_unit_md,
                    briefing_context=request.briefing_context,
                )
        except OpenCodeError as exc:
            await self._report_prompt_error(
                phase="review", error=str(exc), bead_id=request.bead_id
            )
            return
        except Exception as exc:  # noqa: BLE001 — supervisor decides retry policy
            await self._report_prompt_error(
                phase="review", error=str(exc), bead_id=request.bead_id
            )
            return

        if self._review_kind == "correctness":
            await self._supervisor_ref.correctness_review_ready(payload)
        else:
            await self._supervisor_ref.completeness_review_ready(payload)
        # Back-compat fan-out for callers that don't distinguish lenses.
        await self._supervisor_ref.review_ready(payload)

    @xo.no_lock
    async def send_aggregate_review(self, request: AggregateReviewRequest) -> None:
        """Run the epic-level aggregate review.

        Aggregate failures are non-fatal — they route through
        ``payload_parse_error`` so the epic still closes.
        """
        assert self._agent is not None
        logger.debug("reviewer.aggregate_starting", bead_count=request.bead_count)
        try:
            payload: SubmitReviewPayload = await self._agent.aggregate(
                objective=request.objective,
                bead_list=request.bead_list,
                diff_stat=request.diff_stat,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("reviewer.aggregate_failed", error=str(exc))
            await self._supervisor_ref.payload_parse_error("aggregate_review", str(exc))
            return
        await self._supervisor_ref.aggregate_review_ready(payload)
        logger.debug("reviewer.aggregate_completed")

    async def _report_prompt_error(self, *, phase: str, error: str, bead_id: str) -> None:
        from maverick.exceptions.quota import is_quota_error, is_transient_error

        logger.debug(
            "reviewer.prompt_error",
            phase=phase,
            error=error,
            review_kind=self._review_kind,
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
