"""Airframe-native test stubs for actor + workflow tests.

Pattern D actors take a pre-built :class:`Agent` via ``agent=``; the
agent owns its airframe :class:`AgentRuntime`. These stubs let tests
inject canned typed payloads (or scripted errors) into actor shells
without standing up a real adapter SDK or any HTTP transport.

Use one of the per-role stub classes (``StubCodingAgent``,
``StubReviewerAgent``, ``StubBriefingAgent``, ``StubDecomposerAgent``,
``StubGeneratorAgent``) as the ``agent=`` argument to its corresponding
actor shell:

.. code-block:: python

    coder = StubCodingAgent(
        implement_payloads=[SubmitImplementationPayload(...)],
    )
    actor = await xo.create_actor(
        ImplementerActor,
        sup_ref,
        cwd="/tmp",
        agent=coder,
        address=pool_address,
        uid="impl-1",
    )

Each stub exposes:

* ``open()`` / ``close()`` / ``rotate_session()`` — recorded but no-op.
* Domain methods (``implement``, ``review``, ``brief``, etc.) — pop from
  the corresponding canned list, or raise ``raise_error`` when set.
* ``calls`` — chronological record of method invocations
  ``[(method_name, args_dict), ...]``.
* ``rotate_calls`` / ``open_calls`` / ``close_calls`` — counts.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from maverick.payloads import (
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitFixResultPayload,
    SubmitFlightPlanPayload,
    SubmitImplementationPayload,
    SubmitOutlinePayload,
    SubmitReviewPayload,
)

__all__ = [
    "StubAgentBase",
    "StubBriefingAgent",
    "StubCodingAgent",
    "StubDecomposerAgent",
    "StubGeneratorAgent",
    "StubReviewerAgent",
]


class StubAgentBase:
    """Common lifecycle + call-tracking surface.

    Subclasses add the domain methods their actor shell calls. Tests
    poke ``raise_error`` on the stub to make the next domain call
    surface a classified runtime error.
    """

    tag: str = "stub-agent"

    def __init__(self) -> None:
        # Chronological call log: list of ``(method_name, kwargs_dict)``.
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.open_calls = 0
        self.close_calls = 0
        self.rotate_calls = 0
        # Setting this makes the next domain call raise this exception.
        self.raise_error: BaseException | None = None

    # ------------------------------------------------------------------
    # Lifecycle (mirrors :class:`Agent`)
    # ------------------------------------------------------------------

    async def open(self) -> None:
        self.open_calls += 1

    async def close(self) -> None:
        self.close_calls += 1

    async def rotate_session(self) -> None:
        self.rotate_calls += 1
        if self.raise_error is not None:
            err, self.raise_error = self.raise_error, None
            raise err

    async def __aenter__(self) -> StubAgentBase:
        await self.open()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    def _record(self, method: str, **kwargs: Any) -> None:
        self.calls.append((method, kwargs))

    def _maybe_raise(self) -> None:
        if self.raise_error is not None:
            err, self.raise_error = self.raise_error, None
            raise err

    @staticmethod
    def _pop(queue: list[Any], method: str) -> Any:
        if not queue:
            raise AssertionError(
                f"Stub {method}() called more times than scripted payloads provided"
            )
        return queue.pop(0)


# ---------------------------------------------------------------------------
# CodingAgent — implement / fix
# ---------------------------------------------------------------------------


class StubCodingAgent(StubAgentBase):
    """Stub for :class:`maverick.agents.coding.CodingAgent`."""

    tag = "stub-coder"

    def __init__(
        self,
        *,
        implement_payloads: list[SubmitImplementationPayload] | None = None,
        fix_payloads: list[SubmitFixResultPayload] | None = None,
    ) -> None:
        super().__init__()
        self.implement_payloads: list[SubmitImplementationPayload] = list(implement_payloads or [])
        self.fix_payloads: list[SubmitFixResultPayload] = list(fix_payloads or [])

    async def implement(self, prompt: str) -> SubmitImplementationPayload:
        self._record("implement", prompt=prompt)
        self._maybe_raise()
        return self._pop(self.implement_payloads, "implement")

    async def fix(self, prompt: str) -> SubmitFixResultPayload:
        self._record("fix", prompt=prompt)
        self._maybe_raise()
        return self._pop(self.fix_payloads, "fix")


# ---------------------------------------------------------------------------
# ReviewerAgent — review / aggregate
# ---------------------------------------------------------------------------


class StubReviewerAgent(StubAgentBase):
    """Stub for :class:`maverick.agents.reviewer.ReviewerAgent`."""

    tag = "stub-reviewer"

    def __init__(
        self,
        *,
        review_kind: str = "correctness",
        review_payloads: list[SubmitReviewPayload] | None = None,
        aggregate_payloads: list[SubmitReviewPayload] | None = None,
    ) -> None:
        super().__init__()
        self.review_kind = review_kind
        self.review_payloads: list[SubmitReviewPayload] = list(review_payloads or [])
        self.aggregate_payloads: list[SubmitReviewPayload] = list(aggregate_payloads or [])

    async def review(
        self,
        *,
        bead_description: str,
        work_unit_md: str,
        briefing_context: str = "",
    ) -> SubmitReviewPayload:
        self._record(
            "review",
            bead_description=bead_description,
            work_unit_md=work_unit_md,
            briefing_context=briefing_context,
        )
        self._maybe_raise()
        return self._pop(self.review_payloads, "review")

    async def aggregate(
        self,
        *,
        objective: str,
        bead_list: str,
        diff_stat: str,
    ) -> SubmitReviewPayload:
        self._record(
            "aggregate",
            objective=objective,
            bead_list=bead_list,
            diff_stat=diff_stat,
        )
        self._maybe_raise()
        return self._pop(self.aggregate_payloads, "aggregate")


# ---------------------------------------------------------------------------
# BriefingAgent — brief
# ---------------------------------------------------------------------------


class StubBriefingAgent(StubAgentBase):
    """Stub for :class:`maverick.agents.briefing.agent.BriefingAgent`.

    Briefings vary their result schema per-instance (navigator,
    structuralist, recon, etc. each pin a different
    ``Submit*BriefPayload`` or workflow-specific brief payload), so
    ``brief_payloads`` is :class:`BaseModel`-typed; callers feed in
    whatever shape the actor under test expects.
    """

    tag = "stub-briefing"

    def __init__(
        self,
        *,
        agent_name: str = "stub-briefing",
        result_model: type[BaseModel] = BaseModel,
        brief_payloads: list[BaseModel] | None = None,
    ) -> None:
        super().__init__()
        self.agent_name = agent_name
        self.result_model = result_model
        self.brief_payloads: list[BaseModel] = list(brief_payloads or [])

    async def brief(self, prompt: str) -> BaseModel:
        self._record("brief", prompt=prompt)
        self._maybe_raise()
        return self._pop(self.brief_payloads, "brief")


# ---------------------------------------------------------------------------
# DecomposerAgent — outline / details / fix variants
# ---------------------------------------------------------------------------


class StubDecomposerAgent(StubAgentBase):
    """Stub for :class:`maverick.agents.decomposer.DecomposerAgent`.

    Covers every callable surface the actor exercises:
    outline / details / fix-outline / fix-details + set_context.
    """

    tag = "stub-decomposer"

    def __init__(
        self,
        *,
        outline_payloads: list[SubmitOutlinePayload] | None = None,
        details_payloads: list[SubmitDetailsPayload] | None = None,
        fix_payloads: list[SubmitFixPayload] | None = None,
    ) -> None:
        super().__init__()
        self.outline_payloads: list[SubmitOutlinePayload] = list(outline_payloads or [])
        self.details_payloads: list[SubmitDetailsPayload] = list(details_payloads or [])
        self.fix_payloads: list[SubmitFixPayload] = list(fix_payloads or [])
        self.contexts: list[dict[str, Any]] = []

    async def set_context(self, **kwargs: Any) -> None:
        self.contexts.append(kwargs)
        self._record("set_context", **kwargs)

    async def outline(self, prompt: str) -> SubmitOutlinePayload:
        self._record("outline", prompt=prompt)
        self._maybe_raise()
        return self._pop(self.outline_payloads, "outline")

    async def details(self, prompt: str) -> SubmitDetailsPayload:
        self._record("details", prompt=prompt)
        self._maybe_raise()
        return self._pop(self.details_payloads, "details")

    async def fix(self, prompt: str) -> SubmitFixPayload:
        self._record("fix", prompt=prompt)
        self._maybe_raise()
        return self._pop(self.fix_payloads, "fix")


# ---------------------------------------------------------------------------
# GeneratorAgent — generate
# ---------------------------------------------------------------------------


class StubGeneratorAgent(StubAgentBase):
    """Stub for :class:`maverick.agents.generator.GeneratorAgent`."""

    tag = "stub-generator"

    def __init__(
        self,
        *,
        generate_payloads: list[SubmitFlightPlanPayload] | None = None,
    ) -> None:
        super().__init__()
        self.generate_payloads: list[SubmitFlightPlanPayload] = list(generate_payloads or [])

    async def generate(self, prompt: str) -> SubmitFlightPlanPayload:
        self._record("generate", prompt=prompt)
        self._maybe_raise()
        return self._pop(self.generate_payloads, "generate")
