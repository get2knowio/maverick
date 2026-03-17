"""Runway consolidation action.

Distills old episodic records into a semantic markdown summary via an
AI agent, then prunes the JSONL files to keep only recent records.

Best-effort — consolidation failure never raises to the caller.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from maverick.library.actions.types import RunwayConsolidationResult
from maverick.logging import get_logger
from maverick.runway.models import BeadOutcome, FixAttemptRecord, RunwayReviewFinding
from maverick.runway.store import RunwayStore

__all__ = ["consolidate_runway"]

logger = get_logger(__name__)

# Semantic file name for the consolidated summary
_INSIGHTS_FILE = "consolidated-insights.md"


def _get_store(cwd: str | Path | None) -> RunwayStore | None:
    """Resolve runway store from cwd. Returns None if not initialized."""
    base = Path(cwd) if cwd else Path.cwd()
    runway_path = base / ".maverick" / "runway"
    store = RunwayStore(runway_path)
    if not store.is_initialized:
        return None
    return store


def _parse_timestamp(ts: str) -> datetime | None:
    """Parse an ISO timestamp string. Returns None on failure."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _partition_outcomes(
    outcomes: list[BeadOutcome],
    cutoff: datetime,
    max_keep: int,
) -> tuple[list[BeadOutcome], list[BeadOutcome]]:
    """Split outcomes into (keep, consolidate) lists.

    Records older than cutoff go to consolidate. If still over max_keep,
    the oldest records go to consolidate.

    Args:
        outcomes: All bead outcomes.
        cutoff: Records older than this are consolidated.
        max_keep: Maximum records to keep.

    Returns:
        Tuple of (keep, to_consolidate).
    """
    keep: list[BeadOutcome] = []
    consolidate: list[BeadOutcome] = []

    for o in outcomes:
        ts = _parse_timestamp(o.timestamp)
        if ts is None or ts < cutoff:
            consolidate.append(o)
        else:
            keep.append(o)

    # If still over limit, move oldest keep records to consolidate
    if len(keep) > max_keep:
        # Sort by timestamp ascending (oldest first)
        keep.sort(key=lambda x: x.timestamp)
        excess = keep[: len(keep) - max_keep]
        keep = keep[len(keep) - max_keep :]
        consolidate.extend(excess)

    return keep, consolidate


def _partition_findings(
    findings: list[RunwayReviewFinding],
    cutoff_bead_ids: set[str],
    max_keep: int,
) -> tuple[list[RunwayReviewFinding], list[RunwayReviewFinding]]:
    """Split findings based on which beads are being consolidated.

    Findings belonging to consolidated beads go to the consolidate set.
    If still over max_keep, oldest (by position) are consolidated.

    Args:
        findings: All review findings.
        cutoff_bead_ids: Bead IDs that are being consolidated.
        max_keep: Maximum records to keep.

    Returns:
        Tuple of (keep, to_consolidate).
    """
    keep: list[RunwayReviewFinding] = []
    consolidate: list[RunwayReviewFinding] = []

    for f in findings:
        if f.bead_id in cutoff_bead_ids:
            consolidate.append(f)
        else:
            keep.append(f)

    if len(keep) > max_keep:
        excess = keep[: len(keep) - max_keep]
        keep = keep[len(keep) - max_keep :]
        consolidate.extend(excess)

    return keep, consolidate


def _partition_attempts(
    attempts: list[FixAttemptRecord],
    cutoff_bead_ids: set[str],
    max_keep: int,
) -> tuple[list[FixAttemptRecord], list[FixAttemptRecord]]:
    """Split fix attempts based on which beads are being consolidated.

    Args:
        attempts: All fix attempts.
        cutoff_bead_ids: Bead IDs that are being consolidated.
        max_keep: Maximum records to keep.

    Returns:
        Tuple of (keep, to_consolidate).
    """
    keep: list[FixAttemptRecord] = []
    consolidate: list[FixAttemptRecord] = []

    for a in attempts:
        if a.bead_id in cutoff_bead_ids:
            consolidate.append(a)
        else:
            keep.append(a)

    if len(keep) > max_keep:
        excess = keep[: len(keep) - max_keep]
        keep = keep[len(keep) - max_keep :]
        consolidate.extend(excess)

    return keep, consolidate


async def _synthesize_summary(
    store: RunwayStore,
    to_consolidate_outcomes: list[dict[str, Any]],
    to_consolidate_findings: list[dict[str, Any]],
    to_consolidate_attempts: list[dict[str, Any]],
) -> bool:
    """Run the ConsolidatorAgent to produce an updated summary.

    Args:
        store: RunwayStore for reading/writing semantic files.
        to_consolidate_outcomes: Serialized outcomes to consolidate.
        to_consolidate_findings: Serialized findings to consolidate.
        to_consolidate_attempts: Serialized fix attempts to consolidate.

    Returns:
        True if summary was updated, False on failure.
    """
    from maverick.agents.generators.consolidator import ConsolidatorAgent
    from maverick.executor import create_default_executor

    existing_summary = await store.read_semantic_file(_INSIGHTS_FILE)

    agent = ConsolidatorAgent()
    executor = create_default_executor()
    try:
        result = await executor.execute(
            step_name="consolidate",
            agent_name=agent.name,
            prompt={
                "existing_summary": existing_summary,
                "bead_outcomes": to_consolidate_outcomes,
                "review_findings": to_consolidate_findings,
                "fix_attempts": to_consolidate_attempts,
            },
        )
        raw_output = str(result.output) if result.output else ""
    finally:
        await executor.cleanup()

    if not raw_output.strip():
        logger.warning("consolidator_empty_output")
        return False

    summary = agent.parse_summary(raw_output)
    await store.write_semantic_file(_INSIGHTS_FILE, summary)
    return True


async def consolidate_runway(
    *,
    cwd: str | Path | None = None,
    max_age_days: int = 90,
    max_records: int = 500,
    force: bool = False,
) -> RunwayConsolidationResult:
    """Consolidate old runway episodic records into semantic summaries.

    Reads all episodic JSONL files, partitions records into "keep" (recent)
    and "to_consolidate" (old/excess), runs an AI agent to synthesize the
    to_consolidate records into ``consolidated-insights.md``, then rewrites
    the JSONL files with only the kept records.

    Best-effort — catches all exceptions and returns a result.

    Args:
        cwd: Working directory for runway store resolution.
        max_age_days: Records older than this are consolidated.
        max_records: Maximum total records to keep per file.
        force: Run even if below thresholds.

    Returns:
        RunwayConsolidationResult with outcome details.
    """
    try:
        store = _get_store(cwd)
        if store is None:
            return RunwayConsolidationResult(
                success=True,
                records_pruned=0,
                summary_updated=False,
                skipped=True,
                skip_reason="Runway not initialized",
                error=None,
            )

        # Read all records
        outcomes = await store.get_bead_outcomes()
        findings = await store.get_review_findings()
        attempts = await store.get_fix_attempts()

        total_records = len(outcomes) + len(findings) + len(attempts)

        # Check thresholds
        cutoff = datetime.now() - timedelta(days=max_age_days)
        has_old = any(
            (_parse_timestamp(o.timestamp) or datetime.min) < cutoff for o in outcomes
        )

        if not force and total_records < max_records and not has_old:
            return RunwayConsolidationResult(
                success=True,
                records_pruned=0,
                summary_updated=False,
                skipped=True,
                skip_reason=(
                    f"Below thresholds ({total_records} records, none older "
                    f"than {max_age_days} days)"
                ),
                error=None,
            )

        # Per-file max is total max (records are spread across 3 files)
        per_file_max = max(max_records // 3, 10)

        # Partition records
        keep_outcomes, consolidate_outcomes = _partition_outcomes(
            outcomes, cutoff, per_file_max
        )
        consolidated_bead_ids = {o.bead_id for o in consolidate_outcomes}

        keep_findings, consolidate_findings = _partition_findings(
            findings, consolidated_bead_ids, per_file_max
        )
        keep_attempts, consolidate_attempts = _partition_attempts(
            attempts, consolidated_bead_ids, per_file_max
        )

        records_pruned = (
            len(consolidate_outcomes)
            + len(consolidate_findings)
            + len(consolidate_attempts)
        )

        if records_pruned == 0 and not force:
            return RunwayConsolidationResult(
                success=True,
                records_pruned=0,
                summary_updated=False,
                skipped=True,
                skip_reason="No records to consolidate after partitioning",
                error=None,
            )

        # Synthesize summary (best-effort).
        # When forced (e.g. workspace about to be torn down), synthesize
        # from ALL records even if none are "old" — the data will be lost
        # otherwise.  The summary captures the knowledge permanently.
        summary_updated = False
        if force and records_pruned == 0:
            # Nothing to prune, but synthesize from all records
            synthesis_outcomes = [o.to_dict() for o in outcomes]
            synthesis_findings = [f.to_dict() for f in findings]
            synthesis_attempts = [a.to_dict() for a in attempts]
        else:
            synthesis_outcomes = (
                [o.to_dict() for o in consolidate_outcomes]
                if consolidate_outcomes
                else []
            )
            synthesis_findings = (
                [f.to_dict() for f in consolidate_findings]
                if consolidate_findings
                else []
            )
            synthesis_attempts = (
                [a.to_dict() for a in consolidate_attempts]
                if consolidate_attempts
                else []
            )

        has_data = synthesis_outcomes or synthesis_findings or synthesis_attempts
        if has_data:
            try:
                summary_updated = await _synthesize_summary(
                    store,
                    synthesis_outcomes,
                    synthesis_findings,
                    synthesis_attempts,
                )
            except Exception as exc:
                logger.warning(
                    "consolidation_synthesis_failed",
                    error=str(exc),
                )
                # Continue to pruning even if synthesis fails

        # Prune records
        await store.rewrite_bead_outcomes(keep_outcomes)
        await store.rewrite_review_findings(keep_findings)
        await store.rewrite_fix_attempts(keep_attempts)

        # Update index
        index = await store.read_index()
        updated_index = index.model_copy(
            update={
                "last_consolidated": datetime.now().isoformat(),
                "episodic_counts": {
                    "bead-outcomes": len(keep_outcomes),
                    "review-findings": len(keep_findings),
                    "fix-attempts": len(keep_attempts),
                },
            }
        )
        await store.write_index(updated_index)

        return RunwayConsolidationResult(
            success=True,
            records_pruned=records_pruned,
            summary_updated=summary_updated,
            skipped=False,
            skip_reason=None,
            error=None,
        )

    except Exception as exc:
        logger.warning("consolidation_failed", error=str(exc))
        return RunwayConsolidationResult(
            success=False,
            records_pruned=0,
            summary_updated=False,
            skipped=False,
            skip_reason=None,
            error=str(exc),
        )
