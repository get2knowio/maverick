"""``SemanticDependentsAgent`` — judges descendant diffs for semantic dependency.

Review-lens agent used by the reconcile workflow's semantic-dependents
pass (spec 051-reconcile-changed-answers, research.md R6). Given the
ledger `question`, the old `adopted_answer`, the new `human_answer`, the
correction diff that was folded into history, and a batch of descendant
`(change_id, diff)` pairs, returns one finding per descendant judging
whether that descendant still depends on the now-superseded assumption.

Unlike :class:`~maverick.agents.reviewer.ReviewerAgent` (per-instance
persona for correctness/completeness lenses), there is only one
semantic-reviewer persona, so it is fixed at class level — same pattern
as :class:`~maverick.agents.coding.CodingAgent`.

This agent never edits files; it only judges. Any fix a finding calls
for is applied by the ``ReconcilerAgent`` via the correction mechanism
(constitution Principle II — judgment vs. deterministic execution stay
separate). Cross-checking that ``payload.findings`` covers exactly the
supplied ``descendants`` (ids ⊆ supplied set, missing ids ->
``dependent=false``) is the calling workflow's responsibility, per the
contract in ``specs/051-reconcile-changed-answers/contracts/payloads.md``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from maverick.agents.base import Agent
from maverick.payloads import SubmitSemanticDependentsPayload

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime

    from maverick.executor.config import StepConfig
    from maverick.runtime.registry import CostSink

SEMANTIC_ANALYZE_TIMEOUT_SECONDS = 600


class SemanticDependentsAgent(Agent):
    """Review-lens agent: judges descendant diffs for semantic dependency."""

    result_model: ClassVar[type[BaseModel]] = SubmitSemanticDependentsPayload
    provider_tier: ClassVar[str] = "review"
    persona_name: ClassVar[str | None] = "maverick.semantic-reviewer"

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        step_config: StepConfig | dict[str, Any] | None = None,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
    ) -> None:
        super().__init__(
            runtime=runtime,
            cwd=cwd,
            step_config=step_config,
            cost_sink=cost_sink,
            tag=tag,
        )

    async def analyze(
        self,
        *,
        question: str,
        adopted_answer: str,
        human_answer: str,
        correction_diff: str,
        descendants: Sequence[tuple[str, str]],
    ) -> SubmitSemanticDependentsPayload:
        """Judge a batch of descendant diffs for dependency on the old answer.

        Args:
            question: The ledger question, verbatim.
            adopted_answer: The old (now-superseded) assumption, verbatim.
            human_answer: The new human-provided answer, verbatim.
            correction_diff: The diff that was folded into history to
                apply the new answer at its target change.
            descendants: ``(change_id, diff)`` pairs for every descendant
                to analyze in this batch. The model is instructed to
                return exactly one finding per descendant listed here;
                the caller cross-checks the returned ids against this
                set (ids not covered are treated as ``dependent=false``
                by the workflow, not by this agent).

        Returns:
            The validated :class:`SubmitSemanticDependentsPayload`.
        """
        prompt = self._build_analyze_prompt(
            question=question,
            adopted_answer=adopted_answer,
            human_answer=human_answer,
            correction_diff=correction_diff,
            descendants=descendants,
        )
        payload = await self._execute_via_runtime(
            prompt,
            schema=SubmitSemanticDependentsPayload,
            timeout=SEMANTIC_ANALYZE_TIMEOUT_SECONDS,
        )
        assert isinstance(payload, SubmitSemanticDependentsPayload)
        return payload

    def _build_analyze_prompt(
        self,
        *,
        question: str,
        adopted_answer: str,
        human_answer: str,
        correction_diff: str,
        descendants: Sequence[tuple[str, str]],
    ) -> str:
        change_ids = [change_id for change_id, _ in descendants]
        ids_list = ", ".join(change_ids)

        sections: list[str] = [
            f"## Question\n\n{question}",
            f"## Adopted Answer (old assumption)\n\n{adopted_answer}",
            f"## Human Answer (new answer)\n\n{human_answer}",
            f"## Correction Diff\n\n```diff\n{correction_diff}\n```",
        ]
        for change_id, diff in descendants:
            sections.append(f"## Descendant {change_id}\n\n```diff\n{diff}\n```")

        context = "\n\n".join(sections)
        return (
            "Analyze each descendant below for semantic dependency on the "
            "old, now-superseded assumption described above. Return exactly "
            "one finding per descendant in `findings`. The descendants to "
            f"analyze are exactly these change_id values, and no others: "
            f"{ids_list}. Do not invent or omit any of them.\n\n"
            f"{context}"
        )


__all__ = ["SEMANTIC_ANALYZE_TIMEOUT_SECONDS", "SemanticDependentsAgent"]
