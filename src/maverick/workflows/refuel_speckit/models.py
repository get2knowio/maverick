"""Result types for RefuelSpeckitWorkflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RefuelSpeckitResult:
    """Final output from the RefuelSpeckitWorkflow.

    Attributes:
        epic: Epic bead info dict (None if creation failed).
        work_beads: List of created work bead dicts.
        dependencies: List of wired dependency dicts.
        errors: List of error strings encountered during execution.
        commit: Commit SHA string if committed (None in dry_run or on failure).
        merge: Merge commit SHA string if merged (None in dry_run or on failure).
    """

    epic: dict[str, Any] | None
    work_beads: list[dict[str, Any]]
    dependencies: list[dict[str, Any]]
    errors: list[str]
    commit: str | None
    merge: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dictionary for WorkflowResult.final_output.

        Returns:
            Dict with all result fields.
        """
        return {
            "epic": self.epic,
            "work_beads": self.work_beads,
            "dependencies": self.dependencies,
            "errors": self.errors,
            "commit": self.commit,
            "merge": self.merge,
        }
