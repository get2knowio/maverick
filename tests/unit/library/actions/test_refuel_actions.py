"""Unit tests for refuel workflow actions.

Tests the refuel.py action module including:
- process_selected_issues action for batch issue processing
- generate_refuel_summary action for workflow summary generation
"""

from __future__ import annotations

import pytest

from maverick.library.actions.refuel import (
    generate_refuel_summary,
    process_selected_issues,
)


class TestProcessSelectedIssues:
    """Tests for process_selected_issues action."""

    @pytest.mark.asyncio
    async def test_processes_single_issue(self) -> None:
        """Test processes a single issue."""
        issues = [
            {
                "number": 123,
                "title": "Fix parser bug",
            },
        ]

        result = await process_selected_issues(issues=issues, parallel=False)

        assert result["parallel_mode"] is False
        assert len(result["processed"]) == 1

        processed = result["processed"][0]
        assert processed["issue_number"] == 123
        assert processed["issue_title"] == "Fix parser bug"
        assert processed["status"] == "skipped"  # Placeholder status
        assert processed["branch_name"] is None
        assert processed["pr_url"] is None
        assert processed["error"] is None

    @pytest.mark.asyncio
    async def test_processes_multiple_issues(self) -> None:
        """Test processes multiple issues."""
        issues = [
            {"number": 100, "title": "Issue 1"},
            {"number": 200, "title": "Issue 2"},
            {"number": 300, "title": "Issue 3"},
        ]

        result = await process_selected_issues(issues=issues, parallel=False)

        assert len(result["processed"]) == 3
        assert result["processed"][0]["issue_number"] == 100
        assert result["processed"][1]["issue_number"] == 200
        assert result["processed"][2]["issue_number"] == 300

    @pytest.mark.asyncio
    async def test_processes_in_parallel_mode(self) -> None:
        """Test processes issues in parallel mode."""
        issues = [
            {"number": 1, "title": "First"},
            {"number": 2, "title": "Second"},
        ]

        result = await process_selected_issues(issues=issues, parallel=True)

        assert result["parallel_mode"] is True
        assert len(result["processed"]) == 2

    @pytest.mark.asyncio
    async def test_processes_in_sequential_mode(self) -> None:
        """Test processes issues in sequential mode."""
        issues = [
            {"number": 10, "title": "Issue A"},
            {"number": 20, "title": "Issue B"},
        ]

        result = await process_selected_issues(issues=issues, parallel=False)

        assert result["parallel_mode"] is False
        assert len(result["processed"]) == 2

    @pytest.mark.asyncio
    async def test_handles_empty_issue_list(self) -> None:
        """Test handles empty issue list gracefully."""
        result = await process_selected_issues(issues=[], parallel=False)

        assert result["parallel_mode"] is False
        assert len(result["processed"]) == 0

    @pytest.mark.asyncio
    async def test_handles_issue_without_title(self) -> None:
        """Test handles issue without title field."""
        issues = [
            {"number": 999},  # Missing title
        ]

        result = await process_selected_issues(issues=issues, parallel=False)

        assert len(result["processed"]) == 1
        assert result["processed"][0]["issue_number"] == 999
        assert result["processed"][0]["issue_title"] == ""

    @pytest.mark.asyncio
    async def test_returns_placeholder_status(self) -> None:
        """Test returns placeholder status for all issues."""
        issues = [
            {"number": 1, "title": "Test"},
        ]

        result = await process_selected_issues(issues=issues, parallel=False)

        # Currently returns placeholder status
        # This will be updated when sub-workflows are implemented
        assert result["processed"][0]["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_preserves_issue_metadata(self) -> None:
        """Test preserves issue number and title in results."""
        issues = [
            {"number": 42, "title": "The Answer"},
            {"number": 1337, "title": "Leet Issue"},
        ]

        result = await process_selected_issues(issues=issues, parallel=True)

        assert result["processed"][0]["issue_number"] == 42
        assert result["processed"][0]["issue_title"] == "The Answer"
        assert result["processed"][1]["issue_number"] == 1337
        assert result["processed"][1]["issue_title"] == "Leet Issue"


class TestGenerateRefuelSummary:
    """Tests for generate_refuel_summary action."""

    @pytest.mark.asyncio
    async def test_generates_summary_from_parallel_results(self) -> None:
        """Test generates summary from parallel processing results."""
        parallel_result = {
            "processed": [
                {
                    "issue_number": 1,
                    "status": "fixed",
                    "pr_url": "https://github.com/org/repo/pull/100",
                },
                {
                    "issue_number": 2,
                    "status": "failed",
                    "pr_url": None,
                },
                {
                    "issue_number": 3,
                    "status": "skipped",
                    "pr_url": None,
                },
            ],
        }

        result = await generate_refuel_summary(
            parallel_result=parallel_result,
            sequential_result=None,
            total_requested=3,
            label="tech-debt",
            parallel_mode=True,
        )

        assert result["total_issues"] == 3
        assert result["processed_count"] == 3
        assert result["success_count"] == 1
        assert result["failure_count"] == 1
        assert result["skipped_count"] == 1
        assert len(result["issues"]) == 3
        assert len(result["pr_urls"]) == 1
        assert result["pr_urls"][0] == "https://github.com/org/repo/pull/100"

    @pytest.mark.asyncio
    async def test_generates_summary_from_sequential_results(self) -> None:
        """Test generates summary from sequential processing results."""
        sequential_result = {
            "processed": [
                {
                    "issue_number": 10,
                    "status": "fixed",
                    "pr_url": "https://github.com/org/repo/pull/200",
                },
                {
                    "issue_number": 20,
                    "status": "fixed",
                    "pr_url": "https://github.com/org/repo/pull/201",
                },
            ],
        }

        result = await generate_refuel_summary(
            parallel_result=None,
            sequential_result=sequential_result,
            total_requested=2,
            label="bug",
            parallel_mode=False,
        )

        assert result["total_issues"] == 2
        assert result["processed_count"] == 2
        assert result["success_count"] == 2
        assert result["failure_count"] == 0
        assert result["skipped_count"] == 0
        assert len(result["pr_urls"]) == 2

    @pytest.mark.asyncio
    async def test_prefers_parallel_over_sequential(self) -> None:
        """Test uses parallel result when both provided."""
        parallel_result = {
            "processed": [
                {"issue_number": 1, "status": "fixed", "pr_url": "url1"},
            ],
        }
        sequential_result = {
            "processed": [
                {"issue_number": 2, "status": "fixed", "pr_url": "url2"},
                {"issue_number": 3, "status": "fixed", "pr_url": "url3"},
            ],
        }

        result = await generate_refuel_summary(
            parallel_result=parallel_result,
            sequential_result=sequential_result,
            total_requested=3,
            label="test",
            parallel_mode=True,
        )

        # Should use parallel result (1 issue) not sequential (2 issues)
        assert result["processed_count"] == 1
        assert result["success_count"] == 1

    @pytest.mark.asyncio
    async def test_handles_empty_results(self) -> None:
        """Test handles empty processing results."""
        result = await generate_refuel_summary(
            parallel_result=None,
            sequential_result=None,
            total_requested=5,
            label="tech-debt",
            parallel_mode=False,
        )

        assert result["total_issues"] == 5
        assert result["processed_count"] == 0
        assert result["success_count"] == 0
        assert result["failure_count"] == 0
        assert result["skipped_count"] == 0
        assert result["issues"] == ()
        assert result["pr_urls"] == ()

    @pytest.mark.asyncio
    async def test_counts_status_types_correctly(self) -> None:
        """Test correctly counts different status types."""
        parallel_result = {
            "processed": [
                {"issue_number": 1, "status": "fixed", "pr_url": "url1"},
                {"issue_number": 2, "status": "fixed", "pr_url": "url2"},
                {"issue_number": 3, "status": "failed", "pr_url": None},
                {"issue_number": 4, "status": "failed", "pr_url": None},
                {"issue_number": 5, "status": "failed", "pr_url": None},
                {"issue_number": 6, "status": "skipped", "pr_url": None},
            ],
        }

        result = await generate_refuel_summary(
            parallel_result=parallel_result,
            sequential_result=None,
            total_requested=6,
            label="test",
            parallel_mode=True,
        )

        assert result["success_count"] == 2
        assert result["failure_count"] == 3
        assert result["skipped_count"] == 1
        assert result["processed_count"] == 6

    @pytest.mark.asyncio
    async def test_collects_pr_urls(self) -> None:
        """Test collects all PR URLs from successful issues."""
        parallel_result = {
            "processed": [
                {"issue_number": 1, "status": "fixed", "pr_url": "https://github.com/org/repo/pull/1"},
                {"issue_number": 2, "status": "fixed", "pr_url": "https://github.com/org/repo/pull/2"},
                {"issue_number": 3, "status": "failed", "pr_url": None},
                {"issue_number": 4, "status": "fixed", "pr_url": "https://github.com/org/repo/pull/4"},
            ],
        }

        result = await generate_refuel_summary(
            parallel_result=parallel_result,
            sequential_result=None,
            total_requested=4,
            label="test",
            parallel_mode=True,
        )

        assert len(result["pr_urls"]) == 3
        assert "https://github.com/org/repo/pull/1" in result["pr_urls"]
        assert "https://github.com/org/repo/pull/2" in result["pr_urls"]
        assert "https://github.com/org/repo/pull/4" in result["pr_urls"]

    @pytest.mark.asyncio
    async def test_filters_none_pr_urls(self) -> None:
        """Test filters out None PR URLs."""
        parallel_result = {
            "processed": [
                {"issue_number": 1, "status": "fixed", "pr_url": "url1"},
                {"issue_number": 2, "status": "skipped", "pr_url": None},
                {"issue_number": 3, "status": "failed", "pr_url": None},
            ],
        }

        result = await generate_refuel_summary(
            parallel_result=parallel_result,
            sequential_result=None,
            total_requested=3,
            label="test",
            parallel_mode=True,
        )

        assert len(result["pr_urls"]) == 1
        assert result["pr_urls"][0] == "url1"

    @pytest.mark.asyncio
    async def test_returns_tuple_for_issues_and_pr_urls(self) -> None:
        """Test returns tuples for issues and pr_urls (immutable)."""
        parallel_result = {
            "processed": [
                {"issue_number": 1, "status": "fixed", "pr_url": "url1"},
            ],
        }

        result = await generate_refuel_summary(
            parallel_result=parallel_result,
            sequential_result=None,
            total_requested=1,
            label="test",
            parallel_mode=True,
        )

        assert isinstance(result["issues"], tuple)
        assert isinstance(result["pr_urls"], tuple)

    @pytest.mark.asyncio
    async def test_includes_all_issue_data(self) -> None:
        """Test includes all issue data in result."""
        issue_data = {
            "issue_number": 42,
            "issue_title": "Test Issue",
            "status": "fixed",
            "branch_name": "fix/issue-42",
            "pr_url": "https://github.com/org/repo/pull/100",
            "error": None,
        }
        parallel_result = {
            "processed": [issue_data],
        }

        result = await generate_refuel_summary(
            parallel_result=parallel_result,
            sequential_result=None,
            total_requested=1,
            label="test",
            parallel_mode=True,
        )

        assert result["issues"][0] == issue_data

    @pytest.mark.asyncio
    async def test_handles_missing_processed_key(self) -> None:
        """Test handles missing 'processed' key in results."""
        parallel_result = {}  # Missing 'processed' key

        result = await generate_refuel_summary(
            parallel_result=parallel_result,
            sequential_result=None,
            total_requested=0,
            label="test",
            parallel_mode=True,
        )

        assert result["processed_count"] == 0
        assert result["issues"] == ()

    @pytest.mark.asyncio
    async def test_total_requested_preserved(self) -> None:
        """Test total_requested parameter is preserved in result."""
        result = await generate_refuel_summary(
            parallel_result=None,
            sequential_result=None,
            total_requested=10,
            label="test",
            parallel_mode=False,
        )

        assert result["total_issues"] == 10
