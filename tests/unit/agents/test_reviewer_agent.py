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
