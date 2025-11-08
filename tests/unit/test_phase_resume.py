"""Unit tests for resume planning and checkpoint drift handling."""

from datetime import UTC, datetime, timedelta

import pytest

from src.models.phase_automation import (
    PhaseDefinition,
    PhaseResult,
    ResumeState,
    TaskItem,
    WorkflowCheckpoint,
)
from src.utils.tasks_markdown import compute_tasks_md_hash


@pytest.fixture
def sample_phases() -> list[PhaseDefinition]:
    """Create sample phase definitions for testing."""
    return [
        PhaseDefinition(
            phase_id="phase-1",
            ordinal=1,
            title="Setup",
            tasks=(
                TaskItem(task_id="T001", description="Create fixture", is_complete=True, tags=()),
                TaskItem(task_id="T002", description="Add config", is_complete=True, tags=()),
            ),
            execution_hints=None,
            raw_markdown="## Phase 1: Setup\n- [X] T001 Create fixture\n- [X] T002 Add config",
        ),
        PhaseDefinition(
            phase_id="phase-2",
            ordinal=2,
            title="Core Implementation",
            tasks=(
                TaskItem(task_id="T003", description="Implement parser", is_complete=False, tags=()),
                TaskItem(task_id="T004", description="Add tests", is_complete=False, tags=()),
            ),
            execution_hints=None,
            raw_markdown="## Phase 2: Core Implementation\n- [ ] T003 Implement parser\n- [ ] T004 Add tests",
        ),
        PhaseDefinition(
            phase_id="phase-3",
            ordinal=3,
            title="Polish",
            tasks=(TaskItem(task_id="T005", description="Update docs", is_complete=False, tags=()),),
            execution_hints=None,
            raw_markdown="## Phase 3: Polish\n- [ ] T005 Update docs",
        ),
    ]


@pytest.fixture
def sample_checkpoint(sample_phases: list[PhaseDefinition]) -> WorkflowCheckpoint:
    """Create sample checkpoint for testing."""
    now = datetime.now(UTC)
    phase1 = sample_phases[0]
    tasks_content = "\n".join(p.raw_markdown for p in sample_phases)

    result1 = PhaseResult(
        phase_id=phase1.phase_id,
        status="success",
        completed_task_ids=tuple(t.task_id for t in phase1.tasks),
        started_at=now - timedelta(minutes=5),
        finished_at=now - timedelta(minutes=4),
        duration_ms=60000,
        tasks_md_hash=compute_tasks_md_hash(tasks_content),
        stdout_path="/logs/phase-1/stdout.log",
        stderr_path="/logs/phase-1/stderr.log",
        artifact_paths=(),
        summary=("Phase 1 completed successfully",),
    )

    return WorkflowCheckpoint(
        last_completed_phase_index=0,
        results=(result1,),
        tasks_md_hash=compute_tasks_md_hash(tasks_content),
        updated_at=now,
    )


class TestResumeStatePlanning:
    """Test resume state planning logic."""

    def test_plan_resume_from_checkpoint_no_drift(self, sample_phases, sample_checkpoint):
        """Test resume planning when checkpoint hash matches current content."""
        from src.workflows.phase_automation import plan_resume_from_checkpoint

        tasks_content = "\n".join(p.raw_markdown for p in sample_phases)
        current_hash = compute_tasks_md_hash(tasks_content)

        # Checkpoint hash matches current content
        assert sample_checkpoint.tasks_md_hash == current_hash

        resume_state = plan_resume_from_checkpoint(
            phases=sample_phases,
            checkpoint=sample_checkpoint,
            current_hash=current_hash,
        )

        # Should skip phase-1, start with phase-2
        assert resume_state.starting_phase_index == 1
        assert len(resume_state.phases_to_run) == 2
        assert resume_state.phases_to_run[0].phase_id == "phase-2"
        assert resume_state.phases_to_run[1].phase_id == "phase-3"
        assert resume_state.skipped_phase_ids == ("phase-1",)
        assert resume_state.checkpoint == sample_checkpoint

    def test_plan_resume_with_hash_drift(self, sample_phases, sample_checkpoint):
        """Test resume planning when checkpoint hash differs from current content."""
        from unittest.mock import patch

        from src.workflows.phase_automation import plan_resume_from_checkpoint

        # Modify phase content to create hash drift
        modified_phases = list(sample_phases)
        modified_phases[0] = PhaseDefinition(
            phase_id="phase-1",
            ordinal=1,
            title="Setup (Modified)",
            tasks=sample_phases[0].tasks,
            execution_hints=None,
            raw_markdown="## Phase 1: Setup (Modified)\n- [X] T001 Create fixture\n- [X] T002 Add config",
        )

        tasks_content = "\n".join(p.raw_markdown for p in modified_phases)
        current_hash = compute_tasks_md_hash(tasks_content)

        # Checkpoint hash should differ
        assert sample_checkpoint.tasks_md_hash != current_hash

        # Mock workflow.now() for the recalculate_checkpoint call
        mock_now = datetime.now(UTC)
        with patch("src.workflows.phase_automation.workflow") as mock_workflow:
            mock_workflow.now.return_value = mock_now

            resume_state = plan_resume_from_checkpoint(
                phases=modified_phases,
                checkpoint=sample_checkpoint,
                current_hash=current_hash,
            )

        # Should recalculate - phase-1 still complete, start with phase-2
        assert resume_state.starting_phase_index == 1
        assert len(resume_state.phases_to_run) == 2
        assert resume_state.skipped_phase_ids == ("phase-1",)
        # Checkpoint should be updated with new hash
        assert resume_state.checkpoint is not None
        assert resume_state.checkpoint.tasks_md_hash == current_hash

    def test_plan_resume_no_checkpoint(self, sample_phases):
        """Test resume planning with no existing checkpoint."""
        from src.workflows.phase_automation import plan_resume_from_checkpoint

        tasks_content = "\n".join(p.raw_markdown for p in sample_phases)
        current_hash = compute_tasks_md_hash(tasks_content)

        resume_state = plan_resume_from_checkpoint(
            phases=sample_phases,
            checkpoint=None,
            current_hash=current_hash,
        )

        # Should run all phases from the beginning
        assert resume_state.starting_phase_index == 0
        assert len(resume_state.phases_to_run) == 3
        assert resume_state.phases_to_run[0].phase_id == "phase-1"
        assert resume_state.skipped_phase_ids == ()
        assert resume_state.checkpoint is None

    def test_plan_resume_all_phases_complete(self, sample_phases):
        """Test resume planning when all phases already complete."""
        from src.workflows.phase_automation import plan_resume_from_checkpoint

        # Mark all tasks complete
        completed_phases = [
            PhaseDefinition(
                phase_id=phase.phase_id,
                ordinal=phase.ordinal,
                title=phase.title,
                tasks=tuple(
                    TaskItem(
                        task_id=t.task_id,
                        description=t.description,
                        is_complete=True,
                        tags=t.tags,
                    )
                    for t in phase.tasks
                ),
                execution_hints=phase.execution_hints,
                raw_markdown=phase.raw_markdown.replace("[ ]", "[X]"),
            )
            for phase in sample_phases
        ]

        tasks_content = "\n".join(p.raw_markdown for p in completed_phases)
        current_hash = compute_tasks_md_hash(tasks_content)

        now = datetime.now(UTC)
        results = []
        for idx, phase in enumerate(completed_phases):
            result = PhaseResult(
                phase_id=phase.phase_id,
                status="success",
                completed_task_ids=tuple(t.task_id for t in phase.tasks),
                started_at=now - timedelta(minutes=10 - idx),
                finished_at=now - timedelta(minutes=9 - idx),
                duration_ms=60000,
                tasks_md_hash=current_hash,
                stdout_path=f"/logs/{phase.phase_id}/stdout.log",
                stderr_path=f"/logs/{phase.phase_id}/stderr.log",
                artifact_paths=(),
                summary=(f"{phase.phase_id} completed",),
            )
            results.append(result)

        checkpoint = WorkflowCheckpoint(
            last_completed_phase_index=len(completed_phases) - 1,
            results=tuple(results),
            tasks_md_hash=current_hash,
            updated_at=now,
        )

        resume_state = plan_resume_from_checkpoint(
            phases=completed_phases,
            checkpoint=checkpoint,
            current_hash=current_hash,
        )

        # Should have no phases to run
        assert resume_state.starting_phase_index == 0
        assert len(resume_state.phases_to_run) == 0
        assert resume_state.skipped_phase_ids == ("phase-1", "phase-2", "phase-3")


class TestCheckpointRecalculation:
    """Test checkpoint recalculation on hash drift."""

    def test_recalculate_checkpoint_single_complete_phase(self, sample_phases):
        """Test recalculating checkpoint when first phase complete."""
        from src.workflows.phase_automation import _recalculate_checkpoint_impl

        tasks_content = "\n".join(p.raw_markdown for p in sample_phases)
        current_hash = compute_tasks_md_hash(tasks_content)
        now = datetime.now(UTC)

        checkpoint = _recalculate_checkpoint_impl(
            phases=sample_phases,
            current_hash=current_hash,
            now=now,
        )

        # Phase 1 is complete, should be reflected in checkpoint
        assert checkpoint.last_completed_phase_index == 0
        assert len(checkpoint.results) == 1
        assert checkpoint.results[0].phase_id == "phase-1"
        assert checkpoint.results[0].status == "success"
        assert checkpoint.tasks_md_hash == current_hash

    def test_recalculate_checkpoint_no_complete_phases(self, sample_phases):
        """Test recalculating checkpoint when no phases complete."""
        from src.workflows.phase_automation import _recalculate_checkpoint_impl

        # Mark all tasks incomplete
        incomplete_phases = [
            PhaseDefinition(
                phase_id=phase.phase_id,
                ordinal=phase.ordinal,
                title=phase.title,
                tasks=tuple(
                    TaskItem(
                        task_id=t.task_id,
                        description=t.description,
                        is_complete=False,
                        tags=t.tags,
                    )
                    for t in phase.tasks
                ),
                execution_hints=phase.execution_hints,
                raw_markdown=phase.raw_markdown.replace("[X]", "[ ]"),
            )
            for phase in sample_phases
        ]

        tasks_content = "\n".join(p.raw_markdown for p in incomplete_phases)
        current_hash = compute_tasks_md_hash(tasks_content)
        now = datetime.now(UTC)

        checkpoint = _recalculate_checkpoint_impl(
            phases=incomplete_phases,
            current_hash=current_hash,
            now=now,
        )

        # No phases complete
        assert checkpoint.last_completed_phase_index == -1
        assert len(checkpoint.results) == 0
        assert checkpoint.tasks_md_hash == current_hash

    def test_recalculate_checkpoint_partial_phase_not_counted(self, sample_phases):
        """Test that phases with incomplete tasks are not counted as complete."""
        from src.workflows.phase_automation import _recalculate_checkpoint_impl

        # Phase 2 has one complete task and one incomplete
        partial_phases = list(sample_phases)
        partial_phases[1] = PhaseDefinition(
            phase_id="phase-2",
            ordinal=2,
            title="Core Implementation",
            tasks=(
                TaskItem(task_id="T003", description="Implement parser", is_complete=True, tags=()),
                TaskItem(task_id="T004", description="Add tests", is_complete=False, tags=()),
            ),
            execution_hints=None,
            raw_markdown="## Phase 2: Core Implementation\n- [X] T003 Implement parser\n- [ ] T004 Add tests",
        )

        tasks_content = "\n".join(p.raw_markdown for p in partial_phases)
        current_hash = compute_tasks_md_hash(tasks_content)
        now = datetime.now(UTC)

        checkpoint = _recalculate_checkpoint_impl(
            phases=partial_phases,
            current_hash=current_hash,
            now=now,
        )

        # Only phase-1 is fully complete
        assert checkpoint.last_completed_phase_index == 0
        assert len(checkpoint.results) == 1


class TestResumeStateInvariants:
    """Test ResumeState dataclass validation."""

    def test_resume_state_requires_valid_starting_index(self, sample_phases):
        """Test that starting_phase_index must align with phases_to_run."""
        with pytest.raises(ValueError, match="starting_phase_index must align"):
            ResumeState(
                starting_phase_index=10,  # Out of bounds
                phases_to_run=sample_phases[1:],
                skipped_phase_ids=("phase-1",),
                checkpoint=None,
            )

    def test_resume_state_empty_phases_requires_zero_or_negative_index(self):
        """Test that empty phases_to_run requires starting_phase_index -1 or 0."""
        # -1 is valid
        resume = ResumeState(
            starting_phase_index=-1,
            phases_to_run=(),
            skipped_phase_ids=(),
            checkpoint=None,
        )
        assert resume.starting_phase_index == -1

        # 0 is valid
        resume = ResumeState(
            starting_phase_index=0,
            phases_to_run=(),
            skipped_phase_ids=(),
            checkpoint=None,
        )
        assert resume.starting_phase_index == 0

        # Other values invalid
        with pytest.raises(ValueError, match="starting_phase_index must be -1 or 0"):
            ResumeState(
                starting_phase_index=1,
                phases_to_run=(),
                skipped_phase_ids=(),
                checkpoint=None,
            )
