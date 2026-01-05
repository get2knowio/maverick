"""Registry management actions for the review-fix accountability loop.

This module provides actions for managing the IssueRegistry throughout the
review-fix workflow lifecycle. Actions handle creation, updates, exit conditions,
and GitHub issue creation for deferred/blocked findings.

Actions:
- create_issue_registry: Create registry from reviewer findings
- prepare_fixer_input: Convert registry to fixer agent input
- update_issue_registry: Update registry with fixer results
- check_fix_loop_exit: Check if fix loop should exit
- create_tech_debt_issues: Create GitHub issues for unresolved findings
- detect_deleted_files: Auto-block findings referencing deleted files
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from tenacity import (
    AsyncRetrying,
    stop_after_attempt,
    wait_exponential,
)

from maverick.exceptions import GitHubError
from maverick.library.actions.types import TechDebtIssueResult
from maverick.logging import get_logger
from maverick.models.fixer_io import (
    FixerInput,
    FixerInputItem,
    FixerOutput,
    FixerOutputItem,
)
from maverick.models.review_registry import (
    FindingCategory,
    FindingStatus,
    FixAttempt,
    IssueRegistry,
    ReviewFinding,
    Severity,
    TrackedFinding,
)
from maverick.utils.github_client import GitHubClient

logger = get_logger(__name__)

# =============================================================================
# FR-004: Weak Justification Detection
# =============================================================================

# Invalid justification patterns that indicate weak excuses.
# These are normalized (lowercase) and checked via substring matching.
INVALID_JUSTIFICATION_PATTERNS: tuple[str, ...] = (
    "unrelated to the current changes",
    "would take too long",
    "out of scope",
    "pre-existing issue",
    "requires significant refactoring",
    "don't have enough context",
    "too complex",
    "should be done in a separate pr",
    "not my change",
    "takes too long",
)


def is_weak_justification(justification: str | None) -> bool:
    """Check if a justification matches known weak excuse patterns.

    Uses case-insensitive substring matching against INVALID_JUSTIFICATION_PATTERNS.

    Args:
        justification: The justification string to check.

    Returns:
        True if the justification matches a weak excuse pattern, False otherwise.
    """
    if not justification:
        return False

    normalized = justification.lower()
    return any(pattern in normalized for pattern in INVALID_JUSTIFICATION_PATTERNS)


@dataclass
class JustificationValidationResult:
    """Result of validating a fixer justification.

    Attributes:
        is_valid: Whether the justification is acceptable.
        is_weak: Whether the justification matches a weak excuse pattern.
        message: Human-readable explanation of the validation result.
        should_requeue: Whether the finding should be re-queued as pending.
    """

    is_valid: bool
    is_weak: bool
    message: str
    should_requeue: bool


def validate_justification(
    status: str,
    justification: str | None,
) -> JustificationValidationResult:
    """Validate a fixer's justification for blocked/deferred status.

    Per FR-004 spec requirements:
    - For deferred: weak justifications are rejected and the finding is re-queued
    - For blocked: weak justifications get a warning but remain blocked
      (legitimate technical blocks can use similar words)

    Args:
        status: The status reported by the fixer (fixed, blocked, deferred).
        justification: The justification provided for blocked/deferred.

    Returns:
        JustificationValidationResult with validation outcome.
    """
    # Fixed status doesn't need justification validation
    if status == "fixed":
        return JustificationValidationResult(
            is_valid=True,
            is_weak=False,
            message="Status is fixed, no justification validation needed",
            should_requeue=False,
        )

    # Check for weak justification patterns
    is_weak = is_weak_justification(justification)

    if status == "deferred":
        if is_weak:
            return JustificationValidationResult(
                is_valid=False,
                is_weak=True,
                message=(
                    f"Deferred justification rejected as weak excuse: "
                    f"'{justification}'. Finding will be re-queued."
                ),
                should_requeue=True,
            )
        return JustificationValidationResult(
            is_valid=True,
            is_weak=False,
            message="Deferred with acceptable justification",
            should_requeue=False,
        )

    if status == "blocked":
        if is_weak:
            # For blocked: warn but keep blocked (legitimate technical blocks
            # can use similar words)
            return JustificationValidationResult(
                is_valid=True,  # Still valid, just flagged
                is_weak=True,
                message=(
                    f"Warning: Blocked justification matches weak excuse pattern: "
                    f"'{justification}'. Keeping as blocked but flagging for review."
                ),
                should_requeue=False,
            )
        return JustificationValidationResult(
            is_valid=True,
            is_weak=False,
            message="Blocked with valid technical justification",
            should_requeue=False,
        )

    # Unknown status - pass through
    return JustificationValidationResult(
        is_valid=True,
        is_weak=False,
        message=f"Unknown status '{status}', passing through",
        should_requeue=False,
    )


# =============================================================================
# T014: create_issue_registry
# =============================================================================


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Edit distance between the strings
    """
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))

    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Calculate insertions, deletions, and substitutions
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def _normalized_levenshtein(s1: str, s2: str) -> float:
    """Calculate normalized Levenshtein distance.

    Returns 0.0 for identical strings, 1.0 for completely different.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Normalized distance between 0.0 and 1.0
    """
    if not s1 and not s2:
        return 0.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 0.0
    return _levenshtein_distance(s1, s2) / max_len


def _lines_overlap(
    line1_start: int | None,
    line1_end: int | None,
    line2_start: int | None,
    line2_end: int | None,
    tolerance: int = 5,
) -> bool:
    """Check if two line ranges overlap within tolerance.

    Args:
        line1_start: Start of first range
        line1_end: End of first range
        line2_start: Start of second range
        line2_end: End of second range
        tolerance: Number of lines of slack for "overlapping"

    Returns:
        True if ranges overlap within tolerance
    """
    # If either range is not specified, consider them overlapping (conservative)
    if line1_start is None or line2_start is None:
        return True

    # Use start as end if end not specified
    l1_end = line1_end if line1_end is not None else line1_start
    l2_end = line2_end if line2_end is not None else line2_start

    # Expand ranges by tolerance
    l1_start_expanded = line1_start - tolerance
    l1_end_expanded = l1_end + tolerance
    l2_start_expanded = line2_start - tolerance
    l2_end_expanded = l2_end + tolerance

    # Check for overlap: ranges overlap if neither is entirely before the other
    left_is_before = l1_end_expanded < l2_start_expanded
    right_is_before = l2_end_expanded < l1_start_expanded
    return not (left_is_before or right_is_before)


def _is_duplicate(
    finding1: ReviewFinding,
    finding2: ReviewFinding,
    title_threshold: float = 0.3,
    line_tolerance: int = 5,
) -> bool:
    """Check if two findings are duplicates.

    Deduplication criteria:
    - Same file + overlapping line range (within tolerance)
    - Similar title (normalized Levenshtein distance below threshold)

    Args:
        finding1: First finding
        finding2: Second finding
        title_threshold: Maximum normalized Levenshtein distance for similar titles
        line_tolerance: Line range tolerance for overlap

    Returns:
        True if findings are considered duplicates
    """
    # Must be in same file (None means general issue - only dedupe if both None)
    if finding1.file_path != finding2.file_path:
        return False

    # Check line overlap
    if not _lines_overlap(
        finding1.line_start,
        finding1.line_end,
        finding2.line_start,
        finding2.line_end,
        line_tolerance,
    ):
        return False

    # Check title similarity
    title_distance = _normalized_levenshtein(
        finding1.title.lower(), finding2.title.lower()
    )
    return title_distance < title_threshold


def _parse_finding_from_dict(
    data: dict[str, Any],
    source: str,
    id_prefix: str,
    index: int,
) -> ReviewFinding:
    """Parse a finding dict into a ReviewFinding.

    Args:
        data: Finding data dictionary
        source: Source of the finding (spec_reviewer or tech_reviewer)
        id_prefix: Prefix for generated ID (RS for spec, RT for tech)
        index: Index for ID generation

    Returns:
        ReviewFinding instance
    """
    # Parse severity with fallback
    severity_str = data.get("severity", "minor")
    try:
        severity = Severity(severity_str.lower())
    except ValueError:
        severity = Severity.minor

    # Parse category with fallback
    category_str = data.get("category", "correctness")
    try:
        category = FindingCategory(category_str.lower())
    except ValueError:
        category = FindingCategory.correctness

    # Generate ID if not provided
    finding_id = data.get("id") or f"{id_prefix}{index:03d}"

    return ReviewFinding(
        id=finding_id,
        severity=severity,
        category=category,
        title=data.get("title", "Untitled finding"),
        description=data.get("description", ""),
        file_path=data.get("file_path"),
        line_start=data.get("line_start"),
        line_end=data.get("line_end"),
        suggested_fix=data.get("suggested_fix"),
        source=source,
    )


async def create_issue_registry(
    spec_findings: list[dict[str, Any]],
    tech_findings: list[dict[str, Any]],
    max_iterations: int = 3,
) -> IssueRegistry:
    """Create an IssueRegistry from reviewer findings.

    Merges findings from both reviewers, deduplicates, and initializes tracking.

    Deduplication logic:
    - Same file + overlapping line range (within 5 lines)
    - Similar title (normalized Levenshtein distance < 0.3)
    - Keep higher severity when merging

    Args:
        spec_findings: Findings from spec reviewer (list of dicts)
        tech_findings: Findings from tech reviewer (list of dicts)
        max_iterations: Maximum fix loop iterations

    Returns:
        Initialized IssueRegistry with TrackedFinding entries
    """
    logger.info(
        "Creating issue registry from %d spec + %d tech findings",
        len(spec_findings),
        len(tech_findings),
    )

    # Parse spec findings
    parsed_spec: list[ReviewFinding] = []
    for i, data in enumerate(spec_findings, start=1):
        try:
            finding = _parse_finding_from_dict(data, "spec_reviewer", "RS", i)
            parsed_spec.append(finding)
        except Exception as e:
            logger.warning("Failed to parse spec finding %d: %s", i, e)

    # Parse tech findings
    parsed_tech: list[ReviewFinding] = []
    for i, data in enumerate(tech_findings, start=1):
        try:
            finding = _parse_finding_from_dict(data, "tech_reviewer", "RT", i)
            parsed_tech.append(finding)
        except Exception as e:
            logger.warning("Failed to parse tech finding %d: %s", i, e)

    # Combine all findings
    all_findings = parsed_spec + parsed_tech

    # Deduplicate
    deduplicated: list[ReviewFinding] = []
    for finding in all_findings:
        is_dup = False
        for i, existing in enumerate(deduplicated):
            if _is_duplicate(finding, existing):
                is_dup = True
                # Keep higher severity
                severity_order = [Severity.critical, Severity.major, Severity.minor]
                if severity_order.index(finding.severity) < severity_order.index(
                    existing.severity
                ):
                    deduplicated[i] = finding
                logger.debug(
                    "Deduplicating finding '%s' with '%s'",
                    finding.title[:30],
                    existing.title[:30],
                )
                break
        if not is_dup:
            deduplicated.append(finding)

    logger.info(
        "Registry created with %d findings (%d deduplicated)",
        len(deduplicated),
        len(all_findings) - len(deduplicated),
    )

    # Create tracked findings
    tracked = [TrackedFinding(finding=f) for f in deduplicated]

    return IssueRegistry(
        findings=tracked,
        current_iteration=0,
        max_iterations=max_iterations,
    )


# =============================================================================
# T015: prepare_fixer_input
# =============================================================================


async def prepare_fixer_input(
    registry: IssueRegistry,
    context: str = "",
) -> FixerInput:
    """Prepare input for the fixer agent.

    Filters registry to actionable findings and formats for fixer.

    Args:
        registry: Current issue registry
        context: Additional context for fixer

    Returns:
        FixerInput with all actionable items
    """
    actionable = registry.get_actionable()

    logger.info(
        "Preparing fixer input for %d actionable findings (iteration %d)",
        len(actionable),
        registry.current_iteration + 1,
    )

    items: list[FixerInputItem] = []
    for tracked in actionable:
        finding = tracked.finding

        # Build previous attempts tuple
        prev_attempts = tuple(
            {
                "iteration": a.iteration,
                "outcome": a.outcome.value,
                "justification": a.justification,
                "changes_made": a.changes_made,
            }
            for a in tracked.attempts
        )

        # Build line range
        line_range: tuple[int, int] | None = None
        if finding.line_start is not None:
            line_end = (
                finding.line_end if finding.line_end is not None else finding.line_start
            )
            line_range = (finding.line_start, line_end)

        item = FixerInputItem(
            finding_id=finding.id,
            severity=finding.severity.value,
            title=finding.title,
            description=finding.description,
            file_path=finding.file_path,
            line_range=line_range,
            suggested_fix=finding.suggested_fix,
            previous_attempts=prev_attempts,
        )
        items.append(item)

    return FixerInput(
        iteration=registry.current_iteration + 1,
        items=tuple(items),
        context=context,
    )


# =============================================================================
# T016: update_issue_registry
# =============================================================================


async def update_issue_registry(
    registry: IssueRegistry,
    fixer_output: FixerOutput,
) -> IssueRegistry:
    """Update registry with fixer results.

    Applies fixer outcomes to tracked findings, auto-defers missing items.

    Args:
        registry: Current issue registry
        fixer_output: Output from fixer agent

    Returns:
        Updated IssueRegistry
    """
    now = datetime.now()
    current_iter = registry.current_iteration

    # Build lookup of output items by finding ID
    output_by_id: dict[str, FixerOutputItem] = {
        item.finding_id: item for item in fixer_output.items
    }

    # Get actionable findings that were sent to fixer
    actionable = registry.get_actionable()
    actionable_ids = {tf.finding.id for tf in actionable}

    logger.info(
        "Updating registry with %d fixer responses for %d actionable findings",
        len(output_by_id),
        len(actionable_ids),
    )

    # Process each actionable finding
    for tracked in actionable:
        finding_id = tracked.finding.id

        if finding_id in output_by_id:
            output_item = output_by_id[finding_id]

            # Parse status
            try:
                status = FindingStatus(output_item.status)
            except ValueError:
                logger.warning(
                    "Invalid status '%s' for finding %s, treating as deferred",
                    output_item.status,
                    finding_id,
                )
                status = FindingStatus.deferred

            # FR-004: Validate justification for blocked/deferred statuses
            validation = validate_justification(
                status=output_item.status,
                justification=output_item.justification,
            )

            # Handle validation results
            final_status = status
            final_justification = output_item.justification

            if validation.should_requeue:
                # Deferred with weak justification: re-queue as open (no attempt added)
                # The finding stays in its current state to be re-sent next iteration
                logger.warning(
                    "Finding %s: %s",
                    finding_id,
                    validation.message,
                )
                # Add attempt with rejected status note
                attempt = FixAttempt(
                    iteration=current_iter,
                    timestamp=now,
                    outcome=FindingStatus.deferred,
                    justification=(
                        f"[REJECTED - weak excuse] {output_item.justification}"
                    ),
                    changes_made=output_item.changes_made,
                )
                tracked.add_attempt(attempt)
                # Reset status back to open so it's re-sent next iteration
                tracked.status = FindingStatus.open
                continue

            if validation.is_weak and status == FindingStatus.blocked:
                # Blocked with weak justification: warn but keep blocked
                logger.warning(
                    "Finding %s: %s",
                    finding_id,
                    validation.message,
                )
                # Mark the justification as flagged
                final_justification = (
                    f"[FLAGGED - weak excuse pattern] {output_item.justification}"
                )

            # Create fix attempt with potentially modified justification
            attempt = FixAttempt(
                iteration=current_iter,
                timestamp=now,
                outcome=final_status,
                justification=final_justification,
                changes_made=output_item.changes_made,
            )
            tracked.add_attempt(attempt)

            justification_preview = ""
            if final_justification:
                justification_preview = f" - {final_justification[:50]}..."
            logger.debug(
                "Finding %s: %s%s",
                finding_id,
                final_status.value,
                justification_preview,
            )
        else:
            # Auto-defer findings not in fixer output
            logger.warning(
                "Finding %s not in fixer output, auto-deferring",
                finding_id,
            )
            attempt = FixAttempt(
                iteration=current_iter,
                timestamp=now,
                outcome=FindingStatus.deferred,
                justification="Agent did not provide status",
                changes_made=None,
            )
            tracked.add_attempt(attempt)

    # Increment iteration
    registry.increment_iteration()

    return registry


# =============================================================================
# T017: check_fix_loop_exit
# =============================================================================


async def check_fix_loop_exit(
    registry: IssueRegistry,
) -> dict[str, Any]:
    """Check if the fix loop should exit.

    Returns:
        Dict with:
            - should_exit: bool - Whether to exit the loop
            - reason: str - Human-readable exit reason
            - stats: dict - Counts by status
    """
    # Calculate stats
    stats = {
        "fixed": 0,
        "blocked": 0,
        "deferred": 0,
        "open": 0,
        "actionable": 0,
    }

    for tracked in registry.findings:
        stats[tracked.status.value] += 1

    # Actionable = open or deferred with critical/major severity
    stats["actionable"] = len(registry.get_actionable())

    # Determine exit condition
    should_continue = registry.should_continue

    if not should_continue:
        if registry.current_iteration >= registry.max_iterations:
            reason = (
                f"Maximum iterations ({registry.max_iterations}) reached. "
                f"{stats['actionable']} finding(s) still actionable."
            )
        elif stats["actionable"] == 0:
            if stats["fixed"] > 0:
                reason = f"All actionable findings resolved. {stats['fixed']} fixed."
            else:
                reason = "No actionable findings remaining."
        else:
            reason = "Fix loop complete."
    else:
        reason = (
            f"Continue: {stats['actionable']} actionable finding(s), "
            f"iteration {registry.current_iteration}/{registry.max_iterations}"
        )

    result = {
        "should_exit": not should_continue,
        "reason": reason,
        "stats": stats,
    }

    logger.info(
        "Fix loop exit check: should_exit=%s, reason='%s'",
        result["should_exit"],
        reason,
    )

    return result


# =============================================================================
# T018: create_tech_debt_issues
# =============================================================================


def _build_issue_body(
    tracked: TrackedFinding,
    pr_number: int | None,
) -> str:
    """Build GitHub issue body for a tracked finding.

    Args:
        tracked: The tracked finding
        pr_number: PR number to reference

    Returns:
        Formatted issue body
    """
    finding = tracked.finding
    lines = []

    # Header
    lines.append("## Finding Details")
    lines.append("")
    lines.append(f"**Source:** {finding.source}")
    lines.append(f"**Severity:** {finding.severity.value}")
    lines.append(f"**Category:** {finding.category.value}")
    lines.append(f"**Status:** {tracked.status.value}")
    lines.append("")

    # Location
    if finding.file_path:
        location = f"`{finding.file_path}`"
        if finding.line_start is not None:
            if finding.line_end is not None and finding.line_end != finding.line_start:
                location += f" (lines {finding.line_start}-{finding.line_end})"
            else:
                location += f" (line {finding.line_start})"
        lines.append(f"**Location:** {location}")
        lines.append("")

    # Description
    lines.append("## Description")
    lines.append("")
    lines.append(finding.description)
    lines.append("")

    # Suggested fix
    if finding.suggested_fix:
        lines.append("## Suggested Fix")
        lines.append("")
        lines.append(finding.suggested_fix)
        lines.append("")

    # Attempt history
    if tracked.attempts:
        lines.append("## Fix Attempt History")
        lines.append("")
        for attempt in tracked.attempts:
            timestamp_str = attempt.timestamp.isoformat()
            attempt_line = (
                f"- **Iteration {attempt.iteration}** ({timestamp_str}): "
                f"{attempt.outcome.value}"
            )
            lines.append(attempt_line)
            if attempt.justification:
                lines.append(f"  - Justification: {attempt.justification}")
            if attempt.changes_made:
                lines.append(f"  - Changes: {attempt.changes_made}")
        lines.append("")

    # PR reference
    if pr_number is not None:
        lines.append("---")
        lines.append(f"*Created from PR #{pr_number} review findings.*")

    return "\n".join(lines)


async def create_tech_debt_issues(
    registry: IssueRegistry,
    repo: str,
    base_labels: list[str] | None = None,
    pr_number: int | None = None,
    github_client: GitHubClient | None = None,
) -> list[TechDebtIssueResult]:
    """Create GitHub issues for unresolved findings.

    Creates issues for findings that:
    - Are blocked
    - Are deferred after max iterations reached
    - Are minor severity (never sent to fixer)

    Args:
        registry: Final issue registry
        repo: GitHub repo (owner/name)
        base_labels: Labels to add to all issues (default: ["tech-debt"])
        pr_number: PR number to reference in issue body
        github_client: Optional GitHubClient instance. If not provided, one will
            be created.

    Returns:
        List of TechDebtIssueResult for each created issue
    """
    if base_labels is None:
        base_labels = ["tech-debt"]

    # Get findings that need issues
    findings_for_issues = registry.get_for_issues()

    logger.info(
        "Creating %d tech debt issues in %s",
        len(findings_for_issues),
        repo,
    )

    # Create a shared client for all issues to avoid repeated authentication
    client = github_client or GitHubClient()

    results: list[TechDebtIssueResult] = []

    for tracked in findings_for_issues:
        finding = tracked.finding

        # Build labels
        labels = list(base_labels)
        labels.append(finding.severity.value)  # Add severity label

        # Build title
        title = f"[{finding.severity.value.upper()}] {finding.title}"
        if len(title) > 100:
            title = title[:97] + "..."

        # Build body
        body = _build_issue_body(tracked, pr_number)

        # Create issue with retry
        result = await _create_single_issue(
            repo=repo,
            title=title,
            body=body,
            labels=labels,
            finding_id=finding.id,
            github_client=client,
        )

        results.append(result)

        # Update tracked finding with issue number
        if result.success and result.issue_number is not None:
            tracked.github_issue_number = result.issue_number

    # Log summary
    success_count = sum(1 for r in results if r.success)
    logger.info(
        "Created %d/%d tech debt issues",
        success_count,
        len(results),
    )

    return results


async def _create_single_issue(
    repo: str,
    title: str,
    body: str,
    labels: list[str],
    finding_id: str,
    github_client: GitHubClient | None = None,
) -> TechDebtIssueResult:
    """Create a single GitHub issue with retry.

    Args:
        repo: GitHub repo (owner/name)
        title: Issue title
        body: Issue body
        labels: Labels to apply
        finding_id: ID of the associated finding
        github_client: Optional GitHubClient instance. If not provided, one will
            be created.

    Returns:
        TechDebtIssueResult
    """
    client = github_client or GitHubClient()
    last_error: str | None = None

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
        ):
            with attempt:
                issue = await client.create_issue(
                    repo_name=repo,
                    title=title,
                    body=body,
                    labels=labels,
                )

                return TechDebtIssueResult(
                    success=True,
                    issue_number=issue.number,
                    issue_url=issue.html_url,
                    title=title,
                    labels=tuple(labels),
                    finding_id=finding_id,
                    error=None,
                )

    except GitHubError as e:
        last_error = str(e)
        logger.warning(
            "Failed to create issue for finding %s after retries: %s",
            finding_id,
            e,
        )
        return TechDebtIssueResult(
            success=False,
            issue_number=None,
            issue_url=None,
            title=title,
            labels=tuple(labels),
            finding_id=finding_id,
            error=last_error,
        )

    except Exception as e:
        logger.warning(
            "Failed to create issue for finding %s after retries: %s",
            finding_id,
            e,
        )
        return TechDebtIssueResult(
            success=False,
            issue_number=None,
            issue_url=None,
            title=title,
            labels=tuple(labels),
            finding_id=finding_id,
            error=str(e),
        )

    # This should never be reached - the retry loop always returns or raises
    error_msg = last_error or "unknown error"
    raise RuntimeError(f"Retry loop exited unexpectedly for '{title}': {error_msg}")


# =============================================================================
# T019: detect_deleted_files
# =============================================================================


async def detect_deleted_files(
    registry: IssueRegistry,
    repo_root: Path | str,
) -> IssueRegistry:
    """Auto-block findings that reference deleted files.

    Checks if files referenced by findings still exist.
    Auto-marks as blocked with system justification.

    Args:
        registry: Current issue registry
        repo_root: Root directory of repository

    Returns:
        Updated IssueRegistry with deleted file findings blocked
    """
    repo_path = Path(repo_root)
    now = datetime.now()
    blocked_count = 0

    for tracked in registry.findings:
        # Skip already resolved findings
        if tracked.status in (FindingStatus.fixed, FindingStatus.blocked):
            continue

        finding = tracked.finding
        if finding.file_path is None:
            continue

        # Check if file exists
        file_path = repo_path / finding.file_path
        if not file_path.exists():
            logger.info(
                "Blocking finding %s: referenced file '%s' deleted",
                finding.id,
                finding.file_path,
            )

            attempt = FixAttempt(
                iteration=registry.current_iteration,
                timestamp=now,
                outcome=FindingStatus.blocked,
                justification="Referenced file deleted",
                changes_made=None,
            )
            tracked.add_attempt(attempt)
            blocked_count += 1

    if blocked_count > 0:
        logger.info(
            "Blocked %d finding(s) referencing deleted files",
            blocked_count,
        )

    return registry


# =============================================================================
# T020: run_accountability_fix_loop
# =============================================================================


async def run_accountability_fix_loop(
    registry: IssueRegistry | dict[str, Any],
    base_branch: str = "main",
    max_iterations: int = 3,
) -> dict[str, Any]:
    """Run the accountability fix loop until exit conditions are met.

    This action orchestrates the iterative fix loop:
    1. Calls prepare_fixer_input to get actionable items
    2. Runs ReviewFixerAgent from maverick.agents.reviewers.review_fixer
    3. Calls update_issue_registry with the fixer output
    4. Calls check_fix_loop_exit to determine if loop should exit

    Args:
        registry: Current issue registry (IssueRegistry or dict from DSL).
        base_branch: Base branch for context (unused directly but passed for
            potential future context building).
        max_iterations: Maximum number of iterations to run.

    Returns:
        Dict with:
            - registry: Final IssueRegistry state as dict
            - iterations_run: Number of iterations executed
            - exit_reason: Human-readable exit reason
            - stats: Final counts by status
    """
    # Import here to avoid circular imports
    from maverick.agents.reviewers.review_fixer import ReviewFixerAgent

    # Convert dict to IssueRegistry if needed (from DSL serialization)
    reg = IssueRegistry.from_dict(registry) if isinstance(registry, dict) else registry

    # Override max_iterations if provided
    reg.max_iterations = max_iterations

    logger.info(
        "Starting accountability fix loop with %d findings, max %d iterations",
        len(reg.findings),
        max_iterations,
    )

    iterations_run = 0
    exit_reason = "Not started"

    # Create fixer agent
    fixer_agent = ReviewFixerAgent()

    while reg.should_continue:
        iterations_run += 1
        logger.info(
            "Fix loop iteration %d/%d",
            iterations_run,
            max_iterations,
        )

        # Step 1: Prepare fixer input
        fixer_input = await prepare_fixer_input(
            registry=reg,
            context=f"Base branch: {base_branch}",
        )

        if not fixer_input.items:
            logger.info("No actionable items to fix, exiting loop")
            exit_reason = "No actionable items remaining"
            break

        logger.info(
            "Sending %d actionable items to fixer",
            len(fixer_input.items),
        )

        # Step 2: Run fixer agent
        fixer_result = await fixer_agent.execute(fixer_input)

        # The agent returns FixerOutput when given FixerInput
        # but the type system doesn't know this narrowing
        if isinstance(fixer_result, dict):
            # Shouldn't happen with FixerInput, but handle gracefully
            logger.warning(
                "Fixer returned dict instead of FixerOutput, skipping update"
            )
            continue

        logger.info(
            "Fixer returned %d responses",
            len(fixer_result.items),
        )

        # Step 3: Update registry
        reg = await update_issue_registry(
            registry=reg,
            fixer_output=fixer_result,
        )

        # Step 4: Check exit condition
        exit_check = await check_fix_loop_exit(registry=reg)
        exit_reason = exit_check["reason"]

        if exit_check["should_exit"]:
            logger.info("Fix loop exiting: %s", exit_reason)
            break

    # Build final stats
    stats = {
        "fixed": 0,
        "blocked": 0,
        "deferred": 0,
        "open": 0,
    }
    for tracked in reg.findings:
        stats[tracked.status.value] += 1

    logger.info(
        "Fix loop completed after %d iteration(s): %s",
        iterations_run,
        exit_reason,
    )

    return {
        "registry": reg.to_dict(),
        "iterations_run": iterations_run,
        "exit_reason": exit_reason,
        "stats": stats,
    }


# =============================================================================
# T021: generate_registry_summary
# =============================================================================


async def generate_registry_summary(
    registry: IssueRegistry | dict[str, Any],
    issues_created: list[TechDebtIssueResult | dict[str, Any]] | None = None,
    max_iterations: int = 3,
) -> dict[str, Any]:
    """Generate a human-readable summary of the review-fix process.

    Args:
        registry: Final issue registry (IssueRegistry or dict from DSL).
        issues_created: List of TechDebtIssueResult or dicts for created issues.
        max_iterations: Maximum iterations that were allowed.

    Returns:
        Dict with:
            - summary: Human-readable summary string
            - stats: Detailed statistics dict
    """
    # Convert dict to IssueRegistry if needed
    reg = IssueRegistry.from_dict(registry) if isinstance(registry, dict) else registry

    if issues_created is None:
        issues_created = []

    # Calculate stats by status
    stats = {
        "total": len(reg.findings),
        "fixed": 0,
        "blocked": 0,
        "deferred": 0,
        "open": 0,
    }

    for tracked in reg.findings:
        stats[tracked.status.value] += 1

    # Count by severity
    severity_stats = {
        "critical": 0,
        "major": 0,
        "minor": 0,
    }
    for tracked in reg.findings:
        severity_stats[tracked.finding.severity.value] += 1

    # Count GitHub issues created
    issues_success_count = 0
    for issue in issues_created:
        if isinstance(issue, dict):
            if issue.get("success", False):
                issues_success_count += 1
        elif isinstance(issue, TechDebtIssueResult) and issue.success:
            issues_success_count += 1

    # Check if max iterations was reached
    max_iterations_reached = reg.current_iteration >= max_iterations

    # Build summary text
    lines = []
    lines.append("## Review-Fix Summary")
    lines.append("")
    lines.append(f"**Total Findings**: {stats['total']}")
    lines.append("")

    # Severity breakdown
    lines.append("### By Severity")
    lines.append(f"- Critical: {severity_stats['critical']}")
    lines.append(f"- Major: {severity_stats['major']}")
    lines.append(f"- Minor: {severity_stats['minor']}")
    lines.append("")

    # Status breakdown
    lines.append("### By Status")
    lines.append(f"- Fixed: {stats['fixed']}")
    lines.append(f"- Blocked: {stats['blocked']}")
    lines.append(f"- Deferred: {stats['deferred']}")
    lines.append(f"- Open: {stats['open']}")
    lines.append("")

    # Iterations info
    lines.append("### Fix Loop")
    lines.append(f"- Iterations Run: {reg.current_iteration}")
    lines.append(f"- Max Iterations: {max_iterations}")
    if max_iterations_reached:
        lines.append("- **Warning**: Max iterations reached")
    lines.append("")

    # GitHub issues
    if issues_created:
        lines.append("### GitHub Issues Created")
        lines.append(f"- Total: {issues_success_count}")
        lines.append("")

    # Final recommendation
    actionable_remaining = len(reg.get_actionable())
    if stats["fixed"] == stats["total"]:
        recommendation = "All findings resolved"
    elif actionable_remaining == 0:
        recommendation = (
            "No actionable findings remaining (some may be blocked/deferred)"
        )
    elif max_iterations_reached:
        recommendation = (
            f"{actionable_remaining} finding(s) still actionable after max iterations"
        )
    else:
        recommendation = f"{actionable_remaining} actionable finding(s) remain"

    lines.append("### Recommendation")
    lines.append(f"{recommendation}")

    summary_text = "\n".join(lines)

    logger.info(
        "Generated registry summary: %d total, %d fixed, %d blocked, %d deferred",
        stats["total"],
        stats["fixed"],
        stats["blocked"],
        stats["deferred"],
    )

    return {
        "summary": summary_text,
        "stats": {
            **stats,
            "severity": severity_stats,
            "issues_created": issues_success_count,
            "max_iterations_reached": max_iterations_reached,
            "actionable_remaining": actionable_remaining,
        },
    }
