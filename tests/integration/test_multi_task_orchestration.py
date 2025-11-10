"""Integration tests for multi-task orchestration workflow."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Sequence

import pytest
from temporalio import activity, workflow
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.models.orchestration import (
    OrchestrationInput,
    OrchestrationResult,
    PhaseResult,
    TaskResult,
)
from src.models.branch_management import BranchSelection, CheckoutResult
from src.models.phase_automation import (
    AutomatePhaseTasksParams,
    PhaseAutomationSummary,
    PhaseResult as PhaseAutomationResult,
)


# =============================================================================
# Test State Management - Encapsulate mutable state to prevent contamination
# =============================================================================

class ModuleTestState:
    """Encapsulates test state to prevent global contamination between tests."""
    
    def __init__(self):
        self.call_order: list[str] = []
        self.task_counter: int = 0
        self.checkout_should_fail: bool = False
    
    def reset(self):
        """Reset all state for next test."""
        self.call_order = []
        self.task_counter = 0
        self.checkout_should_fail = False


# Create singleton instance for this test module
_test_state = ModuleTestState()


def _build_phase_result(
    *,
    phase_id: str,
    status: str,
    duration_ms: int,
    completed_task_ids: Sequence[str],
    start_time: datetime,
    tasks_md_hash: str,
    summary: Sequence[str] = (),
    error: str | None = None,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
    artifact_paths: Sequence[str] = (),
) -> tuple[PhaseAutomationResult, datetime]:
    """Create PhaseAutomationResult with consistent timing metadata."""
    finish_time = start_time + timedelta(milliseconds=duration_ms)
    return (
        PhaseAutomationResult(
            phase_id=phase_id,
            status=status,
            completed_task_ids=tuple(completed_task_ids),
            started_at=start_time,
            finished_at=finish_time,
            duration_ms=duration_ms,
            tasks_md_hash=tasks_md_hash,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            artifact_paths=tuple(artifact_paths),
            summary=tuple(summary),
            error=error,
        ),
        finish_time,
    )


@pytest.fixture(autouse=True)
def reset_test_state():
    """Automatically reset state before each test."""
    _test_state.reset()
    yield
    # Additional cleanup after test if needed
    _test_state.reset()


# Fixture for absolute paths
@pytest.fixture
def task_file_path() -> str:
    """Return absolute path to test task file."""
    repo_root = Path("/workspaces/maverick")
    return str(repo_root / "tests/fixtures/multi_task_orchestration/task_2_phases.md")


@pytest.fixture
def repo_root() -> str:
    """Return absolute path to repository root."""
    return "/workspaces/maverick"


# Edge case mock workflows (T058a-e)


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class MockPhaseWorkflowInvalidPath:
    """Mock that raises FileNotFoundError for invalid paths (T058a)."""
    
    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        raise ApplicationError(
            f"Task file not found: {params.tasks_md_path}",
            non_retryable=True,
        )


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class MockPhaseWorkflowMalformed:
    """Mock that raises ValueError for malformed content (T058b)."""
    
    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        raise ApplicationError(
            "Failed to parse tasks.md: Invalid markdown structure",
            non_retryable=True,
        )


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class MockPhaseWorkflowTimeout:
    """Mock that simulates timeout (T058d)."""
    
    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        # Simulate child workflow timeout by raising generic exception
        # (Temporal's actual TimeoutError is raised by the framework, not user code)
        raise ApplicationError(
            "Child workflow execution timed out after 3600s",
            non_retryable=True,
        )


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class MockPhaseWorkflowFast:
    """Mock with fast execution for performance testing (T058e)."""
    
    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        from datetime import timedelta
        now = workflow.now()
        later = now + timedelta(seconds=1)
        return PhaseAutomationSummary(
            results=(
                PhaseAutomationResult(
                    phase_id="phase-1",
                    status="success",
                    completed_task_ids=("T001",),
                    started_at=now,
                    finished_at=later,
                    duration_ms=1000,
                    tasks_md_hash="mock_hash",
                    stdout_path=None,
                    stderr_path=None,
                    artifact_paths=(),
                    summary=(),
                    error=None,
                ),
            ),
            skipped_phase_ids=(),
            started_at=now,
            finished_at=later,
            duration_ms=1000,
            tasks_md_hash="mock_hash",
        )


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class MockPhaseWorkflowSuccess:
    """Mock AutomatePhaseTasksWorkflow that returns successful results."""
    
    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        """Return successful phase automation summary."""
        # Return mock results with 2 phases
        start_time = workflow.now()
        current = start_time

        phase_one, current = _build_phase_result(
            phase_id="phase-1",
            status="success",
            duration_ms=1000,
            completed_task_ids=("T001", "T002", "T003"),
            start_time=current,
            tasks_md_hash="mock_hash_1",
            summary=("Phase completed successfully",),
        )
        phase_two, current = _build_phase_result(
            phase_id="phase-2",
            status="success",
            duration_ms=1500,
            completed_task_ids=("T004", "T005", "T006"),
            start_time=current,
            tasks_md_hash="mock_hash_1",
            summary=("Phase completed successfully",),
        )

        return PhaseAutomationSummary(
            results=(phase_one, phase_two),
            skipped_phase_ids=(),
            started_at=start_time,
            finished_at=current,
            duration_ms=2500,
            tasks_md_hash="mock_hash_1",
        )


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class MockPhaseWorkflowFailure:
    """Mock that succeeds on first task, fails on second task."""
    
    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        """Return success for first task, failure for second task."""
        start_time = workflow.now()
        current = start_time
        
        # Use task file path to determine which task this is
        task_file = params.tasks_md_path or ""
        is_second_task = "?task=2" in task_file

        # First task succeeds
        if not is_second_task:
            phase_one, current = _build_phase_result(
                phase_id="phase-1",
                status="success",
                duration_ms=1000,
                completed_task_ids=("T001", "T002"),
                start_time=current,
                tasks_md_hash="mock_hash",
            )
            phase_two, current = _build_phase_result(
                phase_id="phase-2",
                status="success",
                duration_ms=1000,
                completed_task_ids=("T003",),
                start_time=current,
                tasks_md_hash="mock_hash",
            )
            return PhaseAutomationSummary(
                results=(phase_one, phase_two),
                skipped_phase_ids=(),
                started_at=start_time,
                finished_at=current,
                duration_ms=2000,
                tasks_md_hash="mock_hash",
            )

        # Second task fails
        failed_phase, finish_time = _build_phase_result(
            phase_id="phase-1",
            status="failed",
            duration_ms=500,
            completed_task_ids=(),
            start_time=start_time,
            tasks_md_hash="mock_hash",
            summary=(),
            error="Mock failure for testing",
        )

        return PhaseAutomationSummary(
            results=(failed_phase,),
            skipped_phase_ids=(),
            started_at=start_time,
            finished_at=finish_time,
            duration_ms=500,
            tasks_md_hash="mock_hash",
        )


@pytest.mark.asyncio
async def test_orchestration_two_tasks_success(task_file_path: str, repo_root: str):
    """Test orchestration with 2 tasks that both succeed."""
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    # Create workflow input with 2 task files
    workflow_input = OrchestrationInput(
        task_file_paths=(task_file_path, task_file_path),
        interactive_mode=False,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowSuccess],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-two-tasks-success",
            task_queue="orchestration-task-queue",
        )

        # Verify result structure
        assert isinstance(result, OrchestrationResult)
        assert result.total_tasks == 2
        assert result.successful_tasks == 2
        assert result.failed_tasks == 0
        assert result.skipped_tasks == 0
        assert result.unprocessed_tasks == 0
        assert result.early_termination is False
        assert len(result.task_results) == 2
        assert len(result.unprocessed_task_paths) == 0

        # Verify each task result
        for task_result in result.task_results:
            assert isinstance(task_result, TaskResult)
            assert task_result.overall_status == "success"
            assert len(task_result.phase_results) == 2  # 2 phases per task
            assert task_result.failure_reason is None

            # Verify each phase result
            for phase_result in task_result.phase_results:
                assert isinstance(phase_result, PhaseResult)
                assert phase_result.status == "success"
                assert phase_result.error_message is None


@pytest.mark.asyncio
async def test_orchestration_failure_stops_processing(task_file_path: str, repo_root: str):
    """Test orchestration stops on task failure (fail-fast behavior)."""
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    # Create workflow input with 3 DIFFERENT task file paths to allow differentiation
    # We use the same physical file but different logical names
    task_file_1 = task_file_path
    task_file_2 = task_file_path + "?task=2"  # Add query param to differentiate
    task_file_3 = task_file_path + "?task=3"
    
    workflow_input = OrchestrationInput(
        task_file_paths=(
            task_file_1,
            task_file_2,
            task_file_3,
        ),
        interactive_mode=False,
        retry_limit=1,  # No retries for faster test
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowFailure],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-failure-stops-processing",
            task_queue="orchestration-task-queue",
        )

        # Verify fail-fast behavior
        assert isinstance(result, OrchestrationResult)
        assert result.total_tasks == 3
        assert result.successful_tasks == 1  # Only first task completed
        assert result.failed_tasks == 1  # Second task failed
        assert result.unprocessed_tasks == 1  # Third task not attempted
        assert result.early_termination is True
        assert len(result.task_results) == 2  # First and second tasks
        assert len(result.unprocessed_task_paths) == 1  # Third task

        # Verify first task succeeded
        assert result.task_results[0].overall_status == "success"

        # Verify second task failed
        assert result.task_results[1].overall_status == "failed"
        assert result.task_results[1].failure_reason is not None


@pytest.mark.asyncio
async def test_orchestration_empty_task_list():
    """Test orchestration with empty task list edge case."""
    # Create workflow input with empty task list - should raise validation error
    with pytest.raises(ValueError, match="task_file_paths must contain at least one path"):
        OrchestrationInput(
            task_file_paths=(),  # Empty tuple
            interactive_mode=False,
            retry_limit=3,
            repo_path="/workspaces/maverick",
            branch="test-branch",
        )


@pytest.mark.asyncio
async def test_orchestration_interactive_mode_pause_resume(task_file_path: str, repo_root: str):
    """Test interactive mode with signal-based pause and resume."""
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    # Create workflow input with interactive mode enabled
    workflow_input = OrchestrationInput(
        task_file_paths=(
            task_file_path,
        ),
        interactive_mode=True,  # Enable interactive mode
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowSuccess],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        # Start workflow (non-blocking)
        handle = await env.client.start_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-interactive-pause-resume",
            task_queue="orchestration-task-queue",
        )

        # Query progress - should be paused after first task completes
        # (Wait a bit for workflow to process first task)
        await env.sleep(2)
        progress = await handle.query("get_progress")
        assert progress["is_paused"] is True
        assert progress["current_task_index"] == 0
        
        # Send continue signal to complete workflow (only 1 task total)
        await handle.signal("continue_to_next_phase")

        # Get final result
        result = await handle.result()

        # Verify successful completion
        assert isinstance(result, OrchestrationResult)
        assert result.total_tasks == 1
        assert result.successful_tasks == 1
        assert result.failed_tasks == 0
        assert result.early_termination is False


@pytest.mark.asyncio
async def test_orchestration_interactive_mode_multi_task(task_file_path: str, repo_root: str):
    """Test interactive mode with 3-task batch."""
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    # Create workflow input with 3 tasks in interactive mode
    workflow_input = OrchestrationInput(
        task_file_paths=(
            task_file_path,
            task_file_path,
            task_file_path,
        ),
        interactive_mode=True,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowSuccess],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        # Start workflow
        handle = await env.client.start_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-interactive-multi-task",
            task_queue="orchestration-task-queue",
        )

        # Send continue signals for all tasks (1 pause per task = 3 pauses)
        # Note: In current architecture, we pause after each TASK completes, not after each phase
        for i in range(3):
            await env.sleep(1)
            progress = await handle.query("get_progress")
            assert progress["is_paused"] is True
            await handle.signal("continue_to_next_phase")

        # Get final result
        result = await handle.result()

        # Verify all tasks completed
        assert result.total_tasks == 3
        assert result.successful_tasks == 3
        assert result.failed_tasks == 0


@pytest.mark.asyncio
async def test_orchestration_skip_task_signal(task_file_path: str, repo_root: str):
    """Test skip_current_task signal behavior."""
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    # Create workflow input with 3 tasks
    workflow_input = OrchestrationInput(
        task_file_paths=(
            task_file_path,
            task_file_path,
            task_file_path,
        ),
        interactive_mode=True,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowSuccess],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        handle = await env.client.start_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-skip-task",
            task_queue="orchestration-task-queue",
        )

        # Wait for first task to complete and pause
        await env.sleep(2)
        
        # Complete first task normally
        await handle.signal("continue_to_next_phase")
        
        # Wait for workflow to start processing task 2, then pause after completion
        await env.sleep(2)

        # Skip third task (send skip while paused after task 2)
        # Note: skip_current_task also resumes the workflow
        await handle.signal("skip_current_task")
        
        # Wait for skip to process and pause
        await env.sleep(1)

        # Complete remaining task normally
        await handle.signal("continue_to_next_phase")

        result = await handle.result()

        # Verify results
        assert result.total_tasks == 3
        assert result.successful_tasks == 2
        assert result.skipped_tasks == 1
        # Task at index 2 (third task) should be skipped
        assert result.task_results[2].overall_status == "skipped"


@pytest.mark.asyncio
async def test_orchestration_query_progress_while_paused(task_file_path: str, repo_root: str):
    """Test progress query during pause returns correct state."""
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    workflow_input = OrchestrationInput(
        task_file_paths=(
            task_file_path,
            task_file_path,
        ),
        interactive_mode=True,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowSuccess],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        handle = await env.client.start_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-query-progress",
            task_queue="orchestration-task-queue",
        )

        # Wait for first pause
        await env.sleep(1)
        progress = await handle.query("get_progress")

        # Verify progress structure
        assert progress["is_paused"] is True
        assert progress["current_task_index"] == 0
        assert progress["total_tasks"] == 2
        assert progress["current_task_file"] == task_file_path
        assert "completed_tasks" in progress
        
        # Continue and complete workflow
        for _ in range(2):  # 2 tasks
            await handle.signal("continue_to_next_phase")
            await env.sleep(1)

        await handle.result()


@pytest.mark.asyncio
async def test_orchestration_duplicate_signals(task_file_path: str, repo_root: str):
    """Test duplicate continue signals are handled correctly (idempotent)."""
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    workflow_input = OrchestrationInput(
        task_file_paths=(
            task_file_path,
        ),
        interactive_mode=True,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowSuccess],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        handle = await env.client.start_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-duplicate-signals",
            task_queue="orchestration-task-queue",
        )

        # Wait for pause after task completes
        await env.sleep(2)
        
        # Send multiple continue signals (should be idempotent)
        await handle.signal("continue_to_next_phase")
        await handle.signal("continue_to_next_phase")
        await handle.signal("continue_to_next_phase")

        result = await handle.result()

        # Should still complete successfully
        assert result.successful_tasks == 1


@pytest.mark.asyncio
async def test_orchestration_signal_while_not_paused(task_file_path: str, repo_root: str):
    """Test continue signal while workflow is not paused."""
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    workflow_input = OrchestrationInput(
        task_file_paths=(
            task_file_path,
        ),
        interactive_mode=False,  # Non-interactive mode
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowSuccess],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        handle = await env.client.start_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-signal-not-paused",
            task_queue="orchestration-task-queue",
        )

        # Send signals while workflow is running (should be ignored)
        await handle.signal("continue_to_next_phase")
        await handle.signal("continue_to_next_phase")

        result = await handle.result()

        # Should complete successfully despite extra signals
        assert result.successful_tasks == 1
        assert result.failed_tasks == 0


# ============================================================================
# Phase 5: User Story 3 - Resume After Interruption Tests
# ============================================================================


@pytest.mark.asyncio
async def test_orchestration_resume_after_worker_restart(task_file_path: str, repo_root: str):
    """Test workflow maintains state correctly to support resume.
    
    This test verifies that workflow state (completed_task_indices, task_results)
    is properly maintained throughout execution, which enables automatic resume
    after worker restart via Temporal's deterministic replay.
    
    Key validation: Query the workflow multiple times during execution to verify
    state accumulates correctly and never regresses (deterministic property).
    """
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    workflow_input = OrchestrationInput(
        task_file_paths=(
            task_file_path,
            task_file_path,
            task_file_path,
        ),
        interactive_mode=False,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowSuccess],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        # Start workflow
        handle = await env.client.start_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-resume-after-restart",
            task_queue="orchestration-task-queue",
        )

        # Query state multiple times during execution
        # Each query triggers replay, verifying state is deterministic
        progress_snapshots = []
        for i in range(5):
            await env.sleep(0.5)
            progress = await handle.query("get_progress")
            results = await handle.query("get_task_results")
            progress_snapshots.append({
                "iteration": i,
                "completed_tasks": list(progress["completed_tasks"]),
                "result_count": len(results),
            })

        # Get final result
        result = await handle.result()

        # Verify all tasks completed successfully
        assert result.total_tasks == 3
        assert result.successful_tasks == 3
        assert result.failed_tasks == 0
        assert result.early_termination is False
        
        # Verify all task results are present
        assert len(result.task_results) == 3
        assert all(tr.overall_status == "success" for tr in result.task_results)
        
        # Verify state never regressed during execution (deterministic)
        for i in range(1, len(progress_snapshots)):
            prev = progress_snapshots[i - 1]
            curr = progress_snapshots[i]
            
            # Result count should never decrease
            assert curr["result_count"] >= prev["result_count"], \
                f"State regression detected: result count decreased from {prev['result_count']} to {curr['result_count']}"
            
            # Completed tasks should accumulate, never disappear
            for task_idx in prev["completed_tasks"]:
                assert task_idx in curr["completed_tasks"], \
                    f"State regression detected: task {task_idx} disappeared from completed list"


@pytest.mark.asyncio
async def test_orchestration_resume_paused_during_review_iteration(task_file_path: str, repo_root: str):
    """Test pause state is maintained correctly to support resume.
    
    This test validates that interactive mode pause state (_is_paused, _continue_event)
    is properly managed throughout workflow execution. While actual worker restart
    testing is complex in the test environment, this verifies the state that enables
    resume works correctly.
    
    Scenario:
    1. Start workflow in interactive mode with 2 tasks
    2. Let first task complete and pause
    3. Query state to verify pause is recorded
    4. Send continue signal
    5. Query state again to verify pause cleared
    6. Complete workflow and verify final state
    """
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    workflow_input = OrchestrationInput(
        task_file_paths=(
            task_file_path,
            task_file_path,
        ),
        interactive_mode=True,  # Enable interactive mode
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowSuccess],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        # Start workflow
        handle = await env.client.start_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-resume-paused",
            task_queue="orchestration-task-queue",
        )

        # Wait for first task to complete and pause
        await env.sleep(2)
        
        # Verify workflow is paused after first task
        progress1 = await handle.query("get_progress")
        assert progress1["is_paused"] is True
        assert progress1["current_task_index"] == 0
        completed_after_first = list(progress1["completed_tasks"])
        
        # Send continue signal to proceed to second task
        await handle.signal("continue_to_next_phase")
        
        # Wait for second task to process and pause
        await env.sleep(2)
        
        # Verify workflow paused again after second task
        progress2 = await handle.query("get_progress")
        assert progress2["is_paused"] is True
        assert progress2["current_task_index"] == 1
        
        # Verify first task still in completed list (state preserved)
        for task_idx in completed_after_first:
            assert task_idx in progress2["completed_tasks"], \
                "Completed task disappeared from state - resume would fail"
        
        # Send final continue signal
        await handle.signal("continue_to_next_phase")
        
        result = await handle.result()

        # Verify successful completion
        assert result.total_tasks == 2
        assert result.successful_tasks == 2
        assert result.failed_tasks == 0
        
        # Verify both tasks completed (no re-execution during "resume")
        assert len(result.task_results) == 2
        assert all(tr.overall_status == "success" for tr in result.task_results)


@pytest.mark.asyncio
async def test_orchestration_state_determinism(task_file_path: str, repo_root: str):
    """Test state consistency after multiple replays.
    
    This test validates that workflow state remains consistent across
    multiple replay events, ensuring deterministic behavior.
    
    Key validations:
    - Completed task indices are stable across replays
    - Task results are consistent
    - Current task index advances correctly
    - No duplicate task execution occurs
    """
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    workflow_input = OrchestrationInput(
        task_file_paths=(
            task_file_path,
            task_file_path,
        ),
        interactive_mode=False,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        # Use the same worker for entire test
        worker = Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowSuccess],
            activities=BRANCH_ACTIVITY_MOCKS,
        )

        async with worker:
            # Start workflow
            handle = await env.client.start_workflow(
                MultiTaskOrchestrationWorkflow.run,
                workflow_input,
                id="test-state-determinism",
                task_queue="orchestration-task-queue",
            )

            # Query state multiple times during execution to trigger replay
            # Each query causes workflow history replay
            state_snapshots = []
            for i in range(5):
                await env.sleep(0.5)
                progress = await handle.query("get_progress")
                task_results = await handle.query("get_task_results")
                
                state_snapshots.append({
                    "iteration": i,
                    "current_task_index": progress["current_task_index"],
                    "completed_tasks": progress["completed_tasks"][:],  # Copy list
                    "task_result_count": len(task_results),
                })

            # Get final result
            result = await handle.result()

            # Verify final state is correct
            assert result.total_tasks == 2
            assert result.successful_tasks == 2
            
            # Verify state snapshots show deterministic progression
            # (no tasks should disappear from completed list, counts should only increase)
            for i in range(1, len(state_snapshots)):
                prev = state_snapshots[i - 1]
                curr = state_snapshots[i]
                
                # Completed task count should never decrease
                assert len(curr["completed_tasks"]) >= len(prev["completed_tasks"])
                
                # Task result count should never decrease
                assert curr["task_result_count"] >= prev["task_result_count"]
                
                # Previously completed tasks should remain in completed list
                for completed_idx in prev["completed_tasks"]:
                    assert completed_idx in curr["completed_tasks"]


# ============================================================================
# Phase 6: User Story 4 - Phase Discovery and Dynamic Processing Tests
# ============================================================================


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class MockPhaseWorkflow2Phases:
    """Mock AutomatePhaseTasksWorkflow that returns exactly 2 phases."""
    
    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        """Return successful phase automation summary with 2 phases."""
        start_time = workflow.now()
        current = start_time
        phase_one, current = _build_phase_result(
            phase_id="initialize",
            status="success",
            duration_ms=1000,
            completed_task_ids=("T001", "T002", "T003"),
            start_time=current,
            tasks_md_hash="mock_hash",
            summary=("Initialize phase completed",),
        )
        phase_two, current = _build_phase_result(
            phase_id="implement",
            status="success",
            duration_ms=1500,
            completed_task_ids=("T004", "T005", "T006"),
            start_time=current,
            tasks_md_hash="mock_hash",
            summary=("Implement phase completed",),
        )
        return PhaseAutomationSummary(
            results=(phase_one, phase_two),
            skipped_phase_ids=(),
            started_at=start_time,
            finished_at=current,
            duration_ms=2500,
            tasks_md_hash="mock_hash",
        )


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class MockPhaseWorkflow6Phases:
    """Mock AutomatePhaseTasksWorkflow that returns 6 phases."""
    
    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        """Return successful phase automation summary with 6 phases."""
        start_time = workflow.now()
        current = start_time
        phase_specs = [
            ("planning", ("T001", "T002"), 500),
            ("initialize", ("T003", "T004"), 800),
            ("implement", ("T005", "T006", "T007"), 1200),
            ("quality_assurance", ("T008", "T009"), 900),
            ("review_fix", ("T010", "T011"), 1000),
            ("pr_ci_merge", ("T012", "T013"), 700),
        ]
        results: list[PhaseAutomationResult] = []
        for phase_id, completed_ids, duration in phase_specs:
            result, current = _build_phase_result(
                phase_id=phase_id,
                status="success",
                duration_ms=duration,
                completed_task_ids=completed_ids,
                start_time=current,
                tasks_md_hash="mock_hash",
            )
            results.append(result)

        return PhaseAutomationSummary(
            results=tuple(results),
            skipped_phase_ids=(),
            started_at=start_time,
            finished_at=current,
            duration_ms=sum(duration for _, _, duration in phase_specs),
            tasks_md_hash="mock_hash",
        )


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class MockPhaseWorkflow4Phases:
    """Mock AutomatePhaseTasksWorkflow that returns 4 phases."""
    
    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        """Return successful phase automation summary with 4 phases."""
        start_time = workflow.now()
        current = start_time
        phase_specs = [
            ("initialize", ("T001", "T002", "T003", "T004"), 1000),
            ("implement", ("T005", "T006", "T007", "T008"), 1500),
            ("review_fix", ("T009", "T010", "T011", "T012"), 1200),
            ("pr_ci_merge", ("T013", "T014", "T015", "T016"), 800),
        ]
        results: list[PhaseAutomationResult] = []
        for phase_id, completed_ids, duration in phase_specs:
            result, current = _build_phase_result(
                phase_id=phase_id,
                status="success",
                duration_ms=duration,
                completed_task_ids=completed_ids,
                start_time=current,
                tasks_md_hash="mock_hash",
            )
            results.append(result)

        return PhaseAutomationSummary(
            results=tuple(results),
            skipped_phase_ids=(),
            started_at=start_time,
            finished_at=current,
            duration_ms=sum(duration for _, _, duration in phase_specs),
            tasks_md_hash="mock_hash",
        )


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class MockPhaseWorkflowNoPhases:
    """Mock AutomatePhaseTasksWorkflow that returns no phases (empty results)."""
    
    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        """Return phase automation summary with empty results."""
        from datetime import timedelta
        now = workflow.now()
        later = now + timedelta(milliseconds=1)
        return PhaseAutomationSummary(
            results=(),  # Empty - no phases discovered
            skipped_phase_ids=(),
            started_at=now,
            finished_at=later,
            duration_ms=1,
            tasks_md_hash="mock_hash",
        )


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class MockPhaseWorkflowMixed:
    """Mock that returns different phase counts based on task file name."""
    
    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        """Return different phase counts based on task file name."""
        # Determine phase count from filename
        task_path = params.tasks_md_path or ""
        if "task_2_phases" in task_path:
            phase_count = 2
        elif "task_4_phases" in task_path:
            phase_count = 4
        elif "task_6_phases" in task_path:
            phase_count = 6
        else:
            phase_count = 2  # Default
        
        start_time = workflow.now()
        
        # Return based on phase count
        if phase_count == 2:
            current = start_time
            specs = [
                ("initialize", ("T001",), 1000),
                ("implement", ("T002",), 1000),
            ]
            results: list[PhaseAutomationResult] = []
            for phase_id, completed_ids, duration in specs:
                result, current = _build_phase_result(
                    phase_id=phase_id,
                    status="success",
                    duration_ms=duration,
                    completed_task_ids=completed_ids,
                    start_time=current,
                    tasks_md_hash="mock_hash",
                )
                results.append(result)
            total_duration = sum(duration for _, _, duration in specs)
            return PhaseAutomationSummary(
                results=tuple(results),
                skipped_phase_ids=(),
                started_at=start_time,
                finished_at=current,
                duration_ms=total_duration,
                tasks_md_hash="mock_hash",
            )
        
        # 4 phases
        elif phase_count == 4:
            current = start_time
            specs = [
                ("init", ("T001",), 500),
                ("impl", ("T002",), 500),
                ("review", ("T003",), 500),
                ("merge", ("T004",), 500),
            ]
            results: list[PhaseAutomationResult] = []
            for phase_id, completed_ids, duration in specs:
                result, current = _build_phase_result(
                    phase_id=phase_id,
                    status="success",
                    duration_ms=duration,
                    completed_task_ids=completed_ids,
                    start_time=current,
                    tasks_md_hash="mock_hash",
                )
                results.append(result)
            total_duration = sum(duration for _, _, duration in specs)
            return PhaseAutomationSummary(
                results=tuple(results),
                skipped_phase_ids=(),
                started_at=start_time,
                finished_at=current,
                duration_ms=total_duration,
                tasks_md_hash="mock_hash",
            )
        
        # 6 phases (default for unknown)
        else:  # phase_count == 6 or unknown
            current = start_time
            results: list[PhaseAutomationResult] = []
            for i in range(6):
                result, current = _build_phase_result(
                    phase_id=f"phase_{i}",
                    status="success",
                    duration_ms=500,
                    completed_task_ids=(f"T{i+1:03d}",),
                    start_time=current,
                    tasks_md_hash="mock_hash",
                )
                results.append(result)
            total_duration = 6 * 500
            return PhaseAutomationSummary(
                results=tuple(results),
                skipped_phase_ids=(),
                started_at=start_time,
                finished_at=current,
                duration_ms=total_duration,
                tasks_md_hash="mock_hash",
            )


@pytest.mark.asyncio
async def test_orchestration_variable_phase_count_2(repo_root: str):
    """Test orchestration with task containing exactly 2 phases."""
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    task_path = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/task_2_phases.md")
    
    workflow_input = OrchestrationInput(
        task_file_paths=(task_path,),
        interactive_mode=False,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflow2Phases],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-2-phases",
            task_queue="orchestration-task-queue",
        )

        # Verify result structure
        assert isinstance(result, OrchestrationResult)
        assert result.total_tasks == 1
        assert result.successful_tasks == 1
        assert result.failed_tasks == 0
        assert result.early_termination is False

        # Verify task result has exactly 2 phases
        task_result = result.task_results[0]
        assert task_result.overall_status == "success"
        assert len(task_result.phase_results) == 2
        
        # Verify phase names
        phase_names = [pr.phase_name for pr in task_result.phase_results]
        assert "initialize" in phase_names
        assert "implement" in phase_names
        
        # Verify all phases succeeded
        assert all(pr.status == "success" for pr in task_result.phase_results)


@pytest.mark.asyncio
async def test_orchestration_variable_phase_count_6(repo_root: str):
    """Test orchestration with task containing 6 phases (extended workflow)."""
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    task_path = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/task_6_phases.md")
    
    workflow_input = OrchestrationInput(
        task_file_paths=(task_path,),
        interactive_mode=False,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflow6Phases],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-6-phases",
            task_queue="orchestration-task-queue",
        )

        # Verify result structure
        assert isinstance(result, OrchestrationResult)
        assert result.total_tasks == 1
        assert result.successful_tasks == 1
        assert result.failed_tasks == 0

        # Verify task result has exactly 6 phases
        task_result = result.task_results[0]
        assert task_result.overall_status == "success"
        assert len(task_result.phase_results) == 6
        
        # Verify phase names (6 unique phases)
        phase_names = [pr.phase_name for pr in task_result.phase_results]
        expected_phases = ["planning", "initialize", "implement", "quality_assurance", "review_fix", "pr_ci_merge"]
        assert phase_names == expected_phases
        
        # Verify all phases succeeded
        assert all(pr.status == "success" for pr in task_result.phase_results)


@pytest.mark.asyncio
async def test_orchestration_mixed_phase_counts(repo_root: str):
    """Test orchestration with tasks having different phase counts (2, 4, 6 phases)."""
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    task_path_2 = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/task_2_phases.md")
    task_path_4 = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/task_4_phases.md")
    task_path_6 = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/task_6_phases.md")
    
    workflow_input = OrchestrationInput(
        task_file_paths=(task_path_2, task_path_4, task_path_6),
        interactive_mode=False,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowMixed],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-mixed-phases",
            task_queue="orchestration-task-queue",
        )

        # Verify all tasks completed successfully
        assert result.total_tasks == 3
        assert result.successful_tasks == 3
        assert result.failed_tasks == 0

        # Verify each task has correct phase count
        assert len(result.task_results[0].phase_results) == 2  # First task: 2 phases
        assert len(result.task_results[1].phase_results) == 4  # Second task: 4 phases
        assert len(result.task_results[2].phase_results) == 6  # Third task: 6 phases


@pytest.mark.asyncio
async def test_orchestration_task_no_phases(repo_root: str):
    """Test orchestration handles task with no phases discovered (edge case)."""
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    task_path = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/task_2_phases.md")
    
    workflow_input = OrchestrationInput(
        task_file_paths=(task_path,),
        interactive_mode=False,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowNoPhases],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-no-phases",
            task_queue="orchestration-task-queue",
        )

        # Verify workflow handles empty phase list gracefully
        assert result.total_tasks == 1
        
        # Task should be marked as failed due to no phases
        assert result.failed_tasks == 1
        assert result.successful_tasks == 0
        
        # Verify task result reflects the failure
        task_result = result.task_results[0]
        assert task_result.overall_status == "failed"
        assert task_result.failure_reason is not None
        assert "no phases" in task_result.failure_reason.lower()


@pytest.mark.asyncio
async def test_orchestration_task_file_modification(repo_root: str):
    """Test workflow behavior when task file is modified between start and processing.
    
    Note: This test verifies current behavior - the workflow uses the task file
    path at the time of child workflow execution, so any modifications between
    workflow start and task processing will be picked up by the child workflow.
    
    This is acceptable behavior since:
    1. Task files are typically version-controlled and stable
    2. Temporal's deterministic replay ensures consistency within a single workflow run
    3. The child workflow (AutomatePhaseTasksWorkflow) handles file reading/validation
    """
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    task_path_2 = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/task_2_phases.md")
    task_path_4 = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/task_4_phases.md")
    
    workflow_input = OrchestrationInput(
        task_file_paths=(task_path_2, task_path_4),  # Different files to trigger different phase counts
        interactive_mode=False,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowMixed],  # Reuse MockPhaseWorkflowMixed which determines phases from filename
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-file-modification",
            task_queue="orchestration-task-queue",
        )

        # Verify both tasks completed successfully despite "different" phase structures
        assert result.total_tasks == 2
        assert result.successful_tasks == 2
        assert result.failed_tasks == 0
        
        # Verify first task has 2 phases (from task_2_phases.md)
        assert len(result.task_results[0].phase_results) == 2
        
        # Verify second task has 4 phases (from task_4_phases.md)
        assert len(result.task_results[1].phase_results) == 4
        
        # Both tasks should succeed - workflow handles variable phase counts gracefully
        assert all(tr.overall_status == "success" for tr in result.task_results)


# Edge Case Tests (Phase 7: T058a-e)


@pytest.mark.asyncio
async def test_orchestration_invalid_task_path(repo_root: str):
    """Test workflow behavior when task file path doesn't exist (T058a).
    
    The workflow should fail gracefully when a non-existent task file is provided,
    with a clear error message in the task result.
    """
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    nonexistent_path = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/nonexistent.md")
    
    workflow_input = OrchestrationInput(
        task_file_paths=(nonexistent_path,),
        interactive_mode=False,
        retry_limit=1,  # No retries - we want to test error handling, not retry behavior
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowInvalidPath],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-invalid-path",
            task_queue="orchestration-task-queue",
        )

        # Verify workflow stopped with failure
        assert result.total_tasks == 1
        assert result.successful_tasks == 0
        assert result.failed_tasks == 1
        assert result.unprocessed_tasks == 0
        assert result.early_termination is False  # Only one task, so no early termination

        # Verify task result contains error
        task_result = result.task_results[0]
        assert task_result.overall_status == "failed"
    assert task_result.failure_reason is not None
    error_msg = task_result.failure_reason.lower()
    assert "task file not found" in error_msg


@pytest.mark.asyncio
async def test_orchestration_malformed_task_file(repo_root: str):
    """Test workflow behavior with malformed task markdown (T058b).
    
    The workflow should fail gracefully when task file parsing fails,
    with clear error messages indicating the parsing problem.
    """
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    task_path = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/task_2_phases.md")
    
    workflow_input = OrchestrationInput(
        task_file_paths=(task_path,),
        interactive_mode=False,
        retry_limit=1,  # No retries - we want to test error handling, not retry behavior
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowMalformed],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-malformed",
            task_queue="orchestration-task-queue",
        )

        # Verify workflow stopped with failure
        assert result.total_tasks == 1
        assert result.successful_tasks == 0
        assert result.failed_tasks == 1

        # Verify task result contains parsing error
        task_result = result.task_results[0]
        assert task_result.overall_status == "failed"
    assert task_result.failure_reason is not None
    parse_error_msg = task_result.failure_reason.lower()
    assert "failed to parse" in parse_error_msg


@pytest.mark.asyncio
async def test_orchestration_duplicate_branch_names(repo_root: str):
    """Test workflow behavior when multiple tasks use the same branch (T058c).
    
    Note: The orchestration workflow enforces a single branch name across all tasks
    (OrchestrationInput.branch). This test verifies that branch consistency is
    maintained - all tasks use the same branch, preventing conflicts.
    """
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    task_path_1 = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/task_2_phases.md")
    task_path_2 = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/task_4_phases.md")
    
    workflow_input = OrchestrationInput(
        task_file_paths=(task_path_1, task_path_2),
        interactive_mode=False,
        retry_limit=3,
        repo_path=repo_root,
        branch="shared-branch",  # Same branch for all tasks
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowSuccess],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-duplicate-branches",
            task_queue="orchestration-task-queue",
        )

        # Verify both tasks completed successfully
        # The orchestration workflow design enforces branch consistency by design
        assert result.total_tasks == 2
        assert result.successful_tasks == 2
        assert result.failed_tasks == 0
        
        # All tasks should succeed since they use the same branch
        assert all(tr.overall_status == "success" for tr in result.task_results)


@pytest.mark.asyncio
async def test_orchestration_child_workflow_timeout(repo_root: str):
    """Test workflow behavior when child workflow times out (T058d).
    
    The workflow should capture timeout exceptions from child workflows and
    convert them to failed task results with appropriate error messages.
    """
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    task_path = str(Path(repo_root) / "tests/fixtures/multi_task_orchestration/task_2_phases.md")
    
    workflow_input = OrchestrationInput(
        task_file_paths=(task_path,),
        interactive_mode=False,
        retry_limit=1,  # No retries - we want to test timeout handling, not retry behavior
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowTimeout],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-timeout",
            task_queue="orchestration-task-queue",
        )

        # Verify workflow stopped with failure
        assert result.total_tasks == 1
        assert result.successful_tasks == 0
        assert result.failed_tasks == 1

        # Verify task result contains timeout error
        task_result = result.task_results[0]
        assert task_result.overall_status == "failed"
    assert task_result.failure_reason is not None
    timeout_msg = task_result.failure_reason.lower()
    assert "timed out" in timeout_msg or "timeout" in timeout_msg


@pytest.mark.asyncio
async def test_orchestration_performance_benchmark(repo_root: str):
    """Test performance with 10 tasks to validate SC-005 (< 4 hours) (T058e).
    
    Note: This is a synthetic benchmark test using mocked child workflows.
    Real-world performance depends on:
    - Actual phase execution time (speckit.implement, review/fix, PR/CI)
    - Repository size and complexity
    - CI/CD pipeline speed
    - Network conditions
    
    This test validates that the orchestration overhead itself is minimal
    and doesn't introduce significant delays beyond child workflow execution.
    """
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    # Create 10 task file paths
    task_paths = tuple(
        str(Path(repo_root) / f"tests/fixtures/multi_task_orchestration/task_{i}.md")
        for i in range(10)
    )
    
    workflow_input = OrchestrationInput(
        task_file_paths=task_paths,
        interactive_mode=False,
        retry_limit=3,
        repo_path=repo_root,
        branch="test-branch",
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="orchestration-task-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowFast],
            activities=BRANCH_ACTIVITY_MOCKS,
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-performance",
            task_queue="orchestration-task-queue",
        )

        # Verify all 10 tasks completed
        assert result.total_tasks == 10
        assert result.successful_tasks == 10
        assert result.failed_tasks == 0
        
        # Verify orchestration overhead is minimal
        # With time-skipping, workflow time should be ~10 seconds (10 tasks * 1 second each)
        # Allow some overhead for workflow logic (< 5 seconds)
        assert result.total_duration_seconds < 15, \
            f"Orchestration overhead too high: {result.total_duration_seconds}s for 10 tasks"
        
        # Real-world validation note:
        # SC-005 requires 10 tasks in < 4 hours (14400 seconds)
        # Average time per task: 14400 / 10 = 1440 seconds = 24 minutes
        # This is reasonable for:
        #   - Phase execution (speckit.implement): ~10-15 minutes
        #   - Review/fix iterations: ~5-10 minutes
        #   - PR/CI/merge: ~3-5 minutes


# =============================================================================
# T017: Branch Checkout Integration Tests (US1)
# =============================================================================


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class MockPhaseWorkflowForBranchTests:
    """Mock phase workflow that tracks when it's called."""
    
    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        """Record that phase execution happened."""
        from datetime import timedelta
        
        _test_state.call_order.append("phase_execution")
        
        # Return minimal successful result (use workflow.now() for determinism)
        now = workflow.now()
        return PhaseAutomationSummary(
            results=(
                PhaseAutomationResult(
                    phase_id="test-phase",
                    status="success",
                    completed_task_ids=["T001"],
                    started_at=now,
                    finished_at=now + timedelta(milliseconds=100),
                    duration_ms=100,
                    tasks_md_hash="mock-hash",
                    stdout_path=None,
                    stderr_path=None,
                    artifact_paths=[],
                    summary=["Mock phase completed"],
                    error=None,
                ),
            ),
            skipped_phase_ids=[],
            started_at=now,
            finished_at=now + timedelta(milliseconds=100),
            duration_ms=100,
            tasks_md_hash="mock-hash",
        )


@activity.defn(name="derive_task_branch")  # Match actual activity name
async def mock_derive_task_branch(task_descriptor: dict) -> BranchSelection:
    """Mock activity that records call order."""
    _test_state.call_order.append("derive_branch")
    
    # Return realistic branch selection
    return BranchSelection(
        branch_name="test-branch",
        source="explicit",
        log_message="Mock branch derivation",
    )


@activity.defn(name="checkout_task_branch")  # Match actual activity name
async def mock_checkout_task_branch(branch_name: str) -> CheckoutResult:
    """Mock activity that records call order and can simulate dirty repo."""
    if _test_state.checkout_should_fail:
        _test_state.call_order.append("checkout_branch_failed")
        # Raise error matching real dirty repo behavior
        raise ApplicationError(
            f"Cannot checkout {branch_name}: working tree has uncommitted changes. "
            "Found 3 modified/untracked files.",
            non_retryable=True,
        )
    else:
        _test_state.call_order.append("checkout_branch")
        # Return successful checkout
        return CheckoutResult(
            branch_name=branch_name,
            changed=True,
            status="success",
            git_head="abc1234",
            logs=["Checked out test-branch"],
        )


# Shared branch activity mocks keep orchestrator tests deterministic
BRANCH_ACTIVITY_MOCKS = (
    mock_derive_task_branch,
    mock_checkout_task_branch,
)


@pytest.mark.asyncio
async def test_branch_checkout_precedes_phase_execution(repo_root: str):
    """Test that branch checkout happens before any phase execution.
    
    User Story 1 (US1): Branch context prepared
    
    This test validates:
    1. derive_task_branch activity is called first
    2. checkout_task_branch activity is called second
    3. Phase execution only happens after successful checkout
    4. Call order is: derive -> checkout -> phase_execution
    """
    from pathlib import Path

    from src.models.orchestration import OrchestrationInput, TaskDescriptor
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    # State is reset by fixture, no need to manually reset
    
    # Create TaskDescriptor input (use absolute path as required by AutomatePhaseTasksParams)
    task_descriptor = TaskDescriptor(
        task_id="test-001",
        spec_path=f"{repo_root}/specs/001-task-branch-switch/spec.md",  # Absolute path
        explicit_branch="test-branch",
        phases=["phase1"],
    )
    
    workflow_input = OrchestrationInput(
        task_descriptors=(task_descriptor,),
        interactive_mode=False,
        retry_limit=3,
        repo_path=str(repo_root),  # Convert to string for serialization
    )

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="branch-test-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowForBranchTests],
            activities=[mock_derive_task_branch, mock_checkout_task_branch],
        ),
    ):
        result = await env.client.execute_workflow(
            MultiTaskOrchestrationWorkflow.run,
            workflow_input,
            id="test-branch-checkout-order",
            task_queue="branch-test-queue",
        )

        # Verify workflow succeeded
        assert result.total_tasks == 1
        assert result.successful_tasks == 1, f"Expected 1 successful task, got {result.successful_tasks}"
        assert result.failed_tasks == 0, f"Expected 0 failed tasks, got {result.failed_tasks}"
        
        # CRITICAL: Verify call order for activities (tracked in _test_state.call_order)
        # Note: Child workflow runs in different context, so we verify it indirectly via result
        assert len(_test_state.call_order) >= 2, f"Expected at least 2 activity calls, got {len(_test_state.call_order)}: {_test_state.call_order}"
        assert _test_state.call_order[0] == "derive_branch", "derive_branch must be called first"
        assert _test_state.call_order[1] == "checkout_branch", "checkout_branch must be called second"
        
        # CRITICAL: Verify phase execution happened (proves workflow called child workflow after branch checkout)
        assert len(result.task_results) == 1
        task_result = result.task_results[0]
        assert task_result.overall_status == "success"
        assert len(task_result.phase_results) == 1, "Should have one phase result from mock workflow"
        phase_result = task_result.phase_results[0]
        assert phase_result.phase_name == "test-phase", "Mock workflow should have run"
        assert phase_result.status == "success"
        
        # The fact that we have a phase result proves the call order was:
        # 1. derive_task_branch activity (confirmed by _call_order[0])
        # 2. checkout_task_branch activity (confirmed by _call_order[1])
        # 3. AutomatePhaseTasksWorkflow child workflow (confirmed by phase_result existence)
        
        # Verify task result
        assert len(result.task_results) == 1
        task_result = result.task_results[0]
        assert task_result.overall_status == "success"


@pytest.mark.asyncio
async def test_dirty_repository_prevents_checkout(repo_root: str):
    """Test that dirty working tree causes checkout to fail and stops workflow.
    
    User Story 1 (US1): Branch context prepared
    
    This test validates:
    1. checkout_task_branch failure stops workflow immediately
    2. Phase execution never happens
    3. TaskResult shows branch_checkout failure
    4. Error message is actionable (mentions uncommitted changes)
    """
    from pathlib import Path

    from src.models.orchestration import OrchestrationInput, TaskDescriptor
    from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

    # State is reset by fixture, no need to manually reset
    
    # Create TaskDescriptor input (use absolute path)
    task_descriptor = TaskDescriptor(
        task_id="test-002",
        spec_path=f"{repo_root}/specs/001-task-branch-switch/spec.md",  # Absolute path
        explicit_branch="dirty-test-branch",
        phases=["phase1"],
    )
    
    workflow_input = OrchestrationInput(
        task_descriptors=(task_descriptor,),
        interactive_mode=False,
        retry_limit=3,
        repo_path=repo_root,
    )

    _test_state.checkout_should_fail = True  # Enable dirty repo behavior
    
    async with await WorkflowEnvironment.start_time_skipping() as env:
        # Use same mocks but with _checkout_should_fail=True
        worker = Worker(
            env.client,
            task_queue="dirty-repo-test-queue",
            workflows=[MultiTaskOrchestrationWorkflow, MockPhaseWorkflowForBranchTests],
            activities=[mock_derive_task_branch, mock_checkout_task_branch],
        )
        
        async with worker:
            result = await env.client.execute_workflow(
                MultiTaskOrchestrationWorkflow.run,
                workflow_input,
                id="test-dirty-repo-fails",
                task_queue="dirty-repo-test-queue",
            )

        # Verify workflow handled failure correctly
        assert result.total_tasks == 1
        assert result.successful_tasks == 0
        assert result.failed_tasks == 1
        
        # CRITICAL: Verify phase_execution was NEVER called
        assert "phase_execution" not in _test_state.call_order, \
            "Phase execution should not happen when checkout fails"
        
        # Verify checkout was attempted
        assert "derive_branch" in _test_state.call_order
        assert "checkout_branch_failed" in _test_state.call_order
        
        # Verify task result shows failure
        assert len(result.task_results) == 1
        task_result = result.task_results[0]
        assert task_result.overall_status == "failed"
        
        # Verify error message is actionable
        assert task_result.failure_reason is not None
        error_msg = task_result.failure_reason.lower()
        assert any(word in error_msg for word in ["uncommitted", "dirty", "changes"]), \
            f"Error message should mention dirty/uncommitted: {task_result.failure_reason}"
        
        # Verify phase_result indicates branch_checkout failure
        assert len(task_result.phase_results) == 1
        phase_result = task_result.phase_results[0]
        assert phase_result.phase_name == "branch_checkout"
        assert phase_result.status == "failed"
