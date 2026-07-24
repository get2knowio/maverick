"""Models for SpeckitRefuelWorkflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SpeckitRefuelResult:
    """Final output from SpeckitRefuelWorkflow.

    Mirrors ``RefuelMaverickResult.to_dict()`` conventions
    (``workflows/refuel_maverick/models.py``).

    Attributes:
        feature_name: Resolved feature directory basename.
        epic_id: Real bead ID, or ``"dry-run-epic"`` on a dry run.
        created_bead_ids: Task bead IDs created this run.
        skipped_completed: Task IDs checked ``[x]`` (not ingested).
        skipped_existing: Task IDs already ingested under the epic (delta).
        edge_count: Number of dependency edges wired.
        delta_run: Whether an existing epic was adopted.
        dry_run: Whether this run performed zero writes.
        enriched: Whether ``--enrich`` succeeded for this run.
        warnings: Non-fatal warnings collected during the run.
        adopted_remediation_bead_ids: Standalone `spec-remediation` beads
            (from a prior `maverick spec` run) adopted under this epic
            (R6 post-ingest adoption step).
    """

    feature_name: str
    epic_id: str
    created_bead_ids: tuple[str, ...] = field(default=())
    skipped_completed: tuple[str, ...] = field(default=())
    skipped_existing: tuple[str, ...] = field(default=())
    edge_count: int = 0
    delta_run: bool = False
    dry_run: bool = False
    enriched: bool = False
    warnings: tuple[str, ...] = field(default=())
    adopted_remediation_bead_ids: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dictionary for WorkflowResult.final_output."""
        return {
            "feature_name": self.feature_name,
            "epic_id": self.epic_id,
            "created_bead_ids": list(self.created_bead_ids),
            "skipped_completed": list(self.skipped_completed),
            "skipped_existing": list(self.skipped_existing),
            "edge_count": self.edge_count,
            "delta_run": self.delta_run,
            "dry_run": self.dry_run,
            "enriched": self.enriched,
            "warnings": list(self.warnings),
            "adopted_remediation_bead_ids": list(self.adopted_remediation_bead_ids),
        }


__all__ = ["SpeckitRefuelResult"]
