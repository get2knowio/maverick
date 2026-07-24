"""``ReconcilerAgent`` — corrects code and resolves conflicts for a changed answer.

Owns two structured-output payloads:

* ``SubmitCorrectionPayload`` — returned by :meth:`correct`.
* ``SubmitConflictResolutionPayload`` — returned by :meth:`resolve_conflicts`.

Both methods run within the same airframe runtime scope for a given
answer (the workflow calls :meth:`Agent.rotate_session` between
*answers*, not between the two methods) — see
``specs/051-reconcile-changed-answers/research.md`` R11.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from maverick.agents.base import Agent
from maverick.payloads import SubmitConflictResolutionPayload, SubmitCorrectionPayload

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime

    from maverick.executor.config import StepConfig
    from maverick.runtime.registry import CostSink

RECONCILER_PROMPT_TIMEOUT_SECONDS = 1800


class ReconcilerAgent(Agent):
    """Reconcile agent: corrects code for a changed answer and resolves conflicts."""

    # Default schema; ``resolve_conflicts`` overrides per call.
    result_model: ClassVar[type[BaseModel]] = SubmitCorrectionPayload
    provider_tier: ClassVar[str] = "implement"
    persona_name: ClassVar[str | None] = "maverick.reconciler"

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

    async def correct(
        self,
        *,
        question: str,
        adopted_answer: str,
        human_answer: str,
        target_diff: str,
    ) -> SubmitCorrectionPayload:
        """Correct the working-copy child of the target change.

        The working copy must already be positioned as an empty child of
        the target change (the workflow's job) before this call. Returns
        a typed payload describing what changed (or why nothing did).
        """
        prompt = self._build_correct_prompt(
            question=question,
            adopted_answer=adopted_answer,
            human_answer=human_answer,
            target_diff=target_diff,
        )
        payload = await self._execute_via_runtime(
            prompt,
            schema=SubmitCorrectionPayload,
            timeout=RECONCILER_PROMPT_TIMEOUT_SECONDS,
        )
        assert isinstance(payload, SubmitCorrectionPayload)
        return payload

    async def resolve_conflicts(
        self,
        *,
        question: str,
        adopted_answer: str,
        human_answer: str,
        conflicted_files: dict[str, str],
    ) -> SubmitConflictResolutionPayload:
        """Resolve conflict markers materialized for a single conflicted change.

        Reuses the same airframe runtime scope as :meth:`correct` within
        the same answer, so the model retains context across rounds.
        """
        prompt = self._build_resolve_conflicts_prompt(
            question=question,
            adopted_answer=adopted_answer,
            human_answer=human_answer,
            conflicted_files=conflicted_files,
        )
        payload = await self._execute_via_runtime(
            prompt,
            schema=SubmitConflictResolutionPayload,
            timeout=RECONCILER_PROMPT_TIMEOUT_SECONDS,
        )
        assert isinstance(payload, SubmitConflictResolutionPayload)
        return payload

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_correct_prompt(
        self,
        *,
        question: str,
        adopted_answer: str,
        human_answer: str,
        target_diff: str,
    ) -> str:
        return (
            "## Mode: Correction\n\n"
            f"### Question\n{question}\n\n"
            f"### Adopted Answer (old)\n{adopted_answer}\n\n"
            f"### Human Answer (new)\n{human_answer}\n\n"
            "### Target Diff\n"
            "The diff of the change that first encoded the old assumption. "
            "The working copy is positioned as an empty child of this change:\n"
            f"```diff\n{target_diff}\n```\n"
        )

    def _build_resolve_conflicts_prompt(
        self,
        *,
        question: str,
        adopted_answer: str,
        human_answer: str,
        conflicted_files: dict[str, str],
    ) -> str:
        files_section = "\n\n".join(
            f"## File: {path}\n```\n{content}\n```" for path, content in conflicted_files.items()
        )
        return (
            "## Mode: Conflict Resolution\n\n"
            f"### Question\n{question}\n\n"
            f"### Adopted Answer (old)\n{adopted_answer}\n\n"
            f"### Human Answer (new)\n{human_answer}\n\n"
            "### Conflicted Files\n"
            f"{files_section}\n"
        )


__all__ = ["RECONCILER_PROMPT_TIMEOUT_SECONDS", "ReconcilerAgent"]
