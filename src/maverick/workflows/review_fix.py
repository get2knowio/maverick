"""Unified Review and Fix Workflow.

This module provides the main entry point for the simplified review-fix workflow.
It runs a unified reviewer, then iteratively fixes findings until resolved or
max iterations reached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maverick.logging import get_logger
from maverick.models.review_models import (
    FindingTracker,
    TrackedFinding,
)

logger = get_logger(__name__)

__all__ = [
    "ReviewFixResult",
    "review_and_fix",
]


@dataclass(frozen=True, slots=True)
class ReviewFixResult:
    """Result from the review-and-fix workflow.

    Attributes:
        total_findings: Total number of findings from review
        fixed_count: Number of successfully fixed findings
        blocked_count: Number of blocked findings
        deferred_count: Number of deferred findings (exceeded retries)
        issues_created: URLs of GitHub issues created for unresolved findings
        iterations: Number of fix iterations executed
    """

    total_findings: int
    fixed_count: int
    blocked_count: int
    deferred_count: int
    issues_created: list[str] = field(default_factory=list)
    iterations: int = 0

    @property
    def success_rate(self) -> float:
        """Percentage of findings that were fixed."""
        if self.total_findings == 0:
            return 100.0
        return (self.fixed_count / self.total_findings) * 100


async def review_and_fix(
    feature_name: str | None = None,
    cwd: Path | str | None = None,
    max_iterations: int = 3,
    create_issues: bool = True,
    model: str | None = None,
    context: dict[str, Any] | None = None,
) -> ReviewFixResult:
    """Run unified review and iterative fix loop.

    This is the main entry point for the simplified review-fix workflow:
    1. Run unified reviewer (spawns parallel expert subagents)
    2. Track findings
    3. Iteratively fix (up to max_iterations)
    4. Create GitHub issues for unresolved findings

    Args:
        feature_name: Name of the feature for spec lookup.
        cwd: Working directory (repo root). Defaults to current directory.
        max_iterations: Maximum fix iterations (default 3).
        create_issues: Whether to create GitHub issues for unresolved findings.
        model: Optional model override.
        context: Optional additional context for reviewers.

    Returns:
        ReviewFixResult with statistics and created issue URLs.

    Example:
        >>> result = await review_and_fix(
        ...     feature_name="my-feature",
        ...     max_iterations=3,
        ... )
        >>> print(f"Fixed {result.fixed_count}/{result.total_findings}")
    """
    from maverick.agents.reviewers.simple_fixer import SimpleFixerAgent
    from maverick.agents.reviewers.unified_reviewer import UnifiedReviewerAgent

    cwd = Path(cwd) if cwd else Path.cwd()

    # Build review context
    review_context: dict[str, Any] = {
        "cwd": cwd,
        "feature_name": feature_name,
    }
    if context:
        review_context.update(context)

    # Step 1: Run unified review
    logger.info("starting_unified_review", feature_name=feature_name)

    reviewer = UnifiedReviewerAgent(feature_name=feature_name, model=model)
    review_result = await reviewer.execute(review_context)

    if review_result.total_count == 0:
        logger.info("no_findings_from_review")
        return ReviewFixResult(
            total_findings=0,
            fixed_count=0,
            blocked_count=0,
            deferred_count=0,
            iterations=0,
        )

    logger.info(
        "review_complete",
        total_findings=review_result.total_count,
        groups=len(review_result.groups),
    )

    # Step 2: Initialize tracker
    tracker = FindingTracker(review_result)

    # Step 3: Fix loop
    fixer = SimpleFixerAgent(model=model)
    iteration = 0

    while not tracker.is_complete() and iteration < max_iterations:
        iteration += 1

        # Get actionable findings with their groups
        actionable_groups = tracker.get_actionable_with_groups()
        actionable_findings = tracker.get_actionable_findings()

        if not actionable_findings:
            logger.info("no_actionable_findings_remaining")
            break

        logger.info(
            "starting_fix_iteration",
            iteration=iteration,
            actionable_count=len(actionable_findings),
        )

        # Check for deleted files and auto-block
        actionable_findings = await _filter_deleted_files(
            actionable_findings, tracker, cwd
        )

        if not actionable_findings:
            logger.info("all_findings_for_deleted_files")
            break

        # Rebuild groups after filtering
        actionable_groups = tracker.get_actionable_with_groups()

        # Run fixer
        outcomes = await fixer.execute(
            {
                "findings": actionable_findings,
                "groups": actionable_groups,
                "iteration": iteration,
                "cwd": cwd,
            }
        )

        # Record outcomes
        tracker.record_outcomes(outcomes)

        summary = tracker.get_summary()
        logger.info(
            "fix_iteration_complete",
            iteration=iteration,
            fixed=summary["fixed"],
            blocked=summary["blocked"],
            deferred=summary["deferred"],
        )

    # Step 4: Create issues for unresolved
    issues_created: list[str] = []

    if create_issues:
        unresolved = tracker.get_unresolved()
        if unresolved:
            logger.info(
                "creating_issues_for_unresolved",
                count=len(unresolved),
            )
            issues_created = await _create_issues_for_unresolved(
                unresolved, feature_name, cwd
            )

    # Build final result
    summary = tracker.get_summary()

    return ReviewFixResult(
        total_findings=summary["total"],
        fixed_count=summary["fixed"],
        blocked_count=summary["blocked"],
        deferred_count=summary["deferred"],
        issues_created=issues_created,
        iterations=iteration,
    )


async def _filter_deleted_files(
    findings: list[Any],
    tracker: FindingTracker,
    cwd: Path,
) -> list[Any]:
    """Filter out findings for deleted files, auto-blocking them.

    Args:
        findings: List of Finding objects.
        tracker: FindingTracker to record blocked status.
        cwd: Working directory.

    Returns:
        Filtered list of findings for existing files.
    """
    from maverick.agents.contracts import FixOutcome

    remaining = []
    for finding in findings:
        file_path = cwd / finding.file
        if not file_path.exists():
            logger.info(
                "auto_blocking_deleted_file",
                finding_id=finding.id,
                file=finding.file,
            )
            tracker.record_outcome(
                FixOutcome(
                    id=finding.id,
                    outcome="blocked",
                    explanation=f"File no longer exists: {finding.file}",
                )
            )
        else:
            remaining.append(finding)

    return remaining


async def _create_issues_for_unresolved(
    unresolved: list[TrackedFinding],
    feature_name: str | None,
    cwd: Path,
) -> list[str]:
    """Create GitHub issues for unresolved findings.

    Args:
        unresolved: List of TrackedFinding that weren't fixed.
        feature_name: Feature name for issue context.
        cwd: Working directory.

    Returns:
        List of created issue URLs.
    """
    from maverick.utils.github_client import GitHubClient

    if not unresolved:
        return []

    try:
        client = GitHubClient()
    except Exception as e:
        logger.warning("github_client_init_failed", error=str(e))
        return []

    # Get repo name
    try:
        repo_name = await _get_repo_name(cwd)
    except Exception as e:
        logger.warning("failed_to_get_repo_name", error=str(e))
        return []

    created_urls: list[str] = []

    for tf in unresolved:
        finding = tf.finding

        # Build issue title
        title = f"[Tech Debt] {finding.issue[:60]}"
        if len(finding.issue) > 60:
            title += "..."

        # Build issue body
        body_parts = [
            f"## Finding: {finding.id}",
            "",
            f"**File**: `{finding.file}:{finding.line}`",
            f"**Severity**: {finding.severity}",
            f"**Category**: {finding.category}",
            "",
            "## Issue",
            "",
            finding.issue,
        ]

        if finding.fix_hint:
            body_parts.extend(["", "## Suggested Fix", "", finding.fix_hint])

        if tf.attempts:
            body_parts.extend(["", "## Fix Attempts", ""])
            for i, attempt in enumerate(tf.attempts, 1):
                body_parts.append(
                    f"- **Attempt {i}**: {attempt.outcome} - {attempt.explanation}"
                )

        if feature_name:
            body_parts.extend(["", f"_From feature: {feature_name}_"])

        body = "\n".join(body_parts)

        try:
            issue = await client.create_issue(
                repo_name=repo_name,
                title=title,
                body=body,
                labels=["tech-debt"],
            )
            issue_url = issue.html_url
            created_urls.append(issue_url)
            logger.info(
                "issue_created",
                finding_id=finding.id,
                url=issue_url,
            )
        except Exception as e:
            logger.error(
                "failed_to_create_issue",
                finding_id=finding.id,
                error=str(e),
            )

    return created_urls


async def _get_repo_name(cwd: Path) -> str:
    """Get the GitHub repo name from git remote.

    Uses AsyncGitRepository for git operations per Architectural Guardrail #6
    (one canonical wrapper per external system).

    Args:
        cwd: Working directory.

    Returns:
        Repo name in "owner/repo" format.

    Raises:
        ValueError: If repo name cannot be determined.
    """
    import re

    from maverick.git import AsyncGitRepository

    repo = AsyncGitRepository(cwd)
    url = await repo.get_remote_url()

    if url is None:
        raise ValueError("Failed to get git remote URL")

    # Parse GitHub URL formats
    # SSH: git@github.com:owner/repo.git
    # HTTPS: https://github.com/owner/repo.git
    patterns = [
        r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?$",
        r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?$",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise ValueError(f"Could not parse repo name from URL: {url}")
