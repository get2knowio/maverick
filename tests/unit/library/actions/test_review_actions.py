"""Unit tests for review actions.

Tests the review.py action module including:
- gather_pr_context action with PR number auto-detection
- run_coderabbit_review action with availability checking
- combine_review_results action with deduplication and recommendations
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maverick.library.actions.review import (
    combine_review_results,
    gather_pr_context,
    run_coderabbit_review,
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
            patch("maverick.library.actions.review._runner") as mock_runner,
            patch("maverick.library.actions.review.shutil.which") as mock_which,
        ):
            mock_which.return_value = "/usr/bin/coderabbit"
            mock_runner.run = AsyncMock(
                side_effect=[
                    # gh pr view
                    make_result(
                        stdout=json.dumps(
                            {
                                "number": 123,
                                "title": "Add new feature",
                                "body": "This PR adds a new feature",
                                "author": {"login": "testuser"},
                                "labels": [
                                    {"name": "enhancement"},
                                    {"name": "feature"},
                                ],
                            }
                        )
                    ),
                    # git diff
                    make_result(stdout="diff --git a/file.py b/file.py\n"),
                    # git diff --name-only
                    make_result(stdout="src/file1.py\nsrc/file2.py\n"),
                    # git log
                    make_result(stdout="abc123 feat: add feature\ndef456 fix: bug\n"),
                ]
            )

            result = await gather_pr_context(pr_number, base_branch)

            assert result.pr_metadata.number == 123
            assert result.pr_metadata.title == "Add new feature"
            assert result.pr_metadata.description == "This PR adds a new feature"
            assert result.pr_metadata.author == "testuser"
            assert result.pr_metadata.labels == ("enhancement", "feature")
            assert result.pr_metadata.base_branch == "main"
            assert result.changed_files == ("src/file1.py", "src/file2.py")
            assert result.diff == "diff --git a/file.py b/file.py\n"
            assert result.commits == ("abc123 feat: add feature", "def456 fix: bug")
            assert result.coderabbit_available is True

    @pytest.mark.asyncio
    async def test_auto_detects_pr_number_from_current_branch(self) -> None:
        """Test auto-detects PR number from current branch when not provided."""
        base_branch = "main"

        with (
            patch("maverick.library.actions.review._runner") as mock_runner,
            patch("maverick.library.actions.review.shutil.which") as mock_which,
        ):
            mock_which.return_value = "/usr/bin/coderabbit"
            mock_runner.run = AsyncMock(
                side_effect=[
                    # git rev-parse --abbrev-ref HEAD
                    make_result(stdout="feature/test\n"),
                    # gh pr list
                    make_result(stdout=json.dumps([{"number": 456}])),
                    # gh pr view
                    make_result(
                        stdout=json.dumps(
                            {
                                "number": 456,
                                "title": "Test PR",
                                "body": "Test description",
                                "author": {"login": "author"},
                                "labels": [],
                            }
                        )
                    ),
                    # git diff
                    make_result(stdout="diff content\n"),
                    # git diff --name-only
                    make_result(stdout="file.py\n"),
                    # git log
                    make_result(stdout="sha1 commit message\n"),
                ]
            )

            result = await gather_pr_context(None, base_branch)

            assert result.pr_metadata.number == 456
            assert result.pr_metadata.title == "Test PR"

    @pytest.mark.asyncio
    async def test_handles_no_pr_found_for_current_branch(self) -> None:
        """Test handles case when no PR is found for current branch."""
        base_branch = "main"

        with (
            patch("maverick.library.actions.review._runner") as mock_runner,
            patch("maverick.library.actions.review.shutil.which") as mock_which,
            patch("maverick.library.actions.review.logger") as mock_logger,
        ):
            mock_which.return_value = None
            mock_runner.run = AsyncMock(
                side_effect=[
                    # git rev-parse --abbrev-ref HEAD
                    make_result(stdout="feature/no-pr\n"),
                    # gh pr list (empty)
                    make_result(stdout="[]"),
                    # git diff
                    make_result(stdout="diff content\n"),
                    # git diff --name-only
                    make_result(stdout="file.py\n"),
                    # git log
                    make_result(stdout="sha1 message\n"),
                ]
            )

            result = await gather_pr_context(None, base_branch)

            assert result.pr_metadata.number is None
            assert result.pr_metadata.title is None
            mock_logger.warning.assert_called_once()
            assert "No PR found" in str(mock_logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_detects_coderabbit_availability(self) -> None:
        """Test detects CodeRabbit CLI availability."""
        pr_number = 123
        base_branch = "main"

        with (
            patch("maverick.library.actions.review._runner") as mock_runner,
            patch("maverick.library.actions.review.shutil.which") as mock_which,
        ):
            mock_which.return_value = "/usr/local/bin/coderabbit"
            mock_runner.run = AsyncMock(
                side_effect=[
                    make_result(stdout=json.dumps({"number": 123, "labels": []})),
                    make_result(stdout="diff\n"),
                    make_result(stdout="file.py\n"),
                    make_result(stdout="sha1 msg\n"),
                ]
            )

            result = await gather_pr_context(pr_number, base_branch)

            assert result.coderabbit_available is True
            mock_which.assert_called_once_with("coderabbit")

    @pytest.mark.asyncio
    async def test_detects_coderabbit_unavailability(self) -> None:
        """Test detects when CodeRabbit CLI is not available."""
        pr_number = 123
        base_branch = "main"

        with (
            patch("maverick.library.actions.review._runner") as mock_runner,
            patch("maverick.library.actions.review.shutil.which") as mock_which,
        ):
            mock_which.return_value = None
            mock_runner.run = AsyncMock(
                side_effect=[
                    make_result(stdout=json.dumps({"number": 123, "labels": []})),
                    make_result(stdout="diff\n"),
                    make_result(stdout="file.py\n"),
                    make_result(stdout="sha1 msg\n"),
                ]
            )

            result = await gather_pr_context(pr_number, base_branch)

            assert result.coderabbit_available is False

    @pytest.mark.asyncio
    async def test_handles_empty_changed_files(self) -> None:
        """Test handles case with no changed files."""
        pr_number = 123
        base_branch = "main"

        with (
            patch("maverick.library.actions.review._runner") as mock_runner,
            patch("maverick.library.actions.review.shutil.which") as mock_which,
        ):
            mock_which.return_value = None
            mock_runner.run = AsyncMock(
                side_effect=[
                    make_result(stdout=json.dumps({"number": 123, "labels": []})),
                    make_result(stdout=""),  # empty diff
                    make_result(stdout=""),  # no files
                    make_result(stdout=""),  # no commits
                ]
            )

            result = await gather_pr_context(pr_number, base_branch)

            assert result.changed_files == ()
            assert result.diff == ""
            assert result.commits == ()

    @pytest.mark.asyncio
    async def test_handles_pr_view_failure(self) -> None:
        """Test handles failure when viewing PR metadata."""
        pr_number = 123
        base_branch = "main"

        with (
            patch("maverick.library.actions.review._runner") as mock_runner,
            patch("maverick.library.actions.review.shutil.which") as mock_which,
            patch("maverick.library.actions.review.logger") as mock_logger,
        ):
            mock_which.return_value = None
            mock_runner.run = AsyncMock(
                return_value=make_result(returncode=1, stderr="Error: PR not found")
            )

            result = await gather_pr_context(pr_number, base_branch)

            # The result still contains a PR metadata structure but with minimal info
            assert result.pr_metadata.number == 123
            assert result.changed_files == ()
            assert result.diff == ""
            assert result.coderabbit_available is False
            assert result.error is not None
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_git_diff_failure(self) -> None:
        """Test handles failure when getting git diff."""
        pr_number = 123
        base_branch = "main"

        with (
            patch("maverick.library.actions.review._runner") as mock_runner,
            patch("maverick.library.actions.review.shutil.which") as mock_which,
            patch("maverick.library.actions.review.logger") as mock_logger,
        ):
            mock_which.return_value = None
            mock_runner.run = AsyncMock(
                side_effect=[
                    make_result(stdout=json.dumps({"number": 123, "labels": []})),
                    make_result(returncode=128, stderr="fatal: not a git repository"),
                ]
            )

            result = await gather_pr_context(pr_number, base_branch)

            assert result.diff == ""
            assert result.changed_files == ()
            assert result.error is not None
            mock_logger.error.assert_called_once()


class TestRunCoderabbitReview:
    """Tests for run_coderabbit_review action."""

    @pytest.mark.asyncio
    async def test_runs_coderabbit_review_successfully(self) -> None:
        """Test successfully runs CodeRabbit review."""
        pr_number = 123
        context = {"coderabbit_available": True}

        coderabbit_output = {
            "findings": [
                {
                    "file": "src/test.py",
                    "line": 10,
                    "message": "Consider refactoring",
                    "severity": "warning",
                },
                {
                    "file": "src/main.py",
                    "line": 25,
                    "message": "Security issue",
                    "severity": "critical",
                },
            ]
        }

        with patch("maverick.library.actions.review._coderabbit_runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout=json.dumps(coderabbit_output))
            )

            result = await run_coderabbit_review(pr_number, context)

            assert result.available is True
            assert result.error is None
            assert len(result.findings) == 2
            assert result.findings[0]["file"] == "src/test.py"
            assert result.findings[1]["severity"] == "critical"

            # Verify command
            mock_runner.run.assert_called_once()
            call_args = mock_runner.run.call_args[0][0]
            assert call_args == ["coderabbit", "review", "--pr", "123", "--json"]

    @pytest.mark.asyncio
    async def test_skips_review_when_coderabbit_unavailable(self) -> None:
        """Test skips CodeRabbit review when CLI is not available."""
        pr_number = 123
        context = {"coderabbit_available": False}

        with (
            patch("maverick.library.actions.review._coderabbit_runner") as mock_runner,
            patch("maverick.library.actions.review.logger") as mock_logger,
        ):
            result = await run_coderabbit_review(pr_number, context)

            assert result.available is False
            assert result.findings == ()
            assert result.error == "CodeRabbit CLI not installed"
            mock_runner.run.assert_not_called()
            mock_logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_review_when_no_pr_number(self) -> None:
        """Test skips CodeRabbit review when PR number is not available."""
        pr_number = None
        context = {"coderabbit_available": True}

        with (
            patch("maverick.library.actions.review._coderabbit_runner") as mock_runner,
            patch("maverick.library.actions.review.logger") as mock_logger,
        ):
            result = await run_coderabbit_review(pr_number, context)

            assert result.available is True
            assert result.findings == ()
            assert result.error == "No PR number available"
            mock_runner.run.assert_not_called()
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_coderabbit_timeout(self) -> None:
        """Test handles CodeRabbit review timeout."""
        pr_number = 123
        context = {"coderabbit_available": True}

        with (
            patch("maverick.library.actions.review._coderabbit_runner") as mock_runner,
            patch("maverick.library.actions.review.logger") as mock_logger,
        ):
            mock_runner.run = AsyncMock(return_value=make_result(timed_out=True))

            result = await run_coderabbit_review(pr_number, context)

            assert result.available is True
            assert result.findings == ()
            assert result.error == "CodeRabbit review timed out"
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_coderabbit_failure(self) -> None:
        """Test handles CodeRabbit command failure."""
        pr_number = 123
        context = {"coderabbit_available": True}

        with (
            patch("maverick.library.actions.review._coderabbit_runner") as mock_runner,
            patch("maverick.library.actions.review.logger") as mock_logger,
        ):
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    returncode=1, stderr="Error: authentication failed"
                )
            )

            result = await run_coderabbit_review(pr_number, context)

            assert result.available is True
            assert result.findings == ()
            assert result.error == "Error: authentication failed"
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_parses_issues_format(self) -> None:
        """Test parses CodeRabbit output with 'issues' key."""
        pr_number = 123
        context = {"coderabbit_available": True}

        coderabbit_output = {
            "issues": [
                {"file": "test.py", "message": "Issue 1"},
                {"file": "main.py", "message": "Issue 2"},
            ]
        }

        with patch("maverick.library.actions.review._coderabbit_runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout=json.dumps(coderabbit_output))
            )

            result = await run_coderabbit_review(pr_number, context)

            assert len(result.findings) == 2
            assert result.findings[0]["message"] == "Issue 1"

    @pytest.mark.asyncio
    async def test_parses_single_object_as_finding(self) -> None:
        """Test parses single object output as a finding."""
        pr_number = 123
        context = {"coderabbit_available": True}

        coderabbit_output = {
            "file": "test.py",
            "message": "Single finding",
            "severity": "info",
        }

        with patch("maverick.library.actions.review._coderabbit_runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout=json.dumps(coderabbit_output))
            )

            result = await run_coderabbit_review(pr_number, context)

            assert len(result.findings) == 1
            assert result.findings[0]["message"] == "Single finding"

    @pytest.mark.asyncio
    async def test_parses_list_format(self) -> None:
        """Test parses CodeRabbit output as direct list."""
        pr_number = 123
        context = {"coderabbit_available": True}

        coderabbit_output = [
            {"file": "a.py", "message": "Finding A"},
            {"file": "b.py", "message": "Finding B"},
        ]

        with patch("maverick.library.actions.review._coderabbit_runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout=json.dumps(coderabbit_output))
            )

            result = await run_coderabbit_review(pr_number, context)

            assert len(result.findings) == 2

    @pytest.mark.asyncio
    async def test_handles_invalid_json_output(self) -> None:
        """Test handles non-JSON output from CodeRabbit."""
        pr_number = 123
        context = {"coderabbit_available": True}

        with (
            patch("maverick.library.actions.review._coderabbit_runner") as mock_runner,
            patch("maverick.library.actions.review.logger") as mock_logger,
        ):
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout="This is not JSON output")
            )

            result = await run_coderabbit_review(pr_number, context)

            assert len(result.findings) == 1
            assert result.findings[0]["message"] == "This is not JSON output"
            assert result.findings[0]["severity"] == "info"
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_empty_output(self) -> None:
        """Test handles empty output from CodeRabbit."""
        pr_number = 123
        context = {"coderabbit_available": True}

        with patch("maverick.library.actions.review._coderabbit_runner") as mock_runner:
            mock_runner.run = AsyncMock(return_value=make_result(stdout=""))

            result = await run_coderabbit_review(pr_number, context)

            assert result.available is True
            assert result.findings == ()
            assert result.error is None


class TestCombineReviewResults:
    """Tests for combine_review_results action."""

    @pytest.mark.asyncio
    async def test_combines_agent_and_coderabbit_results(self) -> None:
        """Test combines issues from both agent and CodeRabbit."""
        agent_review = {
            "issues": [
                {
                    "file": "src/test.py",
                    "line": 10,
                    "message": "Agent finding",
                    "severity": "warning",
                }
            ]
        }
        coderabbit_review = {
            "findings": [
                {
                    "file": "src/main.py",
                    "line": 20,
                    "message": "CodeRabbit finding",
                    "severity": "error",
                }
            ]
        }
        pr_metadata = {
            "number": 123,
            "title": "Test PR",
            "author": "testuser",
        }

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        assert len(result.issues) == 2
        assert result.issues[0]["source"] == "agent"
        assert result.issues[1]["source"] == "coderabbit"
        assert "Agent finding" in result.review_report
        assert "CodeRabbit finding" in result.review_report

    @pytest.mark.asyncio
    async def test_deduplicates_identical_issues(self) -> None:
        """Test deduplicates identical issues from different sources."""
        agent_review = {
            "issues": [
                {
                    "file": "src/test.py",
                    "line": 10,
                    "message": "Same issue",
                    "severity": "warning",
                }
            ]
        }
        coderabbit_review = {
            "findings": [
                {
                    "file": "src/test.py",
                    "line": 10,
                    "message": "Same issue",
                    "severity": "warning",
                }
            ]
        }
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        # Should only have one issue due to deduplication
        assert len(result.issues) == 1
        assert result.issues[0]["source"] == "agent"

    @pytest.mark.asyncio
    async def test_handles_findings_key_in_agent_review(self) -> None:
        """Test handles agent review with 'findings' key."""
        agent_review = {
            "findings": [{"file": "test.py", "message": "Finding", "severity": "info"}]
        }
        coderabbit_review = {"findings": ()}
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        assert len(result.issues) == 1
        assert result.issues[0]["message"] == "Finding"

    @pytest.mark.asyncio
    async def test_handles_comments_key_in_agent_review(self) -> None:
        """Test handles agent review with 'comments' key."""
        agent_review = {
            "comments": [{"file": "test.py", "message": "Comment", "severity": "info"}]
        }
        coderabbit_review = {"findings": ()}
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        assert len(result.issues) == 1
        assert result.issues[0]["message"] == "Comment"

    @pytest.mark.asyncio
    async def test_generates_markdown_report(self) -> None:
        """Test generates properly formatted markdown report."""
        agent_review = {"issues": []}
        coderabbit_review = {"findings": ()}
        pr_metadata = {
            "number": 456,
            "title": "Feature: New Feature",
            "author": "developer",
        }

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        report = result.review_report
        assert "# Code Review Report" in report
        assert "**PR:** #456" in report
        assert "**Title:** Feature: New Feature" in report
        assert "**Author:** developer" in report
        assert "## Summary" in report
        assert "## Recommendation" in report

    @pytest.mark.asyncio
    async def test_groups_issues_by_severity(self) -> None:
        """Test groups and displays issues by severity."""
        agent_review = {
            "issues": [
                {"file": "a.py", "message": "Critical", "severity": "critical"},
                {"file": "b.py", "message": "Warning", "severity": "warning"},
                {"file": "c.py", "message": "Info", "severity": "info"},
                {"file": "d.py", "message": "Error", "severity": "error"},
            ]
        }
        coderabbit_review = {"findings": ()}
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        report = result.review_report
        assert "## Critical Issues (1)" in report
        assert "## Error Issues (1)" in report
        assert "## Warning Issues (1)" in report
        assert "## Info Issues (1)" in report

    @pytest.mark.asyncio
    async def test_recommends_approve_when_no_issues(self) -> None:
        """Test recommends approve when no issues found."""
        agent_review = {"issues": []}
        coderabbit_review = {"findings": ()}
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        assert result.recommendation == "approve"
        assert "Approve" in result.review_report

    @pytest.mark.asyncio
    async def test_recommends_request_changes_for_critical_issues(self) -> None:
        """Test recommends request changes when critical issues found."""
        agent_review = {
            "issues": [
                {"file": "a.py", "message": "Critical bug", "severity": "critical"}
            ]
        }
        coderabbit_review = {"findings": ()}
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        assert result.recommendation == "request_changes"
        assert "Request Changes" in result.review_report

    @pytest.mark.asyncio
    async def test_recommends_request_changes_for_errors(self) -> None:
        """Test recommends request changes when errors found."""
        agent_review = {
            "issues": [{"file": "a.py", "message": "Error found", "severity": "error"}]
        }
        coderabbit_review = {"findings": ()}
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        assert result.recommendation == "request_changes"

    @pytest.mark.asyncio
    async def test_recommends_comment_for_many_warnings(self) -> None:
        """Test recommends comment when many warnings (>3) found."""
        agent_review = {
            "issues": [
                {"file": "a.py", "message": "Warning 1", "severity": "warning"},
                {"file": "b.py", "message": "Warning 2", "severity": "warning"},
                {"file": "c.py", "message": "Warning 3", "severity": "warning"},
                {"file": "d.py", "message": "Warning 4", "severity": "warning"},
            ]
        }
        coderabbit_review = {"findings": ()}
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        assert result.recommendation == "comment"
        assert "Comment" in result.review_report

    @pytest.mark.asyncio
    async def test_recommends_comment_for_few_warnings(self) -> None:
        """Test recommends comment for few warnings (<=3)."""
        agent_review = {
            "issues": [
                {"file": "a.py", "message": "Warning 1", "severity": "warning"},
                {"file": "b.py", "message": "Info", "severity": "info"},
            ]
        }
        coderabbit_review = {"findings": ()}
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        assert result.recommendation == "comment"

    @pytest.mark.asyncio
    async def test_includes_file_and_line_info_in_report(self) -> None:
        """Test includes file and line information in report."""
        agent_review = {
            "issues": [
                {
                    "file": "src/main.py",
                    "line": 42,
                    "message": "Issue here",
                    "severity": "warning",
                }
            ]
        }
        coderabbit_review = {"findings": ()}
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        report = result.review_report
        assert "src/main.py:42" in report
        assert "Issue here" in report

    @pytest.mark.asyncio
    async def test_handles_missing_file_line_info(self) -> None:
        """Test handles issues without file or line information."""
        agent_review = {"issues": [{"message": "General issue", "severity": "info"}]}
        coderabbit_review = {"findings": ()}
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        report = result.review_report
        assert "unknown" in report
        assert "General issue" in report

    @pytest.mark.asyncio
    async def test_counts_issues_correctly_in_summary(self) -> None:
        """Test counts total, agent, and CodeRabbit issues correctly."""
        agent_review = {
            "issues": [
                {"file": "a.py", "message": "Agent 1", "severity": "info"},
                {"file": "b.py", "message": "Agent 2", "severity": "info"},
            ]
        }
        coderabbit_review = {
            "findings": [
                {"file": "c.py", "message": "CR 1", "severity": "info"},
            ]
        }
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        report = result.review_report
        assert "Total issues found: 3" in report
        assert "Agent review issues: 2" in report
        assert "CodeRabbit issues: 1" in report

    @pytest.mark.asyncio
    async def test_handles_unknown_severity(self) -> None:
        """Test handles issues with unknown severity levels."""
        agent_review = {
            "issues": [
                {"file": "a.py", "message": "Unknown severity", "severity": "unknown"},
                {"file": "b.py", "message": "No severity"},
            ]
        }
        coderabbit_review = {"findings": ()}
        pr_metadata = {"number": 123}

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        report = result.review_report
        assert "## Other Issues (2)" in report
        assert len(result.issues) == 2
