"""Workflow orchestrating sequential execution of Speckit phase tasks.

Logging Events (workflow.logger):
    - workflow_started: Workflow begins execution
    - phase_parsing_completed: tasks.md parsed into phases
    - resume_planning_completed: Resume state calculated from checkpoint
    - phase_activity_starting: About to execute phase activity
    - phase_result_persisted: Phase result saved to disk
    - phase_result_persistence_failed: Failed to save phase result (non-fatal)
    - phase_activity_completed: Phase activity finished
    - workflow_completed: Workflow finished successfully
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from temporalio import workflow


with workflow.unsafe.imports_passed_through():
    from src.activities.persist_phase_result import PersistPhaseResultRequest
    from src.activities.phase_tasks_parser import ParseTasksMdRequest, ParseTasksMdResult
    from src.models.phase_automation import (
        AutomatePhaseTasksParams,
        PhaseAutomationSummary,
        PhaseDefinition,
        PhaseExecutionContext,
        PhaseExecutionHints,
        PhaseResult,
        ResumeState,
        RetryPolicySettings,
        WorkflowCheckpoint,
    )
    from src.utils.tasks_markdown import is_phase_complete


def _merge_phase_hints(
    params: AutomatePhaseTasksParams,
    phase_hints: PhaseExecutionHints | None,
) -> PhaseExecutionHints | None:
    """Combine workflow defaults with metadata-provided hints."""

    model = None
    agent_profile = None
    extra_env: dict[str, str] = {}

    if phase_hints is not None:
        model = phase_hints.model
        agent_profile = phase_hints.agent_profile
        extra_env = dict(phase_hints.extra_env)

    if model is None:
        model = params.default_model
    if agent_profile is None:
        agent_profile = params.default_agent_profile

    if model is None and agent_profile is None and not extra_env:
        return None

    return PhaseExecutionHints(
        model=model,
        agent_profile=agent_profile,
        extra_env=extra_env,
    )


def _recalculate_checkpoint_impl(
    phases: list[PhaseDefinition],
    current_hash: str,
    now,
) -> WorkflowCheckpoint:
    """Internal implementation for checkpoint recalculation.

    Args:
        phases: List of phase definitions to check
        current_hash: Current tasks.md hash
        now: Current timestamp (from workflow.now() or datetime.now(UTC))
    """
    from datetime import timedelta as td

    completed_results: list[PhaseResult] = []

    for phase in phases:
        if not is_phase_complete(phase):
            break

        # Create synthetic result for completed phase
        # Use minimal time delta to satisfy finished_at > started_at invariant
        started_at = now
        finished_at = now + td(microseconds=1)
        result = PhaseResult(
            phase_id=phase.phase_id,
            status="success",
            completed_task_ids=tuple(task.task_id for task in phase.tasks),
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=0,
            tasks_md_hash=current_hash,
            stdout_path=None,
            stderr_path=None,
            artifact_paths=(),
            summary=("Phase already complete",),
        )
        completed_results.append(result)

    last_completed_index = len(completed_results) - 1

    return WorkflowCheckpoint(
        last_completed_phase_index=last_completed_index,
        results=tuple(completed_results),
        tasks_md_hash=current_hash,
        updated_at=now,
    )


def recalculate_checkpoint(
    phases: list[PhaseDefinition],
    current_hash: str,
) -> WorkflowCheckpoint:
    """Recalculate checkpoint based on current phase completion status.

    Used inside workflows when hash drift is detected to rebuild checkpoint
    state from the current tasks.md content.

    This function MUST be called from within a Temporal workflow context.
    """
    return _recalculate_checkpoint_impl(phases, current_hash, workflow.now())


def plan_resume_from_checkpoint(
    phases: list[PhaseDefinition],
    checkpoint: WorkflowCheckpoint | None,
    current_hash: str,
) -> ResumeState:
    """Plan workflow resume based on checkpoint and current content hash.

    Handles three scenarios:
    1. No checkpoint: Run all phases from beginning
    2. Checkpoint hash matches: Skip completed phases, resume from next
    3. Checkpoint hash differs: Recalculate based on current completion state
    """
    if checkpoint is None:
        # No checkpoint - run all phases
        return ResumeState(
            starting_phase_index=0,
            phases_to_run=tuple(phases),
            skipped_phase_ids=(),
            checkpoint=None,
        )

    if checkpoint.tasks_md_hash == current_hash:
        # Hash matches - trust checkpoint
        next_index = checkpoint.last_completed_phase_index + 1
        phases_to_run = phases[next_index:]
        skipped_ids = tuple(phase.phase_id for phase in phases[:next_index])

        return ResumeState(
            starting_phase_index=next_index if phases_to_run else 0,
            phases_to_run=tuple(phases_to_run),
            skipped_phase_ids=skipped_ids,
            checkpoint=checkpoint,
        )

    # Hash drift detected - recalculate checkpoint
    new_checkpoint = recalculate_checkpoint(phases, current_hash)
    next_index = new_checkpoint.last_completed_phase_index + 1
    phases_to_run = phases[next_index:]
    skipped_ids = tuple(phase.phase_id for phase in phases[:next_index])

    return ResumeState(
        starting_phase_index=next_index if phases_to_run else 0,
        phases_to_run=tuple(phases_to_run),
        skipped_phase_ids=skipped_ids,
        checkpoint=new_checkpoint,
    )


@workflow.defn(name="AutomatePhaseTasksWorkflow")
class AutomatePhaseTasksWorkflow:
    """Temporal workflow coordinating automated phase execution."""

    def __init__(self) -> None:
        self._checkpoint: WorkflowCheckpoint | None = None
        self._all_results: list[PhaseResult] = []
        self._persisted_paths: dict[str, str] = {}

    @workflow.query
    def get_phase_results(self) -> list[PhaseResult]:
        """Query handler to retrieve all phase results.

        Returns:
            List of PhaseResult objects for all executed phases
        """
        return self._all_results

    @workflow.query
    def get_persisted_paths(self) -> dict[str, str]:
        """Query handler to retrieve paths to persisted result files.

        Returns:
            Dictionary mapping phase_id to file path
        """
        return self._persisted_paths

    @workflow.run
    async def run(self, params: AutomatePhaseTasksParams) -> PhaseAutomationSummary:
        started_at = workflow.now()
        repo_path = Path(params.repo_path)
        tasks_md_path = Path(params.tasks_md_path) if params.tasks_md_path else None

        workflow.logger.info(
            "workflow_started",
            extra={
                "workflow_id": workflow.info().workflow_id,
                "run_id": workflow.info().run_id,
                "repo_path": str(repo_path),
                "branch": params.branch,
            },
        )

        parse_request = ParseTasksMdRequest(
            tasks_md_path=tasks_md_path,
            tasks_md_content=params.tasks_md_content,
        )

        parse_result: ParseTasksMdResult = await workflow.execute_activity(
            "parse_tasks_md",
            parse_request,
            start_to_close_timeout=timedelta(seconds=60),
            result_type=ParseTasksMdResult,
        )

        workflow.logger.info(
            "phase_parsing_completed",
            extra={
                "workflow_id": workflow.info().workflow_id,
                "phase_count": len(parse_result.phases),
            },
        )

        phases = list(parse_result.phases)
        current_hash = parse_result.tasks_md_hash

        # Plan resume based on checkpoint and current content
        resume_state = plan_resume_from_checkpoint(
            phases=phases,
            checkpoint=self._checkpoint,
            current_hash=current_hash,
        )

        # Log resume planning with checkpoint diagnostics
        checkpoint_status = "none"
        hash_matched = False
        if self._checkpoint is not None:
            checkpoint_status = "present"
            hash_matched = self._checkpoint.tasks_md_hash == current_hash

        workflow.logger.info(
            "resume_planning_completed",
            extra={
                "workflow_id": workflow.info().workflow_id,
                "starting_phase_index": resume_state.starting_phase_index,
                "phases_to_run": len(resume_state.phases_to_run),
                "skipped_phases": list(resume_state.skipped_phase_ids),
                "checkpoint_status": checkpoint_status,
                "hash_matched": hash_matched,
                "current_hash": current_hash[:12],  # First 12 chars for diagnostics
            },
        )

        # Update checkpoint with resume state
        if resume_state.checkpoint is not None:
            self._checkpoint = resume_state.checkpoint

        results: list[PhaseResult] = []
        if self._checkpoint:
            results.extend(self._checkpoint.results)

        skipped_phase_ids: list[str] = list(resume_state.skipped_phase_ids)
        policy_settings = params.retry_policy
        if policy_settings is None:
            raise ValueError("retry_policy must be provided in workflow parameters")
        if isinstance(policy_settings, RetryPolicySettings):
            base_retry_policy = policy_settings.to_retry_policy()
        else:
            base_retry_policy = policy_settings

        for phase in resume_state.phases_to_run:
            effective_hints = _merge_phase_hints(params, phase.execution_hints)
            retry_policy = base_retry_policy

            parsed_path = Path(parse_result.source_path) if parse_result.source_path else None

            context = PhaseExecutionContext(
                repo_path=str(repo_path),
                branch=params.branch,
                tasks_md_path=str(parsed_path) if parsed_path is not None else None,
                tasks_md_content=None if parsed_path is not None else parse_result.source_content,
                phase=phase,
                checkpoint=self._checkpoint,
                timeout_minutes=params.timeout_minutes,
                hints=effective_hints,
            )

            # Log phase activity start with execution hints
            hints_info = None
            if effective_hints:
                hints_info = {
                    "model": effective_hints.model,
                    "agent_profile": effective_hints.agent_profile,
                    "extra_env_keys": list(effective_hints.extra_env.keys()) if effective_hints.extra_env else [],
                }

            workflow.logger.info(
                "phase_activity_starting",
                extra={
                    "workflow_id": workflow.info().workflow_id,
                    "phase_id": phase.phase_id,
                    "task_count": len(phase.tasks),
                    "timeout_minutes": params.timeout_minutes,
                    "execution_hints": hints_info,
                },
            )

            result: PhaseResult = await workflow.execute_activity(
                "run_phase",
                context,
                start_to_close_timeout=timedelta(minutes=params.timeout_minutes),
                retry_policy=retry_policy,
                result_type=PhaseResult,
            )

            results.append(result)
            self._all_results.append(result)

            # Persist phase result to disk (non-blocking, fire-and-forget)
            persist_request = PersistPhaseResultRequest(
                workflow_id=workflow.info().workflow_id,
                phase_result=result,
                results_base_dir="/tmp/phase-results",
            )

            try:
                persisted_path: str = await workflow.execute_activity(
                    "persist_phase_result",
                    persist_request,
                    start_to_close_timeout=timedelta(seconds=30),
                    result_type=str,
                )
                self._persisted_paths[result.phase_id] = persisted_path

                workflow.logger.info(
                    "phase_result_persisted",
                    extra={
                        "workflow_id": workflow.info().workflow_id,
                        "phase_id": result.phase_id,
                        "persisted_path": persisted_path,
                    },
                )
            except Exception as persist_error:
                # Log persistence failure but don't fail the workflow
                workflow.logger.warning(
                    "phase_result_persistence_failed",
                    extra={
                        "workflow_id": workflow.info().workflow_id,
                        "phase_id": result.phase_id,
                        "error": str(persist_error),
                    },
                )

            # Update checkpoint after successful phase completion
            if result.status == "success":
                phase_index = phases.index(phase)
                self._checkpoint = WorkflowCheckpoint(
                    last_completed_phase_index=phase_index,
                    results=tuple(results),
                    tasks_md_hash=result.tasks_md_hash,
                    updated_at=workflow.now(),
                )

            workflow.logger.info(
                "phase_activity_completed",
                extra={
                    "workflow_id": workflow.info().workflow_id,
                    "phase_id": result.phase_id,
                    "status": result.status,
                },
            )

            if result.status == "skipped":
                skipped_phase_ids.append(result.phase_id)

        finished_at = workflow.now()
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        tasks_md_hash = results[-1].tasks_md_hash if results else parse_result.tasks_md_hash

        summary = PhaseAutomationSummary(
            results=results,
            skipped_phase_ids=skipped_phase_ids,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tasks_md_hash=tasks_md_hash,
        )

        workflow.logger.info(
            "workflow_completed",
            extra={
                "workflow_id": workflow.info().workflow_id,
                "run_id": workflow.info().run_id,
                "duration_ms": duration_ms,
                "completed_phases": [result.phase_id for result in results],
            },
        )

        return summary


__all__ = ["AutomatePhaseTasksWorkflow"]
