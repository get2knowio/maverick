"""Unit tests for verify_bead_completion action."""

from __future__ import annotations

import pytest

from maverick.library.actions.beads import verify_bead_completion


class TestVerifyBeadCompletion:
    """Tests for verify_bead_completion action."""

    @pytest.mark.asyncio
    async def test_passes_when_validation_passed(self) -> None:
        result = await verify_bead_completion(
            validation_result={"passed": True},
            skip_review=True,
        )

        assert result.passed is True
        assert result.reasons == ()

    @pytest.mark.asyncio
    async def test_fails_when_validation_failed(self) -> None:
        result = await verify_bead_completion(
            validation_result={
                "passed": False,
                "stage_results": {
                    "lint": {"passed": False},
                    "test": {"passed": False},
                },
            },
            skip_review=True,
        )

        assert result.passed is False
        assert len(result.reasons) == 1
        assert "lint" in result.reasons[0]
        assert "test" in result.reasons[0]

    @pytest.mark.asyncio
    async def test_fails_when_review_requests_changes(self) -> None:
        result = await verify_bead_completion(
            validation_result={"passed": True},
            review_result={
                "recommendation": "request_changes",
                "issues_remaining": [{"id": "1"}, {"id": "2"}],
            },
            skip_review=False,
        )

        assert result.passed is False
        assert len(result.reasons) == 1
        assert "Review requests changes" in result.reasons[0]
        assert "2 issues" in result.reasons[0]

    @pytest.mark.asyncio
    async def test_passes_when_review_approves(self) -> None:
        result = await verify_bead_completion(
            validation_result={"passed": True},
            review_result={
                "recommendation": "approve",
                "issues_remaining": [],
            },
            skip_review=False,
        )

        assert result.passed is True
        assert result.reasons == ()

    @pytest.mark.asyncio
    async def test_passes_when_review_skipped_via_flag(self) -> None:
        """When skip_review=True, review_result is ignored."""
        result = await verify_bead_completion(
            validation_result={"passed": True},
            review_result={
                "recommendation": "request_changes",
                "issues_remaining": [{"id": "1"}],
            },
            skip_review=True,
        )

        assert result.passed is True

    @pytest.mark.asyncio
    async def test_passes_when_review_result_is_none(self) -> None:
        """When DSL skips a step, output is None."""
        result = await verify_bead_completion(
            validation_result={"passed": True},
            review_result=None,
            skip_review=False,
        )

        assert result.passed is True

    @pytest.mark.asyncio
    async def test_fails_both_validation_and_review(self) -> None:
        result = await verify_bead_completion(
            validation_result={
                "passed": False,
                "stage_results": {"format": {"passed": False}},
            },
            review_result={
                "recommendation": "request_changes",
                "issues_remaining": 3,
            },
            skip_review=False,
        )

        assert result.passed is False
        assert len(result.reasons) == 2

    @pytest.mark.asyncio
    async def test_validation_failed_no_stage_details(self) -> None:
        """When stage_results is missing, reason says 'unknown stages'."""
        result = await verify_bead_completion(
            validation_result={"passed": False},
            skip_review=True,
        )

        assert result.passed is False
        assert "unknown stages" in result.reasons[0]

    @pytest.mark.asyncio
    async def test_to_dict(self) -> None:
        result = await verify_bead_completion(
            validation_result={"passed": True},
            skip_review=True,
        )

        d = result.to_dict()
        assert d["passed"] is True
        assert d["reasons"] == []

    @pytest.mark.asyncio
    async def test_review_issues_remaining_as_integer(self) -> None:
        """issues_remaining can be an integer instead of a list."""
        result = await verify_bead_completion(
            validation_result={"passed": True},
            review_result={
                "recommendation": "request_changes",
                "issues_remaining": 5,
            },
            skip_review=False,
        )

        assert result.passed is False
        assert "5 issues" in result.reasons[0]
