"""Unit tests for review actions.

Tests the review.py action module including:
- gather_pr_context action with PR number auto-detection
- combine_review_results action for dual-agent reviews
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maverick.library.actions.review import (
    combine_review_results,
    gather_pr_context,
)
from maverick.runners.models import CommandResult


def make_result(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
) -> CommandResult:
    """Create a CommandResult for testing."""
    return CommandResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        duration_ms=100,
        timed_out=timed_out,
    )


class TestGatherPRContext:
    """Tests for gather_pr_context action."""

    @pytest.mark.asyncio
    async def test_gathers_context_with_pr_number(self) -> None:
        """Test gathers PR context when PR number is provided."""
        pr_number = 123
        base_branch = "main"

        with (
            patch("maverick.library.actions.review.CommandRunner") as mock_runner_class,
            patch(
                "maverick.library.actions.review.AsyncGitRepository"
            ) as mock_git_class,
        ):
            # Mock the CommandRunner instance and its run method (for GitHub CLI)
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner

            # Mock PR view
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    stdout=json.dumps(
                        {
                            "number": 123,
                            "title": "Test PR",
                            "body": "Test description",
                            "author": {"login": "testuser"},
                            "labels": [{"name": "enhancement"}],
                        }
                    )
                )
            )

            # Mock the AsyncGitRepository instance (for git operations)
            mock_repo = AsyncMock()
            mock_git_class.return_value = mock_repo
            mock_repo.current_branch = AsyncMock(return_value="feature-branch")
            mock_repo.diff = AsyncMock(return_value="diff content")
            mock_repo.get_changed_files = AsyncMock(
                return_value=["file1.py", "file2.py"]
            )
            mock_repo.commit_messages_since = AsyncMock(
                return_value=["commit1", "commit2"]
            )

            result = await gather_pr_context(pr_number, base_branch)

            assert result.pr_metadata.number == 123
            assert result.pr_metadata.title == "Test PR"
            assert result.error is None
            assert len(result.changed_files) == 2

    @pytest.mark.asyncio
    async def test_auto_detects_pr_number(self) -> None:
        """Test auto-detects PR number from current branch."""
        base_branch = "main"

        with (
            patch("maverick.library.actions.review.CommandRunner") as mock_runner_class,
            patch(
                "maverick.library.actions.review.AsyncGitRepository"
            ) as mock_git_class,
        ):
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner

            # Mock PR list and view calls
            mock_runner.run = AsyncMock(
                side_effect=[
                    # PR list
                    make_result(stdout=json.dumps([{"number": 456}])),
                    # PR view
                    make_result(
                        stdout=json.dumps(
                            {
                                "number": 456,
                                "title": "Auto PR",
                                "body": "",
                                "author": {"login": "testuser"},
                                "labels": [],
                            }
                        )
                    ),
                ]
            )

            # Mock git repo
            mock_repo = AsyncMock()
            mock_git_class.return_value = mock_repo
            mock_repo.current_branch = AsyncMock(return_value="feature-branch")
            mock_repo.diff = AsyncMock(return_value="diff")
            mock_repo.get_changed_files = AsyncMock(return_value=["file.py"])
            mock_repo.commit_messages_since = AsyncMock(return_value=["commit"])

            result = await gather_pr_context(None, base_branch)

            assert result.pr_metadata.number == 456

    @pytest.mark.asyncio
    async def test_handles_no_pr_found(self) -> None:
        """Test handles case when no PR found for branch."""
        base_branch = "main"

        with (
            patch("maverick.library.actions.review.CommandRunner") as mock_runner_class,
            patch(
                "maverick.library.actions.review.AsyncGitRepository"
            ) as mock_git_class,
        ):
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner

            # Mock PR list (empty)
            mock_runner.run = AsyncMock(return_value=make_result(stdout=json.dumps([])))

            # Mock git repo
            mock_repo = AsyncMock()
            mock_git_class.return_value = mock_repo
            mock_repo.current_branch = AsyncMock(return_value="local-branch")
            mock_repo.diff = AsyncMock(return_value="local diff")
            mock_repo.get_changed_files = AsyncMock(return_value=["local.py"])
            mock_repo.commit_messages_since = AsyncMock(return_value=["local commit"])

            result = await gather_pr_context(None, base_branch)

            assert result.pr_metadata.number is None
            assert result.error is None

    @pytest.mark.asyncio
    async def test_includes_spec_files(self) -> None:
        """Test includes spec files when requested."""
        pr_number = 123
        base_branch = "main"

        with (
            patch("maverick.library.actions.review.CommandRunner") as mock_runner_class,
            patch(
                "maverick.library.actions.review.AsyncGitRepository"
            ) as mock_git_class,
            patch(
                "maverick.library.actions.review._gather_spec_files"
            ) as mock_gather_specs,
        ):
            mock_runner = AsyncMock()
            mock_runner_class.return_value = mock_runner

            mock_runner.run = AsyncMock(
                return_value=make_result(
                    stdout=json.dumps(
                        {
                            "number": 123,
                            "title": "Test",
                            "body": "",
                            "author": {"login": "u"},
                            "labels": [],
                        }
                    )
                )
            )

            # Mock git repo
            mock_repo = AsyncMock()
            mock_git_class.return_value = mock_repo
            mock_repo.current_branch = AsyncMock(return_value="feature")
            mock_repo.diff = AsyncMock(return_value="diff")
            mock_repo.get_changed_files = AsyncMock(return_value=["f.py"])
            mock_repo.commit_messages_since = AsyncMock(return_value=["commit"])

            mock_gather_specs.return_value = {
                "spec.md": "# Spec",
                "tasks.md": "# Tasks",
            }

            result = await gather_pr_context(
                pr_number, base_branch, include_spec_files=True
            )

            assert "spec.md" in result.spec_files
            assert result.spec_files["spec.md"] == "# Spec"


class TestCombineReviewResults:
    """Tests for combine_review_results action."""

    @pytest.mark.asyncio
    async def test_combines_spec_and_technical_reviews(self) -> None:
        """Test combines results from both reviewers."""
        spec_review = {
            "reviewer": "spec",
            "assessment": "COMPLIANT",
            "findings": "All requirements implemented.",
        }
        technical_review = {
            "reviewer": "technical",
            "quality": "GOOD",
            "has_critical": False,
            "findings": "Code is well-structured.",
        }
        pr_metadata = {"number": 123, "title": "Test PR", "author": "testuser"}

        result = await combine_review_results(
            spec_review, technical_review, pr_metadata
        )

        assert "COMPLIANT" in result.review_report
        assert "GOOD" in result.review_report
        assert result.recommendation == "approve"

    @pytest.mark.asyncio
    async def test_handles_missing_spec_review(self) -> None:
        """Test handles missing spec review gracefully."""
        technical_review = {
            "reviewer": "technical",
            "quality": "GOOD",
            "has_critical": False,
            "findings": "Code looks good.",
        }
        pr_metadata = {"number": 123, "title": "Test PR"}

        result = await combine_review_results(None, technical_review, pr_metadata)

        assert "No spec compliance review available" in result.review_report
        assert result.recommendation == "comment"

    @pytest.mark.asyncio
    async def test_handles_missing_technical_review(self) -> None:
        """Test handles missing technical review gracefully."""
        spec_review = {
            "reviewer": "spec",
            "assessment": "COMPLIANT",
            "findings": "Matches spec.",
        }
        pr_metadata = {"number": 123, "title": "Test PR"}

        result = await combine_review_results(spec_review, None, pr_metadata)

        assert "No technical review available" in result.review_report
        assert result.recommendation == "comment"

    @pytest.mark.asyncio
    async def test_handles_both_reviews_missing(self) -> None:
        """Test handles both reviews missing."""
        pr_metadata = {"number": 123, "title": "Test PR"}

        result = await combine_review_results(None, None, pr_metadata)

        assert "No spec compliance review available" in result.review_report
        assert "No technical review available" in result.review_report
        assert result.recommendation == "comment"

    @pytest.mark.asyncio
    async def test_requests_changes_for_critical_issues(self) -> None:
        """Test recommends request_changes when critical issues found."""
        spec_review = {
            "reviewer": "spec",
            "assessment": "PARTIAL",
            "findings": "Some features missing.",
        }
        technical_review = {
            "reviewer": "technical",
            "quality": "NEEDS_WORK",
            "has_critical": True,
            "findings": "CRITICAL: Security vulnerability found.",
        }
        pr_metadata = {"number": 123, "title": "Test PR"}

        result = await combine_review_results(
            spec_review, technical_review, pr_metadata
        )

        assert result.recommendation == "request_changes"

    @pytest.mark.asyncio
    async def test_requests_changes_for_non_compliant(self) -> None:
        """Test recommends request_changes when spec non-compliant."""
        spec_review = {
            "reviewer": "spec",
            "assessment": "NON-COMPLIANT",
            "findings": "Missing required features.",
        }
        technical_review = {
            "reviewer": "technical",
            "quality": "GOOD",
            "has_critical": False,
            "findings": "Code quality is fine.",
        }
        pr_metadata = {"number": 123, "title": "Test PR"}

        result = await combine_review_results(
            spec_review, technical_review, pr_metadata
        )

        assert result.recommendation == "request_changes"

    @pytest.mark.asyncio
    async def test_requests_changes_for_poor_quality(self) -> None:
        """Test recommends request_changes for poor technical quality."""
        spec_review = {
            "reviewer": "spec",
            "assessment": "COMPLIANT",
            "findings": "All requirements met.",
        }
        technical_review = {
            "reviewer": "technical",
            "quality": "POOR",
            "has_critical": False,
            "findings": "Multiple issues found.",
        }
        pr_metadata = {"number": 123, "title": "Test PR"}

        result = await combine_review_results(
            spec_review, technical_review, pr_metadata
        )

        assert result.recommendation == "request_changes"

    @pytest.mark.asyncio
    async def test_comments_for_partial_compliance(self) -> None:
        """Test recommends comment for partial spec compliance."""
        spec_review = {
            "reviewer": "spec",
            "assessment": "PARTIAL",
            "findings": "Most requirements met.",
        }
        technical_review = {
            "reviewer": "technical",
            "quality": "GOOD",
            "has_critical": False,
            "findings": "Code is acceptable.",
        }
        pr_metadata = {"number": 123, "title": "Test PR"}

        result = await combine_review_results(
            spec_review, technical_review, pr_metadata
        )

        assert result.recommendation == "comment"

    @pytest.mark.asyncio
    async def test_comments_for_needs_work_quality(self) -> None:
        """Test recommends comment when technical quality needs work."""
        spec_review = {
            "reviewer": "spec",
            "assessment": "COMPLIANT",
            "findings": "All requirements implemented.",
        }
        technical_review = {
            "reviewer": "technical",
            "quality": "NEEDS_WORK",
            "has_critical": False,
            "findings": "Some improvements suggested.",
        }
        pr_metadata = {"number": 123, "title": "Test PR"}

        result = await combine_review_results(
            spec_review, technical_review, pr_metadata
        )

        assert result.recommendation == "comment"

    @pytest.mark.asyncio
    async def test_approves_for_excellent_reviews(self) -> None:
        """Test recommends approve for excellent reviews."""
        spec_review = {
            "reviewer": "spec",
            "assessment": "COMPLIANT",
            "findings": "All requirements fully implemented.",
        }
        technical_review = {
            "reviewer": "technical",
            "quality": "EXCELLENT",
            "has_critical": False,
            "findings": "Exceptional code quality.",
        }
        pr_metadata = {"number": 123, "title": "Test PR"}

        result = await combine_review_results(
            spec_review, technical_review, pr_metadata
        )

        assert result.recommendation == "approve"

    @pytest.mark.asyncio
    async def test_report_includes_pr_metadata(self) -> None:
        """Test review report includes PR metadata."""
        spec_review = {
            "reviewer": "spec",
            "assessment": "COMPLIANT",
            "findings": "Good.",
        }
        technical_review = {
            "reviewer": "technical",
            "quality": "GOOD",
            "has_critical": False,
            "findings": "Good.",
        }
        pr_metadata = {
            "number": 789,
            "title": "Add feature X",
            "author": "developer",
        }

        result = await combine_review_results(
            spec_review, technical_review, pr_metadata
        )

        assert "#789" in result.review_report
        assert "Add feature X" in result.review_report
        assert "developer" in result.review_report
