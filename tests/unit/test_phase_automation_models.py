"""Unit tests for phase automation dataclasses invariants."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.models.phase_automation import (
    CiFailureDetail,
    PhaseDefinition,
    PhaseExecutionContext,
    PhaseExecutionHints,
    PhaseResult,
    PollingConfiguration,
    PullRequestAutomationRequest,
    PullRequestAutomationResult,
    ResumeState,
    TaskItem,
    WorkflowCheckpoint,
)


@pytest.fixture
def sample_task() -> TaskItem:
    return TaskItem(task_id="T100", description="Do the thing", is_complete=False, tags=["demo"])


@pytest.fixture
def sample_phase(sample_task: TaskItem) -> PhaseDefinition:
    return PhaseDefinition(
        phase_id="phase-1",
        ordinal=1,
        title="Sample Phase",
        tasks=[sample_task],
        execution_hints=None,
        raw_markdown="## Phase 1: Sample Phase\n- [ ] T100 Do the thing",
    )


@pytest.fixture
def sample_phase_result() -> PhaseResult:
    started_at = datetime(2025, 11, 8, 12, 0, tzinfo=UTC)
    finished_at = started_at + timedelta(minutes=1)
    return PhaseResult(
        phase_id="phase-1",
        status="success",
        completed_task_ids=["T100"],
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=60_000,
        tasks_md_hash="deadbeef",
        stdout_path=None,
        stderr_path=None,
        artifact_paths=[],
        summary=["completed"],
        error=None,
    )


def test_phase_definition_requires_positive_ordinal(sample_phase: PhaseDefinition) -> None:
    with pytest.raises(ValueError, match="ordinal must be >= 1"):
        replace(sample_phase, ordinal=0)


def test_phase_definition_requires_matching_phase_id(sample_phase: PhaseDefinition) -> None:
    with pytest.raises(ValueError, match="phase_id must match ordinal"):
        replace(sample_phase, phase_id="phase-2")


def test_phase_definition_requires_title(sample_phase: PhaseDefinition) -> None:
    with pytest.raises(ValueError, match="title must be non-empty"):
        replace(sample_phase, title="   ")


def test_task_item_requires_valid_id(sample_task: TaskItem) -> None:
    with pytest.raises(ValueError, match="task_id must match pattern"):
        replace(sample_task, task_id="ABC123")


def test_task_item_requires_description(sample_task: TaskItem) -> None:
    with pytest.raises(ValueError, match="description must be non-empty"):
        replace(sample_task, description=" ")


def test_phase_execution_hints_requires_uppercase_env_keys() -> None:
    with pytest.raises(ValueError, match="extra_env keys must be uppercase"):
        PhaseExecutionHints(model=None, agent_profile=None, extra_env={"foo": "bar"})


def test_phase_execution_context_requires_exactly_one_tasks_source(sample_phase: PhaseDefinition) -> None:
    repo_path = Path("/tmp")

    with pytest.raises(ValueError, match="Provide exactly one of tasks_md_path or tasks_md_content"):
        PhaseExecutionContext(
            repo_path=str(repo_path),
            branch="main",
            tasks_md_path=str(repo_path / "tasks.md"),
            tasks_md_content="content",
            phase=sample_phase,
            checkpoint=None,
            timeout_minutes=30,
            hints=None,
        )

    with pytest.raises(ValueError, match="Provide exactly one of tasks_md_path or tasks_md_content"):
        PhaseExecutionContext(
            repo_path=str(repo_path),
            branch="main",
            tasks_md_path=None,
            tasks_md_content=None,
            phase=sample_phase,
            checkpoint=None,
            timeout_minutes=30,
            hints=None,
        )


def test_phase_execution_context_requires_absolute_repo_path(sample_phase: PhaseDefinition) -> None:
    repo_path = Path("relative/path")

    with pytest.raises(ValueError, match="repo_path must be absolute"):
        PhaseExecutionContext(
            repo_path=str(repo_path),
            branch="main",
            tasks_md_path=str(Path("/tmp/tasks.md")),
            tasks_md_content=None,
            phase=sample_phase,
            checkpoint=None,
            timeout_minutes=30,
            hints=None,
        )


def test_phase_execution_context_requires_timeout_floor(sample_phase: PhaseDefinition, tmp_path: Path) -> None:
    repo_path = tmp_path

    with pytest.raises(ValueError, match="timeout_minutes must be >= 30"):
        PhaseExecutionContext(
            repo_path=str(repo_path),
            branch="main",
            tasks_md_path=str(repo_path / "tasks.md"),
            tasks_md_content=None,
            phase=sample_phase,
            checkpoint=None,
            timeout_minutes=15,
            hints=None,
        )


def test_phase_result_requires_monotonic_timestamps(sample_phase_result: PhaseResult) -> None:
    with pytest.raises(ValueError, match="finished_at must be after started_at"):
        replace(
            sample_phase_result,
            finished_at=sample_phase_result.started_at - timedelta(seconds=1),
        )


def test_phase_result_requires_consistent_duration(sample_phase_result: PhaseResult) -> None:
    with pytest.raises(ValueError, match="duration_ms must equal elapsed time"):
        replace(sample_phase_result, duration_ms=1)


def test_phase_result_requires_error_when_failed(sample_phase_result: PhaseResult) -> None:
    with pytest.raises(ValueError, match="error must be provided when status='failed'"):
        replace(sample_phase_result, status="failed", error=None)


def test_workflow_checkpoint_requires_index_alignment(sample_phase_result: PhaseResult) -> None:
    with pytest.raises(ValueError, match="last_completed_phase_index"):
        WorkflowCheckpoint(
            last_completed_phase_index=2,
            results=[sample_phase_result],
            tasks_md_hash=sample_phase_result.tasks_md_hash,
            updated_at=sample_phase_result.finished_at,
        )


def test_workflow_checkpoint_requires_hash_alignment(sample_phase_result: PhaseResult) -> None:
    with pytest.raises(ValueError, match="tasks_md_hash must match latest result"):
        WorkflowCheckpoint(
            last_completed_phase_index=0,
            results=[sample_phase_result],
            tasks_md_hash="different",
            updated_at=sample_phase_result.finished_at,
        )


def test_resume_state_requires_matching_start_index(sample_phase: PhaseDefinition) -> None:
    with pytest.raises(ValueError, match="starting_phase_index must align with phases_to_run"):
        ResumeState(
            starting_phase_index=1,
            phases_to_run=[sample_phase],
            skipped_phase_ids=[],
            checkpoint=None,
        )


# PR Automation Models Tests


@pytest.fixture
def sample_polling_config() -> PollingConfiguration:
    return PollingConfiguration(
        interval_seconds=30,
        timeout_minutes=45,
        max_retries=5,
        backoff_coefficient=2.0,
    )


@pytest.fixture
def sample_pr_request(sample_polling_config: PollingConfiguration) -> PullRequestAutomationRequest:
    return PullRequestAutomationRequest(
        source_branch="feature/test",
        summary="Test PR summary",
        workflow_attempt_id="attempt-123",
        target_branch="main",
        polling=sample_polling_config,
        metadata={"key": "value"},
    )


@pytest.fixture
def sample_ci_failure() -> CiFailureDetail:
    return CiFailureDetail(
        job_name="test-job",
        attempt=1,
        status="failure",
        summary="Test failed",
        log_url="https://example.com/logs",
        completed_at=datetime(2025, 11, 8, 12, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_pr_result() -> PullRequestAutomationResult:
    return PullRequestAutomationResult(
        status="merged",
        polling_duration_seconds=120,
        pull_request_number=42,
        pull_request_url="https://github.com/test/repo/pull/42",
        merge_commit_sha="abc123",
        ci_failures=[],
        retry_advice=None,
        error_detail=None,
    )


def test_polling_configuration_requires_positive_interval() -> None:
    with pytest.raises(ValueError, match="interval_seconds must be >= 1"):
        PollingConfiguration(interval_seconds=0)


def test_polling_configuration_requires_positive_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_minutes must be >= 1"):
        PollingConfiguration(timeout_minutes=0)


def test_polling_configuration_requires_non_negative_retries() -> None:
    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        PollingConfiguration(max_retries=-1)


def test_polling_configuration_requires_valid_backoff() -> None:
    with pytest.raises(ValueError, match="backoff_coefficient must be >= 1.0"):
        PollingConfiguration(backoff_coefficient=0.5)


def test_ci_failure_detail_requires_job_name() -> None:
    with pytest.raises(ValueError, match="job_name must be non-empty"):
        CiFailureDetail(job_name="", attempt=1, status="failure")


def test_ci_failure_detail_requires_positive_attempt() -> None:
    with pytest.raises(ValueError, match="attempt must be >= 1"):
        CiFailureDetail(job_name="test", attempt=0, status="failure")


def test_ci_failure_detail_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="completed_at must be timezone-aware"):
        CiFailureDetail(
            job_name="test",
            attempt=1,
            status="failure",
            completed_at=datetime(2025, 11, 8, 12, 0),  # No timezone - intentionally testing validation  # noqa: DTZ001
        )


def test_pr_request_requires_source_branch() -> None:
    with pytest.raises(ValueError, match="source_branch must be non-empty"):
        PullRequestAutomationRequest(
            source_branch="",
            summary="test",
            workflow_attempt_id="attempt-123",
        )


def test_pr_request_requires_summary() -> None:
    with pytest.raises(ValueError, match="summary must be non-empty"):
        PullRequestAutomationRequest(
            source_branch="feature/test",
            summary="",
            workflow_attempt_id="attempt-123",
        )


def test_pr_request_requires_workflow_attempt_id() -> None:
    with pytest.raises(ValueError, match="workflow_attempt_id must be non-empty"):
        PullRequestAutomationRequest(
            source_branch="feature/test",
            summary="test",
            workflow_attempt_id="",
        )


def test_pr_request_requires_target_branch() -> None:
    with pytest.raises(ValueError, match="target_branch must be non-empty"):
        PullRequestAutomationRequest(
            source_branch="feature/test",
            summary="test",
            workflow_attempt_id="attempt-123",
            target_branch="",
        )


def test_pr_result_requires_non_negative_duration(sample_pr_result: PullRequestAutomationResult) -> None:
    with pytest.raises(ValueError, match="polling_duration_seconds must be >= 0"):
        replace(sample_pr_result, polling_duration_seconds=-1)


def test_pr_result_merged_requires_commit_sha() -> None:
    with pytest.raises(ValueError, match="merge_commit_sha must be provided"):
        PullRequestAutomationResult(
            status="merged",
            polling_duration_seconds=120,
            merge_commit_sha=None,  # Invalid for merged status
        )


def test_pr_result_ci_failed_requires_failures(sample_ci_failure: CiFailureDetail) -> None:
    with pytest.raises(ValueError, match="ci_failures must be non-empty"):
        PullRequestAutomationResult(
            status="ci_failed",
            polling_duration_seconds=120,
            ci_failures=[],  # Invalid for ci_failed status
        )

    # Valid case with failures
    result = PullRequestAutomationResult(
        status="ci_failed",
        polling_duration_seconds=120,
        ci_failures=[sample_ci_failure],
    )
    assert len(result.ci_failures) == 1


def test_pr_result_error_requires_detail() -> None:
    with pytest.raises(ValueError, match="error_detail must be provided"):
        PullRequestAutomationResult(
            status="error",
            polling_duration_seconds=120,
            error_detail=None,  # Invalid for error status
        )


def test_pr_result_immutable_ci_failures(sample_ci_failure: CiFailureDetail) -> None:
    result = PullRequestAutomationResult(
        status="ci_failed",
        polling_duration_seconds=120,
        ci_failures=[sample_ci_failure],
    )

    # Verify ci_failures is a tuple
    assert isinstance(result.ci_failures, tuple)
