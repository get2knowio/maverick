"""Data models for FlyBeadsWorkflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maverick.library.actions.types import VerifyBeadCompletionResult


@dataclass
class BeadContext:
    """Per-bead execution context threaded through step functions.

    Mutable because it accumulates results step-by-step.
    Short-lived (one per bead iteration). Not serialised to checkpoints.
    """

    bead_id: str
    title: str
    description: str
    epic_id: str
    cwd: Path | None
    run_dir: Path | None = None
    flight_plan_name: str = ""
    operation_id: str | None = None
    briefing_context: str | None = None
    runway_context: str | None = None
    prior_failures: list[str] = field(default_factory=list)
    prior_attempt_context: str | None = None
    discovered_from_chain: list[str] = field(default_factory=list)

    # Populated by step functions as pipeline progresses
    validation_result: dict[str, Any] | None = None
    review_result: dict[str, Any] | None = None
    verify_result: VerifyBeadCompletionResult | None = None
    gate_result: dict[str, Any] | None = None
    remediation_attempted: bool = False

    # Escalation tracking (set by resolve_provenance)
    escalation_depth: int = 0
    human_review_tag: str | None = None


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
    human_review_items: tuple[dict[str, Any], ...] = ()

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
            "human_review_items": list(self.human_review_items),
        }
