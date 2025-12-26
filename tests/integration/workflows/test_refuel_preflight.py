"""Integration tests for RefuelWorkflow preflight validation failure scenarios.

Tests RefuelWorkflow execution with mocked runners to verify preflight
validation behavior without external dependencies.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.runners.preflight import ValidationResult
from maverick.workflows.refuel import (
    RefuelCompleted,
    RefuelInputs,
    RefuelStarted,
    RefuelWorkflow,
)

# =============================================================================
# Helper Functions
# =============================================================================


def create_mock_git_runner() -> MagicMock:
    """Create a mock GitRunner with default success behavior.

    Returns:
        Configured mock GitRunner.
    """
    mock_git = MagicMock()
    mock_git.create_branch = AsyncMock(return_value="test-branch")
    mock_git.add = AsyncMock(return_value=None)
    mock_git.diff = AsyncMock(return_value="diff --git a/file.py b/file.py\n+new line")
    mock_git.commit = AsyncMock(return_value="abc123")
    mock_git.push = AsyncMock(return_value=None)
    return mock_git


def create_mock_github_runner() -> MagicMock:
    """Create a mock GitHubCLIRunner with default success behavior.

    Returns:
        Configured mock GitHubCLIRunner.
    """
    mock_github = MagicMock()
    mock_github.list_issues = AsyncMock(return_value=[])
    mock_github.create_pr = AsyncMock(
        return_value="https://github.com/owner/repo/pull/123"
    )
    return mock_github


def create_mock_validation_runner(success: bool = True) -> MagicMock:
    """Create a mock ValidationRunner with configurable behavior.

    Args:
        success: Whether validation succeeds.

    Returns:
        Configured mock ValidationRunner.
    """
    from maverick.models.validation import StageResult, StageStatus

    mock_validation = MagicMock()

    if success:
        stage_results = [
            StageResult(
                stage_name="format",
                status=StageStatus.PASSED,
                fix_attempts=0,
                error_message=None,
                output="All files formatted",
                duration_ms=100,
            ),
            StageResult(
                stage_name="lint",
                status=StageStatus.PASSED,
                fix_attempts=0,
                error_message=None,
                output="No linting errors",
                duration_ms=150,
            ),
        ]
    else:
        stage_results = [
            StageResult(
                stage_name="format",
                status=StageStatus.FAILED,
                fix_attempts=0,
                error_message="Formatting failed",
                output="Error: invalid syntax",
                duration_ms=100,
            ),
        ]

    mock_result = MagicMock()
    mock_result.success = success
    mock_result.stages = stage_results

    mock_validation.run = AsyncMock(return_value=mock_result)
    return mock_validation


# =============================================================================
# Preflight Failure Tests
# =============================================================================


class TestRefuelWorkflowPreflightFailure:
    """Tests for RefuelWorkflow preflight validation failure scenarios.

    Verifies that preflight validation:
    - Raises PreflightValidationError on failure (emits RefuelCompleted with failure)
    - Runs before any state changes
    - Runs even in dry_run mode
    """

    @pytest.mark.asyncio
    async def test_refuel_workflow_fails_on_preflight_failure(self) -> None:
        """Test RefuelWorkflow emits failed result on preflight failure."""
        # Create workflow with mock runners
        mock_git = create_mock_git_runner()
        mock_github = create_mock_github_runner()
        mock_validation = create_mock_validation_runner(success=True)

        workflow = RefuelWorkflow(
            git_runner=mock_git,
            github_runner=mock_github,
            validation_runner=mock_validation,
        )

        inputs = RefuelInputs(
            label="tech-debt",
            limit=5,
            parallel=False,
            dry_run=False,
            auto_assign=False,
        )

        # Mock a runner to fail validation
        failing_runner = MagicMock()
        failing_runner.__class__.__name__ = "FailingRunner"
        failing_runner.validate = AsyncMock(
            return_value=ValidationResult(
                success=False,
                component="FailingRunner",
                errors=("Test preflight failure",),
            )
        )

        # Patch _discover_runners to return our failing runner
        with patch.object(workflow, "_discover_runners", return_value=[failing_runner]):
            # Execute and collect events
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Verify: Workflow emitted a RefuelCompleted event with failure
            completed_events = [e for e in events if isinstance(e, RefuelCompleted)]
            assert len(completed_events) == 1

            result = completed_events[0].result
            assert result.success is False
            assert result.issues_failed >= 1

            # Verify: No RefuelStarted event (preflight failed before workflow started)
            started_events = [e for e in events if isinstance(e, RefuelStarted)]
            assert len(started_events) == 0

            # Verify: Git runner was never called (no state changes)
            assert not mock_git.create_branch.called
            assert not mock_git.commit.called
            assert not mock_git.push.called

            # Verify: GitHub runner was never called
            assert not mock_github.list_issues.called
            assert not mock_github.create_pr.called

    @pytest.mark.asyncio
    async def test_refuel_workflow_preflight_runs_before_execute(self) -> None:
        """Verify preflight is called before any state changes."""
        # Create workflow with mock runners
        mock_git = create_mock_git_runner()
        mock_github = create_mock_github_runner()
        mock_validation = create_mock_validation_runner(success=True)

        workflow = RefuelWorkflow(
            git_runner=mock_git,
            github_runner=mock_github,
            validation_runner=mock_validation,
        )

        inputs = RefuelInputs(
            label="tech-debt",
            limit=5,
            parallel=False,
            dry_run=False,
            auto_assign=False,
        )

        # Track call order
        call_order: list[str] = []

        # Mock a runner that tracks when validation is called
        tracking_runner = MagicMock()
        tracking_runner.__class__.__name__ = "TrackingRunner"

        async def track_validate():
            call_order.append("preflight_validate")
            return ValidationResult(
                success=True,
                component="TrackingRunner",
                errors=(),
            )

        tracking_runner.validate = track_validate

        # Wrap github runner to track when list_issues is called
        original_list_issues = mock_github.list_issues

        async def tracked_list_issues(*args, **kwargs):
            call_order.append("github_list_issues")
            return await original_list_issues(*args, **kwargs)

        mock_github.list_issues = AsyncMock(side_effect=tracked_list_issues)

        # Patch _discover_runners to return our tracking runner
        with patch.object(
            workflow, "_discover_runners", return_value=[tracking_runner]
        ):
            # Execute workflow
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Verify: Preflight validation was called before GitHub operations
            # At minimum we should see preflight_validate in the call_order
            assert "preflight_validate" in call_order

            # If GitHub list_issues was called, it should be after preflight
            if "github_list_issues" in call_order:
                assert call_order.index("preflight_validate") < call_order.index(
                    "github_list_issues"
                )

    @pytest.mark.asyncio
    async def test_refuel_workflow_preflight_in_dry_run_mode(self) -> None:
        """Verify preflight still runs even in dry_run mode."""
        # Create workflow with mock runners
        mock_git = create_mock_git_runner()
        mock_github = create_mock_github_runner()
        mock_validation = create_mock_validation_runner(success=True)

        workflow = RefuelWorkflow(
            git_runner=mock_git,
            github_runner=mock_github,
            validation_runner=mock_validation,
        )

        # Enable dry_run mode
        inputs = RefuelInputs(
            label="tech-debt",
            limit=5,
            parallel=False,
            dry_run=True,
            auto_assign=False,
        )

        # Track if preflight validation was called
        preflight_called = False

        # Mock a runner that tracks when validation is called
        tracking_runner = MagicMock()
        tracking_runner.__class__.__name__ = "DryRunTracker"

        async def track_validate():
            nonlocal preflight_called
            preflight_called = True
            return ValidationResult(
                success=True,
                component="DryRunTracker",
                errors=(),
            )

        tracking_runner.validate = track_validate

        # Patch _discover_runners to return our tracking runner
        with patch.object(
            workflow, "_discover_runners", return_value=[tracking_runner]
        ):
            # Execute workflow in dry_run mode
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Verify: Preflight validation was called even in dry_run mode
            assert preflight_called, "Preflight validation should run in dry_run mode"

            # Verify: Workflow completed (preflight passed)
            completed_events = [e for e in events if isinstance(e, RefuelCompleted)]
            assert len(completed_events) == 1

    @pytest.mark.asyncio
    async def test_refuel_workflow_preflight_failure_with_multiple_errors(
        self,
    ) -> None:
        """Test RefuelWorkflow handles multiple preflight errors correctly."""
        # Create workflow with mock runners
        mock_git = create_mock_git_runner()
        mock_github = create_mock_github_runner()
        mock_validation = create_mock_validation_runner(success=True)

        workflow = RefuelWorkflow(
            git_runner=mock_git,
            github_runner=mock_github,
            validation_runner=mock_validation,
        )

        inputs = RefuelInputs(
            label="tech-debt",
            limit=5,
            parallel=False,
            dry_run=False,
            auto_assign=False,
        )

        # Mock a runner with multiple validation errors
        failing_runner = MagicMock()
        failing_runner.__class__.__name__ = "MultiFailRunner"
        failing_runner.validate = AsyncMock(
            return_value=ValidationResult(
                success=False,
                component="MultiFailRunner",
                errors=(
                    "GitHub CLI not authenticated",
                    "Git not configured",
                    "Missing repository access",
                ),
            )
        )

        # Patch _discover_runners to return our failing runner
        with patch.object(workflow, "_discover_runners", return_value=[failing_runner]):
            # Execute and collect events
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Verify: Workflow emitted a RefuelCompleted event with failure
            completed_events = [e for e in events if isinstance(e, RefuelCompleted)]
            assert len(completed_events) == 1

            result = completed_events[0].result
            assert result.success is False

            # Verify: No state-changing operations were called
            assert not mock_git.create_branch.called
            assert not mock_github.create_pr.called
