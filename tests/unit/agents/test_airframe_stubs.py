"""Unit tests for :mod:`tests.unit.agents.airframe_stubs`.

The stubs are test infrastructure used by actor-shell tests after the
Pattern D migration. They have to behave consistently — these tests
pin the contract so subsequent test-file rewrites can rely on them.
"""

from __future__ import annotations

import pytest
from airframe.errors import RuntimeAuthError
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
from tests.unit.agents.airframe_stubs import (
    StubBriefingAgent,
    StubCodingAgent,
    StubDecomposerAgent,
    StubGeneratorAgent,
    StubReviewerAgent,
)

# ---------------------------------------------------------------------------
# Lifecycle (shared base)
# ---------------------------------------------------------------------------


async def test_lifecycle_calls_tracked() -> None:
    """open / close / rotate_session bumps counters."""
    stub = StubCodingAgent()
    await stub.open()
    await stub.open()  # idempotent on real agents; stub records both
    await stub.rotate_session()
    await stub.close()
    assert stub.open_calls == 2
    assert stub.rotate_calls == 1
    assert stub.close_calls == 1


async def test_async_context_manager_opens_and_closes() -> None:
    stub = StubCodingAgent()
    async with stub as s:
        assert s is stub
        assert stub.open_calls == 1
    assert stub.close_calls == 1


# ---------------------------------------------------------------------------
# Coding agent
# ---------------------------------------------------------------------------


async def test_coding_implement_returns_scripted_payload() -> None:
    payload = SubmitImplementationPayload(summary="done")
    stub = StubCodingAgent(implement_payloads=[payload])
    result = await stub.implement("hello")
    assert result is payload
    assert stub.calls == [("implement", {"prompt": "hello"})]


async def test_coding_fix_returns_scripted_payload() -> None:
    payload = SubmitFixResultPayload(summary="fixed")
    stub = StubCodingAgent(fix_payloads=[payload])
    result = await stub.fix("the issue")
    assert result is payload


async def test_coding_raise_error_surfaces_then_clears() -> None:
    payload = SubmitImplementationPayload(summary="ok")
    stub = StubCodingAgent(implement_payloads=[payload])
    stub.raise_error = RuntimeAuthError("bad creds")
    with pytest.raises(RuntimeAuthError):
        await stub.implement("first")
    # Error is one-shot — the next call pops normally.
    result = await stub.implement("second")
    assert result is payload


async def test_coding_overflow_assertion() -> None:
    stub = StubCodingAgent(implement_payloads=[])
    with pytest.raises(AssertionError, match="more times than scripted"):
        await stub.implement("hi")


# ---------------------------------------------------------------------------
# Reviewer agent
# ---------------------------------------------------------------------------


async def test_reviewer_review_returns_scripted_payload() -> None:
    payload = SubmitReviewPayload(approved=True)
    stub = StubReviewerAgent(review_payloads=[payload])
    result = await stub.review(
        bead_description="b1",
        work_unit_md="md",
        briefing_context="",
    )
    assert result is payload
    assert stub.calls[0][0] == "review"
    assert stub.calls[0][1]["bead_description"] == "b1"


async def test_reviewer_aggregate_returns_scripted_payload() -> None:
    payload = SubmitReviewPayload(approved=True)
    stub = StubReviewerAgent(aggregate_payloads=[payload])
    result = await stub.aggregate(objective="obj", bead_list="b1, b2", diff_stat="2 files")
    assert result is payload


# ---------------------------------------------------------------------------
# Briefing agent — per-instance schema
# ---------------------------------------------------------------------------


class _ToyBrief(BaseModel):
    note: str


async def test_briefing_returns_scripted_payload_with_arbitrary_schema() -> None:
    payload = _ToyBrief(note="x")
    stub = StubBriefingAgent(
        agent_name="navigator",
        result_model=_ToyBrief,
        brief_payloads=[payload],
    )
    result = await stub.brief("scope it")
    assert result is payload
    assert stub.agent_name == "navigator"
    assert stub.result_model is _ToyBrief


# ---------------------------------------------------------------------------
# Decomposer agent
# ---------------------------------------------------------------------------


async def test_decomposer_outline_detail_fix() -> None:
    outline = SubmitOutlinePayload(work_units=())
    detail = SubmitDetailsPayload(details=())
    fix = SubmitFixPayload(work_units=(), details=())
    stub = StubDecomposerAgent(
        outline_payloads=[outline],
        detail_payloads=[detail],
        fix_payloads=[fix],
    )
    assert await stub.outline(flight_plan_content="plan", codebase_context=None) is outline
    assert await stub.detail(unit_ids=("wu-1",)) is detail
    assert await stub.fix(coverage_gaps=(), overloaded=()) is fix
    # Kwargs flow through to the call log.
    assert stub.calls[0] == ("outline", {"flight_plan_content": "plan", "codebase_context": None})


async def test_decomposer_nudge_returns_typed_payload() -> None:
    outline = SubmitOutlinePayload(work_units=())
    stub = StubDecomposerAgent(nudge_payloads=[outline])
    result = await stub.nudge(expected_tool="submit_outline", unit_id=None, reason="retry")
    assert result is outline


async def test_decomposer_set_context_recorded() -> None:
    stub = StubDecomposerAgent()
    await stub.set_context(outline_json="{}", flight_plan_content="plan")
    assert len(stub.contexts) == 1
    assert stub.contexts[0]["outline_json"] == "{}"


# ---------------------------------------------------------------------------
# Generator agent
# ---------------------------------------------------------------------------


async def test_generator_returns_scripted_payload() -> None:
    payload = SubmitFlightPlanPayload(
        objective="ship feature x",
        success_criteria=(),
    )
    stub = StubGeneratorAgent(generate_payloads=[payload])
    result = await stub.generate("synthesize")
    assert result is payload
