"""Runway recording actions for workflow integration.

Best-effort recording — failures are caught and returned in the result,
never raised to the caller.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from maverick.library.actions.types import (
    RecordBeadOutcomeResult,
    RecordFixAttemptResult,
    RecordReviewFindingsResult,
)
from maverick.logging import get_logger
from maverick.runway.models import BeadOutcome, FixAttemptRecord, RunwayReviewFinding
from maverick.runway.store import RunwayStore

__all__ = [
    "record_bead_outcome",
    "record_fix_attempt",
    "record_review_findings",
]

logger = get_logger(__name__)


def _get_store(cwd: str | Path | None) -> RunwayStore | None:
    """Resolve runway store from cwd. Returns None if not initialized."""
    base = Path(cwd) if cwd else Path.cwd()
    runway_path = base / ".maverick" / "runway"
    store = RunwayStore(runway_path)
    if not store.is_initialized:
        return None
    return store


async def record_bead_outcome(
    *,
    bead_id: str,
    epic_id: str,
    title: str = "",
    flight_plan: str = "",
    files_changed: list[str] | None = None,
    validation_result: dict[str, Any] | None = None,
    review_result: dict[str, Any] | None = None,
    key_decisions: list[str] | None = None,
    mistakes_caught: list[str] | None = None,
    cwd: str | Path | None = None,
) -> RecordBeadOutcomeResult:
    """Record a bead outcome to the runway store.

    Args:
        bead_id: Unique bead identifier.
        epic_id: Parent epic identifier.
        title: Bead title.
        flight_plan: Originating flight plan name.
        files_changed: Files modified during this bead.
        validation_result: Validation result dict.
        review_result: Review result dict.
        key_decisions: Notable decisions made.
        mistakes_caught: Mistakes identified.
        cwd: Working directory for runway store resolution.

    Returns:
        RecordBeadOutcomeResult with success status.
    """
    try:
        store = _get_store(cwd)
        if store is None:
            return RecordBeadOutcomeResult(
                success=False,
                bead_id=bead_id,
                error="Runway not initialized",
            )

        validation_passed = False
        if validation_result:
            validation_passed = bool(validation_result.get("passed", False))

        review_findings_count = 0
        review_fixed_count = 0
        if review_result:
            review_findings_count = int(review_result.get("issues_found", 0))
            review_fixed_count = int(review_result.get("issues_fixed", 0))

        outcome = BeadOutcome(
            bead_id=bead_id,
            epic_id=epic_id,
            flight_plan=flight_plan,
            title=title,
            files_changed=files_changed or [],
            validation_passed=validation_passed,
            review_findings_count=review_findings_count,
            review_fixed_count=review_fixed_count,
            key_decisions=key_decisions or [],
            mistakes_caught=mistakes_caught or [],
        )
        await store.append_bead_outcome(outcome)
        logger.info("runway_bead_outcome_recorded", bead_id=bead_id)
        return RecordBeadOutcomeResult(success=True, bead_id=bead_id, error=None)
    except Exception as exc:
        logger.warning(
            "runway_bead_outcome_failed",
            bead_id=bead_id,
            error=str(exc),
        )
        return RecordBeadOutcomeResult(success=False, bead_id=bead_id, error=str(exc))


async def record_review_findings(
    *,
    bead_id: str,
    review_result: dict[str, Any],
    cwd: str | Path | None = None,
) -> RecordReviewFindingsResult:
    """Record review findings to the runway store.

    Extracts findings from the review result dict and appends each as a
    RunwayReviewFinding record.

    Args:
        bead_id: Bead the review was for.
        review_result: Review result dict (from review-and-fix workflow).
        cwd: Working directory for runway store resolution.

    Returns:
        RecordReviewFindingsResult with count of findings recorded.
    """
    try:
        store = _get_store(cwd)
        if store is None:
            return RecordReviewFindingsResult(
                success=False, findings_recorded=0, error="Runway not initialized"
            )

        # Extract findings from various review result formats
        findings_data: list[dict[str, Any]] = []

        # Try grouped format (from GroupedReviewResult)
        groups = review_result.get("groups", [])
        for group in groups:
            for finding in group.get("findings", []):
                findings_data.append(finding)

        # Try flat issues_fixed / issues_remaining format
        for issue in review_result.get("issues_fixed", []):
            if isinstance(issue, dict):
                findings_data.append(issue)
        for issue in review_result.get("issues_remaining", []):
            if isinstance(issue, dict):
                findings_data.append(issue)

        count = 0
        for fd in findings_data:
            finding = RunwayReviewFinding(
                finding_id=fd.get("id", fd.get("issue_id", str(uuid.uuid4())[:8])),
                bead_id=bead_id,
                reviewer=fd.get("reviewer", ""),
                severity=fd.get("severity", ""),
                category=fd.get("category", ""),
                file_path=fd.get("file", fd.get("file_path", "")),
                description=fd.get("issue", fd.get("description", "")),
                resolution=fd.get("outcome", fd.get("resolution", "")),
            )
            await store.append_review_finding(finding)
            count += 1

        logger.info(
            "runway_review_findings_recorded",
            bead_id=bead_id,
            count=count,
        )
        return RecordReviewFindingsResult(
            success=True, findings_recorded=count, error=None
        )
    except Exception as exc:
        logger.warning(
            "runway_review_findings_failed",
            bead_id=bead_id,
            error=str(exc),
        )
        return RecordReviewFindingsResult(
            success=False, findings_recorded=0, error=str(exc)
        )


async def record_fix_attempt(
    *,
    finding_id: str,
    bead_id: str,
    approach: str = "",
    succeeded: bool = False,
    failure_reason: str = "",
    cwd: str | Path | None = None,
) -> RecordFixAttemptResult:
    """Record a fix attempt to the runway store.

    Args:
        finding_id: Finding this attempt addressed.
        bead_id: Bead during which the attempt was made.
        approach: Description of the fix approach.
        succeeded: Whether the fix succeeded.
        failure_reason: Reason for failure.
        cwd: Working directory for runway store resolution.

    Returns:
        RecordFixAttemptResult with success status.
    """
    attempt_id = str(uuid.uuid4())[:8]
    try:
        store = _get_store(cwd)
        if store is None:
            return RecordFixAttemptResult(
                success=False, attempt_id=attempt_id, error="Runway not initialized"
            )

        attempt = FixAttemptRecord(
            attempt_id=attempt_id,
            finding_id=finding_id,
            bead_id=bead_id,
            approach=approach,
            succeeded=succeeded,
            failure_reason=failure_reason,
        )
        await store.append_fix_attempt(attempt)
        logger.info(
            "runway_fix_attempt_recorded",
            finding_id=finding_id,
            attempt_id=attempt_id,
        )
        return RecordFixAttemptResult(success=True, attempt_id=attempt_id, error=None)
    except Exception as exc:
        logger.warning(
            "runway_fix_attempt_failed",
            finding_id=finding_id,
            error=str(exc),
        )
        return RecordFixAttemptResult(
            success=False, attempt_id=attempt_id, error=str(exc)
        )
