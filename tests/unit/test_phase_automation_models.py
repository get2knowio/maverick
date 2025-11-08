"""Unit tests for phase automation dataclasses invariants."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.models.phase_automation import (
    PhaseDefinition,
    PhaseExecutionContext,
    PhaseExecutionHints,
    PhaseResult,
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
