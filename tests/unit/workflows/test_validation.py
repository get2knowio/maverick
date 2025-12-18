"""Unit tests for ValidationWorkflow.

Tests the ValidationWorkflow class which orchestrates validation stages with
auto-fix capabilities:
- T014: test_workflow_executes_stages_in_order - stages run in configured order
- T015: test_stage_passes_on_first_attempt - stage passes without fixes
- T016: test_fix_agent_invoked_when_fixable_stage_fails - fix agent called on failure
- T017: test_stage_retried_after_fix_attempt - stage retries after fix
- T018: test_stage_marked_fixed_when_passes_after_fix - stage marked as FIXED
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.models.validation import (
    StageStatus,
    ValidationStage,
    ValidationWorkflowConfig,
    ValidationWorkflowResult,
)
from maverick.workflows.validation import ValidationWorkflow

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_subprocess():
    """Mock subprocess execution factory.

    Returns:
        Callable that creates mock process with specified return code and output.
    """

    def create_mock_process(return_code: int, stdout: str = "", stderr: str = ""):
        """Create a mock subprocess with specified behavior.

        Args:
            return_code: Exit code for the process.
            stdout: Standard output content.
            stderr: Standard error content.

        Returns:
            Mock process with communicate() method (for use with AsyncMock side_effect).
        """
        process = AsyncMock()
        process.returncode = return_code
        process.communicate = AsyncMock(return_value=(stdout.encode(), stderr.encode()))
        return process

    return create_mock_process


@pytest.fixture
def mock_fix_agent():
    """Mock fix agent for testing.

    Returns:
        Mock agent with async execute method.
    """
    agent = MagicMock()
    # The fix agent's execute method should be async and return None
    agent.execute = AsyncMock(return_value=None)
    return agent


@pytest.fixture
def simple_stages() -> list[ValidationStage]:
    """Create simple test stages for basic testing.

    Returns:
        List of three stages with distinct names.
    """
    return [
        ValidationStage(
            name="s1",
            command=["echo", "stage1"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="s2",
            command=["echo", "stage2"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="s3",
            command=["echo", "stage3"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]


@pytest.fixture
def fixable_stage() -> ValidationStage:
    """Create a fixable stage for testing fix agent integration.

    Returns:
        ValidationStage configured as fixable with 3 max attempts.
    """
    return ValidationStage(
        name="lint",
        command=["ruff", "check", "."],
        fixable=True,
        max_fix_attempts=3,
        timeout_seconds=60.0,
    )


# =============================================================================
# Test Cases
# =============================================================================


@pytest.mark.asyncio
async def test_workflow_executes_stages_in_order(
    simple_stages: list[ValidationStage], mock_subprocess
):
    """T014: Unit test that workflow executes stages in configured order.

    Verifies that:
    1. Stages are executed in the order they are configured
    2. Progress updates are yielded for each stage
    3. All stages complete successfully

    Args:
        simple_stages: List of three test stages (s1, s2, s3).
        mock_subprocess: Factory for creating mock subprocess.
    """
    # Arrange: Create workflow with three stages
    workflow = ValidationWorkflow(
        stages=simple_stages,
        fix_agent=None,
        config=ValidationWorkflowConfig(),
    )

    # Track execution order
    executed_stages = []

    # Mock subprocess to always succeed
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=0, stdout="success"
        )

        # Act: Run workflow and collect progress updates
        progress_updates = []
        async for update in workflow.run():
            progress_updates.append(update)
            if update.status == StageStatus.IN_PROGRESS:
                executed_stages.append(update.stage)

        # Assert: Verify stages executed in order
        assert executed_stages == ["s1", "s2", "s3"], (
            f"Stages should execute in order s1->s2->s3, got {executed_stages}"
        )

        # Verify we got progress updates for all stages
        stage_names = {update.stage for update in progress_updates}
        assert stage_names == {"s1", "s2", "s3"}, (
            f"Should have progress updates for all stages, got {stage_names}"
        )

        # Verify workflow completed successfully
        result = workflow.get_result()
        assert result.success is True
        # Should have results for all 3 configured stages
        assert len(result.stage_results) == 3
        assert all(r.status == StageStatus.PASSED for r in result.stage_results)


@pytest.mark.asyncio
async def test_stage_passes_on_first_attempt(
    fixable_stage: ValidationStage, mock_subprocess
):
    """T015: Unit test that stage passes on first attempt.

    Verifies that:
    1. Stage passes when command succeeds first time
    2. Status is PASSED (not FIXED)
    3. fix_attempts is 0
    4. Fix agent is not invoked

    Args:
        fixable_stage: A stage configured as fixable.
        mock_subprocess: Factory for creating mock subprocess.
    """
    # Arrange: Create workflow with single fixable stage and mock fix agent
    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(return_value=None)

    workflow = ValidationWorkflow(
        stages=[fixable_stage],
        fix_agent=mock_agent,
        config=ValidationWorkflowConfig(),
    )

    # Mock subprocess to succeed immediately
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=0, stdout="All checks passed"
        )

        # Act: Run workflow
        progress_updates = []
        async for update in workflow.run():
            progress_updates.append(update)

        # Assert: Verify stage passed on first attempt
        result = workflow.get_result()
        assert result.success is True
        # Should have result for the single stage
        assert len(result.stage_results) == 1

        stage_result = result.stage_results[0]
        assert stage_result.stage_name == "lint"
        assert stage_result.status == StageStatus.PASSED, (
            "Status should be PASSED when succeeds on first attempt"
        )
        # fix_attempts should be 0 when no fixes were needed
        assert stage_result.fix_attempts == 0, (
            "fix_attempts should be 0 when passes first time"
        )
        assert stage_result.passed is True

        # Verify fix agent was never called
        mock_agent.execute.assert_not_called()


@pytest.mark.asyncio
async def test_fix_agent_invoked_when_fixable_stage_fails(
    fixable_stage: ValidationStage, mock_subprocess, mock_fix_agent
):
    """T016: Unit test that fix agent invoked when fixable stage fails.

    Verifies that:
    1. Fix agent's execute method is called when fixable stage fails
    2. Fix agent is only called for fixable stages
    3. Fix agent is not called if stage passes first time

    Args:
        fixable_stage: A stage configured as fixable.
        mock_subprocess: Factory for creating mock subprocess.
        mock_fix_agent: Mock fix agent with execute method.
    """
    # Arrange: Create workflow with fixable stage
    workflow = ValidationWorkflow(
        stages=[fixable_stage],
        fix_agent=mock_fix_agent,
        config=ValidationWorkflowConfig(),
    )

    # Mock subprocess to fail first time
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=1, stderr="Linting errors found"
        )

        # Act: Run workflow (will fail after exhausting fix attempts)
        async for _ in workflow.run():
            pass

        # Assert: Verify fix agent was invoked
        assert mock_fix_agent.execute.called, (
            "Fix agent should be invoked when fixable stage fails"
        )
        assert mock_fix_agent.execute.call_count >= 1, (
            "Fix agent should be called at least once"
        )


@pytest.mark.asyncio
async def test_stage_retried_after_fix_attempt(
    fixable_stage: ValidationStage, mock_subprocess, mock_fix_agent
):
    """T017: Unit test that stage retried after fix attempt.

    Verifies that:
    1. Stage command is executed again after fix attempt
    2. Subprocess is called twice: original + retry after fix
    3. Workflow succeeds when retry passes

    Args:
        fixable_stage: A stage configured as fixable.
        mock_subprocess: Factory for creating mock subprocess.
        mock_fix_agent: Mock fix agent with execute method.
    """
    # Arrange: Create workflow with fixable stage
    workflow = ValidationWorkflow(
        stages=[fixable_stage],
        fix_agent=mock_fix_agent,
        config=ValidationWorkflowConfig(),
    )

    # Track subprocess calls
    call_count = 0

    def subprocess_side_effect(*args, **kwargs):
        """Mock subprocess that fails first time, succeeds second time."""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: fail
            return mock_subprocess(return_code=1, stderr="Error")
        else:
            # Subsequent calls: succeed
            return mock_subprocess(return_code=0, stdout="Fixed")

    # Mock subprocess to fail first time, succeed second time
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = subprocess_side_effect

        # Act: Run workflow
        async for _ in workflow.run():
            pass

        # Assert: Verify subprocess was called twice (initial + retry after fix)
        assert call_count == 2, (
            f"Subprocess should be called twice (original + retry), "
            f"got {call_count} calls"
        )

        # Verify fix agent was called once (between the two validation attempts)
        assert mock_fix_agent.execute.call_count == 1, (
            "Fix agent should be called once between attempts"
        )

        # Verify workflow succeeded
        result = workflow.get_result()
        assert result.success is True


@pytest.mark.asyncio
async def test_stage_marked_fixed_when_passes_after_fix(
    fixable_stage: ValidationStage, mock_subprocess, mock_fix_agent
):
    """T018: Unit test that stage marked FIXED when passes after fix.

    Verifies that:
    1. Stage status is FIXED (not PASSED) when succeeds after fix
    2. fix_attempts reflects the number of fix attempts made
    3. Workflow overall success is True

    Args:
        fixable_stage: A stage configured as fixable.
        mock_subprocess: Factory for creating mock subprocess.
        mock_fix_agent: Mock fix agent with execute method.
    """
    # Arrange: Create workflow with fixable stage
    workflow = ValidationWorkflow(
        stages=[fixable_stage],
        fix_agent=mock_fix_agent,
        config=ValidationWorkflowConfig(),
    )

    # Track subprocess calls
    call_count = 0

    def subprocess_side_effect(*args, **kwargs):
        """Mock subprocess that fails first time, succeeds after fix."""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: fail
            return mock_subprocess(return_code=1, stderr="Linting errors found")
        else:
            # After fix: succeed
            return mock_subprocess(return_code=0, stdout="All checks passed")

    # Mock subprocess to fail first time, succeed second time
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = subprocess_side_effect

        # Act: Run workflow and get result
        async for _ in workflow.run():
            pass

        result = workflow.get_result()

        # Assert: Verify stage was marked as FIXED
        assert result.success is True, "Workflow should succeed after fix"
        # Should have result for the single stage
        assert len(result.stage_results) == 1

        stage_result = result.stage_results[0]
        assert stage_result.stage_name == "lint"
        assert stage_result.status == StageStatus.FIXED, (
            "Status should be FIXED when passes after fix attempt"
        )
        # Should have exactly 1 fix attempt recorded (failed once, then fixed)
        assert stage_result.fix_attempts == 1, (
            "fix_attempts should be 1 after one fix attempt"
        )
        assert stage_result.was_fixed is True
        assert stage_result.passed is True

        # Verify fix agent was called exactly once
        assert mock_fix_agent.execute.call_count == 1


@pytest.mark.asyncio
async def test_stage_fails_after_max_fix_attempts(
    fixable_stage: ValidationStage, mock_subprocess, mock_fix_agent
):
    """Test that stage fails after exhausting max_fix_attempts.

    Verifies that:
    1. Stage fails after max_fix_attempts is reached
    2. Fix agent is called max_fix_attempts times
    3. Status is FAILED

    Args:
        fixable_stage: A stage configured with max_fix_attempts=3.
        mock_subprocess: Factory for creating mock subprocess.
        mock_fix_agent: Mock fix agent with execute method.
    """
    # Arrange: Create workflow with fixable stage
    workflow = ValidationWorkflow(
        stages=[fixable_stage],
        fix_agent=mock_fix_agent,
        config=ValidationWorkflowConfig(),
    )

    # Mock subprocess to always fail
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=1, stderr="Persistent error"
        )

        # Act: Run workflow
        async for _ in workflow.run():
            pass

        # Assert: Verify stage failed after max attempts
        result = workflow.get_result()
        assert result.success is False
        # Should have result for the single stage
        assert len(result.stage_results) == 1

        stage_result = result.stage_results[0]
        assert stage_result.status == StageStatus.FAILED
        assert stage_result.fix_attempts == fixable_stage.max_fix_attempts
        assert stage_result.passed is False

        # Verify fix agent was called max_fix_attempts times
        assert mock_fix_agent.execute.call_count == fixable_stage.max_fix_attempts


@pytest.mark.asyncio
async def test_non_fixable_stage_fails_without_fix_attempts(mock_subprocess):
    """Test that non-fixable stage fails immediately without fix attempts.

    Verifies that:
    1. Non-fixable stage does not invoke fix agent
    2. Status is FAILED after first failure
    3. fix_attempts remains 0
    """
    # Arrange: Create non-fixable stage
    stage = ValidationStage(
        name="test",
        command=["pytest"],
        fixable=False,
        max_fix_attempts=0,
        timeout_seconds=60.0,
    )

    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(return_value=None)

    workflow = ValidationWorkflow(
        stages=[stage],
        fix_agent=mock_agent,
        config=ValidationWorkflowConfig(),
    )

    # Mock subprocess to fail
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=1, stderr="Test failed"
        )

        # Act: Run workflow
        async for _ in workflow.run():
            pass

        # Assert: Verify stage failed without fix attempts
        result = workflow.get_result()
        assert result.success is False
        # Should have result for the single stage
        assert len(result.stage_results) == 1

        stage_result = result.stage_results[0]
        assert stage_result.status == StageStatus.FAILED
        # Should have 0 fix attempts since stage is not fixable
        assert stage_result.fix_attempts == 0
        assert stage_result.passed is False

        # Verify fix agent was never called
        mock_agent.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_result_raises_before_workflow_completes():
    """Test that get_result() raises RuntimeError before workflow completes.

    Verifies that:
    1. Calling get_result() before run() raises RuntimeError
    2. Error message is descriptive
    """
    # Arrange: Create workflow
    stage = ValidationStage(
        name="test",
        command=["echo", "hello"],
        fixable=False,
        max_fix_attempts=0,
    )
    workflow = ValidationWorkflow(stages=[stage])

    # Act & Assert: Verify error is raised
    with pytest.raises(RuntimeError, match="Workflow has not completed"):
        workflow.get_result()


@pytest.mark.asyncio
async def test_workflow_yields_progress_updates(
    simple_stages: list[ValidationStage], mock_subprocess
):
    """Test that workflow yields progress updates during execution.

    Verifies that:
    1. Progress updates are yielded for each stage
    2. Updates include IN_PROGRESS and completion statuses
    3. Update messages are descriptive
    """
    # Arrange: Create workflow
    workflow = ValidationWorkflow(
        stages=simple_stages,
        config=ValidationWorkflowConfig(),
    )

    # Mock subprocess to succeed
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=0, stdout="success"
        )

        # Act: Collect all progress updates
        updates = []
        async for update in workflow.run():
            updates.append(update)

        # Assert: Verify we got updates for all stages
        assert len(updates) > 0, "Should yield progress updates"

        # Verify each stage has at least one update
        stages_with_updates = {update.stage for update in updates}
        assert stages_with_updates == {"s1", "s2", "s3"}

        # Verify we have IN_PROGRESS updates
        in_progress_updates = [
            u for u in updates if u.status == StageStatus.IN_PROGRESS
        ]
        assert len(in_progress_updates) >= 3, (
            "Should have at least one IN_PROGRESS update per stage"
        )


@pytest.mark.asyncio
async def test_workflow_config_stop_on_failure(mock_subprocess):
    """Test that workflow stops on first failure when stop_on_failure=True.

    Verifies that:
    1. Workflow stops after first stage failure
    2. Subsequent stages are not executed
    3. Result reflects only executed stages
    """
    # Arrange: Create stages where first one fails
    stages = [
        ValidationStage(name="fail", command=["false"], fixable=False),
        ValidationStage(name="pass", command=["true"], fixable=False),
    ]

    workflow = ValidationWorkflow(
        stages=stages,
        config=ValidationWorkflowConfig(stop_on_failure=True),
    )

    # Track which stages were attempted
    attempted_stages = []

    def track_subprocess(*args, **kwargs):
        """Track subprocess calls and fail first stage."""
        cmd = args[0] if args else "unknown"
        attempted_stages.append(cmd)
        if cmd == "false":
            return mock_subprocess(return_code=1, stderr="Failed")
        return mock_subprocess(return_code=0, stdout="Success")

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = track_subprocess

        # Act: Run workflow
        async for _ in workflow.run():
            pass

        # Assert: Verify only first stage was attempted
        assert "false" in attempted_stages
        assert "true" not in attempted_stages, (
            "Second stage should not execute when stop_on_failure=True"
        )

        result = workflow.get_result()
        assert result.success is False
        # Should have 1 failed stage (the first one that failed and stopped execution)
        assert result.failed_count == 1


# =============================================================================
# Failure Scenarios and Edge Cases (T019-T023a)
# =============================================================================


@pytest.mark.asyncio
async def test_stage_marked_failed_after_exhausting_fix_attempts(mock_subprocess):
    """T019: Unit test that stage marked FAILED after exhausting fix attempts.

    This test verifies that when a fixable stage fails repeatedly
    (initial run + all fix attempts), it is ultimately marked as FAILED
    with the correct fix_attempts count and error message.

    Scenario:
    - Create fixable stage with max_fix_attempts=2
    - Mock subprocess to always fail (exit code 1)
    - Create mock fix agent that "attempts" fixes
    - Run workflow
    - Verify stage status is FAILED
    - Verify fix_attempts equals max_fix_attempts (2)
    - Verify error_message is set
    """
    # Arrange: Create fixable stage with max_fix_attempts=2
    stage = ValidationStage(
        name="test-stage",
        command=["echo", "test"],
        fixable=True,
        max_fix_attempts=2,
        timeout_seconds=10.0,
    )

    # Create mock fix agent
    mock_fix_agent = MagicMock()
    mock_fix_agent.execute = AsyncMock(return_value=None)

    workflow = ValidationWorkflow(
        stages=[stage],
        fix_agent=mock_fix_agent,
    )

    # Mock subprocess to always fail
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=1, stderr="Command failed"
        )

        # Act: Run workflow
        async for _ in workflow.run():
            pass

        # Assert: Verify stage is marked as FAILED
        result = workflow.get_result()
        assert result.success is False
        # Should have result for the single stage
        assert len(result.stage_results) == 1

        stage_result = result.stage_results[0]
        assert stage_result.status == StageStatus.FAILED, (
            "Stage should be marked FAILED after exhausting fix attempts"
        )
        assert stage_result.stage_name == "test-stage"

        # Verify fix_attempts equals max_fix_attempts (2 in this test)
        assert stage_result.fix_attempts == stage.max_fix_attempts, (
            f"fix_attempts should equal max_fix_attempts ({stage.max_fix_attempts})"
        )
        assert stage_result.fix_attempts == 2

        # Verify error_message is set
        assert stage_result.error_message is not None, (
            "error_message should be set when stage fails"
        )
        assert len(stage_result.error_message) > 0

        # Verify fix agent was called the correct number of times (2 for this test)
        assert mock_fix_agent.execute.call_count == 2, (
            "Fix agent should be called max_fix_attempts times"
        )


@pytest.mark.asyncio
async def test_non_fixable_stage_not_retried_on_failure(mock_subprocess):
    """T020: Unit test that non-fixable stage not retried on failure.

    This test verifies that when a non-fixable stage fails
    (either fixable=False or max_fix_attempts=0), the workflow
    does not attempt any retries and immediately marks the stage as FAILED.

    Scenario:
    - Create stage with fixable=False or max_fix_attempts=0
    - Mock subprocess to fail
    - Run workflow (no fix agent)
    - Verify subprocess was called only once (no retry)
    - Verify stage status is FAILED
    """
    # Arrange: Create non-fixable stage
    stage = ValidationStage(
        name="non-fixable-stage",
        command=["echo", "test"],
        fixable=False,
        max_fix_attempts=0,
        timeout_seconds=10.0,
    )

    workflow = ValidationWorkflow(
        stages=[stage],
        fix_agent=None,  # No fix agent
    )

    # Track subprocess calls
    call_count = 0

    def track_subprocess_calls(*args, **kwargs):
        """Track subprocess calls."""
        nonlocal call_count
        call_count += 1
        return mock_subprocess(return_code=1, stderr="Command failed")

    # Mock subprocess to fail
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = track_subprocess_calls

        # Act: Run workflow
        async for _ in workflow.run():
            pass

        # Assert: Verify subprocess was called only once (initial attempt, no retry)
        assert call_count == 1, (
            "Subprocess should be called only once for non-fixable stage"
        )

        # Verify stage is FAILED
        result = workflow.get_result()
        # Should have result for the single stage
        assert len(result.stage_results) == 1
        stage_result = result.stage_results[0]
        assert stage_result.status == StageStatus.FAILED

        # Verify no fix attempts were made (0 since stage is not fixable)
        assert stage_result.fix_attempts == 0


@pytest.mark.asyncio
async def test_workflow_continues_to_next_stage_after_failure(mock_subprocess):
    """T021: Unit test that workflow continues to next stage after failure.

    This test verifies that when stop_on_failure=False (default),
    the workflow continues executing subsequent stages even after
    a stage failure.

    Scenario:
    - Create 3 stages, middle one will fail
    - Mock subprocess appropriately (pass, fail, pass)
    - Run workflow with stop_on_failure=False (default)
    - Verify all 3 stages were executed
    - Verify result shows 2 passed, 1 failed
    """
    # Arrange: Create three stages
    stage1 = ValidationStage(
        name="stage-1",
        command=["echo", "stage1"],
        fixable=False,
        max_fix_attempts=0,
        timeout_seconds=10.0,
    )
    stage2 = ValidationStage(
        name="stage-2",
        command=["echo", "stage2"],
        fixable=False,
        max_fix_attempts=0,
        timeout_seconds=10.0,
    )
    stage3 = ValidationStage(
        name="stage-3",
        command=["echo", "stage3"],
        fixable=False,
        max_fix_attempts=0,
        timeout_seconds=10.0,
    )

    workflow = ValidationWorkflow(
        stages=[stage1, stage2, stage3],
        fix_agent=None,
        config=ValidationWorkflowConfig(stop_on_failure=False),
    )

    # Track execution order
    execution_order = []

    def track_subprocess(*args, **kwargs):
        """Track subprocess calls and fail middle stage."""
        # Determine which stage based on command
        if "stage1" in args:
            execution_order.append("stage-1")
            return mock_subprocess(return_code=0, stdout="Success")
        elif "stage2" in args:
            execution_order.append("stage-2")
            return mock_subprocess(return_code=1, stderr="Stage 2 failed")
        elif "stage3" in args:
            execution_order.append("stage-3")
            return mock_subprocess(return_code=0, stdout="Success")
        else:
            return mock_subprocess(return_code=0)

    # Mock subprocess
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = track_subprocess

        # Act: Run workflow
        async for _ in workflow.run():
            pass

        # Assert: Verify all 3 stages were executed in order
        assert execution_order == ["stage-1", "stage-2", "stage-3"], (
            "All stages should execute even when one fails"
        )

        # Get result
        result = workflow.get_result()

        # Verify we have results for all 3 stages (executed despite middle failure)
        assert len(result.stage_results) == 3

        # Verify 2 passed, 1 failed (stages 1 and 3 passed, stage 2 failed)
        assert result.passed_count == 2, "Should have 2 passed stages"
        assert result.failed_count == 1, "Should have 1 failed stage"

        # Verify overall success is False (because one stage failed)
        assert result.success is False

        # Verify specific stage statuses
        assert result.stage_results[0].status == StageStatus.PASSED
        assert result.stage_results[1].status == StageStatus.FAILED
        assert result.stage_results[2].status == StageStatus.PASSED


@pytest.mark.asyncio
async def test_workflow_reports_overall_success_when_all_stages_pass(mock_subprocess):
    """T022: Unit test that workflow reports overall success when all stages pass.

    This test verifies that when all stages complete successfully,
    the workflow result has success=True and all stage_results
    show PASSED status.

    Scenario:
    - Create 3 stages that all pass
    - Mock subprocess to return success for all
    - Run workflow
    - Verify result.success is True
    - Verify all stage_results have status PASSED
    """
    # Arrange: Create three passing stages
    stages = [
        ValidationStage(
            name=f"stage-{i}",
            command=["echo", f"stage{i}"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        )
        for i in range(1, 4)
    ]

    workflow = ValidationWorkflow(
        stages=stages,
        fix_agent=None,
    )

    # Mock subprocess to always succeed
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=0, stdout="success"
        )

        # Act: Run workflow
        async for _ in workflow.run():
            pass

        # Assert: Verify overall success
        result = workflow.get_result()
        assert result.success is True, "Workflow should succeed when all stages pass"

        # Verify all stages passed (all 3 stages executed successfully)
        assert len(result.stage_results) == 3
        assert result.passed_count == 3, "All 3 stages should pass"
        assert result.failed_count == 0, "No stages should fail"

        # Verify each stage has PASSED status
        for i, stage_result in enumerate(result.stage_results):
            assert stage_result.status == StageStatus.PASSED, (
                f"Stage {i + 1} should have PASSED status"
            )
            assert stage_result.passed is True


@pytest.mark.asyncio
async def test_command_not_found_fails_stage_immediately(mock_subprocess):
    """T023: Unit test that command not found fails stage immediately.

    This test verifies that when a command does not exist
    (FileNotFoundError), the stage is immediately marked as FAILED
    and no fix agent is invoked (command errors are not fixable).

    Scenario:
    - Create stage with command that doesn't exist
    - Run workflow (mock subprocess.create to raise FileNotFoundError)
    - Verify stage is marked FAILED
    - Verify no fix agent was called
    - Verify error_message mentions command not found
    """
    # Arrange: Create stage with non-existent command
    stage = ValidationStage(
        name="bad-command-stage",
        command=["nonexistent_cmd_xyz", "--flag"],
        fixable=True,  # Even though fixable=True, command errors shouldn't be retried
        max_fix_attempts=3,
        timeout_seconds=10.0,
    )

    # Mock fix agent to track if it's called
    mock_fix_agent = MagicMock()
    mock_fix_agent.execute = AsyncMock(return_value=None)

    workflow = ValidationWorkflow(
        stages=[stage],
        fix_agent=mock_fix_agent,
    )

    # Mock subprocess to raise FileNotFoundError
    async def raise_file_not_found(*args, **kwargs):
        """Simulate command not found."""
        raise FileNotFoundError("Command not found: nonexistent_cmd_xyz")

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = raise_file_not_found

        # Act: Run workflow
        async for _ in workflow.run():
            pass

        # Assert: Verify stage is FAILED
        result = workflow.get_result()
        # Should have result for the single stage
        assert len(result.stage_results) == 1
        stage_result = result.stage_results[0]
        assert stage_result.status == StageStatus.FAILED

        # Verify fix agent was NOT called (command errors are not fixable)
        mock_fix_agent.execute.assert_not_called()

        # Verify error message mentions command not found
        assert stage_result.error_message is not None
        error_msg_lower = stage_result.error_message.lower()
        assert "not found" in error_msg_lower or "nonexistent" in error_msg_lower, (
            f"error_message should mention not found: {stage_result.error_message}"
        )


# =============================================================================
# User Story 3: Configure Validation Stages (T039-T042)
# =============================================================================


@pytest.mark.asyncio
async def test_custom_commands_used_instead_of_defaults(mock_subprocess):
    """T039: Unit test that custom commands are used instead of defaults.

    This test verifies that when custom ValidationStage configurations
    are provided, the workflow executes the specified commands rather
    than any defaults.

    Scenario:
    - Create stages with custom commands (not from DEFAULT_PYTHON_STAGES)
    - Track which commands are executed
    - Verify exact custom commands were called
    """
    # Arrange: Create stages with custom commands
    custom_stages = [
        ValidationStage(
            name="custom-check",
            command=["my-custom-tool", "--check", "src/"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=30.0,
        ),
        ValidationStage(
            name="custom-build",
            command=["my-build-tool", "compile", "--fast"],
            fixable=True,
            max_fix_attempts=2,
            timeout_seconds=120.0,
        ),
    ]

    workflow = ValidationWorkflow(
        stages=custom_stages,
        fix_agent=None,
    )

    # Track executed commands
    executed_commands = []

    def track_commands(*args, **kwargs):
        """Track executed commands."""
        # args[0] is the command, the rest are arguments
        if args:
            executed_commands.append(list(args))
        return mock_subprocess(return_code=0, stdout="Success")

    # Mock subprocess
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = track_commands

        # Act: Run workflow
        async for _ in workflow.run():
            pass

        # Assert: Verify custom commands were executed (both configured stages)
        assert len(executed_commands) == 2, (
            f"Should execute 2 custom commands, got {len(executed_commands)}"
        )

        # Verify first custom command
        assert executed_commands[0] == ["my-custom-tool", "--check", "src/"], (
            f"First command should be custom check, got {executed_commands[0]}"
        )

        # Verify second custom command
        assert executed_commands[1] == ["my-build-tool", "compile", "--fast"], (
            f"Second command should be custom build, got {executed_commands[1]}"
        )

        # Verify workflow succeeded
        result = workflow.get_result()
        assert result.success is True


@pytest.mark.asyncio
async def test_command_timeout_fails_stage_immediately():
    """T023a: Unit test that command timeout fails stage immediately.

    This test verifies that when a command times out
    (asyncio.TimeoutError), the stage is marked as FAILED
    with an appropriate error message.

    Scenario:
    - Create stage with short timeout (e.g., 0.1 seconds)
    - Mock subprocess to hang/timeout (raise asyncio.TimeoutError)
    - Run workflow
    - Verify stage is marked FAILED
    - Verify error_message mentions timeout
    """
    # Arrange: Create stage with very short timeout
    stage = ValidationStage(
        name="timeout-stage",
        command=["sleep", "10"],  # Would take 10 seconds
        fixable=False,
        max_fix_attempts=0,
        timeout_seconds=0.1,  # But timeout is 0.1 seconds
    )

    workflow = ValidationWorkflow(
        stages=[stage],
        fix_agent=None,
    )

    # Mock subprocess.communicate to raise TimeoutError
    async def create_timeout_process(*args, **kwargs):
        """Create a process that times out."""
        mock_process = AsyncMock()

        async def mock_communicate():
            """Simulate timeout."""
            raise asyncio.TimeoutError("Command timed out")

        mock_process.communicate = mock_communicate
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()
        return mock_process

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = create_timeout_process

        # Act: Run workflow
        async for _ in workflow.run():
            pass

        # Assert: Verify stage is FAILED
        result = workflow.get_result()
        # Should have result for the single stage
        assert len(result.stage_results) == 1
        stage_result = result.stage_results[0]
        assert stage_result.status == StageStatus.FAILED

        # Verify error message mentions timeout
        assert stage_result.error_message is not None
        error_lower = stage_result.error_message.lower()
        assert "timeout" in error_lower or "timed out" in error_lower, (
            f"error_message should mention timeout, got: {stage_result.error_message}"
        )


# =============================================================================
# User Story 4: Dry-Run Mode (T048-T050)
# =============================================================================


@pytest.mark.asyncio
async def test_dry_run_mode_does_not_execute_commands(
    simple_stages: list[ValidationStage],
):
    """T048: Unit test that dry-run mode does not execute commands.

    Verifies that:
    1. When dry_run=True in config, no actual commands are executed
    2. Subprocess is never called
    3. Workflow completes successfully without running commands

    Args:
        simple_stages: List of three test stages (s1, s2, s3).
    """
    # Arrange: Create workflow with dry_run enabled
    workflow = ValidationWorkflow(
        stages=simple_stages,
        fix_agent=None,
        config=ValidationWorkflowConfig(dry_run=True),
    )

    # Track subprocess calls
    subprocess_called = False

    async def track_subprocess_calls(*args, **kwargs):
        """Track if subprocess is called."""
        nonlocal subprocess_called
        subprocess_called = True
        # Return a mock process (should never be called)
        process = AsyncMock()
        process.returncode = 0
        process.communicate = AsyncMock(return_value=(b"", b""))
        return process

    # Mock subprocess to track calls
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = track_subprocess_calls

        # Act: Run workflow in dry-run mode
        async for _ in workflow.run():
            pass

        # Assert: Verify subprocess was never called
        assert not subprocess_called, "Subprocess should not be called in dry-run mode"
        mock_exec.assert_not_called()

        # Verify workflow completed successfully
        result = workflow.get_result()
        assert result.success is True
        # Should have results for all 3 configured stages
        assert len(result.stage_results) == 3


@pytest.mark.asyncio
async def test_dry_run_reports_planned_commands_in_progress_updates(
    simple_stages: list[ValidationStage],
):
    """T049: Unit test that dry-run reports planned commands in progress updates.

    Verifies that:
    1. Progress updates are yielded for each stage in dry-run mode
    2. Updates indicate this is a dry-run
    3. Progress messages show the planned commands

    Args:
        simple_stages: List of three test stages (s1, s2, s3).
    """
    # Arrange: Create workflow with dry_run enabled
    workflow = ValidationWorkflow(
        stages=simple_stages,
        fix_agent=None,
        config=ValidationWorkflowConfig(dry_run=True),
    )

    # Act: Collect all progress updates
    progress_updates = []
    async for update in workflow.run():
        progress_updates.append(update)

    # Assert: Verify we got progress updates for all stages
    assert len(progress_updates) > 0, "Should yield progress updates in dry-run mode"

    # Verify each stage has at least one update
    stages_with_updates = {update.stage for update in progress_updates}
    assert stages_with_updates == {"s1", "s2", "s3"}, (
        "Should have progress updates for all stages in dry-run mode"
    )

    # Verify progress messages indicate dry-run mode
    messages = [update.message for update in progress_updates]
    dry_run_messages = [
        msg for msg in messages if "dry" in msg.lower() or "would" in msg.lower()
    ]
    assert len(dry_run_messages) > 0, "Progress messages should indicate dry-run mode"

    # Verify progress messages show the planned commands
    # At least one message should mention the command
    command_mentions = [msg for msg in messages if "echo" in msg.lower()]
    assert len(command_mentions) > 0, "Progress messages should show planned commands"


@pytest.mark.asyncio
async def test_dry_run_returns_success_result(simple_stages: list[ValidationStage]):
    """T050: Unit test that dry-run returns success result.

    Verifies that:
    1. Workflow result has success=True in dry-run mode
    2. All stages show PASSED status (simulated success)
    3. Metadata includes dry_run=True flag

    Args:
        simple_stages: List of three test stages (s1, s2, s3).
    """
    # Arrange: Create workflow with dry_run enabled
    workflow = ValidationWorkflow(
        stages=simple_stages,
        fix_agent=None,
        config=ValidationWorkflowConfig(dry_run=True),
    )

    # Act: Run workflow in dry-run mode
    async for _ in workflow.run():
        pass

    # Assert: Verify workflow succeeded
    result = workflow.get_result()
    assert result.success is True, "Dry-run should report success"

    # Verify all stages passed (simulated) - all 3 configured stages
    assert len(result.stage_results) == 3
    assert result.passed_count == 3, "All stages should pass in dry-run mode"
    assert result.failed_count == 0, "No stages should fail in dry-run mode"

    # Verify each stage has PASSED status
    for stage_result in result.stage_results:
        assert stage_result.status == StageStatus.PASSED, (
            f"Stage {stage_result.stage_name} should have PASSED status in dry-run mode"
        )
        assert stage_result.passed is True

    # Verify metadata includes dry_run flag
    assert "dry_run" in result.metadata, "Result metadata should include 'dry_run' flag"
    assert result.metadata["dry_run"] is True, (
        "Result metadata should indicate dry_run=True"
    )


# =============================================================================
# User Story 2: Progress Update Tests (T031-T034)
# =============================================================================


@pytest.mark.asyncio
async def test_progress_update_emitted_when_stage_begins(
    simple_stages: list[ValidationStage], mock_subprocess
):
    """T031: Unit test that progress update emitted when stage begins.

    Verifies that:
    1. ProgressUpdate with status=IN_PROGRESS is yielded when stage starts
    2. Update is emitted before any command execution
    3. Update includes correct stage name

    Args:
        simple_stages: List of test stages.
        mock_subprocess: Factory for creating mock subprocess.
    """
    # Arrange: Create workflow with single stage
    workflow = ValidationWorkflow(
        stages=[simple_stages[0]],  # Just use first stage
        config=ValidationWorkflowConfig(),
    )

    # Mock subprocess to succeed
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=0, stdout="success"
        )

        # Act: Run workflow and collect updates
        updates = []
        async for update in workflow.run():
            updates.append(update)

        # Assert: Verify IN_PROGRESS update was emitted first
        assert len(updates) >= 2, "Should have IN_PROGRESS and completion updates"

        first_update = updates[0]
        assert first_update.status == StageStatus.IN_PROGRESS, (
            "First update should have IN_PROGRESS status"
        )
        assert first_update.stage == "s1", "First update should have correct stage name"


@pytest.mark.asyncio
async def test_progress_update_includes_fix_attempt_number(
    fixable_stage: ValidationStage, mock_subprocess, mock_fix_agent
):
    """T032: Unit test that progress update includes fix attempt number.

    Verifies that:
    1. ProgressUpdate includes fix_attempt=0 for initial run
    2. ProgressUpdate includes fix_attempt=1,2,... for fix cycles
    3. fix_attempt increments correctly with each attempt

    Args:
        fixable_stage: A fixable stage with max_fix_attempts=3.
        mock_subprocess: Factory for creating mock subprocess.
        mock_fix_agent: Mock fix agent.
    """
    # Arrange: Create workflow with fixable stage
    workflow = ValidationWorkflow(
        stages=[fixable_stage],
        fix_agent=mock_fix_agent,
        config=ValidationWorkflowConfig(),
    )

    # Track subprocess calls
    call_count = 0

    def subprocess_side_effect(*args, **kwargs):
        """Mock subprocess that fails twice, then succeeds."""
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            # First two calls: fail
            return mock_subprocess(return_code=1, stderr="Error")
        else:
            # Third call: succeed
            return mock_subprocess(return_code=0, stdout="Fixed")

    # Mock subprocess
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = subprocess_side_effect

        # Act: Collect all progress updates
        updates = []
        async for update in workflow.run():
            updates.append(update)

        # Assert: Verify fix_attempt numbers are correct
        # Should have: initial (0), fix attempt 1, fix attempt 2, final (2)
        fix_attempts = [u.fix_attempt for u in updates]

        # Verify we have initial attempt with fix_attempt=0
        assert 0 in fix_attempts, "Should have initial run with fix_attempt=0"

        # Verify we have fix attempts with fix_attempt >= 1
        assert any(fa >= 1 for fa in fix_attempts), (
            "Should have progress updates with fix_attempt >= 1"
        )

        # Verify final update has correct fix_attempt count (2 attempts made)
        final_update = updates[-1]
        assert final_update.fix_attempt == 2, (
            f"Final update should show 2 fix attempts, got {final_update.fix_attempt}"
        )


@pytest.mark.asyncio
async def test_progress_update_emitted_on_stage_completion(
    simple_stages: list[ValidationStage], mock_subprocess
):
    """T033: Unit test that progress update emitted on stage completion.

    Verifies that:
    1. ProgressUpdate with final status is yielded when stage completes
    2. Final status is PASSED, FAILED, or FIXED as appropriate
    3. Update is emitted after command execution finishes

    Args:
        simple_stages: List of test stages.
        mock_subprocess: Factory for creating mock subprocess.
    """
    # Arrange: Create workflow with single passing stage
    workflow = ValidationWorkflow(
        stages=[simple_stages[0]],
        config=ValidationWorkflowConfig(),
    )

    # Mock subprocess to succeed
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=0, stdout="success"
        )

        # Act: Collect all progress updates
        updates = []
        async for update in workflow.run():
            updates.append(update)

        # Assert: Verify final update has completion status
        assert len(updates) >= 2, "Should have at least start and completion updates"

        final_update = updates[-1]
        assert final_update.status in (
            StageStatus.PASSED,
            StageStatus.FAILED,
            StageStatus.FIXED,
        ), f"Final update should have completion status, got {final_update.status}"

        # For a passing stage, should be PASSED
        assert final_update.status == StageStatus.PASSED, (
            "Final status should be PASSED for successful stage"
        )


@pytest.mark.asyncio
async def test_timestamp_included_in_progress_updates(
    simple_stages: list[ValidationStage], mock_subprocess
):
    """T034: Unit test that timestamp included in progress updates.

    Verifies that:
    1. Each ProgressUpdate has a timestamp field
    2. Timestamp is a valid Unix timestamp (float)
    3. Timestamps increase monotonically for sequential updates
    4. Timestamps are reasonably recent (within last few seconds)

    Args:
        simple_stages: List of test stages.
        mock_subprocess: Factory for creating mock subprocess.
    """
    import time

    # Arrange: Create workflow
    workflow = ValidationWorkflow(
        stages=[simple_stages[0]],
        config=ValidationWorkflowConfig(),
    )

    # Get current time before workflow starts
    start_time = time.time()

    # Mock subprocess to succeed
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=0, stdout="success"
        )

        # Act: Collect all progress updates
        updates = []
        async for update in workflow.run():
            updates.append(update)

        # Get time after workflow completes
        end_time = time.time()

        # Assert: Verify timestamps are present and valid
        assert len(updates) > 0, "Should have progress updates"

        for update in updates:
            # Check timestamp exists and is a float
            assert hasattr(update, "timestamp"), "Update should have timestamp field"
            assert isinstance(update.timestamp, float), (
                f"Timestamp should be float, got {type(update.timestamp)}"
            )

            # Check timestamp is reasonable (between start and end of test)
            assert start_time <= update.timestamp <= end_time, (
                f"Timestamp {update.timestamp} should be between "
                f"{start_time} and {end_time}"
            )

        # Verify timestamps increase monotonically
        timestamps = [u.timestamp for u in updates]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1], (
                f"Timestamps should increase monotonically, but "
                f"timestamp[{i}]={timestamps[i]} < "
                f"timestamp[{i - 1}]={timestamps[i - 1]}"
            )


# =============================================================================
# Cancellation Tests (T054-T058) - User Story 5
# =============================================================================


@pytest.mark.asyncio
async def test_cancel_sets_cancellation_flag(simple_stages: list[ValidationStage]):
    """T054: Unit test that cancel() sets cancellation flag.

    This test verifies that calling cancel() on a workflow sets the
    internal cancellation event, which can be checked to determine if
    cancellation has been requested.

    Scenario:
    - Create workflow
    - Verify cancellation not set initially
    - Call cancel()
    - Verify cancellation flag is now set
    """
    # Arrange: Create workflow
    workflow = ValidationWorkflow(
        stages=simple_stages,
        fix_agent=None,
    )

    # Verify cancellation not set initially
    assert not workflow._cancel_event.is_set(), (
        "Cancellation event should not be set initially"
    )

    # Act: Request cancellation
    workflow.cancel()

    # Assert: Verify cancellation flag is set
    assert workflow._cancel_event.is_set(), (
        "Cancellation event should be set after calling cancel()"
    )


@pytest.mark.asyncio
async def test_workflow_stops_at_earliest_safe_point_after_cancel(
    simple_stages: list[ValidationStage], mock_subprocess
):
    """T055: Unit test that workflow stops at earliest safe point after cancel.

    This test verifies that when cancel() is called during workflow execution,
    the workflow stops between stages at the earliest safe point (does not
    interrupt a running stage command).

    Scenario:
    - Create workflow with 3 stages
    - Start workflow execution
    - After first stage completes, request cancellation
    - Verify workflow stops before third stage
    - Verify partial results include first stage only
    """
    # Arrange: Create workflow with 3 stages
    workflow = ValidationWorkflow(
        stages=simple_stages,
        fix_agent=None,
    )

    executed_stages = []

    def track_and_succeed(*args, **kwargs):
        """Track which stages executed and succeed."""
        # Extract stage name from command
        if len(args) > 1:
            stage_id = args[1]  # "stage1", "stage2", "stage3"
            executed_stages.append(stage_id)
        return mock_subprocess(return_code=0, stdout="success")

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = track_and_succeed

        # Act: Run workflow and cancel after first stage
        async for update in workflow.run():
            # Cancel after first stage completes
            if update.status == StageStatus.PASSED and update.stage == "s1":
                workflow.cancel()

        # Assert: Verify workflow stopped early (only 1 stage executed)
        assert len(executed_stages) == 1, (
            f"Should execute only first stage before cancelling, got {executed_stages}"
        )
        assert executed_stages == ["stage1"]

        # Verify result shows cancellation
        result = workflow.get_result()
        assert result.cancelled is True, "Result should indicate cancellation"

        # Verify we have results for all 3 stages (1 passed, 2 cancelled)
        assert len(result.stage_results) == 3, (
            "Should have results for all stages (completed + cancelled)"
        )

        # Verify first stage passed, remaining are cancelled
        assert result.stage_results[0].status == StageStatus.PASSED
        assert result.stage_results[1].status == StageStatus.CANCELLED
        assert result.stage_results[2].status == StageStatus.CANCELLED


@pytest.mark.asyncio
async def test_partial_results_available_after_cancellation(
    simple_stages: list[ValidationStage], mock_subprocess
):
    """T056: Unit test that partial results available after cancellation.

    This test verifies that after cancellation, get_result() returns
    a valid ValidationWorkflowResult containing results for completed
    stages and showing cancelled=True.

    Scenario:
    - Create workflow with 3 stages
    - Start execution and cancel after first stage
    - Verify get_result() returns valid result
    - Verify result.cancelled is True
    - Verify result contains completed stage results
    """
    # Arrange: Create workflow
    workflow = ValidationWorkflow(
        stages=simple_stages,
        fix_agent=None,
    )

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=0, stdout="success"
        )

        # Act: Run workflow and cancel after first update
        updates_count = 0
        async for _update in workflow.run():
            updates_count += 1
            if updates_count == 2:  # After first stage completes
                workflow.cancel()

        # Assert: Verify partial results available
        result = workflow.get_result()
        assert result is not None, "Should have result after cancellation"
        assert isinstance(result, ValidationWorkflowResult)
        assert result.cancelled is True, "Result should indicate cancellation"

        # Verify we have some completed stages
        assert len(result.stage_results) > 0, "Should have at least one stage result"

        # Verify result has sensible values
        assert result.total_duration_ms >= 0


@pytest.mark.asyncio
async def test_remaining_stages_marked_cancelled(
    simple_stages: list[ValidationStage], mock_subprocess
):
    """T057: Unit test that remaining stages marked CANCELLED.

    This test verifies that when workflow is cancelled, all stages that
    have not yet started execution are marked with status CANCELLED in
    the final result.

    Scenario:
    - Create workflow with 3 stages
    - Cancel after first stage completes
    - Verify stages 2 and 3 have status CANCELLED
    - Verify CANCELLED stages have appropriate error message
    """
    # Arrange: Create workflow with 3 stages
    workflow = ValidationWorkflow(
        stages=simple_stages,
        fix_agent=None,
    )

    cancelled_updates = []

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=0, stdout="success"
        )

        # Act: Run and cancel after first stage
        async for update in workflow.run():
            if update.status == StageStatus.CANCELLED:
                cancelled_updates.append(update)
            if update.status == StageStatus.PASSED and update.stage == "s1":
                workflow.cancel()

        # Assert: Verify remaining stages marked CANCELLED
        result = workflow.get_result()
        # Should have results for all 3 stages (1 passed, 2 cancelled)
        assert len(result.stage_results) == 3

        # First stage should be PASSED
        assert result.stage_results[0].status == StageStatus.PASSED
        assert result.stage_results[0].stage_name == "s1"

        # Remaining stages should be CANCELLED
        for i in [1, 2]:
            stage_result = result.stage_results[i]
            assert stage_result.status == StageStatus.CANCELLED, (
                f"Stage {i + 1} should be CANCELLED"
            )
            assert stage_result.error_message is not None, (
                "CANCELLED stage should have error message"
            )
            assert "cancel" in stage_result.error_message.lower(), (
                "Error message should mention cancellation"
            )

        # Verify CANCELLED stages yielded progress updates (for 2 remaining stages)
        assert len(cancelled_updates) >= 2, (
            "Should yield CANCELLED updates for remaining stages"
        )


@pytest.mark.asyncio
async def test_cancellation_within_5_seconds():
    """T058: Unit test that cancellation completes within 5 seconds (SC-005).

    This test verifies the success criterion SC-005: workflow responds to
    cancellation within 5 seconds by stopping at the next safe point.

    Scenario:
    - Create workflow with stages that take time to execute
    - Start execution
    - Request cancellation
    - Measure time until workflow stops
    - Verify cancellation completes within 5 seconds
    """
    import time

    # Arrange: Create stages with realistic timeouts
    stages = [
        ValidationStage(
            name="slow-stage-1",
            command=["sleep", "0.5"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="slow-stage-2",
            command=["sleep", "0.5"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="slow-stage-3",
            command=["sleep", "0.5"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]

    workflow = ValidationWorkflow(
        stages=stages,
        fix_agent=None,
    )

    # Track when we request cancellation
    cancel_requested_at = None
    cancel_completed_at = None

    # Act: Run workflow and cancel after first stage
    async for update in workflow.run():
        if update.status == StageStatus.PASSED and update.stage == "slow-stage-1":
            # Request cancellation
            cancel_requested_at = time.time()
            workflow.cancel()

    cancel_completed_at = time.time()

    # Assert: Verify cancellation completed within 5 seconds
    if cancel_requested_at is not None:
        cancellation_duration = cancel_completed_at - cancel_requested_at
        assert cancellation_duration <= 5.0, (
            f"Cancellation should complete within 5 seconds (SC-005), "
            f"took {cancellation_duration:.2f}s"
        )

    # Verify workflow was cancelled
    result = workflow.get_result()
    assert result.cancelled is True


@pytest.mark.asyncio
async def test_cancellation_during_fix_attempts(mock_subprocess):
    """Test that cancellation works during fix attempt loop.

    This test verifies that cancellation is checked between fix attempts,
    not just between stages.

    Scenario:
    - Create fixable stage that will fail multiple times
    - Start execution
    - Cancel during fix attempts
    - Verify workflow stops gracefully
    """
    # Arrange: Create fixable stage with multiple attempts
    stage = ValidationStage(
        name="fixable-stage",
        command=["echo", "test"],
        fixable=True,
        max_fix_attempts=5,  # Many attempts
        timeout_seconds=10.0,
    )

    mock_fix_agent = MagicMock()
    mock_fix_agent.execute = AsyncMock(return_value=None)

    workflow = ValidationWorkflow(
        stages=[stage],
        fix_agent=mock_fix_agent,
    )

    # Mock subprocess to always fail
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = lambda *args, **kwargs: mock_subprocess(
            return_code=1, stderr="Error"
        )

        # Act: Run and cancel during fix attempts
        fix_attempt_count = 0
        async for update in workflow.run():
            if update.fix_attempt > 0:
                fix_attempt_count = update.fix_attempt
                # Cancel after first fix attempt
                if fix_attempt_count == 1:
                    workflow.cancel()

        # Assert: Verify workflow stopped early (didn't complete all 5 attempts)
        result = workflow.get_result()

        # Verify cancellation was detected and recorded
        assert result.cancelled is True, (
            "Result should indicate cancellation was detected"
        )

        # Verify workflow stopped early (should be less than max_fix_attempts=5)
        assert result.stage_results[0].fix_attempts < 5, (
            "Should not complete all fix attempts after cancellation"
        )
        # Should stop shortly after cancellation (at most 2 attempts)
        assert fix_attempt_count <= 2, (
            "Should stop fix attempts shortly after cancellation"
        )

        # Verify stage status reflects cancellation (could be CANCELLED or FAILED)
        stage_status = result.stage_results[0].status
        assert stage_status in (StageStatus.CANCELLED, StageStatus.FAILED), (
            f"Stage should be CANCELLED or FAILED after cancellation, "
            f"got {stage_status}"
        )
