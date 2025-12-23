"""DSL mapping and utilities for the Fly Workflow.

This module defines constants and helpers for translating between
DSL step names and Fly workflow stages, as well as task file parsing.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from maverick.workflows.fly.models import WorkflowStage


class DslStepName(str, Enum):
    """DSL step names used in fly.yaml workflow definition.

    Maps step names from the YAML workflow to standardized constants,
    preventing magic strings in event translation logic.
    """

    INIT = "init"
    INIT_DRY_RUN = "init_dry_run"
    IMPLEMENT = "implement"
    VALIDATE_AND_FIX = "validate_and_fix"
    COMMIT_AND_PUSH = "commit_and_push"
    REVIEW = "review"
    CREATE_PR = "create_pr"

    def __str__(self) -> str:
        """Return the lowercase string value."""
        return self.value


# Mapping from DSL step names to workflow stages
DSL_STEP_TO_STAGE: dict[str, WorkflowStage] = {
    DslStepName.INIT.value: WorkflowStage.INIT,
    DslStepName.INIT_DRY_RUN.value: WorkflowStage.INIT,
    DslStepName.IMPLEMENT.value: WorkflowStage.IMPLEMENTATION,
    DslStepName.VALIDATE_AND_FIX.value: WorkflowStage.VALIDATION,
    DslStepName.COMMIT_AND_PUSH.value: WorkflowStage.PR_CREATION,
    DslStepName.REVIEW.value: WorkflowStage.CODE_REVIEW,
    DslStepName.CREATE_PR.value: WorkflowStage.PR_CREATION,
}


def get_phase_names(task_file: str | Path) -> list[str]:
    """Extract ordered phase names from a tasks.md file.

    This helper function is used by the DSL workflow to iterate over phases,
    enabling phase-level task execution where Claude handles parallelization
    of [P] marked tasks within each phase.

    Args:
        task_file: Path to the tasks.md file.

    Returns:
        List of phase names in the order they appear in the file.

    Raises:
        FileNotFoundError: If task_file doesn't exist.
        TaskParseError: If file format is invalid.

    Example:
        >>> phases = get_phase_names("specs/001/tasks.md")
        >>> phases
        ['Phase 1: Setup', 'Phase 2: Core', 'Phase 3: Integration']
    """
    from maverick.models.implementation import TaskFile

    path = Path(task_file) if isinstance(task_file, str) else task_file
    task_file_obj = TaskFile.parse(path)
    return list(task_file_obj.phases.keys())


__all__ = [
    "DslStepName",
    "DSL_STEP_TO_STAGE",
    "get_phase_names",
]
