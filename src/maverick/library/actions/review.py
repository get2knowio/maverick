"""Code review actions for workflow execution."""

from __future__ import annotations

import json
import shutil
from typing import Any

from maverick.library.actions.types import (
    CodeRabbitResult,
    CombinedReviewResult,
    PRMetadata,
    ReviewContextResult,
)
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner

logger = get_logger(__name__)

# Shared runner instance for review actions
_runner = CommandRunner(timeout=60.0)
# 5 minute timeout for CodeRabbit
_coderabbit_runner = CommandRunner(timeout=300.0)


async def gather_pr_context(
    pr_number: int | None,
    base_branch: str,
) -> ReviewContextResult:
    """Gather PR context for code review.

    Args:
        pr_number: PR number (optional, auto-detect if None)
        base_branch: Base branch for comparison

    Returns:
        ReviewContextResult with PR metadata and diff
    """
    try:
        # Auto-detect PR number if not provided
        if pr_number is None:
            current_branch_result = await _runner.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            )
            if not current_branch_result.success:
                raise RuntimeError(
                    f"Failed to get current branch: {current_branch_result.stderr}"
                )
            current_branch = current_branch_result.stdout.strip()

            # Try to find PR for current branch
            pr_list_result = await _runner.run(
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
            pr_view_result = await _runner.run(
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

        # Get diff against base branch
        diff_result = await _runner.run(
            ["git", "diff", f"{base_branch}...HEAD"],
        )
        if not diff_result.success:
            raise RuntimeError(f"Failed to get diff: {diff_result.stderr}")
        diff = diff_result.stdout

        # Get changed files
        files_result = await _runner.run(
            ["git", "diff", "--name-only", f"{base_branch}...HEAD"],
        )
        if not files_result.success:
            raise RuntimeError(f"Failed to get changed files: {files_result.stderr}")
        changed_files = tuple(
            f.strip() for f in files_result.stdout.strip().split("\n") if f.strip()
        )

        # Get commit messages
        log_result = await _runner.run(
            [
                "git",
                "log",
                "--oneline",
                f"{base_branch}..HEAD",
            ],
        )
        if not log_result.success:
            raise RuntimeError(f"Failed to get commit log: {log_result.stderr}")
        commits = tuple(
            c.strip() for c in log_result.stdout.strip().split("\n") if c.strip()
        )

        # Check if CodeRabbit CLI is available
        coderabbit_available = shutil.which("coderabbit") is not None

        return ReviewContextResult(
            pr_metadata=pr_metadata,
            changed_files=changed_files,
            diff=diff,
            commits=commits,
            coderabbit_available=coderabbit_available,
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
            coderabbit_available=False,
            error=str(e),
        )


async def run_coderabbit_review(
    pr_number: int | None,
    context: dict[str, Any],
) -> CodeRabbitResult:
    """Execute CodeRabbit review if available.

    Args:
        pr_number: PR number to review
        context: Gathered PR context

    Returns:
        CodeRabbitResult with findings
    """
    # Check if CodeRabbit is available
    if not context.get("coderabbit_available", False):
        logger.info("CodeRabbit CLI not available, skipping CodeRabbit review")
        return CodeRabbitResult(
            available=False,
            findings=(),
            error="CodeRabbit CLI not installed",
        )

    if pr_number is None:
        logger.warning("No PR number available, skipping CodeRabbit review")
        return CodeRabbitResult(
            available=True,
            findings=(),
            error="No PR number available",
        )

    try:
        # Run CodeRabbit review
        result = await _coderabbit_runner.run(
            [
                "coderabbit",
                "review",
                "--pr",
                str(pr_number),
                "--json",
            ],
        )

        if result.timed_out:
            logger.error("CodeRabbit review timed out after 5 minutes")
            return CodeRabbitResult(
                available=True,
                findings=(),
                error="CodeRabbit review timed out",
            )

        if not result.success:
            logger.error(f"CodeRabbit review failed: {result.stderr}")
            return CodeRabbitResult(
                available=True,
                findings=(),
                error=result.stderr or f"Command failed with code {result.returncode}",
            )

        # Parse CodeRabbit output
        findings = []
        if result.stdout.strip():
            try:
                coderabbit_data = json.loads(result.stdout)
                # CodeRabbit may return findings in various formats
                # Normalize to a list of finding dicts
                if isinstance(coderabbit_data, dict):
                    if "findings" in coderabbit_data:
                        findings = coderabbit_data["findings"]
                    elif "issues" in coderabbit_data:
                        findings = coderabbit_data["issues"]
                    else:
                        # Treat the whole object as a single finding
                        findings = [coderabbit_data]
                elif isinstance(coderabbit_data, list):
                    findings = coderabbit_data
            except json.JSONDecodeError:
                logger.warning("CodeRabbit output is not valid JSON, treating as text")
                findings = [{"message": result.stdout, "severity": "info"}]

        return CodeRabbitResult(
            available=True,
            findings=tuple(findings),
            error=None,
        )

    except Exception as e:
        logger.error(f"CodeRabbit review failed: {e}")
        return CodeRabbitResult(
            available=True,
            findings=(),
            error=str(e),
        )


async def combine_review_results(
    agent_review: dict[str, Any],
    coderabbit_review: dict[str, Any],
    pr_metadata: dict[str, Any],
) -> CombinedReviewResult:
    """Combine review results from multiple sources.

    Args:
        agent_review: Agent review output
        coderabbit_review: CodeRabbit review output
        pr_metadata: PR metadata

    Returns:
        CombinedReviewResult with unified report
    """
    # Extract issues from both sources
    agent_issues = []
    if isinstance(agent_review, dict):
        # Agent review may have various structures
        if "issues" in agent_review:
            agent_issues = list(agent_review["issues"])
        elif "findings" in agent_review:
            agent_issues = list(agent_review["findings"])
        elif "comments" in agent_review:
            agent_issues = list(agent_review["comments"])

    coderabbit_issues = list(coderabbit_review.get("findings", ()))

    # Combine and de-duplicate issues
    all_issues = []
    seen_issues = set()

    for issue in agent_issues:
        # Create a simple hash key for deduplication
        issue_key = (
            issue.get("file", ""),
            issue.get("line", 0),
            issue.get("message", "")[:100],
        )
        if issue_key not in seen_issues:
            seen_issues.add(issue_key)
            all_issues.append(
                {
                    **issue,
                    "source": "agent",
                }
            )

    for issue in coderabbit_issues:
        issue_key = (
            issue.get("file", ""),
            issue.get("line", 0),
            issue.get("message", "")[:100],
        )
        if issue_key not in seen_issues:
            seen_issues.add(issue_key)
            all_issues.append(
                {
                    **issue,
                    "source": "coderabbit",
                }
            )

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

    report_lines.append("## Summary")
    report_lines.append("")
    report_lines.append(f"- Total issues found: {len(all_issues)}")
    agent_count = len([i for i in all_issues if i.get("source") == "agent"])
    report_lines.append(f"- Agent review issues: {agent_count}")
    coderabbit_count = len([i for i in all_issues if i.get("source") == "coderabbit"])
    report_lines.append(f"- CodeRabbit issues: {coderabbit_count}")
    report_lines.append("")

    # Group issues by severity
    severity_groups: dict[str, list[dict[str, Any]]] = {
        "critical": [],
        "error": [],
        "warning": [],
        "info": [],
        "other": [],
    }

    for issue in all_issues:
        severity = issue.get("severity", "other").lower()
        if severity in severity_groups:
            severity_groups[severity].append(issue)
        else:
            severity_groups["other"].append(issue)

    # Add issues to report by severity
    for severity in ["critical", "error", "warning", "info", "other"]:
        issues = severity_groups[severity]
        if not issues:
            continue

        report_lines.append(f"## {severity.title()} Issues ({len(issues)})")
        report_lines.append("")

        for i, issue in enumerate(issues, 1):
            file_info = issue.get("file", "unknown")
            line_info = issue.get("line", "")
            if line_info:
                file_info = f"{file_info}:{line_info}"

            source = issue.get("source", "unknown")
            report_lines.append(f"{i}. **{file_info}** ({source})")
            report_lines.append(f"   {issue.get('message', 'No message')}")
            report_lines.append("")

    # Determine recommendation
    critical_count = len(severity_groups["critical"])
    error_count = len(severity_groups["error"])
    warning_count = len(severity_groups["warning"])

    if critical_count > 0 or error_count > 0:
        recommendation = "request_changes"
    elif warning_count > 3:
        recommendation = "comment"
    elif len(all_issues) == 0:
        recommendation = "approve"
    else:
        recommendation = "comment"

    report_lines.append("## Recommendation")
    report_lines.append("")
    report_lines.append(f"**{recommendation.replace('_', ' ').title()}**")

    return CombinedReviewResult(
        review_report="\n".join(report_lines),
        issues=tuple(all_issues),
        recommendation=recommendation,
    )
