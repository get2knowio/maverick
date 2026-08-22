"""Tests for :class:`maverick.agents.reviewer.ReviewerAgent`."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.agents.reviewer import ReviewerAgent
from maverick.payloads import SubmitReviewPayload


def _approved_payload() -> dict[str, Any]:
    return {
        "kind": "submit_review",
        "approved": True,
        "summary": "looks good",
        "findings": [],
    }


def _payload_with_finding(reviewer: str | None = None) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "kind": "review_finding",
        "severity": "major",
        "category": "logic",
        "description": "off-by-one in loop",
    }
    if reviewer is not None:
        finding["reviewer"] = reviewer
    return {
        "kind": "submit_review",
        "approved": False,
        "summary": "issues found",
        "findings": [finding],
    }


def _cost() -> CostRecord:
    return CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.02,
        input_tokens=20,
        output_tokens=40,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )


def _make_runtime(structured: dict[str, Any]) -> Any:
    runtime = MagicMock()
    runtime.label = "stub"
    runtime.execute = AsyncMock(
        return_value=RuntimeResult(text="", structured=structured, cost=_cost(), finish="end_turn")
    )
    runtime.reset = AsyncMock()
    runtime.close = AsyncMock()
    return runtime


def _make_agent(
    runtime: Any,
    *,
    review_kind: str = "correctness",
    persona_name: str = "maverick.correctness-reviewer",
) -> ReviewerAgent:
    return ReviewerAgent(
        runtime=runtime,
        cwd="/tmp",
        review_kind=review_kind,  # type: ignore[arg-type]
        persona_name=persona_name,
    )


async def test_review_first_round_includes_full_context() -> None:
    runtime = _make_runtime(_approved_payload())
    async with _make_agent(runtime) as agent:
        await agent.review(
            bead_description="bead text",
            work_unit_md="## work unit",
            briefing_context="briefing notes",
        )
    call = runtime.execute.await_args
    prompt = call.args[0]
    assert "Work Unit Specification" in prompt
    assert "Pre-Flight Briefing" in prompt


async def test_review_subsequent_round_sends_short_followup() -> None:
    runtime = _make_runtime(_approved_payload())
    async with _make_agent(runtime) as agent:
        await agent.review(
            bead_description="bead",
            work_unit_md=None,
            briefing_context=None,
        )
        await agent.review(
            bead_description="bead",
            work_unit_md=None,
            briefing_context=None,
        )
    second_prompt = runtime.execute.await_args_list[1].args[0]
    assert "previous findings were addressed" in second_prompt
    assert "Work Unit Specification" not in second_prompt


async def test_review_stamps_provenance_correctness() -> None:
    runtime = _make_runtime(_payload_with_finding())
    async with _make_agent(runtime) as agent:
        payload = await agent.review(
            bead_description="bead",
            work_unit_md=None,
            briefing_context=None,
        )
    assert isinstance(payload, SubmitReviewPayload)
    assert payload.findings[0].reviewer == "correctness"


async def test_review_preserves_existing_provenance() -> None:
    runtime = _make_runtime(_payload_with_finding(reviewer="completeness"))
    async with _make_agent(runtime) as agent:
        payload = await agent.review(
            bead_description="bead",
            work_unit_md=None,
            briefing_context=None,
        )
    assert payload.findings[0].reviewer == "completeness"


async def test_rotate_session_resets_review_count() -> None:
    runtime = _make_runtime(_approved_payload())
    async with _make_agent(runtime) as agent:
        await agent.review(
            bead_description="bead",
            work_unit_md="md",
            briefing_context=None,
        )
        await agent.rotate_session()
        await agent.review(
            bead_description="bead",
            work_unit_md="md",
            briefing_context=None,
        )
    # First call after rotate should be a first-round prompt again.
    assert "Work Unit Specification" in runtime.execute.await_args_list[1].args[0]


async def test_aggregate_rotates_session_first() -> None:
    runtime = _make_runtime(_approved_payload())
    async with _make_agent(
        runtime,
        review_kind="completeness",
        persona_name="maverick.completeness-reviewer",
    ) as agent:
        await agent.review(
            bead_description="bead",
            work_unit_md="md",
            briefing_context=None,
        )
        await agent.aggregate(
            objective="ship feature",
            bead_list="- bead 1",
            diff_stat="1 file changed",
        )
    runtime.reset.assert_awaited()
    aggregate_prompt = runtime.execute.await_args_list[1].args[0]
    assert "AGGREGATE changes" in aggregate_prompt


async def test_review_kind_validation() -> None:
    with pytest.raises(ValueError, match="review_kind"):
        ReviewerAgent(
            runtime=MagicMock(),
            cwd="/tmp",
            review_kind="bogus",  # type: ignore[arg-type]
            persona_name="x",
        )


async def test_persona_forwarded_in_send() -> None:
    runtime = _make_runtime(_approved_payload())
    async with _make_agent(
        runtime,
        review_kind="completeness",
        persona_name="maverick.completeness-reviewer",
    ) as agent:
        await agent.review(
            bead_description="bead",
            work_unit_md=None,
            briefing_context=None,
        )
    assert runtime.execute.await_args.kwargs["persona"] == "maverick.completeness-reviewer"


class TestCritique:
    """``ReviewerAgent.critique`` — one-shot standalone-scope review."""

    async def test_prompt_states_scope_and_change(self) -> None:
        runtime = _make_runtime(_approved_payload())
        async with _make_agent(runtime) as agent:
            await agent.critique(
                scope_summary="working copy vs main — 4 files",
                change_summary="src/a.py | 3 +++\n@@ -1 +1 @@\n-old\n+new",
            )
        prompt = runtime.execute.await_args.args[0]
        assert "working copy vs main — 4 files" in prompt
        assert "src/a.py | 3 +++" in prompt
        assert "+new" in prompt

    async def test_prompt_omits_bead_and_work_unit_framing(self) -> None:
        runtime = _make_runtime(_approved_payload())
        async with _make_agent(runtime) as agent:
            await agent.critique(
                scope_summary="HEAD~1..HEAD — 1 file",
                change_summary="src/a.py | 1 +",
            )
        prompt = runtime.execute.await_args.args[0].lower()
        assert "bead" not in prompt
        assert "work unit" not in prompt
        assert "work unit specification" not in prompt

    async def test_rotates_session_before_send(self) -> None:
        runtime = _make_runtime(_approved_payload())
        manager = MagicMock()
        manager.attach_mock(runtime.reset, "reset")
        manager.attach_mock(runtime.execute, "execute")
        async with _make_agent(runtime) as agent:
            await agent.critique(scope_summary="scope", change_summary="change")
        ordering = [name for name, _args, _kwargs in manager.mock_calls]
        assert ordering.index("reset") < ordering.index("execute")

    async def test_stamps_provenance(self) -> None:
        runtime = _make_runtime(_payload_with_finding())
        async with _make_agent(
            runtime,
            review_kind="completeness",
            persona_name="maverick.completeness-reviewer",
        ) as agent:
            payload = await agent.critique(
                scope_summary="scope",
                change_summary="change",
            )
        assert isinstance(payload, SubmitReviewPayload)
        assert payload.findings[0].reviewer == "completeness"

    async def test_is_stateless_across_calls(self) -> None:
        runtime = _make_runtime(_approved_payload())
        async with _make_agent(runtime) as agent:
            await agent.critique(scope_summary="scope", change_summary="change")
            await agent.critique(scope_summary="scope", change_summary="change")
        first_prompt = runtime.execute.await_args_list[0].args[0]
        second_prompt = runtime.execute.await_args_list[1].args[0]
        assert second_prompt == first_prompt
        assert "previous findings were addressed" not in second_prompt
