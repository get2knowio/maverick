"""Tests for review-fix loop error handling.

Verifies that reviewer timeouts, fixer timeouts, and dual-reviewer failures
are surfaced correctly rather than silently treated as passing reviews.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from maverick.library.actions.review import (
    _run_dual_review,
    run_review_fix_loop,
)
from maverick.library.actions.types import ReviewAndFixReport

# ── Helpers ──────────────────────────────────────────────────────────


def _make_mock_executor(side_effect: Any) -> AsyncMock:
    """Build a mock executor with the given execute side_effect."""
    mock = AsyncMock()
    mock.execute.side_effect = side_effect
    mock.cleanup = AsyncMock()
    return mock


def _review_input() -> dict[str, Any]:
    return {
        "review_metadata": {"title": "Test PR"},
        "changed_files": ["src/foo.py"],
        "diff": "diff --git a/src/foo.py b/src/foo.py\n+x = 1",
    }


# ── Both reviewers fail → recommendation is "error" ─────────────────


@pytest.mark.asyncio
async def test_dual_review_both_fail_returns_error() -> None:
    """When both reviewers raise, _run_dual_review returns recommendation='error'."""

    async def _always_fail(**kwargs: Any) -> None:
        raise TimeoutError("timed out")

    mock_executor = _make_mock_executor(side_effect=_always_fail)

    with patch(
        "maverick.executor.create_default_executor",
        return_value=mock_executor,
    ):
        result = await _run_dual_review(_review_input(), "main")

    assert result["recommendation"] == "error"
    assert "review_error" in result


# ── Reviewer error does not count as "approve" in the loop ───────────


@pytest.mark.asyncio
async def test_loop_reviewer_error_not_treated_as_approve() -> None:
    """Review errors must not be treated as 'no issues found' / approve."""

    async def _always_fail(**kwargs: Any) -> None:
        raise TimeoutError("reviewer timed out")

    mock_executor = _make_mock_executor(side_effect=_always_fail)

    with patch(
        "maverick.executor.create_default_executor",
        return_value=mock_executor,
    ):
        result = await run_review_fix_loop(
            review_input=_review_input(),
            base_branch="main",
            max_attempts=2,
            generate_report=True,
        )

    assert isinstance(result, ReviewAndFixReport)
    # Must NOT be "approve" — reviewers errored out
    assert result.recommendation != "approve"


# ── Fixer timeout is surfaced (not silently swallowed) ───────────────


@pytest.mark.asyncio
async def test_fixer_timeout_does_not_produce_approve() -> None:
    """When the fixer times out, the loop should not claim success."""
    from maverick.executor.result import ExecutorResult
    from maverick.models.review_models import (
        Finding,
        FindingGroup,
        GroupedReviewResult,
    )

    findings_result = GroupedReviewResult(
        groups=[
            FindingGroup(
                description="Correctness",
                findings=[
                    Finding(
                        id="F001",
                        severity="major",
                        category="correctness",
                        file="src/foo.py",
                        line="1",
                        issue="Missing error handling",
                        fix_hint="Add try/except",
                    ),
                ],
            )
        ]
    )

    async def _fake_execute(**kwargs: Any) -> ExecutorResult:
        step_name = kwargs.get("step_name", "")

        if "fixer" in step_name:
            raise TimeoutError("fixer timed out after 300s")

        # Reviewer calls — return findings with major issues
        return ExecutorResult(
            output=findings_result,
            success=True,
            events=(),
            usage=None,
        )

    mock_executor = _make_mock_executor(side_effect=_fake_execute)

    with patch(
        "maverick.executor.create_default_executor",
        return_value=mock_executor,
    ):
        result = await run_review_fix_loop(
            review_input=_review_input(),
            base_branch="main",
            max_attempts=2,
            generate_report=True,
        )

    assert isinstance(result, ReviewAndFixReport)
    # Review found major issues and fixer timed out — must not approve
    assert result.recommendation != "approve"


# ── generate_review_fix_report does not upgrade request_changes ──────


@pytest.mark.asyncio
async def test_report_does_not_upgrade_request_changes() -> None:
    """generate_review_fix_report must not upgrade request_changes to approve."""
    from maverick.library.actions.review import generate_review_fix_report

    report = await generate_review_fix_report(
        loop_result={
            "success": False,
            "attempts": 2,
            "final_recommendation": "request_changes",
            "skipped": False,
            "skip_reason": None,
            "issues_fixed": [],
            "issues_remaining": [],
        },
        max_attempts=2,
    )

    assert report.recommendation == "request_changes"
    # With no review_findings in the loop result, issues_remaining is 0.
    # The recommendation alone carries the signal — phantom sentinel counts
    # (the old `else 1` fallback) were removed to prevent false blocking.
    assert report.issues_remaining == 0


@pytest.mark.asyncio
async def test_report_approved_has_zero_remaining() -> None:
    """Approved report has issues_remaining == 0."""
    from maverick.library.actions.review import generate_review_fix_report

    report = await generate_review_fix_report(
        loop_result={
            "success": True,
            "attempts": 1,
            "final_recommendation": "approve",
            "skipped": False,
            "skip_reason": None,
            "issues_fixed": [],
            "issues_remaining": [],
        },
        max_attempts=2,
    )

    assert report.recommendation == "approve"
    assert report.issues_remaining == 0


@pytest.mark.asyncio
async def test_report_upgrades_comment_on_success() -> None:
    """When success=True and recommendation is 'comment', upgrade to approve."""
    from maverick.library.actions.review import generate_review_fix_report

    report = await generate_review_fix_report(
        loop_result={
            "success": True,
            "attempts": 1,
            "final_recommendation": "comment",
            "skipped": False,
            "skip_reason": None,
            "issues_fixed": [],
            "issues_remaining": [],
        },
        max_attempts=2,
    )

    assert report.recommendation == "approve"
