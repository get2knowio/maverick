"""Cleanup workflow actions for batch issue processing."""

from __future__ import annotations

import asyncio
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)


async def process_selected_issues(
    issues: list[dict[str, Any]],
    parallel: bool,
) -> dict[str, Any]:
    """Process selected issues (parallel or sequential).

    This action orchestrates the processing of multiple GitHub issues either
    in parallel or sequentially, implementing FR-020 and FR-021.

    For each issue, it should ideally invoke the process_single_issue workflow,
    but since Python actions don't have direct access to the workflow registry,
    this implementation handles the orchestration logic and gracefully handles
    failures per FR-021.

    NOTE: This is currently a placeholder implementation. Full implementation
    requires either:
    1. Adding loop/foreach support to the DSL (to call process_single_issue in YAML)
    2. Dependency injection of the registry/executor to this action
    3. Refactoring to use direct Python calls instead of sub-workflows

    Args:
        issues: List of selected issues to process. Each issue dict should have
            'number' and 'title' fields at minimum.
        parallel: Whether to process in parallel (True) or sequentially (False).
            Parallel processing uses asyncio.gather() per FR-020.

    Returns:
        Dict with:
        - processed: List of ProcessedIssueEntry dicts
        - parallel_mode: Boolean indicating processing mode

    Example:
        >>> result = await process_selected_issues(
        ...     issues=[{"number": 123, "title": "Fix bug"}],
        ...     parallel=True
        ... )
        >>> result["processed"][0]["status"]
        'skipped'
    """
    results = []

    if parallel:
        # Process all issues in parallel using asyncio.gather per FR-020
        # Use return_exceptions=True to handle failures gracefully per FR-021
        coroutines = [_process_single_issue(issue) for issue in issues]
        raw_results = await asyncio.gather(*coroutines, return_exceptions=True)

        # Convert results and exceptions to ProcessedIssueEntry format
        for issue, raw_result in zip(issues, raw_results, strict=True):
            if isinstance(raw_result, Exception):
                # Issue processing raised an exception - record as failed
                # Satisfies FR-021: graceful handling without crashing workflow
                logger.debug(
                    f"Issue {issue.get('number')} failed with exception: {raw_result}"
                )
                result: dict[str, Any] = {
                    "issue_number": issue.get("number"),
                    "issue_title": issue.get("title", ""),
                    "status": "failed",
                    "branch_name": None,
                    "pr_url": None,
                    "error": str(raw_result),
                }
                results.append(result)
            else:
                # Type checker knows raw_result is not Exception here
                assert isinstance(raw_result, dict)
                results.append(raw_result)
    else:
        # Process issues sequentially per FR-020
        # One failure doesn't stop the rest per FR-021
        for issue in issues:
            try:
                result = await _process_single_issue(issue)
                results.append(result)
            except Exception as e:
                # Log exception but continue with remaining issues per FR-021
                logger.exception(f"Failed to process issue {issue.get('number')}")
                result = {
                    "issue_number": issue.get("number"),
                    "issue_title": issue.get("title", ""),
                    "status": "failed",
                    "branch_name": None,
                    "pr_url": None,
                    "error": str(e),
                }
                results.append(result)

    mode = "parallel" if parallel else "sequential"
    logger.info(f"Processed {len(results)} issues in {mode} mode")

    return {
        "processed": results,
        "parallel_mode": parallel,
    }


async def _process_single_issue(issue: dict[str, Any]) -> dict[str, Any]:
    """Process a single issue.

    NOTE: This is a placeholder implementation that returns a "skipped" status.
    Full implementation would invoke the process_single_issue workflow or call
    the appropriate Python functions/agents directly.

    TODO: Implement actual issue processing:
    - Create branch for the issue
    - Invoke issue fixer agent
    - Run validation loop
    - Commit and push changes
    - Create pull request

    Args:
        issue: Issue dict with at least 'number' and 'title'

    Returns:
        ProcessedIssueEntry dict with status, branch, PR URL, and error
    """
    issue_number = issue.get("number")
    issue_title = issue.get("title", "")

    # Placeholder implementation - returns "skipped" status
    # Real implementation would process the issue through the full workflow
    return {
        "issue_number": issue_number,
        "issue_title": issue_title,
        "status": "skipped",  # Placeholder - indicates not yet implemented
        "branch_name": None,
        "pr_url": None,
        "error": None,
    }


async def generate_cleanup_summary(
    parallel_result: dict[str, Any] | None,
    sequential_result: dict[str, Any] | None,
    total_requested: int,
    label: str,
    parallel_mode: bool,
) -> dict[str, Any]:
    """Generate summary of cleanup workflow execution.

    Args:
        parallel_result: Result from parallel processing (optional)
        sequential_result: Result from sequential processing (optional)
        total_requested: Total issues requested
        label: Label used for filtering
        parallel_mode: Whether parallel mode was used

    Returns:
        CleanupSummaryResult as dict
    """
    # Get processed results from whichever mode was used
    results = []
    if parallel_result:
        results = parallel_result.get("processed", [])
    elif sequential_result:
        results = sequential_result.get("processed", [])

    # Count statuses
    success_count = sum(1 for r in results if r.get("status") == "fixed")
    failure_count = sum(1 for r in results if r.get("status") == "failed")
    skipped_count = sum(1 for r in results if r.get("status") == "skipped")

    # Collect PR URLs
    pr_urls = [r.get("pr_url") for r in results if r.get("pr_url")]

    logger.info(
        f"Cleanup summary: {success_count} fixed, {failure_count} failed, "
        f"{skipped_count} skipped out of {total_requested} total issues"
    )

    return {
        "total_issues": total_requested,
        "processed_count": len(results),
        "success_count": success_count,
        "failure_count": failure_count,
        "skipped_count": skipped_count,
        "issues": tuple(results),
        "pr_urls": tuple(pr_urls),
    }
