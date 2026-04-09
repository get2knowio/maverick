"""FlyReport — structured record of a bead's processing.

The fly report captures the complete message exchange at bead
completion.  It replaces the scattered attempt snapshots, review
findings JSONL, and bead-outcomes JSONL with a single structured
document per bead.

Written to: .maverick/runs/{run_id}/beads/{bead_id}/fly-report.json

Consumed by ``maverick land`` for runway consolidation and
process-level learning.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from maverick.logging import get_logger
from maverick.workflows.fly_beads.supervisor import BeadOutcome

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FlyReport:
    """Complete record of a bead's processing through the actor pipeline.

    Attributes:
        bead_id: The bead that was processed.
        title: Human-readable bead title.
        epic_id: Parent epic identifier.
        outcome: "committed", "committed-needs-review", or "abandoned".
        started_at: ISO 8601 timestamp.
        completed_at: ISO 8601 timestamp.
        duration_seconds: Wall-clock processing time.
        messages: Serialized message exchange (complete log).
        gate_attempts: Number of gate fix cycles.
        review_rounds: Number of review-fix negotiation rounds.
        total_messages: Count of all messages exchanged.
        findings_trajectory: Review finding counts per round.
        commit_sha: jj change ID if committed.
        files_changed: List of files modified by this bead.
        human_review_tag: Set if needs human attention.
    """

    bead_id: str
    title: str
    epic_id: str
    outcome: str
    started_at: str
    completed_at: str
    duration_seconds: float
    messages: list[dict[str, Any]]
    gate_attempts: int
    review_rounds: int
    total_messages: int
    findings_trajectory: list[int]
    commit_sha: str | None
    files_changed: list[str]
    human_review_tag: str | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return asdict(self)


def build_fly_report(
    *,
    bead_outcome: BeadOutcome,
    title: str,
    epic_id: str,
    started_at: str,
) -> FlyReport:
    """Build a FlyReport from a BeadOutcome and metadata.

    Args:
        bead_outcome: The supervisor's processing result.
        title: Human-readable bead title.
        epic_id: Parent epic.
        started_at: ISO timestamp when processing began.

    Returns:
        Complete FlyReport ready for serialization.
    """
    now = datetime.now(tz=UTC).isoformat()

    if bead_outcome.committed and not bead_outcome.needs_human_review:
        outcome = "committed"
    elif bead_outcome.committed and bead_outcome.needs_human_review:
        outcome = "committed-needs-review"
    else:
        outcome = "abandoned"

    return FlyReport(
        bead_id=bead_outcome.bead_id,
        title=title,
        epic_id=epic_id,
        outcome=outcome,
        started_at=started_at,
        completed_at=now,
        duration_seconds=bead_outcome.duration_seconds,
        messages=[m.to_dict() for m in bead_outcome.message_log],
        gate_attempts=bead_outcome.gate_attempts,
        review_rounds=bead_outcome.review_rounds,
        total_messages=len(bead_outcome.message_log),
        findings_trajectory=bead_outcome.findings_trajectory,
        commit_sha=bead_outcome.commit_sha,
        files_changed=bead_outcome.files_changed,
        human_review_tag=("needs-human-review" if bead_outcome.needs_human_review else None),
    )


async def write_fly_report(
    report: FlyReport,
    run_dir: Path,
) -> Path:
    """Write the fly report to the run directory.

    Args:
        report: The complete fly report.
        run_dir: .maverick/runs/{run_id}/ directory.

    Returns:
        Path to the written report file.
    """
    bead_dir = run_dir / "beads" / report.bead_id
    bead_dir.mkdir(parents=True, exist_ok=True)

    report_path = bead_dir / "fly-report.json"
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )

    logger.info(
        "fly_report.written",
        bead_id=report.bead_id,
        path=str(report_path),
        outcome=report.outcome,
        messages=report.total_messages,
        review_rounds=report.review_rounds,
    )
    return report_path
