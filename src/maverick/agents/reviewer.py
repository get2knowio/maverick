"""``ReviewerAgent`` — code reviewer with correctness/completeness lens.

The persona is per-instance: callers construct two reviewers per
workflow (one ``maverick.correctness-reviewer``, one
``maverick.completeness-reviewer``) and run them in parallel, then
merge the typed payloads.

The agent stamps a ``reviewer`` field on every finding so downstream
merging can attribute issues back to the lens that flagged them.
Findings that already carry a ``reviewer`` value are preserved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal

from maverick.agents.base import Agent
from maverick.payloads import SubmitReviewPayload

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime

    from maverick.executor.config import StepConfig
    from maverick.runtime.opencode import CostSink

REVIEW_PROMPT_TIMEOUT_SECONDS = 600
AGGREGATE_REVIEW_TIMEOUT_SECONDS = 600

ReviewKind = Literal["correctness", "completeness"]


class ReviewerAgent(Agent):
    """Code reviewer (correctness or completeness lens)."""

    result_model: ClassVar[type[SubmitReviewPayload]] = SubmitReviewPayload
    provider_tier: ClassVar[str] = "review"
    # opencode_agent is per-instance (correctness vs completeness).

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        review_kind: ReviewKind,
        opencode_agent: str,
        step_config: StepConfig | dict[str, Any] | None = None,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
    ) -> None:
        if review_kind not in ("correctness", "completeness"):
            raise ValueError(
                f"ReviewerAgent 'review_kind' must be 'correctness' or "
                f"'completeness', got {review_kind!r}"
            )
        super().__init__(
            runtime=runtime,
            cwd=cwd,
            step_config=step_config,
            cost_sink=cost_sink,
            tag=tag or f"reviewer.{review_kind}",
            opencode_agent=opencode_agent,
        )
        self._review_kind: ReviewKind = review_kind
        self._review_count = 0

    @property
    def review_kind(self) -> ReviewKind:
        return self._review_kind

    async def rotate_session(self) -> None:
        """Reset the per-bead review-round counter and drop the runtime scope."""
        self._review_count = 0
        await super().rotate_session()

    async def review(
        self,
        *,
        bead_description: str,
        work_unit_md: str | None,
        briefing_context: str | None,
    ) -> SubmitReviewPayload:
        """Run a per-bead review and return the provenance-stamped payload.

        The first call within a bead sends the full review context;
        subsequent calls (after the implementer has applied fixes)
        send a short "did you address my prior findings?" prompt that
        relies on the persistent airframe-runtime scope for context.

        Bead identity flows in via
        :func:`~maverick.agents.context.tagged` — the caller wraps the
        call in ``with tagged(bead_id=...):`` for cost attribution.
        """
        self._review_count += 1
        prompt = self._build_review_prompt(
            bead_description=bead_description,
            work_unit_md=work_unit_md,
            briefing_context=briefing_context,
        )
        payload = await self._execute_via_runtime(prompt, timeout=REVIEW_PROMPT_TIMEOUT_SECONDS)
        assert isinstance(payload, SubmitReviewPayload)
        return self._stamp_provenance(payload)

    async def aggregate(
        self,
        *,
        objective: str,
        bead_list: str,
        diff_stat: str,
    ) -> SubmitReviewPayload:
        """Run the epic-level aggregate review.

        Always rotates the session first so the aggregate runs in a
        fresh runtime scope.
        """
        await self.rotate_session()
        prompt = self._build_aggregate_prompt(objective, bead_list, diff_stat)
        payload = await self._execute_via_runtime(prompt, timeout=AGGREGATE_REVIEW_TIMEOUT_SECONDS)
        assert isinstance(payload, SubmitReviewPayload)
        return self._stamp_provenance(payload)

    def _stamp_provenance(self, payload: SubmitReviewPayload) -> SubmitReviewPayload:
        """Stamp ``self._review_kind`` onto every finding lacking one."""
        if not payload.findings:
            return payload
        kind: ReviewKind = self._review_kind
        new_findings = tuple(
            f if f.reviewer is not None else f.model_copy(update={"reviewer": kind})
            for f in payload.findings
        )
        return payload.model_copy(update={"findings": new_findings})

    def _build_review_prompt(
        self,
        *,
        bead_description: str,
        work_unit_md: str | None,
        briefing_context: str | None,
    ) -> str:
        if self._review_count == 1:
            sections: list[str] = []
            if work_unit_md:
                sections.append(f"## Work Unit Specification\n\n{work_unit_md}")
            else:
                sections.append(f"## Task Description\n\n{bead_description}")
            if briefing_context:
                sections.append(
                    "## Pre-Flight Briefing (risks & contrarian findings)\n\n"
                    f"{briefing_context[:4000]}"
                )
            user_content = "\n\n".join(sections)
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

    def _build_aggregate_prompt(
        self,
        objective: str,
        bead_list: str,
        diff_stat: str,
    ) -> str:
        return (
            "Review the AGGREGATE changes across all beads in this epic.\n\n"
            f"## Flight Plan\n\n{objective}\n\n"
            f"## Beads Completed\n\n{bead_list}\n\n"
            f"## Full Diff Stats\n\n```\n{diff_stat}\n```\n\n"
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


__all__ = [
    "AGGREGATE_REVIEW_TIMEOUT_SECONDS",
    "REVIEW_PROMPT_TIMEOUT_SECONDS",
    "ReviewKind",
    "ReviewerAgent",
]
