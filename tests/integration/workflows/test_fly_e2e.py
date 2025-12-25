"""End-to-end integration tests for FlyWorkflow.

Tests FlyWorkflow execution with mocked runners and agents to verify
the complete workflow orchestration without external dependencies.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.agents.result import AgentResult, AgentUsage
from maverick.exceptions import AgentError
from maverick.models.validation import (
    StageResult,
    StageStatus,
)
from maverick.runners.preflight import PreflightResult, ValidationResult
from maverick.workflows.fly import (
    FlyConfig,
    FlyInputs,
    FlyStageCompleted,
    FlyStageStarted,
    FlyWorkflow,
    FlyWorkflowCompleted,
    FlyWorkflowFailed,
    FlyWorkflowStarted,
    WorkflowStage,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_preflight():
    """Fixture to mock preflight validation to pass.

    This fixture patches run_preflight to return a successful result,
    allowing tests that don't specifically test preflight to run without
    setting up full async validator mocks.
    """
    success_result = PreflightResult(
        success=True,
        results=[
            ValidationResult(
                success=True,
                component="MockRunner",
            )
        ],
        total_duration_ms=10,
    )

    with patch.object(
        FlyWorkflow,
        "run_preflight",
        new_callable=AsyncMock,
        return_value=success_result,
    ):
        yield


# =============================================================================
# Helper Functions
# =============================================================================


def create_mock_git_runner(
    create_branch_success: bool = True,
    commit_success: bool = True,
    push_success: bool = True,
) -> MagicMock:
    """Create a mock AsyncGitRepository with configurable behavior.

    The mock matches the new AsyncGitRepository API which returns values
    directly and raises exceptions on failure.

    Args:
        create_branch_success: Whether branch creation succeeds.
        commit_success: Whether commit succeeds.
        push_success: Whether push succeeds.

    Returns:
        Configured mock AsyncGitRepository.
    """
    from maverick.exceptions import GitError

    mock_git = MagicMock()

    # AsyncGitRepository.create_branch_with_fallback returns the branch name
    if create_branch_success:
        mock_git.create_branch_with_fallback = AsyncMock(return_value="test-branch")
    else:
        mock_git.create_branch_with_fallback = AsyncMock(
            side_effect=GitError("Failed to create branch")
        )

    # create_branch doesn't return anything (raises on failure)
    if create_branch_success:
        mock_git.create_branch = AsyncMock(return_value=None)
    else:
        mock_git.create_branch = AsyncMock(
            side_effect=GitError("Failed to create branch")
        )

    # add_all doesn't return anything
    mock_git.add_all = AsyncMock(return_value=None)
    # Legacy add method (for backward compatibility)
    mock_git.add = AsyncMock(return_value=None)

    # diff returns string
    mock_git.diff = AsyncMock(return_value="diff --git a/file.py b/file.py\n+new line")

    # commit returns the commit SHA
    if commit_success:
        mock_git.commit = AsyncMock(return_value="abc123")
    else:
        mock_git.commit = AsyncMock(side_effect=GitError("Commit failed"))

    # push doesn't return anything (raises on failure)
    if push_success:
        mock_git.push = AsyncMock(return_value=None)
    else:
        mock_git.push = AsyncMock(side_effect=GitError("Push failed"))

    # get_remote_url for _get_repo_name helper
    mock_git.get_remote_url = AsyncMock(
        return_value="https://github.com/owner/repo.git"
    )

    return mock_git


def create_mock_validation_runner(success: bool = True) -> MagicMock:
    """Create a mock ValidationRunner with configurable behavior.

    Args:
        success: Whether validation succeeds.

    Returns:
        Configured mock ValidationRunner.
    """
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

    # Create a mock object with success and stages attributes
    mock_result = MagicMock()
    mock_result.success = success
    mock_result.stages = stage_results

    mock_validation.run = AsyncMock(return_value=mock_result)
    return mock_validation


def create_mock_github_runner(create_pr_success: bool = True) -> MagicMock:
    """Create a mock GitHubClient with configurable behavior.

    The mock matches the new GitHubClient API which returns PyGithub PullRequest
    objects and raises GitHubError on failure.

    Args:
        create_pr_success: Whether PR creation succeeds.

    Returns:
        Configured mock GitHubClient.
    """
    from maverick.exceptions import GitHubError

    mock_github = MagicMock()

    if create_pr_success:
        # Create a mock PullRequest object with html_url
        mock_pr = MagicMock()
        mock_pr.html_url = "https://github.com/owner/repo/pull/123"
        mock_pr.number = 123
        mock_github.create_pr = AsyncMock(return_value=mock_pr)
    else:
        mock_github.create_pr = AsyncMock(
            side_effect=GitHubError("Failed to create PR")
        )

    return mock_github


def create_mock_implementer_agent(success: bool = True) -> MagicMock:
    """Create a mock ImplementerAgent with configurable behavior.

    Args:
        success: Whether implementation succeeds.

    Returns:
        Configured mock ImplementerAgent.
    """
    mock_agent = MagicMock()
    usage = AgentUsage(
        input_tokens=500,
        output_tokens=250,
        total_cost_usd=0.015,
        duration_ms=2000,
    )

    if success:
        result = AgentResult.success_result(
            output="Implementation complete: 3 tasks completed",
            usage=usage,
        )
    else:
        result = AgentResult.failure_result(
            errors=[
                AgentError("Implementation failed: syntax error in generated code")
            ],
            usage=usage,
        )

    mock_agent.execute = AsyncMock(return_value=result)
    return mock_agent


def create_mock_code_reviewer_agent() -> MagicMock:
    """Create a mock CodeReviewerAgent.

    Returns:
        Configured mock CodeReviewerAgent.
    """
    mock_agent = MagicMock()
    usage = AgentUsage(
        input_tokens=300,
        output_tokens=150,
        total_cost_usd=0.008,
        duration_ms=1500,
    )
    result = AgentResult.success_result(
        output="Code review complete: no critical issues found",
        usage=usage,
    )
    mock_agent.execute = AsyncMock(return_value=result)
    return mock_agent


def create_mock_commit_generator() -> MagicMock:
    """Create a mock CommitMessageGenerator.

    Returns:
        Configured mock CommitMessageGenerator.
    """
    mock_gen = MagicMock()
    mock_gen.generate = AsyncMock(
        return_value=(
            "feat: implement user authentication\n\nAdded login and signup endpoints."
        )
    )
    return mock_gen


def create_mock_pr_generator() -> MagicMock:
    """Create a mock PRDescriptionGenerator.

    Returns:
        Configured mock PRDescriptionGenerator.
    """
    mock_gen = MagicMock()
    mock_gen.generate = AsyncMock(
        return_value=(
            "## Summary\n\n"
            "Implemented user authentication feature:\n"
            "- Added login endpoint\n"
            "- Added signup endpoint\n"
            "- Added password hashing\n\n"
            "## Test Plan\n\n"
            "- [x] Unit tests pass\n"
            "- [x] Integration tests pass\n"
        )
    )
    return mock_gen


# =============================================================================
# T063: Integration test using all mocked runners
# =============================================================================


@pytest.mark.asyncio
async def test_complete_workflow_execution_with_all_mocked_dependencies(
    tmp_path, mock_preflight
):
    """Test complete FlyWorkflow execution with all dependencies mocked.

    Verifies:
    - All workflow stages execute in correct order
    - Each stage emits appropriate progress events
    - Mocked runners are called with correct parameters
    - Token usage is aggregated correctly
    - Final result indicates success
    """
    # Setup: Create task file
    task_file = tmp_path / "tasks.md"
    task_file.write_text(
        "# Tasks\n\n"
        "- [ ] T001 Implement login endpoint\n"
        "- [ ] T002 Implement signup endpoint\n"
        "- [ ] T003 Add password hashing\n"
    )

    # Setup: Create all mocked dependencies
    mock_git = create_mock_git_runner()
    mock_validation = create_mock_validation_runner(success=True)
    mock_github = create_mock_github_runner(create_pr_success=True)
    mock_implementer = create_mock_implementer_agent(success=True)
    mock_reviewer = create_mock_code_reviewer_agent()
    mock_commit_gen = create_mock_commit_generator()
    mock_pr_gen = create_mock_pr_generator()

    # Setup: Create workflow configuration
    config = FlyConfig(
        parallel_reviews=True,
        max_validation_attempts=3,
        coderabbit_enabled=False,
        auto_merge=False,
        notification_on_complete=True,
    )

    # Execute: Create and run workflow
    workflow = FlyWorkflow(
        config=config,
        git_runner=mock_git,
        validation_runner=mock_validation,
        github_runner=mock_github,
        implementer_agent=mock_implementer,
        code_reviewer_agent=mock_reviewer,
        commit_generator=mock_commit_gen,
        pr_generator=mock_pr_gen,
    )

    inputs = FlyInputs(
        branch_name="feature/user-auth",
        task_file=task_file,
        skip_review=False,
        skip_pr=False,
        draft_pr=False,
        base_branch="main",
    )

    # Collect all progress events
    events = []
    async for event in workflow.execute(inputs):
        events.append(event)

    # Verify: Workflow started event
    started_events = [e for e in events if isinstance(e, FlyWorkflowStarted)]
    assert len(started_events) == 1
    assert started_events[0].inputs.branch_name == "feature/user-auth"

    # Verify: Stage execution order
    stage_started_events = [e for e in events if isinstance(e, FlyStageStarted)]
    expected_stages = [
        WorkflowStage.INIT,
        WorkflowStage.IMPLEMENTATION,
        WorkflowStage.VALIDATION,
        WorkflowStage.CODE_REVIEW,
        WorkflowStage.CONVENTION_UPDATE,
        WorkflowStage.PR_CREATION,
    ]

    for idx, expected_stage in enumerate(expected_stages):
        assert stage_started_events[idx].stage == expected_stage

    # Verify: Stage completion events
    stage_completed_events = [e for e in events if isinstance(e, FlyStageCompleted)]
    assert len(stage_completed_events) >= len(expected_stages)

    # Verify: Workflow completed successfully
    completed_events = [e for e in events if isinstance(e, FlyWorkflowCompleted)]
    assert len(completed_events) == 1

    result = completed_events[0].result
    assert result.success is True
    assert result.token_usage.input_tokens == 800  # 500 + 300
    assert result.token_usage.output_tokens == 400  # 250 + 150
    assert result.total_cost_usd == 0.023  # 0.015 + 0.008

    # Verify: Mock calls
    mock_git.create_branch_with_fallback.assert_called_once_with(
        "feature/user-auth", "HEAD"
    )
    mock_implementer.execute.assert_called_once()
    mock_validation.run.assert_called_once()
    mock_reviewer.execute.assert_called_once()
    mock_commit_gen.generate.assert_called_once()
    mock_pr_gen.generate.assert_called_once()
    mock_github.create_pr.assert_called_once()

    # Verify: No failure events
    failed_events = [e for e in events if isinstance(e, FlyWorkflowFailed)]
    assert len(failed_events) == 0


# =============================================================================
# T064: Integration test for mocked runner error responses
# =============================================================================


@pytest.mark.asyncio
async def test_workflow_handles_git_runner_branch_creation_failure(
    tmp_path, mock_preflight
):
    """Test workflow handles GitRunner branch creation failure gracefully.

    Verifies:
    - Branch creation failure is caught
    - Workflow emits FlyWorkflowFailed event
    - No subsequent stages execute
    - Error is captured in result
    """
    # Setup: Create task file
    task_file = tmp_path / "tasks.md"
    task_file.write_text("- [ ] T001 Test task\n")

    # Setup: Create git runner that fails branch creation
    mock_git = create_mock_git_runner(create_branch_success=False)
    mock_validation = create_mock_validation_runner(success=True)
    mock_implementer = create_mock_implementer_agent(success=True)

    # Execute: Create and run workflow
    workflow = FlyWorkflow(
        git_runner=mock_git,
        validation_runner=mock_validation,
        implementer_agent=mock_implementer,
    )

    inputs = FlyInputs(branch_name="test-branch", task_file=task_file)

    events = []
    async for event in workflow.execute(inputs):
        events.append(event)

    # Verify: Workflow failed event
    failed_events = [e for e in events if isinstance(e, FlyWorkflowFailed)]
    assert len(failed_events) == 1
    assert "Failed to create branch" in failed_events[0].error

    # Verify: INIT stage started but other stages did not
    stage_started = [e for e in events if isinstance(e, FlyStageStarted)]
    assert len(stage_started) == 1
    assert stage_started[0].stage == WorkflowStage.INIT

    # Verify: Implementation stage never executed
    assert not mock_implementer.execute.called


@pytest.mark.asyncio
async def test_workflow_handles_github_runner_pr_creation_failure(
    tmp_path, mock_preflight
):
    """Test workflow handles GitHub PR creation failure gracefully.

    Verifies:
    - PR creation failure is caught
    - Workflow continues and completes
    - Error is logged in state
    - Success flag reflects the failure
    """
    # Setup: Create task file
    task_file = tmp_path / "tasks.md"
    task_file.write_text("- [ ] T001 Test task\n")

    # Setup: Create mocks with PR creation failure
    mock_git = create_mock_git_runner()
    mock_validation = create_mock_validation_runner(success=True)
    mock_github = create_mock_github_runner(create_pr_success=False)
    mock_implementer = create_mock_implementer_agent(success=True)
    mock_reviewer = create_mock_code_reviewer_agent()
    mock_commit_gen = create_mock_commit_generator()
    mock_pr_gen = create_mock_pr_generator()

    # Execute: Create and run workflow
    workflow = FlyWorkflow(
        git_runner=mock_git,
        validation_runner=mock_validation,
        github_runner=mock_github,
        implementer_agent=mock_implementer,
        code_reviewer_agent=mock_reviewer,
        commit_generator=mock_commit_gen,
        pr_generator=mock_pr_gen,
    )

    inputs = FlyInputs(
        branch_name="test-branch",
        task_file=task_file,
        skip_review=False,
        skip_pr=False,
    )

    events = []
    async for event in workflow.execute(inputs):
        events.append(event)

    # Verify: Workflow completed (not failed - graceful degradation)
    completed_events = [e for e in events if isinstance(e, FlyWorkflowCompleted)]
    assert len(completed_events) == 1

    # Verify: Error recorded in state
    result = completed_events[0].result
    assert len(result.state.errors) > 0
    assert any("PR creation failed" in error for error in result.state.errors)

    # Verify: PR URL is None due to failure
    assert result.state.pr_url is None


@pytest.mark.asyncio
async def test_workflow_handles_implementer_agent_failure(tmp_path, mock_preflight):
    """Test workflow handles ImplementerAgent failure gracefully.

    Verifies:
    - Agent failure is caught
    - Workflow continues to subsequent stages
    - Error is captured but workflow doesn't abort
    """
    # Setup: Create task file
    task_file = tmp_path / "tasks.md"
    task_file.write_text("- [ ] T001 Test task\n")

    # Setup: Create mocks with failing implementer
    mock_git = create_mock_git_runner()
    mock_validation = create_mock_validation_runner(success=True)
    mock_implementer = create_mock_implementer_agent(success=False)
    mock_commit_gen = create_mock_commit_generator()
    mock_pr_gen = create_mock_pr_generator()
    mock_github = create_mock_github_runner()

    # Execute: Create and run workflow
    workflow = FlyWorkflow(
        git_runner=mock_git,
        validation_runner=mock_validation,
        implementer_agent=mock_implementer,
        commit_generator=mock_commit_gen,
        pr_generator=mock_pr_gen,
        github_runner=mock_github,
    )

    inputs = FlyInputs(
        branch_name="test-branch",
        task_file=task_file,
        skip_review=True,  # Skip review for simpler test
    )

    events = []
    async for event in workflow.execute(inputs):
        events.append(event)

    # Verify: Workflow completed despite implementation failure
    completed_events = [e for e in events if isinstance(e, FlyWorkflowCompleted)]
    assert len(completed_events) == 1

    # Verify: Implementation stage completed (even with failure)
    impl_completed = [
        e
        for e in events
        if isinstance(e, FlyStageCompleted) and e.stage == WorkflowStage.IMPLEMENTATION
    ]
    assert len(impl_completed) == 1

    # Verify: Validation stage still executed
    validation_started = [
        e
        for e in events
        if isinstance(e, FlyStageStarted) and e.stage == WorkflowStage.VALIDATION
    ]
    assert len(validation_started) == 1


# =============================================================================
# T065: Verify ValidationRunner failure triggers fixer agent behavior
# =============================================================================


@pytest.mark.asyncio
async def test_validation_failure_continues_workflow_with_draft_pr(
    tmp_path, mock_preflight
):
    """Test ValidationRunner failure results in draft PR but continues workflow.

    Verifies:
    - Validation failure is captured
    - Workflow continues to PR creation
    - PR is created as draft due to validation failure
    - Result indicates validation did not pass
    """
    # Setup: Create task file
    task_file = tmp_path / "tasks.md"
    task_file.write_text("- [ ] T001 Test task\n")

    # Setup: Create mocks with failing validation
    mock_git = create_mock_git_runner()
    mock_validation = create_mock_validation_runner(success=False)
    mock_github = create_mock_github_runner(create_pr_success=True)
    mock_implementer = create_mock_implementer_agent(success=True)
    mock_reviewer = create_mock_code_reviewer_agent()
    mock_commit_gen = create_mock_commit_generator()
    mock_pr_gen = create_mock_pr_generator()

    # Execute: Create and run workflow with max attempts = 1 (no retry)
    config = FlyConfig(max_validation_attempts=1)
    workflow = FlyWorkflow(
        config=config,
        git_runner=mock_git,
        validation_runner=mock_validation,
        github_runner=mock_github,
        implementer_agent=mock_implementer,
        code_reviewer_agent=mock_reviewer,
        commit_generator=mock_commit_gen,
        pr_generator=mock_pr_gen,
    )

    inputs = FlyInputs(
        branch_name="test-branch",
        task_file=task_file,
        skip_review=False,
        skip_pr=False,
        draft_pr=False,  # Explicitly set to False - should become True due to failure
    )

    events = []
    async for event in workflow.execute(inputs):
        events.append(event)

    # Verify: Workflow completed
    completed_events = [e for e in events if isinstance(e, FlyWorkflowCompleted)]
    assert len(completed_events) == 1
    result = completed_events[0].result

    # Verify: Validation failed
    assert result.state.validation_result is not None
    assert result.state.validation_result.success is False

    # Verify: PR was still created
    assert mock_github.create_pr.called

    # Verify: PR was created as draft (check call arguments)
    call_args = mock_github.create_pr.call_args
    assert call_args is not None
    assert call_args.kwargs.get("draft") is True

    # Verify: All stages executed despite validation failure
    stage_completed = [e for e in events if isinstance(e, FlyStageCompleted)]
    stage_names = {e.stage for e in stage_completed}
    assert WorkflowStage.VALIDATION in stage_names
    assert WorkflowStage.CODE_REVIEW in stage_names
    assert WorkflowStage.PR_CREATION in stage_names


@pytest.mark.asyncio
async def test_validation_failure_captured_in_final_result(tmp_path, mock_preflight):
    """Test validation failure is properly captured in final workflow result.

    Verifies:
    - Validation result is stored in state
    - Final success flag reflects validation failure
    - Error information is accessible
    """
    # Setup: Create task file
    task_file = tmp_path / "tasks.md"
    task_file.write_text("- [ ] T001 Test task\n")

    # Setup: Create mocks with failing validation
    mock_git = create_mock_git_runner()
    mock_validation = create_mock_validation_runner(success=False)
    mock_implementer = create_mock_implementer_agent(success=True)

    # Execute: Create and run workflow
    config = FlyConfig(max_validation_attempts=1)
    workflow = FlyWorkflow(
        config=config,
        git_runner=mock_git,
        validation_runner=mock_validation,
        implementer_agent=mock_implementer,
    )

    inputs = FlyInputs(
        branch_name="test-branch",
        task_file=task_file,
        skip_review=True,
        skip_pr=True,
    )

    events = []
    async for event in workflow.execute(inputs):
        events.append(event)

    # Verify: Final result
    completed_events = [e for e in events if isinstance(e, FlyWorkflowCompleted)]
    assert len(completed_events) == 1
    result = completed_events[0].result

    # Verify: Success is False due to validation failure
    assert result.success is False

    # Verify: Validation result details are accessible
    assert result.state.validation_result is not None
    assert result.state.validation_result.success is False
    assert len(result.state.validation_result.stage_results) > 0

    failed_stage = result.state.validation_result.stage_results[0]
    assert failed_stage.status == StageStatus.FAILED
    assert failed_stage.error_message == "Formatting failed"


# =============================================================================
# Additional Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_workflow_with_skip_review_flag(tmp_path, mock_preflight):
    """Test workflow correctly skips CODE_REVIEW stage when skip_review=True."""
    # Setup
    task_file = tmp_path / "tasks.md"
    task_file.write_text("- [ ] T001 Test task\n")

    mock_git = create_mock_git_runner()
    mock_validation = create_mock_validation_runner(success=True)
    mock_implementer = create_mock_implementer_agent(success=True)
    mock_reviewer = create_mock_code_reviewer_agent()

    # Execute
    workflow = FlyWorkflow(
        git_runner=mock_git,
        validation_runner=mock_validation,
        implementer_agent=mock_implementer,
        code_reviewer_agent=mock_reviewer,
    )

    inputs = FlyInputs(
        branch_name="test-branch",
        task_file=task_file,
        skip_review=True,
        skip_pr=True,
    )

    events = []
    async for event in workflow.execute(inputs):
        events.append(event)

    # Verify: CODE_REVIEW stage never started
    stage_started = [e for e in events if isinstance(e, FlyStageStarted)]
    review_stages = [e for e in stage_started if e.stage == WorkflowStage.CODE_REVIEW]
    assert len(review_stages) == 0

    # Verify: Reviewer agent never called
    assert not mock_reviewer.execute.called


@pytest.mark.asyncio
async def test_workflow_with_skip_pr_flag(tmp_path, mock_preflight):
    """Test workflow correctly skips PR_CREATION stage when skip_pr=True."""
    # Setup
    task_file = tmp_path / "tasks.md"
    task_file.write_text("- [ ] T001 Test task\n")

    mock_git = create_mock_git_runner()
    mock_validation = create_mock_validation_runner(success=True)
    mock_implementer = create_mock_implementer_agent(success=True)
    mock_github = create_mock_github_runner()

    # Execute
    workflow = FlyWorkflow(
        git_runner=mock_git,
        validation_runner=mock_validation,
        implementer_agent=mock_implementer,
        github_runner=mock_github,
    )

    inputs = FlyInputs(
        branch_name="test-branch",
        task_file=task_file,
        skip_review=True,
        skip_pr=True,
    )

    events = []
    async for event in workflow.execute(inputs):
        events.append(event)

    # Verify: PR_CREATION stage never started
    stage_started = [e for e in events if isinstance(e, FlyStageStarted)]
    pr_stages = [e for e in stage_started if e.stage == WorkflowStage.PR_CREATION]
    assert len(pr_stages) == 0

    # Verify: GitHub runner never called
    assert not mock_github.create_pr.called

    # Verify: Workflow still completed successfully
    completed_events = [e for e in events if isinstance(e, FlyWorkflowCompleted)]
    assert len(completed_events) == 1


# =============================================================================
# T045: Preflight Failure Scenarios
# =============================================================================


class TestFlyWorkflowPreflightFailure:
    """Tests for FlyWorkflow preflight validation failure scenarios.

    Verifies that preflight validation:
    - Raises PreflightValidationError on failure
    - Runs before any state changes
    - Runs even in dry_run mode
    """

    @pytest.mark.asyncio
    async def test_fly_workflow_fails_on_preflight_failure(self, tmp_path):
        """Test FlyWorkflow raises PreflightValidationError on preflight failure."""
        from maverick.runners.preflight import ValidationResult

        # Setup: Create task file
        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test task\n")

        # Create workflow with mock runners
        mock_git = create_mock_git_runner()
        mock_validation = create_mock_validation_runner(success=True)
        mock_implementer = create_mock_implementer_agent(success=True)

        workflow = FlyWorkflow(
            git_runner=mock_git,
            validation_runner=mock_validation,
            implementer_agent=mock_implementer,
        )

        inputs = FlyInputs(
            branch_name="test-branch",
            task_file=task_file,
            skip_review=True,
            skip_pr=True,
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
            # Execute and verify workflow fails with preflight error
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Verify: Workflow emitted a FlyWorkflowFailed event
            failed_events = [e for e in events if isinstance(e, FlyWorkflowFailed)]
            assert len(failed_events) == 1
            assert "Preflight validation failed" in failed_events[0].error

            # Verify: No other stages executed (no FlyStageStarted events)
            stage_started = [e for e in events if isinstance(e, FlyStageStarted)]
            assert len(stage_started) == 0

            # Verify: Git runner was never called (no state changes)
            assert not mock_git.create_branch_with_fallback.called
            assert not mock_git.create_branch.called

    @pytest.mark.asyncio
    async def test_fly_workflow_preflight_runs_before_execute(self, tmp_path):
        """Verify preflight is called before any state changes."""
        from maverick.runners.preflight import ValidationResult

        # Setup: Create task file
        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test task\n")

        # Create workflow with mock runners
        mock_git = create_mock_git_runner()
        mock_validation = create_mock_validation_runner(success=True)
        mock_implementer = create_mock_implementer_agent(success=True)

        workflow = FlyWorkflow(
            git_runner=mock_git,
            validation_runner=mock_validation,
            implementer_agent=mock_implementer,
        )

        inputs = FlyInputs(
            branch_name="test-branch",
            task_file=task_file,
            skip_review=True,
            skip_pr=True,
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

        # Wrap git runner to track when it's called
        original_create_branch = mock_git.create_branch_with_fallback

        async def tracked_create_branch(*args, **kwargs):
            call_order.append("git_create_branch")
            return await original_create_branch(*args, **kwargs)

        mock_git.create_branch_with_fallback = AsyncMock(
            side_effect=tracked_create_branch
        )

        # Patch _discover_runners to return our tracking runner
        with patch.object(
            workflow, "_discover_runners", return_value=[tracking_runner]
        ):
            # Execute workflow
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Verify: Preflight validation was called before git operations
            assert len(call_order) >= 2
            assert call_order[0] == "preflight_validate"
            assert "git_create_branch" in call_order
            assert call_order.index("preflight_validate") < call_order.index(
                "git_create_branch"
            )

    @pytest.mark.asyncio
    async def test_fly_workflow_preflight_in_dry_run_mode(self, tmp_path):
        """Verify preflight still runs even in dry_run mode."""
        from maverick.runners.preflight import ValidationResult

        # Setup: Create task file
        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test task\n")

        # Create workflow with mock runners
        mock_git = create_mock_git_runner()
        mock_validation = create_mock_validation_runner(success=True)
        mock_implementer = create_mock_implementer_agent(success=True)

        workflow = FlyWorkflow(
            git_runner=mock_git,
            validation_runner=mock_validation,
            implementer_agent=mock_implementer,
        )

        # Enable dry_run mode
        inputs = FlyInputs(
            branch_name="test-branch",
            task_file=task_file,
            skip_review=True,
            skip_pr=True,
            dry_run=True,
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

            # Verify: Workflow started (preflight passed)
            started_events = [e for e in events if isinstance(e, FlyWorkflowStarted)]
            assert len(started_events) == 1
