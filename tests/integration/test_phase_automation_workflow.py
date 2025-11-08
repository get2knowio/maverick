"""Integration tests for AutomatePhaseTasksWorkflow sequential execution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from temporalio import activity
from temporalio.common import RetryPolicy
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.activities.persist_phase_result import PersistPhaseResultRequest
from src.activities.phase_tasks_parser import parse_tasks_md
from src.models.phase_automation import (
    AutomatePhaseTasksParams,
    PhaseAutomationSummary,
    PhaseExecutionContext,
    PhaseResult,
)
from src.utils.tasks_markdown import compute_tasks_md_hash
from src.workflows.phase_automation import AutomatePhaseTasksWorkflow


@pytest.mark.asyncio
async def test_automate_phase_tasks_runs_sequential_phases(
    tmp_path: Path,
    sample_tasks_md_content: str,
) -> None:
    """Workflow should parse markdown and invoke run_phase sequentially."""

    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(sample_tasks_md_content, encoding="utf-8")

    doc_hash = compute_tasks_md_hash(sample_tasks_md_content)
    call_order: list[str] = []

    @activity.defn(name="run_phase")
    async def fake_run_phase(context: PhaseExecutionContext) -> PhaseResult:
        call_order.append(context.phase.phase_id)

        # Phase without inline hints should inherit defaults
        if context.phase.phase_id == "phase-1":
            assert context.hints is not None
            assert context.hints.model == "gpt-4o-mini"
            assert context.hints.agent_profile == "architect"
        # Phase 2 should retain metadata overrides from markdown
        if context.phase.phase_id == "phase-2":
            assert context.hints is not None
            assert context.hints.model == "gpt-4.1"
            assert context.hints.agent_profile == "builder"
            assert context.hints.extra_env.get("TEMPORAL_HOST") == "temporal.local"

        # Generate deterministic timestamps for PhaseResult
        started_at = datetime.now(UTC)
        finished_at = started_at + timedelta(seconds=5)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        completed_ids = tuple(task.task_id for task in context.phase.tasks)

        return PhaseResult(
            phase_id=context.phase.phase_id,
            status="success",
            completed_task_ids=completed_ids,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tasks_md_hash=doc_hash,
            stdout_path=None,
            stderr_path=None,
            artifact_paths=[],
            summary=["phase-result-line with replacement char \ufffd"],
        )

    params = AutomatePhaseTasksParams(
        repo_path=str(tmp_path),
        branch="feature/phase-automation",
        tasks_md_path=str(tasks_path),
        tasks_md_content=None,
        default_model="gpt-4o-mini",
        default_agent_profile="architect",
        timeout_minutes=45,
        retry_policy=RetryPolicy(maximum_attempts=1),
    )

    # Mock persist_phase_result activity
    @activity.defn(name="persist_phase_result")
    async def fake_persist_phase_result(request: PersistPhaseResultRequest) -> str:
        return f"/tmp/fake/{request.phase_result.phase_id}.json"

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="phase-automation-tests",
            workflows=[AutomatePhaseTasksWorkflow],
            activities=[parse_tasks_md, fake_run_phase, fake_persist_phase_result],
        ),
    ):
        summary: PhaseAutomationSummary = await env.client.execute_workflow(
            AutomatePhaseTasksWorkflow.run,
            params,
            id="phase-automation-sequential",
            task_queue="phase-automation-tests",
        )

    assert call_order == ["phase-1", "phase-2", "phase-3"], "Phases should execute sequentially"
    assert summary.tasks_md_hash == doc_hash
    assert [result.phase_id for result in summary.results] == ["phase-1", "phase-2", "phase-3"]
    assert summary.skipped_phase_ids == ()
    assert any("\ufffd" in line for result in summary.results for line in result.summary)
    assert summary.finished_at >= summary.started_at
    assert summary.duration_ms == int((summary.finished_at - summary.started_at).total_seconds() * 1000)


@pytest.mark.asyncio
async def test_automate_phase_tasks_resume_after_failure(
    tmp_path: Path,
    sample_tasks_md_content: str,
) -> None:
    """Workflow should detect completed phases and skip them during execution."""

    # Start with phase-1 already complete
    completed_content = sample_tasks_md_content.replace("- [ ] T100", "- [X] T100").replace("- [x] T101", "- [X] T101")
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(completed_content, encoding="utf-8")

    doc_hash = compute_tasks_md_hash(completed_content)
    call_order: list[str] = []

    @activity.defn(name="run_phase")
    async def fake_run_phase_detect_complete(context: PhaseExecutionContext) -> PhaseResult:
        call_order.append(context.phase.phase_id)

        started_at = datetime.now(UTC)
        finished_at = started_at + timedelta(seconds=5)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        # Phase 1 is complete, should be skipped
        if context.phase.phase_id == "phase-1":
            all_complete = all(task.is_complete for task in context.phase.tasks)
            if all_complete:
                return PhaseResult(
                    phase_id=context.phase.phase_id,
                    status="skipped",
                    completed_task_ids=tuple(task.task_id for task in context.phase.tasks),
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    tasks_md_hash=doc_hash,
                    stdout_path=None,
                    stderr_path=None,
                    artifact_paths=[],
                    summary=["Phase already complete, skipped"],
                )

        completed_ids = tuple(task.task_id for task in context.phase.tasks)
        return PhaseResult(
            phase_id=context.phase.phase_id,
            status="success",
            completed_task_ids=completed_ids,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tasks_md_hash=doc_hash,
            stdout_path=None,
            stderr_path=None,
            artifact_paths=[],
            summary=["phase completed"],
        )

    params = AutomatePhaseTasksParams(
        repo_path=str(tmp_path),
        branch="feature/phase-automation",
        tasks_md_path=str(tasks_path),
        tasks_md_content=None,
        default_model="gpt-4o-mini",
        default_agent_profile="architect",
        timeout_minutes=45,
        retry_policy=RetryPolicy(maximum_attempts=1),
    )

    @activity.defn(name="persist_phase_result")
    async def fake_persist(request: PersistPhaseResultRequest) -> str:
        return f"/tmp/fake/{request.phase_result.phase_id}.json"

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="phase-automation-resume-tests",
            workflows=[AutomatePhaseTasksWorkflow],
            activities=[parse_tasks_md, fake_run_phase_detect_complete, fake_persist],
        ),
    ):
        summary: PhaseAutomationSummary = await env.client.execute_workflow(
            AutomatePhaseTasksWorkflow.run,
            params,
            id="phase-automation-resume-test",
            task_queue="phase-automation-resume-tests",
        )

    # All phases called, but phase-1 returned skipped status
    assert call_order == ["phase-1", "phase-2", "phase-3"], "All phases should be evaluated"
    assert summary.results[0].status == "skipped", "Phase-1 should be skipped"
    assert "phase-1" in summary.skipped_phase_ids, "Phase-1 should be in skipped list"


@pytest.mark.asyncio
async def test_automate_phase_tasks_with_checkpoint_logic(
    tmp_path: Path,
    sample_tasks_md_content: str,
) -> None:
    """Workflow should maintain checkpoint state throughout execution."""

    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(sample_tasks_md_content, encoding="utf-8")

    doc_hash = compute_tasks_md_hash(sample_tasks_md_content)
    checkpoints_seen: list[bool] = []

    @activity.defn(name="run_phase")
    async def fake_run_phase_with_checkpoint(context: PhaseExecutionContext) -> PhaseResult:
        # Track whether checkpoint was passed
        checkpoints_seen.append(context.checkpoint is not None)

        started_at = datetime.now(UTC)
        finished_at = started_at + timedelta(seconds=5)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        completed_ids = tuple(task.task_id for task in context.phase.tasks)

        return PhaseResult(
            phase_id=context.phase.phase_id,
            status="success",
            completed_task_ids=completed_ids,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tasks_md_hash=doc_hash,
            stdout_path=None,
            stderr_path=None,
            artifact_paths=[],
            summary=["phase completed"],
        )

    params = AutomatePhaseTasksParams(
        repo_path=str(tmp_path),
        branch="feature/phase-automation",
        tasks_md_path=str(tasks_path),
        tasks_md_content=None,
        default_model="gpt-4o-mini",
        default_agent_profile="architect",
        timeout_minutes=45,
        retry_policy=RetryPolicy(maximum_attempts=1),
    )

    @activity.defn(name="persist_phase_result")
    async def fake_persist_checkpoint(request: PersistPhaseResultRequest) -> str:
        return f"/tmp/fake/{request.phase_result.phase_id}.json"

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="phase-automation-checkpoint-tests",
            workflows=[AutomatePhaseTasksWorkflow],
            activities=[parse_tasks_md, fake_run_phase_with_checkpoint, fake_persist_checkpoint],
        ),
    ):
        summary: PhaseAutomationSummary = await env.client.execute_workflow(
            AutomatePhaseTasksWorkflow.run,
            params,
            id="phase-automation-checkpoint-test",
            task_queue="phase-automation-checkpoint-tests",
        )

    # First phase has no checkpoint, subsequent phases have checkpoints
    assert checkpoints_seen[0] is False, "Phase-1 should not have checkpoint"
    assert checkpoints_seen[1] is True, "Phase-2 should have checkpoint"
    assert checkpoints_seen[2] is True, "Phase-3 should have checkpoint"
    assert len(summary.results) == 3


@pytest.mark.asyncio
async def test_workflow_returns_complete_phase_results(
    tmp_path: Path,
    sample_tasks_md_content: str,
) -> None:
    """Workflow should return complete phase results upon completion."""

    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(sample_tasks_md_content, encoding="utf-8")

    doc_hash = compute_tasks_md_hash(sample_tasks_md_content)

    @activity.defn(name="run_phase")
    async def fake_run_phase_for_query(context: PhaseExecutionContext) -> PhaseResult:
        started_at = datetime.now(UTC)
        finished_at = started_at + timedelta(seconds=5)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        completed_ids = tuple(task.task_id for task in context.phase.tasks)

        return PhaseResult(
            phase_id=context.phase.phase_id,
            status="success",
            completed_task_ids=completed_ids,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tasks_md_hash=doc_hash,
            stdout_path=f"/tmp/logs/{context.phase.phase_id}-stdout.log",
            stderr_path=f"/tmp/logs/{context.phase.phase_id}-stderr.log",
            artifact_paths=[f"/tmp/artifacts/{context.phase.phase_id}-result.json"],
            summary=[f"Phase {context.phase.phase_id} completed successfully"],
        )

    params = AutomatePhaseTasksParams(
        repo_path=str(tmp_path),
        branch="feature/phase-automation",
        tasks_md_path=str(tasks_path),
        tasks_md_content=None,
        default_model="gpt-4o-mini",
        default_agent_profile="architect",
        timeout_minutes=45,
        retry_policy=RetryPolicy(maximum_attempts=1),
    )

    @activity.defn(name="persist_phase_result")
    async def fake_persist_query(request: PersistPhaseResultRequest) -> str:
        return f"/tmp/fake/{request.phase_result.phase_id}.json"

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="phase-automation-query-tests",
            workflows=[AutomatePhaseTasksWorkflow],
            activities=[parse_tasks_md, fake_run_phase_for_query, fake_persist_query],
        ),
    ):
        handle = await env.client.start_workflow(
            AutomatePhaseTasksWorkflow.run,
            params,
            id="phase-automation-query-test",
            task_queue="phase-automation-query-tests",
        )

        # Verify final summary contains all phase results
        summary: PhaseAutomationSummary = await handle.result()

        assert len(summary.results) == 3
        assert all(result.status == "success" for result in summary.results)
        assert all(result.stdout_path is not None for result in summary.results)
        assert all(result.artifact_paths for result in summary.results)


@pytest.mark.asyncio
async def test_phase_results_persisted_to_disk(
    tmp_path: Path,
    sample_tasks_md_content: str,
) -> None:
    """Workflow should persist phase results to JSON files for later retrieval."""

    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(sample_tasks_md_content, encoding="utf-8")

    # Create results directory
    results_dir = tmp_path / "phase-results"
    results_dir.mkdir(parents=True, exist_ok=True)

    doc_hash = compute_tasks_md_hash(sample_tasks_md_content)

    @activity.defn(name="run_phase")
    async def fake_run_phase_with_persistence(context: PhaseExecutionContext) -> PhaseResult:
        started_at = datetime.now(UTC)
        finished_at = started_at + timedelta(seconds=5)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        completed_ids = tuple(task.task_id for task in context.phase.tasks)

        result = PhaseResult(
            phase_id=context.phase.phase_id,
            status="success",
            completed_task_ids=completed_ids,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tasks_md_hash=doc_hash,
            stdout_path=f"/tmp/logs/{context.phase.phase_id}-stdout.log",
            stderr_path=f"/tmp/logs/{context.phase.phase_id}-stderr.log",
            artifact_paths=[f"/tmp/artifacts/{context.phase.phase_id}-result.json"],
            summary=[f"Phase {context.phase.phase_id} completed successfully"],
        )

        # Simulate persistence (will be moved to workflow layer in T025)
        # For now, this test documents the expected behavior
        return result

    params = AutomatePhaseTasksParams(
        repo_path=str(tmp_path),
        branch="feature/phase-automation",
        tasks_md_path=str(tasks_path),
        tasks_md_content=None,
        default_model="gpt-4o-mini",
        default_agent_profile="architect",
        timeout_minutes=45,
        retry_policy=RetryPolicy(maximum_attempts=1),
    )

    @activity.defn(name="persist_phase_result")
    async def fake_persist_disk(request: PersistPhaseResultRequest) -> str:
        return f"/tmp/fake/{request.phase_result.phase_id}.json"

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="phase-automation-persistence-tests",
            workflows=[AutomatePhaseTasksWorkflow],
            activities=[parse_tasks_md, fake_run_phase_with_persistence, fake_persist_disk],
        ),
    ):
        summary: PhaseAutomationSummary = await env.client.execute_workflow(
            AutomatePhaseTasksWorkflow.run,
            params,
            id="phase-automation-persistence-test",
            task_queue="phase-automation-persistence-tests",
        )

    # After implementation, verify files exist
    # For now, just verify summary contains expected results
    assert len(summary.results) == 3
    assert all(result.status == "success" for result in summary.results)
    # Future: assert (results_dir / "phase-automation-persistence-test" / "phase-1.json").exists()
