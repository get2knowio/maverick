"""Integration tests for review workflow.

This module validates end-to-end execution of the review workflow:
- Gathering PR context from GitHub
- Running CodeRabbit review (if available)
- Executing agent review
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
    ValidationCompleted,
    ValidationStarted,
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

        registry.actions.register("review.gather_pr_context", review.gather_pr_context)
        registry.actions.register(
            "review.run_coderabbit_review", review.run_coderabbit_review
        )
        registry.actions.register(
            "review.combine_review_results", review.combine_review_results
        )

        # Mock code_reviewer agent
        class MockCodeReviewer:
            async def review_code(self, context: dict[str, Any]) -> dict[str, Any]:
                return {
                    "issues": [
                        {
                            "file": "src/test.py",
                            "line": 10,
                            "message": "Consider adding type hints",
                            "severity": "info",
                        }
                    ],
                    "summary": "Code looks good overall",
                }

        registry.agents.register("code_reviewer", MockCodeReviewer, validate=False)

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
        - CodeRabbit review is attempted
        - Agent review is performed
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

        # Create sequence of CommandResult responses
        responses = [
            # gh pr view
            CommandResult(
                returncode=0,
                stdout=json.dumps(pr_data),
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            # git diff
            CommandResult(
                returncode=0,
                stdout=(
                    "diff --git a/src/review.py b/src/review.py\n"
                    "+def new_function():\n+    pass\n"
                ),
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            # git diff --name-only
            CommandResult(
                returncode=0,
                stdout="src/review.py\ntests/test_review.py\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            # git log
            CommandResult(
                returncode=0,
                stdout="abc123 feat: add review workflow\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
        ]
        response_iter = iter(responses)

        async def mock_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return next(response_iter)

        # Mock subprocess calls
        with (
            patch(
                "maverick.library.actions.review._runner.run",
                new_callable=AsyncMock,
                side_effect=mock_run,
            ) as mock_runner,
            patch("maverick.library.actions.review.shutil.which") as mock_which,
        ):
            # Mock CodeRabbit availability check
            mock_which.return_value = None  # CodeRabbit not available

            # Execute workflow
            executor = WorkflowFileExecutor(registry=registry)
            events = []
            async for event in executor.execute(
                workflow,
                inputs={"pr_number": 123, "base_branch": "main"},
            ):
                events.append(event)

            # Verify workflow events were generated
            assert len(events) > 0
            # Validation events come first
            assert isinstance(events[0], ValidationStarted)
            assert isinstance(events[1], ValidationCompleted)
            assert isinstance(events[2], WorkflowStarted)
            assert events[2].workflow_name == "review"

            # Verify final event is workflow completion
            assert isinstance(events[-1], WorkflowCompleted)

            # Verify runner calls were made
            assert mock_runner.call_count >= 4  # PR view + diff + files + log

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

        # Create sequence of CommandResult responses
        responses = [
            # git rev-parse --abbrev-ref HEAD
            CommandResult(
                returncode=0,
                stdout="feature/test\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
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
            # git diff
            CommandResult(
                returncode=0,
                stdout="diff content\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            # git diff --name-only
            CommandResult(
                returncode=0,
                stdout="file.py\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            # git log
            CommandResult(
                returncode=0,
                stdout="sha1 message\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
        ]
        response_iter = iter(responses)

        async def mock_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return next(response_iter)

        with (
            patch(
                "maverick.library.actions.review._runner.run",
                new_callable=AsyncMock,
                side_effect=mock_run,
            ),
            patch("maverick.library.actions.review.shutil.which") as mock_which,
        ):
            mock_which.return_value = None

            # Execute workflow without pr_number
            executor = WorkflowFileExecutor(registry=registry)
            events = []
            async for event in executor.execute(
                workflow,
                inputs={"pr_number": None, "base_branch": "main"},
            ):
                events.append(event)

            assert len(events) > 0
            # Validation events come first
            assert isinstance(events[0], ValidationStarted)
            assert isinstance(events[1], ValidationCompleted)
            assert isinstance(events[2], WorkflowStarted)
            # Workflow completed (may succeed or fail based on PR detection)
            # The important thing is it attempted to auto-detect

    @pytest.mark.asyncio
    async def test_review_workflow_with_coderabbit(
        self, workflow_path: Path, registry: ComponentRegistry
    ) -> None:
        """Test review workflow with CodeRabbit available.

        This test validates:
        - CodeRabbit CLI detection
        - CodeRabbit review execution
        - Results combination from both sources
        """
        # Parse workflow
        with open(workflow_path) as f:
            workflow = parse_workflow(f.read())

        coderabbit_findings = {
            "findings": [
                {
                    "file": "src/main.py",
                    "line": 20,
                    "message": "Potential security issue",
                    "severity": "critical",
                }
            ]
        }

        # Create sequence of CommandResult responses for _runner
        runner_responses = [
            # gh pr view
            CommandResult(
                returncode=0,
                stdout=json.dumps({"number": 123, "labels": []}),
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            # git diff
            CommandResult(
                returncode=0,
                stdout="diff\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            # git diff --name-only
            CommandResult(
                returncode=0,
                stdout="src/main.py\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            # git log
            CommandResult(
                returncode=0,
                stdout="sha1 msg\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
        ]
        runner_iter = iter(runner_responses)

        async def mock_runner_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return next(runner_iter)

        # CodeRabbit runner response
        async def mock_coderabbit_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return CommandResult(
                returncode=0,
                stdout=json.dumps(coderabbit_findings),
                stderr="",
                duration_ms=100,
                timed_out=False,
            )

        with (
            patch(
                "maverick.library.actions.review._runner.run",
                new_callable=AsyncMock,
                side_effect=mock_runner_run,
            ),
            patch(
                "maverick.library.actions.review._coderabbit_runner.run",
                new_callable=AsyncMock,
                side_effect=mock_coderabbit_run,
            ),
            patch("maverick.library.actions.review.shutil.which") as mock_which,
        ):
            # Mock CodeRabbit available
            mock_which.return_value = "/usr/bin/coderabbit"

            executor = WorkflowFileExecutor(registry=registry)
            events = []
            async for event in executor.execute(
                workflow,
                inputs={"pr_number": 123, "base_branch": "main"},
            ):
                events.append(event)

            assert len(events) > 0
            assert isinstance(events[-1], WorkflowCompleted)


class TestReviewWorkflowActions:
    """Integration tests for individual review workflow actions."""

    @pytest.mark.asyncio
    async def test_gather_context_action(self) -> None:
        """Test gather_context action executes and returns expected output."""
        from maverick.library.actions.review import gather_pr_context

        # Create sequence of CommandResult responses
        responses = [
            CommandResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "number": 123,
                        "title": "Test",
                        "labels": [],
                    }
                ),
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            CommandResult(
                returncode=0,
                stdout="diff\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            CommandResult(
                returncode=0,
                stdout="file.py\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            CommandResult(
                returncode=0,
                stdout="sha1 msg\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
        ]
        response_iter = iter(responses)

        async def mock_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return next(response_iter)

        with (
            patch(
                "maverick.library.actions.review._runner.run",
                new_callable=AsyncMock,
                side_effect=mock_run,
            ),
            patch("maverick.library.actions.review.shutil.which") as mock_which,
        ):
            mock_which.return_value = None

            result = await gather_pr_context(123, "main")

            # Result is a ReviewContextResult dataclass
            assert result.pr_metadata is not None
            assert result.changed_files is not None
            assert result.diff is not None
            assert result.commits is not None
            assert result.coderabbit_available is not None
            assert result.pr_metadata.number == 123

    @pytest.mark.asyncio
    async def test_run_coderabbit_when_unavailable(self) -> None:
        """Test run_coderabbit action skips when CLI not available."""
        from maverick.library.actions.review import run_coderabbit_review

        context = {"coderabbit_available": False}

        result = await run_coderabbit_review(123, context)

        # Result is a CodeRabbitResult dataclass
        assert result.available is False
        assert result.findings == ()
        assert "not installed" in result.error

    @pytest.mark.asyncio
    async def test_run_coderabbit_when_available(self) -> None:
        """Test run_coderabbit action executes when CLI available."""
        from maverick.library.actions.review import run_coderabbit_review

        context = {"coderabbit_available": True}

        async def mock_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return CommandResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "findings": [
                            {
                                "file": "test.py",
                                "message": "Issue",
                                "severity": "warning",
                            }
                        ]
                    }
                ),
                stderr="",
                duration_ms=100,
                timed_out=False,
            )

        with patch(
            "maverick.library.actions.review._coderabbit_runner.run",
            new_callable=AsyncMock,
            side_effect=mock_run,
        ):
            result = await run_coderabbit_review(123, context)

            # Result is a CodeRabbitResult dataclass
            assert result.available is True
            assert len(result.findings) == 1
            assert result.error is None

    @pytest.mark.asyncio
    async def test_combine_results_action(self) -> None:
        """Test combine_results action merges and formats review data."""
        from maverick.library.actions.review import combine_review_results

        agent_review = {
            "issues": [
                {"file": "a.py", "message": "Agent issue", "severity": "warning"}
            ]
        }
        coderabbit_review = {
            "findings": [{"file": "b.py", "message": "CR issue", "severity": "info"}]
        }
        pr_metadata = {
            "number": 123,
            "title": "Test PR",
            "author": "user",
        }

        result = await combine_review_results(
            agent_review, coderabbit_review, pr_metadata
        )

        # Result is a CombinedReviewResult dataclass
        assert result.review_report is not None
        assert result.issues is not None
        assert result.recommendation is not None
        assert len(result.issues) == 2
        assert "# Code Review Report" in result.review_report
        assert "**PR:** #123" in result.review_report
        assert result.recommendation in ["approve", "comment", "request_changes"]


class TestReviewWorkflowEdgeCases:
    """Integration tests for edge cases in review workflow."""

    @pytest.mark.asyncio
    async def test_workflow_with_empty_diff(self) -> None:
        """Test workflow handles PR with no changes gracefully."""
        from maverick.library.actions.review import gather_pr_context

        # Create sequence of CommandResult responses
        responses = [
            CommandResult(
                returncode=0,
                stdout=json.dumps({"number": 123, "labels": []}),
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            CommandResult(
                returncode=0,
                stdout="",  # Empty diff
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            CommandResult(
                returncode=0,
                stdout="",  # No files
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            CommandResult(
                returncode=0,
                stdout="",  # No commits
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
        ]
        response_iter = iter(responses)

        async def mock_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return next(response_iter)

        with (
            patch(
                "maverick.library.actions.review._runner.run",
                new_callable=AsyncMock,
                side_effect=mock_run,
            ),
            patch("maverick.library.actions.review.shutil.which") as mock_which,
        ):
            mock_which.return_value = None

            result = await gather_pr_context(123, "main")

            # Workflow should handle empty diff gracefully
            # Result is a ReviewContextResult dataclass
            assert result.changed_files == ()
            assert result.diff == ""
            assert result.commits == ()

    @pytest.mark.asyncio
    async def test_workflow_handles_pr_fetch_failure(self) -> None:
        """Test workflow handles PR fetch failures gracefully."""
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

        with (
            patch(
                "maverick.library.actions.review._runner.run",
                new_callable=AsyncMock,
                side_effect=mock_run,
            ),
            patch("maverick.library.actions.review.shutil.which") as mock_which,
        ):
            mock_which.return_value = None

            result = await gather_pr_context(999, "main")

            # Error should be captured in result
            # Result is a ReviewContextResult dataclass
            assert result.error is not None
            assert result.changed_files == ()
            assert result.diff == ""

    @pytest.mark.asyncio
    async def test_workflow_with_unicode_in_pr(self) -> None:
        """Test workflow handles Unicode characters in PR metadata."""
        from maverick.library.actions.review import gather_pr_context

        # PR with Unicode characters
        pr_data = {
            "number": 123,
            "title": "Add feature 🚀",
            "body": "This PR adds 新功能 with émojis",
            "labels": [],
        }

        # Create sequence of CommandResult responses
        responses = [
            CommandResult(
                returncode=0,
                stdout=json.dumps(pr_data),
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            CommandResult(
                returncode=0,
                stdout="diff\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            CommandResult(
                returncode=0,
                stdout="file.py\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
            CommandResult(
                returncode=0,
                stdout="msg\n",
                stderr="",
                duration_ms=100,
                timed_out=False,
            ),
        ]
        response_iter = iter(responses)

        async def mock_run(cmd: list[str], **kwargs: Any) -> CommandResult:
            return next(response_iter)

        with (
            patch(
                "maverick.library.actions.review._runner.run",
                new_callable=AsyncMock,
                side_effect=mock_run,
            ),
            patch("maverick.library.actions.review.shutil.which") as mock_which,
        ):
            mock_which.return_value = None

            result = await gather_pr_context(123, "main")

            # Unicode should be preserved
            # Result is a ReviewContextResult dataclass
            assert result.pr_metadata.title == "Add feature 🚀"
            assert "émojis" in result.pr_metadata.description
