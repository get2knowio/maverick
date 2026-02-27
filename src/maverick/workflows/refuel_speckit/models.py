"""Result types for RefuelSpeckitWorkflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RefuelSpeckitResult:
    """Final output from the RefuelSpeckitWorkflow.

    Attributes:
        epic: Epic bead info dict (None if creation failed).
        work_beads: Tuple of created work bead dicts.
        dependencies: Tuple of wired dependency dicts.
        errors: Tuple of error strings encountered during execution.
        commit: Commit SHA string if committed (None in dry_run or on failure).
        merge: Merge commit SHA string if merged (None in dry_run or on failure).
    """

    epic: dict[str, Any] | None
    work_beads: tuple[dict[str, Any], ...]
    dependencies: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]
    commit: str | None
    merge: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dictionary for WorkflowResult.final_output.

        Returns:
            Dict with all result fields.
        """
        return {
            "epic": self.epic,
            "work_beads": list(self.work_beads),
            "dependencies": list(self.dependencies),
            "errors": list(self.errors),
            "commit": self.commit,
            "merge": self.merge,
        }
