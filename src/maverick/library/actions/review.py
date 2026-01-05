"""Code review actions for workflow execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from maverick.git import AsyncGitRepository
from maverick.library.actions.types import (
    AnalyzedFindingsResult,
    CombinedReviewResult,
    IssueFixResult,
    IssueGroup,
    PRMetadata,
    ReviewAndFixReport,
    ReviewContextResult,
    ReviewFixLoopResult,
    ReviewIssue,
)
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner

logger = get_logger(__name__)


async def gather_pr_context(
    pr_number: int | None,
    base_branch: str,
    include_spec_files: bool = False,
    spec_dir: str | None = None,
) -> ReviewContextResult:
    """Gather PR context for code review.

    Args:
        pr_number: PR number (optional, auto-detect if None)
        base_branch: Base branch for comparison
        include_spec_files: Whether to include spec files in context
        spec_dir: Directory containing spec files (auto-detect if None)

    Returns:
        ReviewContextResult with PR metadata, diff, and optionally spec files
    """
    try:
        # Initialize git repository
        repo = AsyncGitRepository()

        # Create runner instance for GitHub CLI operations
        runner = CommandRunner(timeout=60.0)

        # Auto-detect PR number if not provided
        current_branch = None
        if pr_number is None:
            current_branch = await repo.current_branch()

            # Try to find PR for current branch
            pr_list_result = await runner.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--head",
                    current_branch,
                    "--json",
                    "number",
                    "--limit",
                    "1",
                ],
            )
            if pr_list_result.success:
                pr_list = json.loads(pr_list_result.stdout)
                if pr_list:
                    pr_number = pr_list[0]["number"]
                else:
                    logger.warning(
                        f"No PR found for current branch '{current_branch}', "
                        "proceeding with local diff"
                    )
            else:
                logger.warning(
                    f"Failed to list PRs: {pr_list_result.stderr}, "
                    "proceeding with local diff"
                )

        # Fetch PR metadata if we have a PR number
        pr_metadata = PRMetadata(
            number=pr_number,
            title=None,
            description=None,
            author=None,
            labels=(),
            base_branch=base_branch,
        )

        if pr_number is not None:
            pr_view_result = await runner.run(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr_number),
                    "--json",
                    "number,title,body,author,labels",
                ],
            )
            if pr_view_result.success:
                pr_data = json.loads(pr_view_result.stdout)
                pr_metadata = PRMetadata(
                    number=pr_data["number"],
                    title=pr_data.get("title"),
                    description=pr_data.get("body"),
                    author=pr_data.get("author", {}).get("login"),
                    labels=tuple(label["name"] for label in pr_data.get("labels", [])),
                    base_branch=base_branch,
                )

        # Get diff against base branch using three-dot syntax (base...HEAD)
        diff = await repo.diff(base=f"{base_branch}...HEAD")

        # Get changed files using three-dot syntax
        changed_files_list = await repo.get_changed_files(ref=f"{base_branch}...HEAD")
        changed_files = tuple(changed_files_list)

        # Get commit messages since base branch (two-dot syntax)
        commit_messages = await repo.commit_messages_since(ref=base_branch)
        commits = tuple(commit_messages)

        # Gather spec files if requested
        spec_files: dict[str, str] = {}
        if include_spec_files:
            spec_files = await _gather_spec_files(spec_dir, current_branch)

        return ReviewContextResult(
            pr_metadata=pr_metadata,
            changed_files=changed_files,
            diff=diff,
            commits=commits,
            spec_files=spec_files,
            error=None,
        )

    except Exception as e:
        logger.error(f"Failed to gather PR context: {e}")
        return ReviewContextResult(
            pr_metadata=PRMetadata(
                number=pr_number,
                title=None,
                description=None,
                author=None,
                labels=(),
                base_branch=base_branch,
            ),
            changed_files=(),
            diff="",
            commits=(),
            spec_files={},
            error=str(e),
        )


async def _gather_spec_files(
    spec_dir: str | None,
    current_branch: str | None,
) -> dict[str, str]:
    """Gather spec files for review context.

    Args:
        spec_dir: Explicit spec directory or None for auto-detect
        current_branch: Current branch name for auto-detection

    Returns:
        Dict mapping spec file names to their contents
    """
    spec_files: dict[str, str] = {}

    # Determine spec directory
    if spec_dir:
        spec_path = Path(spec_dir)
    elif current_branch:
        # Try specs/<branch-name>/ first
        spec_path = Path(f"specs/{current_branch}")
        if not spec_path.exists():
            # Try .specify/<branch-name>/
            spec_path = Path(f".specify/{current_branch}")
        if not spec_path.exists():
            # Fall back to ./specs/
            spec_path = Path("specs")
    else:
        spec_path = Path("specs")

    if not spec_path.exists():
        logger.debug(f"Spec directory not found: {spec_path}")
        return spec_files

    # Read standard spec files
    spec_file_names = ["spec.md", "plan.md", "tasks.md", "constitution.md"]
    for filename in spec_file_names:
        file_path = spec_path / filename
        if file_path.exists():
            try:
                content = file_path.read_text()
                spec_files[filename] = content
                logger.debug(f"Loaded spec file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to read spec file {file_path}: {e}")

    return spec_files


async def combine_review_results(
    spec_review: dict[str, Any] | None,
    technical_review: dict[str, Any] | None,
    pr_metadata: dict[str, Any],
) -> CombinedReviewResult:
    """Combine review results from spec and technical reviewers.

    Args:
        spec_review: Spec compliance review output
        technical_review: Technical quality review output
        pr_metadata: PR metadata

    Returns:
        CombinedReviewResult with unified report
    """
    # Extract findings from both sources
    spec_findings = ""
    spec_assessment = "UNKNOWN"
    if spec_review:
        spec_findings = spec_review.get("findings", "")
        spec_assessment = spec_review.get("assessment", "UNKNOWN")

    technical_findings = ""
    technical_quality = "UNKNOWN"
    has_critical = False
    if technical_review:
        technical_findings = technical_review.get("findings", "")
        technical_quality = technical_review.get("quality", "UNKNOWN")
        has_critical = technical_review.get("has_critical", False)

    # Generate unified report
    report_lines = []
    report_lines.append("# Code Review Report")
    report_lines.append("")

    if pr_metadata.get("number"):
        report_lines.append(f"**PR:** #{pr_metadata['number']}")
    if pr_metadata.get("title"):
        report_lines.append(f"**Title:** {pr_metadata['title']}")
    if pr_metadata.get("author"):
        report_lines.append(f"**Author:** {pr_metadata['author']}")
    report_lines.append("")

    # Summary section
    report_lines.append("## Summary")
    report_lines.append("")
    report_lines.append(f"- **Spec Compliance:** {spec_assessment}")
    report_lines.append(f"- **Technical Quality:** {technical_quality}")
    report_lines.append("")

    # Spec Review section
    report_lines.append("## Spec Compliance Review")
    report_lines.append("")
    if spec_findings:
        report_lines.append(spec_findings)
    else:
        report_lines.append("_No spec compliance review available._")
    report_lines.append("")

    # Technical Review section
    report_lines.append("## Technical Quality Review")
    report_lines.append("")
    if technical_findings:
        report_lines.append(technical_findings)
    else:
        report_lines.append("_No technical review available._")
    report_lines.append("")

    # Determine recommendation
    if (
        has_critical
        or spec_assessment == "NON-COMPLIANT"
        or technical_quality == "POOR"
    ):
        recommendation = "request_changes"
    elif spec_assessment == "PARTIAL" or technical_quality == "NEEDS_WORK":
        recommendation = "comment"
    elif spec_assessment == "COMPLIANT" and technical_quality in ("GOOD", "EXCELLENT"):
        recommendation = "approve"
    else:
        recommendation = "comment"

    report_lines.append("## Recommendation")
    report_lines.append("")
    report_lines.append(f"**{recommendation.replace('_', ' ').title()}**")

    return CombinedReviewResult(
        review_report="\n".join(report_lines),
        issues=(),  # No structured issues, findings are in the report
        recommendation=recommendation,
    )


# =============================================================================
# Review-and-Fix Actions
# =============================================================================


class _ReviewStillFailingError(Exception):
    """Internal exception to signal review still has issues and retry is needed."""

    pass


async def analyze_review_findings(
    review_result: dict[str, Any],
    recommendation: str,
) -> AnalyzedFindingsResult:
    """Analyze review findings and categorize issues for parallel fixing.

    This function consolidates findings from the review step and groups them
    by file for parallelization. Issues affecting different files can be
    fixed in parallel, while issues affecting the same file are grouped
    for sequential processing within that group.

    Args:
        review_result: Combined review result from the review workflow
        recommendation: Review recommendation (approve, comment, request_changes)

    Returns:
        AnalyzedFindingsResult with categorized issue groups
    """
    # If review already recommends approve, skip analysis
    if recommendation == "approve":
        return AnalyzedFindingsResult(
            total_issues=0,
            critical_count=0,
            major_count=0,
            minor_count=0,
            suggestion_count=0,
            issue_groups=(),
            needs_fixes=False,
            skip_reason="Review already recommends approve",
        )

    # Extract issues from the review report
    review_report = review_result.get("review_report", "")
    issues = _parse_issues_from_report(review_report)

    if not issues:
        return AnalyzedFindingsResult(
            total_issues=0,
            critical_count=0,
            major_count=0,
            minor_count=0,
            suggestion_count=0,
            issue_groups=(),
            needs_fixes=False,
            skip_reason="No actionable issues found in review",
        )

    # Count issues by severity
    severity_counts: dict[str, int] = defaultdict(int)
    for issue in issues:
        severity_counts[issue.severity] += 1

    # Group issues by file path for parallelization
    file_groups: dict[str | None, list[ReviewIssue]] = defaultdict(list)
    for issue in issues:
        file_groups[issue.file_path].append(issue)

    # Create issue groups
    issue_groups = []
    for file_path, group_issues in file_groups.items():
        group_id = _generate_group_id(file_path, group_issues)
        issue_groups.append(
            IssueGroup(
                group_id=group_id,
                file_path=file_path,
                issues=tuple(group_issues),
                can_parallelize=file_path is not None,  # File-specific can parallelize
            )
        )

    # Determine if fixes are needed (critical or major issues)
    needs_fixes = severity_counts["critical"] > 0 or severity_counts["major"] > 0

    return AnalyzedFindingsResult(
        total_issues=len(issues),
        critical_count=severity_counts["critical"],
        major_count=severity_counts["major"],
        minor_count=severity_counts["minor"],
        suggestion_count=severity_counts["suggestion"],
        issue_groups=tuple(issue_groups),
        needs_fixes=needs_fixes,
        skip_reason=None,
    )


def _parse_issues_from_report(report: str) -> list[ReviewIssue]:
    """Parse structured issues from the review report.

    This function extracts actionable issues from the review report text
    by looking for common patterns in issue descriptions.

    Args:
        report: Review report text

    Returns:
        List of ReviewIssue objects
    """
    issues: list[ReviewIssue] = []
    issue_counter = 0

    # Patterns to match issue sections
    section_patterns = [
        (r"###\s*Critical Issues.*?\n(.*?)(?=###|\Z)", "critical"),
        (r"###\s*Major Issues.*?\n(.*?)(?=###|\Z)", "major"),
        (r"###\s*Minor Issues.*?\n(.*?)(?=###|\Z)", "minor"),
        (r"###\s*Suggestions.*?\n(.*?)(?=###|\Z)", "suggestion"),
    ]

    # Pattern to match file:line references
    file_line_pattern = re.compile(r"([a-zA-Z0-9_./\-]+\.[a-zA-Z]+):(\d+)")

    for pattern, severity in section_patterns:
        matches = re.findall(pattern, report, re.DOTALL | re.IGNORECASE)
        for section_content in matches:
            # Split by bullet points or numbered items
            items = re.split(r"\n\s*[-*•]\s*|\n\s*\d+\.\s*", section_content)
            for item in items:
                item = item.strip()
                if not item or len(item) < 10:
                    continue

                # Try to extract file:line reference
                file_match = file_line_pattern.search(item)
                file_path = file_match.group(1) if file_match else None
                line_number = int(file_match.group(2)) if file_match else None

                # Determine category based on content
                category = _categorize_issue(item)

                # Determine reviewer based on section
                reviewer = "technical"
                if "spec" in item.lower() or "requirement" in item.lower():
                    reviewer = "spec"

                issue_counter += 1
                issues.append(
                    ReviewIssue(
                        id=f"issue_{issue_counter}",
                        file_path=file_path,
                        line_number=line_number,
                        severity=severity,
                        category=category,
                        description=item[:500],  # Limit description length
                        suggested_fix=None,
                        reviewer=reviewer,
                    )
                )

    return issues


def _categorize_issue(description: str) -> str:
    """Categorize an issue based on its description.

    Args:
        description: Issue description text

    Returns:
        Category string
    """
    desc_lower = description.lower()

    if any(
        kw in desc_lower
        for kw in ["security", "vulnerability", "injection", "xss", "auth"]
    ):
        return "security"
    elif any(
        kw in desc_lower
        for kw in ["performance", "slow", "inefficient", "o(n²)", "memory"]
    ):
        return "performance"
    elif any(
        kw in desc_lower
        for kw in ["spec", "requirement", "missing feature", "expected"]
    ):
        return "spec"
    elif any(
        kw in desc_lower
        for kw in ["style", "format", "naming", "convention", "readability"]
    ):
        return "style"
    else:
        return "correctness"


def _generate_group_id(file_path: str | None, issues: list[ReviewIssue]) -> str:
    """Generate a unique ID for an issue group.

    Args:
        file_path: File path for the group
        issues: Issues in the group

    Returns:
        Unique group ID
    """
    content = f"{file_path}:{len(issues)}"
    return hashlib.md5(content.encode()).hexdigest()[:8]


async def run_review_fix_loop(
    pr_context: dict[str, Any],
    base_branch: str,
    max_attempts: int,
    skip_if_approved: bool = True,
) -> ReviewFixLoopResult:
    """Execute review-fix loop with dual-agent review and single fixer.

    This implements the simplified review-fix architecture:
    1. Run both reviewers in parallel (spec + technical)
    2. Combine findings
    3. If approved or no issues, exit loop
    4. Run single fixer agent (handles parallelization internally via subagents)
    5. Loop back until max_attempts exhausted

    The fixer agent receives ALL issues and handles parallelization internally,
    spawning subagents to fix issues affecting different files in parallel.

    Args:
        pr_context: PR context from gather_pr_context (dict with pr_metadata, etc.)
        base_branch: Base branch for comparison
        max_attempts: Maximum review-fix cycles (0 disables fixes)
        skip_if_approved: Skip fix loop if review recommends approve

    Returns:
        ReviewFixLoopResult with review and fix outcomes
    """
    # Convert pr_context if it's a ReviewContextResult
    if hasattr(pr_context, "to_dict"):
        pr_context = pr_context.to_dict()

    if max_attempts <= 0:
        # Just run review once, no fixing
        review_result = await _run_dual_review(pr_context, base_branch)
        return ReviewFixLoopResult(
            success=True,
            attempts=0,
            issues_fixed=(),
            issues_remaining=(),
            final_recommendation=review_result.get("recommendation", "comment"),
            skipped=True,
            skip_reason="Fix attempts disabled (max_attempts=0)",
        )

    attempts = 0
    current_recommendation = "request_changes"

    for attempt_num in range(1, max_attempts + 1):
        attempts = attempt_num
        logger.info("Review-fix cycle %d/%d", attempt_num, max_attempts)

        # Step 1: Run dual review (spec + technical in parallel)
        review_result = await _run_dual_review(pr_context, base_branch)
        current_recommendation = review_result.get("recommendation", "request_changes")

        # Step 2: Check if we're done (approved on first attempt = skip fixes)
        if current_recommendation == "approve":
            logger.info("Review approved on attempt %d", attempt_num)
            return ReviewFixLoopResult(
                success=True,
                attempts=attempts,
                issues_fixed=(),
                issues_remaining=(),
                final_recommendation=current_recommendation,
                skipped=(attempt_num == 1 and skip_if_approved),
                skip_reason="Initial review approved" if attempt_num == 1 else None,
            )

        # Step 3: Check if there are issues worth fixing
        has_critical = review_result.get("has_critical", False)
        review_report = review_result.get("review_report", "")
        has_major = "MAJOR" in review_report.upper() or "### Major" in review_report

        if not has_critical and not has_major:
            logger.info("No critical/major issues, accepting current state")
            return ReviewFixLoopResult(
                success=True,
                attempts=attempts,
                issues_fixed=(),
                issues_remaining=(),
                final_recommendation=current_recommendation,
                skipped=False,
                skip_reason=None,
            )

        # Step 4: Run fixer agent (handles parallelization internally)
        # Don't fix on the last attempt - just report what's remaining
        if attempt_num < max_attempts:
            logger.info("Running review fixer agent")
            await _run_review_fixer(review_result, pr_context)

    # Max attempts exhausted
    return ReviewFixLoopResult(
        success=current_recommendation == "approve",
        attempts=attempts,
        issues_fixed=(),
        issues_remaining=(),
        final_recommendation=current_recommendation,
        skipped=False,
        skip_reason=None,
    )


async def _run_dual_review(
    pr_context: dict[str, Any],
    base_branch: str,
) -> dict[str, Any]:
    """Run both reviewers in parallel and combine results.

    Args:
        pr_context: PR context dict
        base_branch: Base branch for comparison

    Returns:
        Combined review result with recommendation and report
    """
    try:
        # Import reviewer agents
        from maverick.agents.reviewers.spec_reviewer import SpecReviewerAgent
        from maverick.agents.reviewers.technical_reviewer import TechnicalReviewerAgent

        # Build context dict for reviewers
        pr_metadata = pr_context.get("pr_metadata", {})
        if hasattr(pr_metadata, "to_dict"):
            pr_metadata = pr_metadata.to_dict()

        review_context = {
            "pr_metadata": pr_metadata,
            "changed_files": list(pr_context.get("changed_files", [])),
            "diff": pr_context.get("diff", ""),
            "commits": list(pr_context.get("commits", [])),
            "spec_files": pr_context.get("spec_files", {}),
            "base_branch": base_branch,
        }

        # Run both reviewers in parallel
        spec_agent = SpecReviewerAgent()
        technical_agent = TechnicalReviewerAgent()

        spec_task = spec_agent.execute(review_context)
        technical_task = technical_agent.execute(review_context)

        results = await asyncio.gather(
            spec_task, technical_task, return_exceptions=True
        )

        # Extract results with proper type narrowing
        spec_result = results[0]
        tech_result = results[1]

        spec_review: dict[str, Any] | None = None
        if isinstance(spec_result, Exception):
            logger.warning("Spec review failed: %s", spec_result)
        elif isinstance(spec_result, dict):
            spec_review = spec_result

        technical_review: dict[str, Any] | None = None
        if isinstance(tech_result, Exception):
            logger.warning("Technical review failed: %s", tech_result)
        elif isinstance(tech_result, dict):
            technical_review = tech_result

        # Combine results
        combined = await combine_review_results(
            spec_review=spec_review,
            technical_review=technical_review,
            pr_metadata=pr_metadata,
        )

        return {
            "recommendation": combined.recommendation,
            "review_report": combined.review_report,
            "has_critical": (
                technical_review.get("has_critical", False)
                if technical_review is not None
                else False
            ),
        }

    except ImportError as e:
        logger.warning("Failed to import reviewer agents: %s", e)
        return {
            "recommendation": "request_changes",
            "review_report": "",
            "has_critical": False,
        }
    except Exception as e:
        logger.warning("Dual review failed: %s", e)
        return {
            "recommendation": "request_changes",
            "review_report": "",
            "has_critical": False,
        }


async def _run_review_fixer(
    review_result: dict[str, Any],
    pr_context: dict[str, Any],
) -> dict[str, Any]:
    """Run the review fixer agent to address issues.

    The fixer agent handles parallelization internally by spawning subagents
    for issues affecting different files.

    Args:
        review_result: Combined review result with report and recommendation
        pr_context: PR context dict

    Returns:
        Fix result dict
    """
    try:
        from maverick.agents.reviewers.review_fixer import (
            ReviewFixerAgent,
            build_fixer_input_from_legacy,
        )

        # Build context for fixer
        pr_metadata = pr_context.get("pr_metadata", {})
        if hasattr(pr_metadata, "to_dict"):
            pr_metadata = pr_metadata.to_dict()

        legacy_context = {
            "review_report": review_result.get("review_report", ""),
            "recommendation": review_result.get("recommendation", "request_changes"),
            "changed_files": list(pr_context.get("changed_files", [])),
            "diff": pr_context.get("diff", ""),
            "pr_metadata": pr_metadata,
        }

        # Convert legacy dict to typed FixerInput at boundary
        fixer_input = build_fixer_input_from_legacy(legacy_context)

        # Run fixer agent with typed input
        fixer_agent = ReviewFixerAgent()
        result = await fixer_agent.execute(fixer_input)

        # Convert typed output to dict for legacy callers
        return result.to_dict()

    except ImportError as e:
        logger.warning("Failed to import ReviewFixerAgent: %s", e)
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.warning("Review fixer failed: %s", e)
        return {"success": False, "error": str(e)}


def _flatten_issue_groups(
    issue_groups: list[dict[str, Any]],
) -> tuple[ReviewIssue, ...]:
    """Flatten issue groups into a tuple of ReviewIssue objects.

    Args:
        issue_groups: List of issue group dicts

    Returns:
        Tuple of ReviewIssue objects
    """
    issues: list[ReviewIssue] = []
    for group in issue_groups:
        for issue_dict in group.get("issues", []):
            issues.append(
                ReviewIssue(
                    id=issue_dict.get("id", "unknown"),
                    file_path=issue_dict.get("file_path"),
                    line_number=issue_dict.get("line_number"),
                    severity=issue_dict.get("severity", "minor"),
                    category=issue_dict.get("category", "correctness"),
                    description=issue_dict.get("description", ""),
                    suggested_fix=issue_dict.get("suggested_fix"),
                    reviewer=issue_dict.get("reviewer", "technical"),
                )
            )
    return tuple(issues)


async def _fix_issue_groups_parallel(
    issue_groups: list[dict[str, Any]],
    fixer_agent: str,
) -> list[IssueFixResult]:
    """Fix issue groups in parallel where possible.

    Groups affecting different files are fixed in parallel.
    Issues within the same file group are fixed sequentially.

    Args:
        issue_groups: List of issue group dicts
        fixer_agent: Name of fixer agent to use

    Returns:
        List of IssueFixResult for each issue
    """
    # Separate parallelizable and sequential groups
    parallel_groups = [g for g in issue_groups if g.get("can_parallelize", False)]
    sequential_groups = [g for g in issue_groups if not g.get("can_parallelize", False)]

    all_results: list[IssueFixResult] = []

    # Process parallel groups concurrently
    if parallel_groups:
        parallel_tasks = [
            _fix_single_group(group, fixer_agent) for group in parallel_groups
        ]
        parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)

        for result in parallel_results:
            if isinstance(result, Exception):
                logger.warning("Parallel fix group failed: %s", result)
            elif isinstance(result, list):
                all_results.extend(result)

    # Process sequential groups one at a time
    for group in sequential_groups:
        try:
            results = await _fix_single_group(group, fixer_agent)
            all_results.extend(results)
        except Exception as e:
            logger.warning("Sequential fix group failed: %s", e)

    return all_results


async def _fix_single_group(
    group: dict[str, Any],
    fixer_agent: str,
) -> list[IssueFixResult]:
    """Fix all issues in a single group.

    Args:
        group: Issue group dict
        fixer_agent: Name of fixer agent to use

    Returns:
        List of IssueFixResult for issues in this group
    """
    results: list[IssueFixResult] = []
    file_path = group.get("file_path", "unknown")
    issues = group.get("issues", [])

    for issue in issues:
        issue_id = issue.get("id", "unknown")
        description = issue.get("description", "")
        severity = issue.get("severity", "minor")

        try:
            # Build fix prompt for this issue
            fix_prompt = _build_review_fix_prompt(
                file_path=file_path,
                issue_description=description,
                severity=severity,
                suggested_fix=issue.get("suggested_fix"),
            )

            # Invoke fixer agent
            fix_result = await _invoke_review_fixer_agent(
                fix_prompt=fix_prompt,
                fixer_agent=fixer_agent,
            )

            results.append(
                IssueFixResult(
                    issue_id=issue_id,
                    fixed=fix_result.get("success", False),
                    fix_description=fix_result.get("changes_made"),
                    error=fix_result.get("error"),
                )
            )

        except Exception as e:
            logger.warning("Failed to fix issue %s: %s", issue_id, e)
            results.append(
                IssueFixResult(
                    issue_id=issue_id,
                    fixed=False,
                    fix_description=None,
                    error=str(e),
                )
            )

    return results


def _build_review_fix_prompt(
    file_path: str | None,
    issue_description: str,
    severity: str,
    suggested_fix: str | None,
) -> str:
    """Build a prompt for the fixer agent based on review issue.

    Args:
        file_path: File path affected
        issue_description: Description of the issue
        severity: Issue severity
        suggested_fix: Suggested fix if available

    Returns:
        Formatted prompt string for fixer agent
    """
    parts = [f"Fix the following {severity} review issue:"]

    if file_path:
        parts.append(f"\nFile: {file_path}")

    parts.append(f"\nIssue: {issue_description}")

    if suggested_fix:
        parts.append(f"\nSuggested fix: {suggested_fix}")

    parts.append(
        "\n\nPlease apply a minimal fix to resolve this issue. "
        "Focus only on the specific problem described."
    )

    return "\n".join(parts)


async def _invoke_review_fixer_agent(
    fix_prompt: str,
    fixer_agent: str,
) -> dict[str, Any]:
    """Invoke the fixer agent to apply a fix.

    Args:
        fix_prompt: The prompt describing the fix to apply
        fixer_agent: Name of the fixer agent

    Returns:
        Dict with success status and fix details or error message
    """
    try:
        # Import here to avoid circular imports
        from maverick.agents.context import AgentContext
        from maverick.agents.fixer import FixerAgent
        from maverick.config import MaverickConfig

        # Create agent instance
        agent = FixerAgent()

        # Build context with the fix prompt
        context = AgentContext.from_cwd(
            cwd=Path.cwd(),
            config=MaverickConfig(),
            extra={"prompt": fix_prompt},
        )

        # Execute the agent
        result = await agent.execute(context)

        if result.success:
            output = result.output or ""
            try:
                parsed = json.loads(output)
                return {
                    "success": True,
                    "changes_made": parsed.get("changes_made", "Fix applied"),
                }
            except (json.JSONDecodeError, TypeError):
                return {
                    "success": True,
                    "changes_made": output[:200] if output else "Fix applied",
                }
        else:
            error_messages = []
            for error in result.errors or []:
                if hasattr(error, "message"):
                    error_messages.append(error.message)
                else:
                    error_messages.append(str(error))

            return {
                "success": False,
                "error": "; ".join(error_messages) if error_messages else "Fix failed",
            }

    except ImportError as e:
        logger.error("Failed to import agent modules: %s", e)
        return {"success": False, "error": f"Import error: {e}"}
    except ValueError as e:
        logger.error("Invalid context configuration: %s", e)
        return {"success": False, "error": f"Context error: {e}"}
    except Exception as e:
        logger.exception("Unexpected error invoking fixer agent: %s", e)
        return {"success": False, "error": str(e)}


async def _run_review_check(base_branch: str) -> dict[str, Any]:
    """Re-run the review to check if issues are resolved.

    This performs a lightweight review check by gathering PR context
    and re-running the reviewers, without invoking the full workflow.

    Args:
        base_branch: Base branch for comparison

    Returns:
        Review result dict with recommendation
    """
    try:
        # Gather fresh PR context
        context_result = await gather_pr_context(
            pr_number=None,  # Auto-detect from current branch
            base_branch=base_branch,
            include_spec_files=True,
        )

        if context_result.error:
            logger.warning("Failed to gather PR context: %s", context_result.error)
            return {"recommendation": "request_changes"}

        # Import reviewer agents
        from maverick.agents.reviewers.spec_reviewer import SpecReviewerAgent
        from maverick.agents.reviewers.technical_reviewer import TechnicalReviewerAgent

        # Build context dict for reviewers
        review_context = {
            "pr_metadata": context_result.pr_metadata.to_dict(),
            "changed_files": list(context_result.changed_files),
            "diff": context_result.diff,
            "commits": list(context_result.commits),
            "spec_files": context_result.spec_files,
            "base_branch": base_branch,
        }

        # Run both reviewers (simplified - not in parallel to avoid overwhelming)
        spec_review = None
        technical_review = None

        try:
            spec_agent = SpecReviewerAgent()
            spec_review = await spec_agent.execute(review_context)
        except Exception as e:
            logger.warning("Spec review failed in re-check: %s", e)

        try:
            technical_agent = TechnicalReviewerAgent()
            technical_review = await technical_agent.execute(review_context)
        except Exception as e:
            logger.warning("Technical review failed in re-check: %s", e)

        # Combine results
        combined = await combine_review_results(
            spec_review=spec_review,
            technical_review=technical_review,
            pr_metadata=context_result.pr_metadata.to_dict(),
        )

        return {
            "recommendation": combined.recommendation,
            "review_report": combined.review_report,
        }

    except ImportError as e:
        logger.warning("Failed to import reviewer agents: %s", e)
        return {"recommendation": "request_changes"}
    except Exception as e:
        logger.warning("Re-review failed: %s, assuming issues remain", e)
        return {"recommendation": "request_changes"}


async def generate_review_fix_report(
    loop_result: dict[str, Any],
    max_attempts: int,
) -> ReviewAndFixReport:
    """Generate final review-and-fix report.

    Args:
        loop_result: Result from run_review_fix_loop
        max_attempts: Configured max attempts

    Returns:
        ReviewAndFixReport with final summary
    """
    # Handle ReviewFixLoopResult if passed directly
    if hasattr(loop_result, "to_dict"):
        loop_result = loop_result.to_dict()

    # Extract metrics
    attempts = loop_result.get("attempts", 0)
    final_recommendation = loop_result.get("final_recommendation", "comment")
    skipped = loop_result.get("skipped", False)
    skip_reason = loop_result.get("skip_reason")
    success = loop_result.get("success", False)

    # Build fix summary
    fix_summary_lines = []
    if skipped:
        fix_summary_lines.append(f"Fix loop skipped: {skip_reason}")
    elif attempts > 0:
        fix_summary_lines.append(f"Completed {attempts} review-fix cycle(s)")
        if success:
            fix_summary_lines.append("Review passed")
        else:
            fix_summary_lines.append("Issues remain after max attempts")
    else:
        fix_summary_lines.append("No fix attempts needed")

    # Build combined report
    report_lines = []
    report_lines.append("# Review and Fix Report")
    report_lines.append("")
    report_lines.append("## Summary")
    report_lines.append("")
    report_lines.append(f"- **Review-Fix Cycles:** {attempts}/{max_attempts}")
    report_lines.append(f"- **Final Recommendation:** {final_recommendation}")
    report_lines.append(f"- **Success:** {'Yes' if success else 'No'}")
    if skipped:
        report_lines.append(f"- **Skipped:** {skip_reason}")
    report_lines.append("")

    report_lines.append("## Process")
    report_lines.append("")
    for line in fix_summary_lines:
        report_lines.append(f"- {line}")
    report_lines.append("")

    return ReviewAndFixReport(
        review_report="\n".join(report_lines),
        recommendation=final_recommendation,
        issues_found=0,  # Not tracking individual issues in simplified flow
        issues_fixed=0,
        issues_remaining=0,
        attempts=attempts,
        fix_summary=tuple(fix_summary_lines),
    )
