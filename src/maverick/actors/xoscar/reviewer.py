"""xoscar ReviewerActor — OpenCode-backed code reviewer.

Receives :class:`ReviewRequest` / :class:`AggregateReviewRequest` from
the supervisor; forwards typed :class:`SubmitReviewPayload` payloads via
``review_ready`` / ``aggregate_review_ready``. Errors route through
``prompt_error`` (per-bead, fatal until escalated) or
``payload_parse_error`` (aggregate, non-fatal at the workflow level).

Transport: OpenCode HTTP with ``format=json_schema``. The legacy
ACP+MCP-gateway path is gone — no on_tool_call, no two-turn self-nudge,
no JSON-in-text fallback. OpenCode's ``StructuredOutput`` tool forces
the model to comply on the first turn.

Parallel reviewer split (Phase 6+):

The supervisor instantiates **two** ``ReviewerActor`` instances per tier
— one with ``opencode_agent="maverick.correctness-reviewer"`` and
``review_kind="correctness"``, one with the completeness counterparts.
xoscar runs them as independent actors on the same pool; the supervisor
fans out via ``asyncio.gather`` and merges payloads. The actor stamps
each finding's ``reviewer`` field from ``review_kind`` so the supervisor
can attribute findings back to the lens that flagged them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal

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
from maverick.payloads import ReviewFindingPayload, SubmitReviewPayload
from maverick.runtime.opencode import OpenCodeError

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)

REVIEW_PROMPT_TIMEOUT_SECONDS = 600
AGGREGATE_REVIEW_TIMEOUT_SECONDS = 600

ReviewKind = Literal["correctness", "completeness"]


class ReviewerActor(OpenCodeAgentMixin, xo.Actor):
    """Reviewer with OpenCode-backed structured-output transport.

    The persona system prompt is loaded from
    ``runtime/opencode/profile/agents/<opencode_agent>.md`` via
    ``OPENCODE_CONFIG_DIR``. Two actor instances run in parallel for
    every bead — see module docstring for the supervisor-side pattern.
    """

    result_model: ClassVar[type[SubmitReviewPayload]] = SubmitReviewPayload
    provider_tier: ClassVar[str] = "review"

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
        self._review_count = 0
        self._in_aggregate = False
        # Per-instance persona override + provenance tag. ``opencode_agent``
        # supersedes the class-level default; ``review_kind`` is stamped on
        # every finding so the supervisor can attribute findings back to
        # the lens that flagged them after merging two parallel reviewers.
        self.opencode_agent = opencode_agent  # type: ignore[misc]  # override classvar per-instance
        self._review_kind: ReviewKind = review_kind

    async def __post_create__(self) -> None:
        self._actor_tag = f"reviewer[{self.uid.decode()}]"
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
        """Run a per-bead review and forward ``review_ready`` on success."""
        self._review_count += 1
        self._in_aggregate = False
        prompt = self._build_review_prompt(request)
        logger.debug(
            "reviewer.review_starting",
            review_count=self._review_count,
            bead_id=request.bead_id,
            review_kind=self._review_kind,
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
                f"ReviewerActor expected SubmitReviewPayload, got {type(payload).__name__}",
            )
            return

        # Stamp provenance on every finding so the supervisor can
        # attribute the issue back to the correctness vs completeness
        # lens after merging two parallel reviewer payloads. The
        # supervisor exposes per-kind inbox methods so the merge layer
        # knows which lens delivered which payload (the ``findings``
        # tuple may be empty, so per-finding tagging alone isn't enough).
        # ``review_ready`` is also fired for back-compat with callers
        # that don't distinguish reviewer kinds.
        stamped = self._stamp_provenance(payload)
        if self._review_kind == "correctness":
            await self._supervisor_ref.correctness_review_ready(stamped)
        else:
            await self._supervisor_ref.completeness_review_ready(stamped)
        await self._supervisor_ref.review_ready(stamped)

    @xo.no_lock
    async def send_aggregate_review(self, request: AggregateReviewRequest) -> None:
        """Run the epic-level aggregate review.

        Aggregate failures are non-fatal — they route through
        ``payload_parse_error`` so the epic still closes.
        """
        self._in_aggregate = True
        logger.debug("reviewer.aggregate_starting", bead_count=request.bead_count)

        try:
            await self._rotate_session()
        except Exception as exc:  # noqa: BLE001
            logger.error("reviewer.aggregate_session_rotate_failed", error=str(exc))
            await self._supervisor_ref.payload_parse_error("aggregate_review", str(exc))
            return

        prompt = self._build_aggregate_prompt(request)
        try:
            payload = await self._send_structured(prompt, timeout=AGGREGATE_REVIEW_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001
            logger.error("reviewer.aggregate_failed", error=str(exc))
            await self._supervisor_ref.payload_parse_error("aggregate_review", str(exc))
            return

        if not isinstance(payload, SubmitReviewPayload):
            await self._supervisor_ref.payload_parse_error(
                "aggregate_review",
                f"ReviewerActor expected SubmitReviewPayload, got {type(payload).__name__}",
            )
            return

        # Aggregate review only runs once per epic and uses one of the
        # two reviewer instances (the supervisor picks one); stamp
        # provenance for symmetry but the merge logic upstream treats
        # the aggregate result as standalone, so this is informational.
        stamped = self._stamp_provenance(payload)
        await self._supervisor_ref.aggregate_review_ready(stamped)
        logger.debug("reviewer.aggregate_completed")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _stamp_provenance(self, payload: SubmitReviewPayload) -> SubmitReviewPayload:
        """Stamp ``self._review_kind`` onto every finding.

        Returns a new payload — :class:`SubmitReviewPayload` is frozen.
        Findings that already have a ``reviewer`` value (e.g. routed
        from a different lens) are preserved.
        """
        if not payload.findings:
            return payload
        kind: ReviewKind = self._review_kind
        new_findings = tuple(
            f if f.reviewer is not None else f.model_copy(update={"reviewer": kind})
            for f in payload.findings
        )
        return payload.model_copy(update={"findings": new_findings})

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

            # Persona role/voice lives in the per-kind agent .md file
            # (loaded via OPENCODE_CONFIG_DIR + ``self.opencode_agent``).
            # User prompt only carries per-bead specifics so the system
            # prompt stays cacheable.
            return (
                "Review the implementation already in the working "
                "directory against the spec below. Also consult "
                "`.maverick/runway/` (`episodic/review-findings.jsonl`, "
                "`episodic/bead-outcomes.jsonl`, `semantic/`) for "
                "project context if it exists.\n\n"
                "Only flag CRITICAL or MAJOR issues. Set "
                "approved=true with an empty findings array when no "
                "critical/major issues remain.\n\n"
                f"# Review context\n\n{user_content}"
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


__all__ = ["AGGREGATE_REVIEW_TIMEOUT_SECONDS", "REVIEW_PROMPT_TIMEOUT_SECONDS", "ReviewerActor"]


# Re-export for tests that need to construct ReviewFindingPayload directly.
_ = ReviewFindingPayload
