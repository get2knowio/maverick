"""RefuelReport — structured record of a refuel workflow run.

Captures outcome, phase completion, and bead creation for a refuel run.
Written on every run termination (success or failure) to give post-run
analysis, resume logic, and runway learning a single authoritative
artifact to consume — mirroring the fly_report pattern for beads.

Written to: .maverick/runs/{run_id}/refuel-report.json
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RefuelReport:
    """Complete record of a refuel workflow run.

    Attributes:
        plan_name: Flight plan identifier (kebab-case).
        flight_plan_path: Absolute path to the flight plan markdown file.
        run_id: Unique identifier for this run (matches .maverick/runs/<run_id>).
        outcome: "refueled" when beads were created, "failed" otherwise.
        started_at: ISO 8601 timestamp.
        completed_at: ISO 8601 timestamp.
        duration_seconds: Wall-clock run time.
        skip_briefing: Whether briefing was skipped on this run.
        phases_completed: Ordered names of phases that completed successfully.
        work_units_count: Number of work units produced by decomposition.
        fix_rounds: Number of validation-fix iterations executed.
        epic_id: Bead epic ID created (None on failure before bead creation).
        work_bead_ids: Bead IDs created under the epic.
        error: Error message if the run failed.
    """

    plan_name: str
    flight_plan_path: str
    run_id: str
    outcome: str
    started_at: str
    completed_at: str
    duration_seconds: float
    skip_briefing: bool
    phases_completed: list[str] = field(default_factory=list)
    work_units_count: int = 0
    fix_rounds: int = 0
    epic_id: str | None = None
    work_bead_ids: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def write_refuel_report(report: RefuelReport, run_dir: Path) -> Path:
    """Write the refuel report to the run directory.

    Args:
        report: The complete refuel report.
        run_dir: .maverick/runs/{run_id}/ directory.

    Returns:
        Path to the written report file.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "refuel-report.json"
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    logger.info(
        "refuel_report.written",
        run_id=report.run_id,
        plan=report.plan_name,
        path=str(report_path),
        outcome=report.outcome,
        phases=len(report.phases_completed),
        work_units=report.work_units_count,
    )
    return report_path
