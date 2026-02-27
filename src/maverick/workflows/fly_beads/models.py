"""Data models for FlyBeadsWorkflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FlyBeadsResult:
    """Typed result returned by FlyBeadsWorkflow._run().

    Attributes:
        epic_id: Epic filter used for this run (empty string means no filter).
        workspace_path: Path to the hidden jj workspace, or None for dry-run.
        beads_processed: Total number of bead attempts (succeeded + failed + skipped).
        beads_succeeded: Number of beads successfully completed and committed.
        beads_failed: Number of beads that failed verification or threw an error.
        beads_skipped: Number of beads skipped due to checkpoint resume.
    """

    epic_id: str
    workspace_path: str | None
    beads_processed: int
    beads_succeeded: int
    beads_failed: int
    beads_skipped: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for DSL output.

        Returns:
            Dict matching the FlyBeadsWorkflow output contract.
        """
        return {
            "epic_id": self.epic_id,
            "workspace_path": self.workspace_path,
            "beads_processed": self.beads_processed,
            "beads_succeeded": self.beads_succeeded,
            "beads_failed": self.beads_failed,
            "beads_skipped": self.beads_skipped,
        }
