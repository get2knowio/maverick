"""Tests for :class:`maverick.agents.reviewer.ReviewerAgent`."""

from __future__ import annotations

from typing import Any

import pytest

from maverick.agents.reviewer import ReviewerAgent
from maverick.payloads import SubmitReviewPayload

from .conftest import FakeClient, fake_handle, payload_send_result


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


def _make_agent(
    client: FakeClient,
    *,
    review_kind: str = "correctness",
    opencode_agent: str = "maverick.correctness-reviewer",
) -> ReviewerAgent:
    return ReviewerAgent(
        handle=fake_handle(),
        cwd="/tmp",
        review_kind=review_kind,  # type: ignore[arg-type]
        opencode_agent=opencode_agent,
        client_factory=lambda: client,
    )


async def test_review_first_round_includes_full_context() -> None:
    client = FakeClient(send_result=payload_send_result(_approved_payload()))
    async with _make_agent(client) as agent:
        await agent.review(
            bead_description="bead text",
            work_unit_md="## work unit",
            briefing_context="briefing notes",
        )
    assert len(client.send_calls) == 1
    prompt = client.send_calls[0]["content"]
    assert "Work Unit Specification" in prompt
    assert "Pre-Flight Briefing" in prompt


async def test_review_subsequent_round_sends_short_followup() -> None:
    client = FakeClient(send_result=payload_send_result(_approved_payload()))
    async with _make_agent(client) as agent:
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
    second_prompt = client.send_calls[1]["content"]
    assert "previous findings were addressed" in second_prompt
    assert "Work Unit Specification" not in second_prompt


async def test_review_stamps_provenance_correctness() -> None:
    client = FakeClient(send_result=payload_send_result(_payload_with_finding()))
    async with _make_agent(client) as agent:
        payload = await agent.review(
            bead_description="bead",
            work_unit_md=None,
            briefing_context=None,
        )
    assert isinstance(payload, SubmitReviewPayload)
    assert payload.findings[0].reviewer == "correctness"


async def test_review_preserves_existing_provenance() -> None:
    client = FakeClient(
        send_result=payload_send_result(_payload_with_finding(reviewer="completeness"))
    )
    async with _make_agent(client) as agent:
        payload = await agent.review(
            bead_description="bead",
            work_unit_md=None,
            briefing_context=None,
        )
    # Existing reviewer value not overwritten.
    assert payload.findings[0].reviewer == "completeness"


async def test_rotate_session_resets_review_count() -> None:
    """After rotate_session, the next review re-uses the first-round prompt."""
    client = FakeClient(send_result=payload_send_result(_approved_payload()))
    async with _make_agent(client) as agent:
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
    assert "Work Unit Specification" in client.send_calls[1]["content"]


async def test_aggregate_rotates_session_first() -> None:
    client = FakeClient(send_result=payload_send_result(_approved_payload()))
    async with _make_agent(
        client,
        review_kind="completeness",
        opencode_agent="maverick.completeness-reviewer",
    ) as agent:
        await agent.review(
            bead_description="bead",
            work_unit_md="md",
            briefing_context=None,
        )
        sid_before_aggregate = agent._session_id  # noqa: SLF001
        await agent.aggregate(
            objective="ship feature",
            bead_list="- bead 1",
            diff_stat="1 file changed",
        )
    assert sid_before_aggregate in client.deleted_sessions
    aggregate_prompt = client.send_calls[1]["content"]
    assert "AGGREGATE changes" in aggregate_prompt


async def test_review_kind_validation() -> None:
    with pytest.raises(ValueError, match="review_kind"):
        ReviewerAgent(
            handle=fake_handle(),
            cwd="/tmp",
            review_kind="bogus",  # type: ignore[arg-type]
            opencode_agent="x",
        )


async def test_persona_forwarded_in_send() -> None:
    client = FakeClient(send_result=payload_send_result(_approved_payload()))
    async with _make_agent(
        client,
        review_kind="completeness",
        opencode_agent="maverick.completeness-reviewer",
    ) as agent:
        await agent.review(
            bead_description="bead",
            work_unit_md=None,
            briefing_context=None,
        )
    assert client.send_calls[0]["agent"] == "maverick.completeness-reviewer"


# ---------------------------------------------------------------------------
# Pattern D path — runtime= constructor
# ---------------------------------------------------------------------------


def test_constructor_requires_handle_or_runtime() -> None:
    with pytest.raises(ValueError, match="handle.*runtime"):
        ReviewerAgent(
            cwd="/tmp",
            review_kind="correctness",
            opencode_agent="maverick.correctness-reviewer",
        )


def test_constructor_rejects_both_handle_and_runtime() -> None:
    from unittest.mock import MagicMock

    with pytest.raises(ValueError, match="both"):
        ReviewerAgent(
            handle=fake_handle(),
            runtime=MagicMock(),
            cwd="/tmp",
            review_kind="correctness",
            opencode_agent="maverick.correctness-reviewer",
        )


async def test_review_via_runtime_stamps_provenance() -> None:
    """The runtime path still stamps `reviewer` onto findings."""
    from unittest.mock import AsyncMock, MagicMock

    from airframe.cost import CostRecord
    from airframe.protocol import RuntimeResult

    cost = CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.02,
        input_tokens=20,
        output_tokens=40,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )
    fake_runtime = MagicMock()
    fake_runtime.label = "claude_code"
    fake_runtime.execute = AsyncMock(
        return_value=RuntimeResult(
            text="", structured=_payload_with_finding(), cost=cost, finish="end_turn"
        )
    )
    fake_runtime.reset = AsyncMock()
    fake_runtime.close = AsyncMock()

    agent = ReviewerAgent(
        runtime=fake_runtime,
        cwd="/tmp",
        review_kind="correctness",
        opencode_agent="maverick.correctness-reviewer",
    )
    async with agent:
        payload = await agent.review(
            bead_description="bead text",
            work_unit_md=None,
            briefing_context=None,
        )

    assert isinstance(payload, SubmitReviewPayload)
    assert len(payload.findings) == 1
    assert payload.findings[0].reviewer == "correctness"
    call = fake_runtime.execute.await_args
    assert call.kwargs["persona"] == "maverick.correctness-reviewer"


async def test_aggregate_via_runtime_rotates_session_first() -> None:
    """aggregate() calls runtime.reset before sending."""
    from unittest.mock import AsyncMock, MagicMock

    from airframe.cost import CostRecord
    from airframe.protocol import RuntimeResult

    cost = CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.02,
        input_tokens=20,
        output_tokens=40,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )
    fake_runtime = MagicMock()
    fake_runtime.label = "claude_code"
    fake_runtime.execute = AsyncMock(
        return_value=RuntimeResult(
            text="", structured=_approved_payload(), cost=cost, finish="end_turn"
        )
    )
    fake_runtime.reset = AsyncMock()
    fake_runtime.close = AsyncMock()

    agent = ReviewerAgent(
        runtime=fake_runtime,
        cwd="/tmp",
        review_kind="correctness",
        opencode_agent="maverick.correctness-reviewer",
    )
    async with agent:
        # First a review to set _review_count > 0.
        await agent.review(
            bead_description="bead",
            work_unit_md=None,
            briefing_context=None,
        )
        # Then aggregate — should call reset before execute.
        await agent.aggregate(
            objective="ship it",
            bead_list="bead-1",
            diff_stat="1 file changed",
        )

    fake_runtime.reset.assert_awaited()
    assert fake_runtime.execute.await_count == 2
