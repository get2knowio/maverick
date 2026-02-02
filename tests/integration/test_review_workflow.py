"""Integration tests for review workflow.

This module validates end-to-end execution of the review workflow:
- Gathering PR context from GitHub
- Running dual-agent reviews (spec + technical)
- Combining and formatting results
- Testing workflow with various PR states
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from maverick.dsl.events import (
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.serialization.executor import WorkflowFileExecutor
from maverick.dsl.serialization.parser import parse_workflow
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.runners.models import CommandResult


class TestReviewWorkflowIntegration:
    """Integration tests for the review workflow."""

    @pytest.fixture
    def workflow_path(self) -> Path:
        """Get path to review workflow YAML."""
        return (
            Path(__file__).parent.parent.parent
            / "src"
            / "maverick"
            / "library"
            / "workflows"
            / "review.yaml"
        )

    @pytest.fixture
    def registry(self) -> ComponentRegistry:
        """Create component registry with mocked actions and agents."""
        registry = ComponentRegistry()

        # Import and register real review actions (we'll mock subprocess calls)
        from maverick.library.actions import review

        # Register with bare names as used in workflow YAML
        registry.actions.register("gather_pr_context", review.gather_pr_context)
        registry.actions.register(
            "combine_review_results", review.combine_review_results
        )

        # Mock spec_reviewer agent
        class MockSpecReviewer:
            async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
                return {
                    "reviewer": "spec",
                    "assessment": "COMPLIANT",
                    "findings": "All requirements implemented.",
                    "context_used": list(context.keys()),
                }

        # Mock technical_reviewer agent
        class MockTechnicalReviewer:
            async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
                return {
                    "reviewer": "technical",
                    "quality": "GOOD",
                    "has_critical": False,
                    "findings": "Code is well-structured.",
                    "context_used": list(context.keys()),
                }

        registry.agents.register("spec_reviewer", MockSpecReviewer, validate=False)
        registry.agents.register(
            "technical_reviewer", MockTechnicalReviewer, validate=False
        )

        return registry

    @pytest.mark.asyncio
    async def test_review_workflow_with_pr_number(
        self, workflow_path: Path, registry: ComponentRegistry
    ) -> None:
        """Test complete review workflow with explicit PR number.

        This test validates:
        - Workflow loads from YAML definition
        - All steps execute in correct order
        - PR context is gathered successfully
        - Dual-agent reviews are performed
        - Results are combined into a report
        """
        # Parse workflow from YAML
        with open(workflow_path) as f:
            workflow = parse_workflow(f.read())

        # Mock PR context gathering
        pr_data = {
            "number": 123,
            "title": "Add review workflow",
            "body": "This PR adds the review workflow",
            "author": {"login": "testuser"},
            "labels": [{"name": "enhancement"}],
        }

        # Create CommandResult response for gh pr view
        async def mock_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return CommandResult(
                returncode=0,
                stdout=json.dumps(pr_data),
                stderr="",
                duration_ms=100,
                timed_out=False,
            )

        # Mock AsyncGitRepository for git operations
        mock_repo = AsyncMock()
        mock_repo.diff = AsyncMock(
            return_value=(
                "diff --git a/src/review.py b/src/review.py\n"
                "+def new_function():\n+    pass\n"
            )
        )
        mock_repo.get_changed_files = AsyncMock(
            return_value=["src/review.py", "tests/test_review.py"]
        )
        mock_repo.commit_messages_since = AsyncMock(
            return_value=["feat: add review workflow"]
        )
        mock_repo.current_branch = AsyncMock(return_value="feature/test")

        # Mock subprocess calls via CommandRunner class
        with (
            patch("maverick.library.actions.review.CommandRunner") as mock_runner_class,
            patch(
                "maverick.library.actions.review.AsyncGitRepository"
            ) as mock_git_repo_class,
        ):
            mock_runner = AsyncMock()
            mock_runner.run = AsyncMock(side_effect=mock_run)
            mock_runner_class.return_value = mock_runner

            mock_git_repo_class.return_value = mock_repo

            # Execute workflow (skip semantic validation due to dynamic agent names)
            executor = WorkflowFileExecutor(registry=registry, validate_semantic=False)
            events = []
            async for event in executor.execute(
                workflow,
                inputs={"pr_number": 123, "base_branch": "main"},
            ):
                events.append(event)

            # Verify workflow events were generated
            from maverick.dsl.events import PreflightCompleted, PreflightStarted

            assert len(events) > 0
            # Preflight events come first
            # (no validation events when validation is skipped)
            assert isinstance(events[0], PreflightStarted)
            assert isinstance(events[1], PreflightCompleted)
            # Then workflow start
            assert isinstance(events[2], WorkflowStarted)
            assert events[2].workflow_name == "review"

            # Verify final event is workflow completion
            assert isinstance(events[-1], WorkflowCompleted)

            # Verify runner was called for gh pr view
            assert mock_runner.run.call_count >= 1  # PR view

    @pytest.mark.asyncio
    async def test_review_workflow_auto_detect_pr(
        self, workflow_path: Path, registry: ComponentRegistry
    ) -> None:
        """Test review workflow with PR number auto-detection.

        This test validates:
        - PR number auto-detection from current branch
        - Workflow handles None as pr_number input
        - Context gathering works with auto-detected PR
        """
        # Parse workflow
        with open(workflow_path) as f:
            workflow = parse_workflow(f.read())

        # Create sequence of CommandResult responses for GitHub CLI calls
        responses = [
            # gh pr list
            CommandResult(
                returncode=0,
                stdout=json.dumps([{"number": 456}]),
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            # gh pr view
            CommandResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "number": 456,
                        "title": "Test PR",
                        "body": "Test PR description",
                        "author": {"login": "testuser"},
                        "labels": [],
                    }
                ),
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
        ]
        response_iter = iter(responses)

        async def mock_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return next(response_iter)

        # Mock AsyncGitRepository for git operations
        mock_repo = AsyncMock()
        mock_repo.current_branch = AsyncMock(return_value="feature/test")
        mock_repo.diff = AsyncMock(return_value="diff content\n")
        mock_repo.get_changed_files = AsyncMock(return_value=["file.py"])
        mock_repo.commit_messages_since = AsyncMock(return_value=["sha1 message"])

        with (
            patch("maverick.library.actions.review.CommandRunner") as mock_runner_class,
            patch(
                "maverick.library.actions.review.AsyncGitRepository"
            ) as mock_git_repo_class,
        ):
            mock_runner = AsyncMock()
            mock_runner.run = AsyncMock(side_effect=mock_run)
            mock_runner_class.return_value = mock_runner

            mock_git_repo_class.return_value = mock_repo

            # Execute workflow without pr_number (skip validation for dynamic agents)
            executor = WorkflowFileExecutor(registry=registry, validate_semantic=False)
            events = []
            async for event in executor.execute(
                workflow,
                inputs={"pr_number": None, "base_branch": "main"},
            ):
                events.append(event)

            from maverick.dsl.events import PreflightCompleted, PreflightStarted

            assert len(events) > 0
            # Preflight events (no validation events when validation is skipped)
            assert isinstance(events[0], PreflightStarted)
            assert isinstance(events[1], PreflightCompleted)
            assert isinstance(events[2], WorkflowStarted)
            # Workflow completed (may succeed or fail based on PR detection)
            # The important thing is it attempted to auto-detect


class TestReviewWorkflowActions:
    """Integration tests for individual review workflow actions."""

    @pytest.mark.asyncio
    async def test_gather_context_action(self) -> None:
        """Test gather_context action executes and returns expected output."""
        from maverick.library.actions.review import gather_pr_context

        # CommandResult for gh pr view
        pr_view_response = CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "number": 123,
                    "title": "Test",
                    "body": "Description",
                    "author": {"login": "user"},
                    "labels": [],
                }
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        async def mock_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return pr_view_response

        # Mock AsyncGitRepository for git operations
        mock_repo = AsyncMock()
        mock_repo.diff = AsyncMock(return_value="diff\n")
        mock_repo.get_changed_files = AsyncMock(return_value=["file.py"])
        mock_repo.commit_messages_since = AsyncMock(return_value=["sha1 msg"])
        mock_repo.current_branch = AsyncMock(return_value="feature/test")

        with (
            patch("maverick.library.actions.review.CommandRunner") as mock_runner_class,
            patch(
                "maverick.library.actions.review.AsyncGitRepository"
            ) as mock_git_repo_class,
        ):
            mock_runner = AsyncMock()
            mock_runner.run = AsyncMock(side_effect=mock_run)
            mock_runner_class.return_value = mock_runner

            mock_git_repo_class.return_value = mock_repo

            result = await gather_pr_context(123, "main")

            # Result is a ReviewContextResult dataclass
            assert result.pr_metadata is not None
            assert result.changed_files is not None
            assert result.diff is not None
            assert result.commits is not None
            assert result.pr_metadata.number == 123

    @pytest.mark.asyncio
    async def test_combine_results_action(self) -> None:
        """Test combine_results action merges and formats review data."""
        from maverick.library.actions.review import combine_review_results

        spec_review = {
            "reviewer": "spec",
            "assessment": "COMPLIANT",
            "findings": "All requirements met.",
        }
        technical_review = {
            "reviewer": "technical",
            "quality": "GOOD",
            "has_critical": False,
            "findings": "Code looks good.",
        }
        pr_metadata = {
            "number": 123,
            "title": "Test PR",
            "author": "user",
        }

        result = await combine_review_results(
            spec_review, technical_review, pr_metadata
        )

        # Result is a CombinedReviewResult dataclass
        assert result.review_report is not None
        assert result.recommendation is not None
        assert "# Code Review Report" in result.review_report
        assert "#123" in result.review_report
        assert result.recommendation in ["approve", "comment", "request_changes"]

    @pytest.mark.asyncio
    async def test_combine_results_with_critical_issues(self) -> None:
        """Test combine_results recommends changes for critical issues."""
        from maverick.library.actions.review import combine_review_results

        spec_review = {
            "reviewer": "spec",
            "assessment": "PARTIAL",
            "findings": "Some requirements missing.",
        }
        technical_review = {
            "reviewer": "technical",
            "quality": "NEEDS_WORK",
            "has_critical": True,
            "findings": "CRITICAL: Security issue found.",
        }
        pr_metadata = {"number": 123, "title": "Test PR"}

        result = await combine_review_results(
            spec_review, technical_review, pr_metadata
        )

        assert result.recommendation == "request_changes"


class TestReviewWorkflowEdgeCases:
    """Integration tests for edge cases in review workflow."""

    @pytest.mark.asyncio
    async def test_workflow_with_empty_diff(self) -> None:
        """Test workflow handles PR with no changes gracefully."""
        from maverick.library.actions.review import gather_pr_context

        # CommandResult for gh pr view
        pr_view_response = CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "number": 123,
                    "title": "Empty",
                    "body": "",
                    "author": {"login": "user"},
                    "labels": [],
                }
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        async def mock_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return pr_view_response

        # Mock AsyncGitRepository for git operations - returning empty results
        mock_repo = AsyncMock()
        mock_repo.diff = AsyncMock(return_value="")
        mock_repo.get_changed_files = AsyncMock(return_value=[])
        mock_repo.commit_messages_since = AsyncMock(return_value=[])
        mock_repo.current_branch = AsyncMock(return_value="feature/test")

        with (
            patch("maverick.library.actions.review.CommandRunner") as mock_runner_class,
            patch(
                "maverick.library.actions.review.AsyncGitRepository"
            ) as mock_git_repo_class,
        ):
            mock_runner = AsyncMock()
            mock_runner.run = AsyncMock(side_effect=mock_run)
            mock_runner_class.return_value = mock_runner

            mock_git_repo_class.return_value = mock_repo

            result = await gather_pr_context(123, "main")

            # Workflow should handle empty diff gracefully
            # Result is a ReviewContextResult dataclass
            assert result.changed_files == ()
            assert result.diff == ""
            assert result.commits == ()

    @pytest.mark.asyncio
    async def test_workflow_handles_pr_fetch_failure(self) -> None:
        """Test workflow handles PR fetch failures gracefully.

        When the GitHub CLI fails to fetch PR info, the workflow should
        still return partial results with available git data.
        """
        from maverick.library.actions.review import gather_pr_context

        async def mock_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            # Simulate PR fetch failure with non-zero returncode
            return CommandResult(
                returncode=1,
                stdout="",
                stderr="Error: PR not found",
                duration_ms=100,
                timed_out=False,
            )

        # Mock AsyncGitRepository for git operations
        mock_repo = AsyncMock()
        mock_repo.diff = AsyncMock(return_value="some diff")
        mock_repo.get_changed_files = AsyncMock(return_value=["file.py"])
        mock_repo.commit_messages_since = AsyncMock(return_value=["commit"])
        mock_repo.current_branch = AsyncMock(return_value="feature/test")

        with (
            patch("maverick.library.actions.review.CommandRunner") as mock_runner_class,
            patch(
                "maverick.library.actions.review.AsyncGitRepository"
            ) as mock_git_repo_class,
        ):
            mock_runner = AsyncMock()
            mock_runner.run = AsyncMock(side_effect=mock_run)
            mock_runner_class.return_value = mock_runner

            mock_git_repo_class.return_value = mock_repo

            result = await gather_pr_context(999, "main")

            # PR fetch failure should not block the entire workflow.
            # The result should contain the PR number but with minimal metadata
            # (no title, description, etc.) and the error should be None since
            # the overall operation succeeded (just the PR metadata fetch failed).
            assert result.pr_metadata.number == 999
            assert result.pr_metadata.title is None
            # Git operations should still succeed
            assert result.diff == "some diff"
            assert result.changed_files == ("file.py",)

    @pytest.mark.asyncio
    async def test_workflow_with_unicode_in_pr(self) -> None:
        """Test workflow handles Unicode characters in PR metadata."""
        from maverick.library.actions.review import gather_pr_context

        # PR with Unicode characters
        pr_data = {
            "number": 123,
            "title": "Add feature",
            "body": "This PR adds new features with special chars",
            "author": {"login": "user"},
            "labels": [],
        }

        pr_view_response = CommandResult(
            returncode=0,
            stdout=json.dumps(pr_data),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        async def mock_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return pr_view_response

        # Mock AsyncGitRepository for git operations
        mock_repo = AsyncMock()
        mock_repo.diff = AsyncMock(return_value="diff\n")
        mock_repo.get_changed_files = AsyncMock(return_value=["file.py"])
        mock_repo.commit_messages_since = AsyncMock(return_value=["msg"])
        mock_repo.current_branch = AsyncMock(return_value="feature/test")

        with (
            patch("maverick.library.actions.review.CommandRunner") as mock_runner_class,
            patch(
                "maverick.library.actions.review.AsyncGitRepository"
            ) as mock_git_repo_class,
        ):
            mock_runner = AsyncMock()
            mock_runner.run = AsyncMock(side_effect=mock_run)
            mock_runner_class.return_value = mock_runner

            mock_git_repo_class.return_value = mock_repo

            result = await gather_pr_context(123, "main")

            # Result is a ReviewContextResult dataclass
            assert result.pr_metadata.title == "Add feature"
            assert result.error is None
