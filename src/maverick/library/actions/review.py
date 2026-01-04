"""Code review actions for workflow execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maverick.library.actions.types import (
    CombinedReviewResult,
    PRMetadata,
    ReviewContextResult,
)
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner

logger = get_logger(__name__)

# Shared runner instance for review actions
_runner = CommandRunner(timeout=60.0)


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
        # Auto-detect PR number if not provided
        current_branch = None
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
