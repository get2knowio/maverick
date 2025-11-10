"""Unit tests for orchestration data models.

Tests validate all dataclass invariants, edge cases, and error conditions
following TDD principles from the Constitution.
"""

import pytest

from src.models.orchestration import (
    OrchestrationInput,
    OrchestrationResult,
    PhaseResult,
    TaskProgress,
    TaskResult,
)


class TestOrchestrationInput:
    """Test suite for OrchestrationInput validation."""

    def test_valid_input_minimal(self) -> None:
        """Valid input with minimal required fields."""
        input_data = OrchestrationInput(
            task_file_paths=("task1.md",),
            interactive_mode=False,
            retry_limit=3,
            repo_path="/workspace/repo",
            branch="main",
        )
        assert input_data.task_file_paths == ("task1.md",)
        assert input_data.interactive_mode is False
        assert input_data.retry_limit == 3
        assert input_data.repo_path == "/workspace/repo"
        assert input_data.branch == "main"
        assert input_data.default_model is None
        assert input_data.default_agent_profile is None

    def test_valid_input_with_optionals(self) -> None:
        """Valid input with all optional fields."""
        input_data = OrchestrationInput(
            task_file_paths=("task1.md", "task2.md"),
            interactive_mode=True,
            retry_limit=5,
            repo_path="/workspace/repo",
            branch="feature-branch",
            default_model="gpt-4",
            default_agent_profile="expert",
        )
        assert len(input_data.task_file_paths) == 2
        assert input_data.default_model == "gpt-4"
        assert input_data.default_agent_profile == "expert"

    def test_normalizes_paths(self) -> None:
        """Paths are normalized (whitespace stripped)."""
        input_data = OrchestrationInput(
            task_file_paths=("  task1.md  ", "task2.md  "),
            interactive_mode=False,
            retry_limit=3,
            repo_path="  /workspace/repo  ",
            branch="  main  ",
        )
        assert input_data.task_file_paths == ("task1.md", "task2.md")
        assert input_data.repo_path == "/workspace/repo"
        assert input_data.branch == "main"

    def test_empty_task_file_paths(self) -> None:
        """Empty task_file_paths raises ValueError."""
        with pytest.raises(ValueError, match="task_file_paths must contain at least one path"):
            OrchestrationInput(
                task_file_paths=(),
                interactive_mode=False,
                retry_limit=3,
                repo_path="/workspace/repo",
                branch="main",
            )

    def test_task_file_paths_with_empty_string(self) -> None:
        """task_file_paths with empty string after normalization raises ValueError."""
        with pytest.raises(ValueError, match="task_file_paths cannot contain empty paths"):
            OrchestrationInput(
                task_file_paths=("task1.md", "   "),
                interactive_mode=False,
                retry_limit=3,
                repo_path="/workspace/repo",
                branch="main",
            )

    def test_retry_limit_too_low(self) -> None:
        """retry_limit < 1 raises ValueError."""
        with pytest.raises(ValueError, match="retry_limit must be between 1 and 10"):
            OrchestrationInput(
                task_file_paths=("task1.md",),
                interactive_mode=False,
                retry_limit=0,
                repo_path="/workspace/repo",
                branch="main",
            )

    def test_retry_limit_too_high(self) -> None:
        """retry_limit > 10 raises ValueError."""
        with pytest.raises(ValueError, match="retry_limit must be between 1 and 10"):
            OrchestrationInput(
                task_file_paths=("task1.md",),
                interactive_mode=False,
                retry_limit=11,
                repo_path="/workspace/repo",
                branch="main",
            )

    def test_retry_limit_boundary_values(self) -> None:
        """retry_limit accepts boundary values 1 and 10."""
        input_min = OrchestrationInput(
            task_file_paths=("task1.md",),
            interactive_mode=False,
            retry_limit=1,
            repo_path="/workspace/repo",
            branch="main",
        )
        assert input_min.retry_limit == 1

        input_max = OrchestrationInput(
            task_file_paths=("task1.md",),
            interactive_mode=False,
            retry_limit=10,
            repo_path="/workspace/repo",
            branch="main",
        )
        assert input_max.retry_limit == 10

    def test_empty_repo_path(self) -> None:
        """Empty repo_path raises ValueError."""
        with pytest.raises(ValueError, match="repo_path must be non-empty"):
            OrchestrationInput(
                task_file_paths=("task1.md",),
                interactive_mode=False,
                retry_limit=3,
                repo_path="",
                branch="main",
            )

    def test_whitespace_only_repo_path(self) -> None:
        """Whitespace-only repo_path raises ValueError."""
        with pytest.raises(ValueError, match="repo_path must be non-empty"):
            OrchestrationInput(
                task_file_paths=("task1.md",),
                interactive_mode=False,
                retry_limit=3,
                repo_path="   ",
                branch="main",
            )

    def test_empty_branch(self) -> None:
        """Empty branch raises ValueError."""
        with pytest.raises(ValueError, match="branch must be non-empty"):
            OrchestrationInput(
                task_file_paths=("task1.md",),
                interactive_mode=False,
                retry_limit=3,
                repo_path="/workspace/repo",
                branch="",
            )

    def test_whitespace_only_branch(self) -> None:
        """Whitespace-only branch raises ValueError."""
        with pytest.raises(ValueError, match="branch must be non-empty"):
            OrchestrationInput(
                task_file_paths=("task1.md",),
                interactive_mode=False,
                retry_limit=3,
                repo_path="/workspace/repo",
                branch="   ",
            )


class TestPhaseResult:
    """Test suite for PhaseResult validation."""

    def test_valid_success_result(self) -> None:
        """Valid success result with no error message."""
        result = PhaseResult(
            phase_name="initialize",
            status="success",
            duration_seconds=45,
            error_message=None,
            retry_count=0,
        )
        assert result.phase_name == "initialize"
        assert result.status == "success"
        assert result.duration_seconds == 45
        assert result.error_message is None
        assert result.retry_count == 0

    def test_valid_failed_result(self) -> None:
        """Valid failed result with error message."""
        result = PhaseResult(
            phase_name="implement",
            status="failed",
            duration_seconds=120,
            error_message="Compilation error",
            retry_count=2,
        )
        assert result.phase_name == "implement"
        assert result.status == "failed"
        assert result.error_message == "Compilation error"
        assert result.retry_count == 2

    def test_normalizes_phase_name(self) -> None:
        """Phase name is normalized (whitespace stripped)."""
        result = PhaseResult(
            phase_name="  initialize  ",
            status="success",
            duration_seconds=45,
            error_message=None,
            retry_count=0,
        )
        assert result.phase_name == "initialize"

    def test_empty_phase_name(self) -> None:
        """Empty phase_name raises ValueError."""
        with pytest.raises(ValueError, match="phase_name must be non-empty"):
            PhaseResult(
                phase_name="",
                status="success",
                duration_seconds=45,
                error_message=None,
                retry_count=0,
            )

    def test_whitespace_only_phase_name(self) -> None:
        """Whitespace-only phase_name raises ValueError."""
        with pytest.raises(ValueError, match="phase_name must be non-empty"):
            PhaseResult(
                phase_name="   ",
                status="success",
                duration_seconds=45,
                error_message=None,
                retry_count=0,
            )

    def test_negative_duration(self) -> None:
        """Negative duration_seconds raises ValueError."""
        with pytest.raises(ValueError, match="duration_seconds must be >= 0"):
            PhaseResult(
                phase_name="initialize",
                status="success",
                duration_seconds=-1,
                error_message=None,
                retry_count=0,
            )

    def test_failed_without_error_message(self) -> None:
        """Failed status without error_message raises ValueError."""
        with pytest.raises(ValueError, match="status=failed requires non-None error_message"):
            PhaseResult(
                phase_name="implement",
                status="failed",
                duration_seconds=120,
                error_message=None,
                retry_count=2,
            )

    def test_success_with_error_message(self) -> None:
        """Success status with error_message raises ValueError."""
        with pytest.raises(ValueError, match="status=success requires error_message=None"):
            PhaseResult(
                phase_name="implement",
                status="success",
                duration_seconds=120,
                error_message="Unexpected error",
                retry_count=0,
            )

    def test_negative_retry_count(self) -> None:
        """Negative retry_count raises ValueError."""
        with pytest.raises(ValueError, match="retry_count must be >= 0"):
            PhaseResult(
                phase_name="initialize",
                status="success",
                duration_seconds=45,
                error_message=None,
                retry_count=-1,
            )


class TestTaskResult:
    """Test suite for TaskResult validation."""

    def test_valid_success_result(self) -> None:
        """Valid success result with all phases successful."""
        phase1 = PhaseResult("initialize", "success", 45, None, 0)
        phase2 = PhaseResult("implement", "success", 120, None, 0)
        result = TaskResult(
            task_file_path="task1.md",
            overall_status="success",
            phase_results=(phase1, phase2),
            total_duration_seconds=165,
            failure_reason=None,
        )
        assert result.task_file_path == "task1.md"
        assert result.overall_status == "success"
        assert len(result.phase_results) == 2
        assert result.total_duration_seconds == 165
        assert result.failure_reason is None

    def test_valid_failed_result(self) -> None:
        """Valid failed result with at least one failed phase."""
        phase1 = PhaseResult("initialize", "success", 45, None, 0)
        phase2 = PhaseResult("implement", "failed", 120, "Compilation error", 2)
        result = TaskResult(
            task_file_path="task1.md",
            overall_status="failed",
            phase_results=(phase1, phase2),
            total_duration_seconds=165,
            failure_reason="Phase 'implement' failed",
        )
        assert result.overall_status == "failed"
        assert result.failure_reason == "Phase 'implement' failed"

    def test_valid_skipped_result(self) -> None:
        """Valid skipped result with no phases."""
        result = TaskResult(
            task_file_path="task1.md",
            overall_status="skipped",
            phase_results=(),
            total_duration_seconds=0,
            failure_reason=None,
        )
        assert result.overall_status == "skipped"
        assert len(result.phase_results) == 0

    def test_valid_unprocessed_result(self) -> None:
        """Valid unprocessed result with no phases."""
        result = TaskResult(
            task_file_path="task1.md",
            overall_status="unprocessed",
            phase_results=(),
            total_duration_seconds=0,
            failure_reason=None,
        )
        assert result.overall_status == "unprocessed"
        assert len(result.phase_results) == 0

    def test_normalizes_task_file_path(self) -> None:
        """task_file_path is normalized (whitespace stripped)."""
        result = TaskResult(
            task_file_path="  task1.md  ",
            overall_status="skipped",
            phase_results=(),
            total_duration_seconds=0,
            failure_reason=None,
        )
        assert result.task_file_path == "task1.md"

    def test_empty_task_file_path(self) -> None:
        """Empty task_file_path raises ValueError."""
        with pytest.raises(ValueError, match="task_file_path must be non-empty"):
            TaskResult(
                task_file_path="",
                overall_status="skipped",
                phase_results=(),
                total_duration_seconds=0,
                failure_reason=None,
            )

    def test_negative_total_duration(self) -> None:
        """Negative total_duration_seconds raises ValueError."""
        with pytest.raises(ValueError, match="total_duration_seconds must be >= 0"):
            TaskResult(
                task_file_path="task1.md",
                overall_status="skipped",
                phase_results=(),
                total_duration_seconds=-1,
                failure_reason=None,
            )

    def test_success_with_failed_phase(self) -> None:
        """Success status with failed phase raises ValueError."""
        phase1 = PhaseResult("initialize", "failed", 45, "Error", 1)
        with pytest.raises(ValueError, match="overall_status=success cannot have failed phase_results"):
            TaskResult(
                task_file_path="task1.md",
                overall_status="success",
                phase_results=(phase1,),
                total_duration_seconds=45,
                failure_reason=None,
            )

    def test_failed_without_failed_phase(self) -> None:
        """Failed status without any failed phase raises ValueError."""
        phase1 = PhaseResult("initialize", "success", 45, None, 0)
        with pytest.raises(
            ValueError, match="overall_status=failed requires at least one failed phase_result"
        ):
            TaskResult(
                task_file_path="task1.md",
                overall_status="failed",
                phase_results=(phase1,),
                total_duration_seconds=45,
                failure_reason="Some error",
            )

    def test_failed_without_failure_reason(self) -> None:
        """Failed status without failure_reason raises ValueError."""
        phase1 = PhaseResult("initialize", "failed", 45, "Error", 1)
        with pytest.raises(ValueError, match="overall_status=failed requires non-None failure_reason"):
            TaskResult(
                task_file_path="task1.md",
                overall_status="failed",
                phase_results=(phase1,),
                total_duration_seconds=45,
                failure_reason=None,
            )

    def test_non_failed_with_failure_reason(self) -> None:
        """Non-failed status with failure_reason raises ValueError."""
        with pytest.raises(ValueError, match="failure_reason must be None when overall_status is not failed"):
            TaskResult(
                task_file_path="task1.md",
                overall_status="success",
                phase_results=(),
                total_duration_seconds=0,
                failure_reason="Should not have reason",
            )

    def test_unprocessed_with_phases(self) -> None:
        """Unprocessed status with phases raises ValueError."""
        phase1 = PhaseResult("initialize", "success", 45, None, 0)
        with pytest.raises(ValueError, match="overall_status=unprocessed requires empty phase_results"):
            TaskResult(
                task_file_path="task1.md",
                overall_status="unprocessed",
                phase_results=(phase1,),
                total_duration_seconds=45,
                failure_reason=None,
            )


class TestOrchestrationResult:
    """Test suite for OrchestrationResult validation."""

    def test_valid_all_successful(self) -> None:
        """Valid result with all tasks successful."""
        task1 = TaskResult("task1.md", "success", (), 100, None)
        task2 = TaskResult("task2.md", "success", (), 200, None)
        result = OrchestrationResult(
            total_tasks=2,
            successful_tasks=2,
            failed_tasks=0,
            skipped_tasks=0,
            unprocessed_tasks=0,
            task_results=(task1, task2),
            unprocessed_task_paths=(),
            early_termination=False,
            total_duration_seconds=300,
        )
        assert result.total_tasks == 2
        assert result.successful_tasks == 2
        assert result.early_termination is False

    def test_valid_with_failure_and_early_termination(self) -> None:
        """Valid result with failure and early termination."""
        phase1 = PhaseResult("implement", "failed", 120, "Error", 2)
        task1 = TaskResult("task1.md", "success", (), 100, None)
        task2 = TaskResult("task2.md", "failed", (phase1,), 120, "Phase failed")
        result = OrchestrationResult(
            total_tasks=4,
            successful_tasks=1,
            failed_tasks=1,
            skipped_tasks=0,
            unprocessed_tasks=2,
            task_results=(task1, task2),
            unprocessed_task_paths=("task3.md", "task4.md"),
            early_termination=True,
            total_duration_seconds=220,
        )
        assert result.total_tasks == 4
        assert result.unprocessed_tasks == 2
        assert result.early_termination is True
        assert len(result.unprocessed_task_paths) == 2

    def test_negative_total_tasks(self) -> None:
        """Negative total_tasks raises ValueError."""
        with pytest.raises(ValueError, match="total_tasks must be >= 0"):
            OrchestrationResult(
                total_tasks=-1,
                successful_tasks=0,
                failed_tasks=0,
                skipped_tasks=0,
                unprocessed_tasks=0,
                task_results=(),
                unprocessed_task_paths=(),
                early_termination=False,
                total_duration_seconds=0,
            )

    def test_count_sum_mismatch(self) -> None:
        """Total tasks not equal to sum of status counts raises ValueError."""
        phase1 = PhaseResult("implement", "failed", 120, "Error", 2)
        with pytest.raises(ValueError, match="total_tasks .* must equal sum of status counts"):
            OrchestrationResult(
                total_tasks=5,  # Should be 3
                successful_tasks=2,
                failed_tasks=1,
                skipped_tasks=0,
                unprocessed_tasks=0,
                task_results=(
                    TaskResult("task1.md", "success", (), 100, None),
                    TaskResult("task2.md", "success", (), 100, None),
                    TaskResult("task3.md", "failed", (phase1,), 120, "Error"),
                ),
                unprocessed_task_paths=(),
                early_termination=False,
                total_duration_seconds=300,
            )

    def test_result_list_count_mismatch(self) -> None:
        """Total tasks not equal to results + unprocessed raises ValueError."""
        with pytest.raises(
            ValueError, match="total_tasks .* must equal task_results \\+ unprocessed_task_paths"
        ):
            OrchestrationResult(
                total_tasks=2,  # Counts sum correctly
                successful_tasks=1,
                failed_tasks=0,
                skipped_tasks=0,
                unprocessed_tasks=1,
                task_results=(TaskResult("task1.md", "success", (), 100, None),),
                unprocessed_task_paths=("task2.md", "task3.md", "task4.md"),  # 3 unprocessed but declared 1
                early_termination=False,
                total_duration_seconds=100,
            )

    def test_early_termination_without_unprocessed(self) -> None:
        """early_termination=True without unprocessed tasks raises ValueError."""
        with pytest.raises(ValueError, match="early_termination=True requires unprocessed_tasks > 0"):
            OrchestrationResult(
                total_tasks=2,
                successful_tasks=2,
                failed_tasks=0,
                skipped_tasks=0,
                unprocessed_tasks=0,
                task_results=(
                    TaskResult("task1.md", "success", (), 100, None),
                    TaskResult("task2.md", "success", (), 100, None),
                ),
                unprocessed_task_paths=(),
                early_termination=True,
                total_duration_seconds=200,
            )

    def test_successful_count_mismatch(self) -> None:
        """Declared successful count not matching actual raises ValueError."""
        with pytest.raises(ValueError, match="successful_tasks .* does not match actual count"):
            OrchestrationResult(
                total_tasks=2,
                successful_tasks=0,  # Should be 2 (counts sum to 2, but actual results have 2 successes)
                failed_tasks=0,
                skipped_tasks=0,
                unprocessed_tasks=2,
                task_results=(
                    TaskResult("task1.md", "success", (), 100, None),
                    TaskResult("task2.md", "success", (), 100, None),
                ),
                unprocessed_task_paths=(),
                early_termination=False,
                total_duration_seconds=200,
            )

    def test_failed_count_mismatch(self) -> None:
        """Declared failed count not matching actual raises ValueError."""
        phase1 = PhaseResult("implement", "failed", 120, "Error", 2)
        with pytest.raises(ValueError, match="failed_tasks .* does not match actual count"):
            OrchestrationResult(
                total_tasks=2,
                successful_tasks=1,
                failed_tasks=0,  # Should be 1 (counts sum to 2, but actual results have 1 failed)
                skipped_tasks=0,
                unprocessed_tasks=1,
                task_results=(
                    TaskResult("task1.md", "success", (), 100, None),
                    TaskResult("task2.md", "failed", (phase1,), 120, "Error"),
                ),
                unprocessed_task_paths=(),
                early_termination=False,
                total_duration_seconds=220,
            )

    def test_skipped_count_mismatch(self) -> None:
        """Declared skipped count not matching actual raises ValueError."""
        with pytest.raises(ValueError, match="skipped_tasks .* does not match actual count"):
            OrchestrationResult(
                total_tasks=2,
                successful_tasks=1,
                failed_tasks=0,
                skipped_tasks=0,  # Should be 1 (counts sum to 2, but actual results have 1 skipped)
                unprocessed_tasks=1,
                task_results=(
                    TaskResult("task1.md", "success", (), 100, None),
                    TaskResult("task2.md", "skipped", (), 0, None),
                ),
                unprocessed_task_paths=(),
                early_termination=False,
                total_duration_seconds=100,
            )


class TestTaskProgress:
    """Test suite for TaskProgress validation."""

    def test_valid_pending_progress(self) -> None:
        """Valid pending progress state."""
        progress = TaskProgress(
            task_index=0,
            task_file_path="task1.md",
            current_phase=None,
            completed_phases=[],
            status="pending",
        )
        assert progress.task_index == 0
        assert progress.current_phase is None
        assert progress.completed_phases == []
        assert progress.status == "pending"

    def test_valid_in_progress(self) -> None:
        """Valid in_progress state."""
        progress = TaskProgress(
            task_index=1,
            task_file_path="task2.md",
            current_phase="implement",
            completed_phases=["initialize"],
            status="in_progress",
        )
        assert progress.current_phase == "implement"
        assert len(progress.completed_phases) == 1

    def test_valid_completed(self) -> None:
        """Valid completed state."""
        progress = TaskProgress(
            task_index=2,
            task_file_path="task3.md",
            current_phase=None,
            completed_phases=["initialize", "implement", "review_fix"],
            status="completed",
        )
        assert progress.current_phase is None
        assert len(progress.completed_phases) == 3

    def test_negative_task_index(self) -> None:
        """Negative task_index raises ValueError."""
        with pytest.raises(ValueError, match="task_index must be >= 0"):
            TaskProgress(
                task_index=-1,
                task_file_path="task1.md",
                current_phase=None,
                completed_phases=[],
                status="pending",
            )

    def test_empty_task_file_path(self) -> None:
        """Empty task_file_path raises ValueError."""
        with pytest.raises(ValueError, match="task_file_path must be non-empty"):
            TaskProgress(
                task_index=0,
                task_file_path="",
                current_phase=None,
                completed_phases=[],
                status="pending",
            )

    def test_pending_with_current_phase(self) -> None:
        """Pending status with current_phase raises ValueError."""
        with pytest.raises(ValueError, match="status=pending requires current_phase=None"):
            TaskProgress(
                task_index=0,
                task_file_path="task1.md",
                current_phase="initialize",
                completed_phases=[],
                status="pending",
            )

    def test_pending_with_completed_phases(self) -> None:
        """Pending status with completed_phases raises ValueError."""
        with pytest.raises(ValueError, match="status=pending requires empty completed_phases"):
            TaskProgress(
                task_index=0,
                task_file_path="task1.md",
                current_phase=None,
                completed_phases=["initialize"],
                status="pending",
            )

    def test_completed_with_current_phase(self) -> None:
        """Completed status with current_phase raises ValueError."""
        with pytest.raises(ValueError, match="status=completed requires current_phase=None"):
            TaskProgress(
                task_index=0,
                task_file_path="task1.md",
                current_phase="implement",
                completed_phases=["initialize"],
                status="completed",
            )

    def test_in_progress_without_current_phase(self) -> None:
        """In_progress status without current_phase raises ValueError."""
        with pytest.raises(ValueError, match="status=in_progress requires non-None current_phase"):
            TaskProgress(
                task_index=0,
                task_file_path="task1.md",
                current_phase=None,
                completed_phases=["initialize"],
                status="in_progress",
            )
