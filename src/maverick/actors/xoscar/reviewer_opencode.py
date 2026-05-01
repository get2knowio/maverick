"""xoscar reviewer actor backed by OpenCode (Phase 2 migration target).

Same behavioural contract as :class:`ReviewerActor` (the legacy
ACP+MCP variant) — receives :class:`ReviewRequest` /
:class:`AggregateReviewRequest`, forwards :class:`SubmitReviewPayload`
to the supervisor's ``review_ready`` / ``aggregate_review_ready`` —
but the transport is OpenCode HTTP with ``format=json_schema`` instead
of the per-actor MCP gateway.

What we delete relative to the legacy reviewer:

* The MCP tool registration / unregistration boilerplate.
* ``on_tool_call``.
* The two-turn self-nudge loop (``_run_with_self_nudge``,
  ``build_tool_required_nudge_prompt``). OpenCode's tool-forcing makes
  this dead code — the synthesized ``StructuredOutput`` tool is called
  by the model on every successful turn.
* The JSON-in-text fallback. Same reason.
* The ``_end_turn`` cancel hook. The send returns when the turn is done.

Kept from the legacy reviewer:

* The first-turn full-context prompt vs. follow-up "review changes" prompt.
* Aggregate-review flow.
* Routing of ``payload_parse_error`` for aggregate failures (non-fatal)
  vs. ``prompt_error`` for per-bead failures (fatal until escalated).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import xoscar as xo

from maverick.actors.step_config import load_step_config
from maverick.actors.xoscar.messages import (
    AggregateReviewRequest,
    NewBeadRequest,
    PromptError,
    ReviewRequest,
)
from maverick.actors.xoscar.opencode_mixin import OpenCodeAgentMixin
from maverick.logging import get_logger
from maverick.runtime.opencode import OpenCodeError
from maverick.tools.agent_inbox.models import SubmitReviewPayload

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)

REVIEW_PROMPT_TIMEOUT_SECONDS = 600
AGGREGATE_REVIEW_TIMEOUT_SECONDS = 600


class OpenCodeReviewerActor(OpenCodeAgentMixin, xo.Actor):
    """OpenCode-backed reviewer.

    Behaviour parity with :class:`ReviewerActor` from the legacy mixin
    so the supervisor's ``review_ready`` / ``aggregate_review_ready`` /
    ``prompt_error`` paths see exactly the same messages.
    """

    result_model: ClassVar[type[SubmitReviewPayload]] = SubmitReviewPayload
    provider_tier: ClassVar[str] = "review"

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str,
        config: StepConfig | dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        if not cwd:
            raise ValueError("OpenCodeReviewerActor requires 'cwd'")
        self._supervisor_ref = supervisor_ref
        self._cwd = cwd
        self._step_config = load_step_config(config)
        self._review_count = 0
        self._in_aggregate = False

    async def __post_create__(self) -> None:
        self._actor_tag = f"reviewer-oc[{self.uid.decode()}]"
        await self._opencode_post_create()

    async def __pre_destroy__(self) -> None:
        await self._opencode_pre_destroy()

    # ------------------------------------------------------------------
    # Supervisor → agent surface
    # ------------------------------------------------------------------

    async def new_bead(self, request: NewBeadRequest) -> None:
        """Rotate the OpenCode session for a new bead."""
        self._review_count = 0
        self._in_aggregate = False
        try:
            await self._rotate_session()
        except Exception as exc:  # noqa: BLE001 — bubble through supervisor's error channel
            await self._supervisor_ref.prompt_error(
                PromptError(
                    phase="new_bead",
                    error=str(exc),
                    unit_id=request.bead_id,
                )
            )

    @xo.no_lock
    async def send_review(self, request: ReviewRequest) -> None:
        """Run a per-bead review and forward ``review_ready``.

        On any classified failure, route a :class:`PromptError` instead.
        """
        self._review_count += 1
        self._in_aggregate = False
        prompt = self._build_review_prompt(request)
        logger.debug(
            "reviewer_oc.review_starting",
            review_count=self._review_count,
            bead_id=request.bead_id,
        )

        try:
            payload = await self._send_structured(prompt, timeout=REVIEW_PROMPT_TIMEOUT_SECONDS)
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

        if not isinstance(payload, SubmitReviewPayload):
            await self._supervisor_ref.payload_parse_error(
                "submit_review",
                "OpenCodeReviewerActor expected SubmitReviewPayload, "
                f"got {type(payload).__name__}",
            )
            return

        await self._supervisor_ref.review_ready(payload)

    @xo.no_lock
    async def send_aggregate_review(self, request: AggregateReviewRequest) -> None:
        """Run the epic-level aggregate review.

        Aggregate failures are non-fatal — we route them through
        ``payload_parse_error`` so the epic still closes.
        """
        self._in_aggregate = True
        logger.debug("reviewer_oc.aggregate_starting", bead_count=request.bead_count)

        # Aggregate review starts a new context regardless of prior bead history.
        try:
            await self._rotate_session()
        except Exception as exc:  # noqa: BLE001
            logger.error("reviewer_oc.aggregate_session_rotate_failed", error=str(exc))
            await self._supervisor_ref.payload_parse_error("aggregate_review", str(exc))
            return

        prompt = self._build_aggregate_prompt(request)
        try:
            payload = await self._send_structured(prompt, timeout=AGGREGATE_REVIEW_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001
            logger.error("reviewer_oc.aggregate_failed", error=str(exc))
            await self._supervisor_ref.payload_parse_error("aggregate_review", str(exc))
            return

        if not isinstance(payload, SubmitReviewPayload):
            await self._supervisor_ref.payload_parse_error(
                "aggregate_review",
                "OpenCodeReviewerActor expected SubmitReviewPayload, "
                f"got {type(payload).__name__}",
            )
            return

        await self._supervisor_ref.aggregate_review_ready(payload)
        logger.debug("reviewer_oc.aggregate_completed")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _report_prompt_error(self, *, phase: str, error: str, bead_id: str) -> None:
        from maverick.exceptions.quota import is_quota_error, is_transient_error

        logger.debug("reviewer_oc.prompt_error", phase=phase, error=error)
        await self._supervisor_ref.prompt_error(
            PromptError(
                phase=phase,
                error=error,
                quota_exhausted=is_quota_error(error),
                transient=is_transient_error(error),
                unit_id=bead_id,
            )
        )

    def _build_review_prompt(self, request: ReviewRequest) -> str:
        if self._review_count == 1:
            sections: list[str] = []
            if request.work_unit_md:
                sections.append(f"## Work Unit Specification\n\n{request.work_unit_md}")
            else:
                sections.append(f"## Task Description\n\n{request.bead_description}")
            if request.briefing_context:
                briefing_excerpt = request.briefing_context[:4000]
                sections.append(
                    f"## Pre-Flight Briefing (risks & contrarian findings)\n\n{briefing_excerpt}"
                )
            user_content = "\n\n".join(sections)

            return (
                "You are the REVIEWER, NOT the implementer. The implementation "
                "is already complete in the working directory. Read the existing "
                "code and judge it against the work unit specification below — "
                "do NOT write or edit code. The 'Implement X' instructions in "
                "the spec were directed at the implementer (already done), not "
                "at you.\n\n"
                "Also consult `.maverick/runway/` for project context if it "
                "exists (`episodic/review-findings.jsonl`, "
                "`episodic/bead-outcomes.jsonl`, `semantic/`).\n\n"
                "Review checklist:\n"
                "1. Does the implementation satisfy ALL acceptance criteria in "
                "the work unit spec?\n"
                "2. Are there bugs, security issues, or correctness problems?\n"
                "3. Does the approach align with the briefing's risk assessment "
                "and contrarian findings?\n"
                "4. Only flag CRITICAL or MAJOR issues.\n\n"
                f"# Review context\n\n{user_content}\n\n"
                "Set approved=true with an empty findings array if no "
                "critical/major issues."
            )
        return (
            "The implementer has made changes since your previous review. "
            "Review ONLY whether your previous findings were addressed; do "
            "NOT introduce new findings."
        )

    def _build_aggregate_prompt(self, request: AggregateReviewRequest) -> str:
        return (
            "Review the AGGREGATE changes across all beads in this epic.\n\n"
            f"## Flight Plan\n\n{request.objective}\n\n"
            f"## Beads Completed\n\n{request.bead_list}\n\n"
            f"## Full Diff Stats\n\n```\n{request.diff_stat}\n```\n\n"
            "## Focus Areas\n\n"
            "- Cross-bead consistency: are deleted modules still referenced "
            "elsewhere?\n"
            "- Architectural coherence: do the approaches across beads align "
            "with each other?\n"
            "- Missing integration between beads\n"
            "- Dead code left behind by one bead that another bead depended on\n\n"
            "Do NOT re-review individual bead correctness — that was already "
            "done per-bead.\n\n"
            "Set approved=true if no cross-bead concerns found."
        )
