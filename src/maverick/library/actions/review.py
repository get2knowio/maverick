"""Code review actions for workflow execution."""

from __future__ import annotations

import fnmatch
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    StreamCallback = Callable[[str], Coroutine[None, None, None]] | None

from maverick.git import AsyncGitRepository
from maverick.library.actions.types import (
    AnalyzedFindingsResult,
    IssueGroup,
    ReviewAndFixReport,
    ReviewContextResult,
    ReviewFixLoopResult,
    ReviewIssue,
    ReviewMetadata,
)
from maverick.logging import get_logger

logger = get_logger(__name__)

# Default patterns to exclude from review scope
# These are typically tooling/spec files, not implementation code
DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...] = (
    "specs/**",
    ".specify/**",
    ".claude/**",
    ".github/**",
)


def _matches_any_pattern(path: str, patterns: tuple[str, ...]) -> bool:
    """Check if a path matches any of the given glob patterns.

    Args:
        path: File path to check
        patterns: Tuple of glob patterns (e.g., "specs/**", "*.md")

    Returns:
        True if path matches any pattern
    """
    for pattern in patterns:
        # Handle ** patterns by checking if path starts with the prefix
        if "**" in pattern:
            prefix = pattern.split("**")[0].rstrip("/")
            if path.startswith(prefix) or path.startswith(prefix + "/"):
                return True
        # Standard fnmatch for other patterns
        elif fnmatch.fnmatch(path, pattern):
            return True
    return False


def _filter_changed_files(
    files: tuple[str, ...],
    exclude_patterns: tuple[str, ...],
) -> tuple[str, ...]:
    """Filter changed files list to exclude matching patterns.

    Args:
        files: Tuple of file paths
        exclude_patterns: Patterns to exclude

    Returns:
        Filtered tuple of file paths
    """
    if not exclude_patterns:
        return files
    return tuple(f for f in files if not _matches_any_pattern(f, exclude_patterns))


def _filter_diff(diff: str, exclude_patterns: tuple[str, ...]) -> str:
    """Filter diff to remove hunks for excluded files.

    Args:
        diff: Full diff string
        exclude_patterns: Patterns to exclude

    Returns:
        Filtered diff string
    """
    if not exclude_patterns or not diff:
        return diff

    # Split diff into file sections (each starts with "diff --git")
    sections = re.split(r"(?=^diff --git )", diff, flags=re.MULTILINE)

    filtered_sections = []
    for section in sections:
        if not section.strip():
            continue

        # Extract the file path from the diff header
        # Format: "diff --git a/path/to/file b/path/to/file"
        match = re.match(r"diff --git a/(.+?) b/", section)
        if match:
            file_path = match.group(1)
            if _matches_any_pattern(file_path, exclude_patterns):
                logger.debug(f"Excluding from diff: {file_path}")
                continue

        filtered_sections.append(section)

    return "".join(filtered_sections)


async def gather_local_review_context(
    base_branch: str = "main",
    include_spec_files: bool = False,
    spec_dir: str | None = None,
    exclude_patterns: tuple[str, ...] | list[str] | None = None,
    cwd: str | None = None,
) -> ReviewContextResult:
    """Gather local review context including uncommitted changes.

    Combines uncommitted changes (staged + unstaged) with committed
    branch changes to produce a single review context suitable for pre-commit
    review workflows. Does not depend on the ``gh`` CLI.

    Args:
        base_branch: Base branch for comparison (default: "main").
        include_spec_files: Whether to include spec files in context.
        spec_dir: Directory containing spec files (auto-detect if None).
        exclude_patterns: Glob patterns for files to exclude from review scope.
            Defaults to DEFAULT_EXCLUDE_PATTERNS.
        cwd: Working directory for git operations (defaults to current directory).

    Returns:
        ReviewContextResult with diff, changed files, and optionally spec files.
    """
    if exclude_patterns is None:
        exclude_patterns = DEFAULT_EXCLUDE_PATTERNS
    elif isinstance(exclude_patterns, list):
        exclude_patterns = tuple(exclude_patterns)

    try:
        repo = AsyncGitRepository(cwd)

        current_branch = await repo.current_branch()

        # Get uncommitted diff (staged + unstaged vs HEAD)
        uncommitted_diff = await repo.diff("HEAD")

        # Get branch diff (committed changes since base)
        branch_diff = await repo.diff(base=f"{base_branch}...HEAD")

        # Combine both diffs
        combined_parts: list[str] = []
        if branch_diff:
            combined_parts.append(branch_diff)
        if uncommitted_diff:
            combined_parts.append(uncommitted_diff)
        raw_diff = "\n".join(combined_parts)

        # Get changed files from both uncommitted status and branch diff
        status = await repo.status()
        local_files = set(status.staged + status.unstaged + status.untracked)

        branch_changed = await repo.get_changed_files(ref=f"{base_branch}...HEAD")
        all_changed = tuple(sorted(local_files | set(branch_changed)))

        # Apply exclusion filters
        if exclude_patterns:
            changed_files = _filter_changed_files(all_changed, exclude_patterns)
            diff = _filter_diff(raw_diff, exclude_patterns)
        else:
            changed_files = all_changed
            diff = raw_diff

        # Get commit messages since base branch
        commit_messages = await repo.commit_messages_since(ref=base_branch)
        commits = tuple(commit_messages)

        # Gather spec files if requested
        spec_files: dict[str, str] = {}
        if include_spec_files:
            spec_files = await _gather_spec_files(spec_dir, current_branch)

        return ReviewContextResult(
            review_metadata=ReviewMetadata(base_branch=base_branch),
            changed_files=changed_files,
            diff=diff,
            commits=commits,
            spec_files=spec_files,
            error=None,
        )

    except Exception as e:
        logger.debug(f"Failed to gather local review context: {e}")
        return ReviewContextResult(
            review_metadata=ReviewMetadata(base_branch=base_branch),
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
    review_input: dict[str, Any],
    base_branch: str,
    max_attempts: int,
    skip_if_approved: bool = True,
    generate_report: bool = False,
    stream_callback: StreamCallback | None = None,
    cwd: str | None = None,
    briefing_context: str | None = None,
) -> ReviewFixLoopResult | ReviewAndFixReport:
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
        review_input: Review context dict (from ``gather_local_review_context``)
            containing review_metadata,
            changed_files, diff, etc.
        base_branch: Base branch for comparison
        max_attempts: Maximum review-fix cycles (0 disables fixes)
        skip_if_approved: Skip fix loop if review recommends approve
        generate_report: When True (default), generate a
            ``ReviewAndFixReport`` instead of the raw ``ReviewFixLoopResult``.
        stream_callback: Optional callback for streaming agent output text.
        cwd: Working directory for review/fix operations (defaults to current
            directory). When provided, overrides any cwd in review_input.
        briefing_context: Optional serialized BriefingDocument content. When
            provided, reviewers receive architecture decisions, data model
            contracts, and risk analysis to verify implementation against.

    Returns:
        When *generate_report* is True: ``ReviewAndFixReport`` with the final
        summary.  Otherwise: ``ReviewFixLoopResult`` with raw review and fix
        outcomes.
    """
    # Convert review_input if it's a ReviewContextResult
    if hasattr(review_input, "to_dict"):
        review_input = review_input.to_dict()

    # Inject explicit cwd so reviewers/fixers use it
    if cwd:
        review_input["cwd"] = cwd

    # Inject briefing context for architecture/risk-aware review
    if briefing_context:
        review_input["briefing_context"] = briefing_context

    async def _maybe_report(
        result: ReviewFixLoopResult,
    ) -> ReviewFixLoopResult | ReviewAndFixReport:
        if generate_report:
            return await generate_review_fix_report(
                loop_result=result.to_dict(),
                max_attempts=max_attempts,
            )
        return result

    if max_attempts <= 0:
        # Just run review once, no fixing
        review_result = await _run_dual_review(
            review_input, base_branch, stream_callback
        )
        return await _maybe_report(
            ReviewFixLoopResult(
                success=True,
                attempts=0,
                issues_fixed=(),
                issues_remaining=(),
                final_recommendation=review_result.get("recommendation", "comment"),
                skipped=True,
                skip_reason="Fix attempts disabled (max_attempts=0)",
            )
        )

    attempts = 0
    current_recommendation = "request_changes"
    review_errors: list[str] = []

    for attempt_num in range(1, max_attempts + 1):
        attempts = attempt_num
        logger.info("Review-fix cycle %d/%d", attempt_num, max_attempts)

        # Step 1: Run dual review (spec + technical in parallel)
        review_result = await _run_dual_review(
            review_input, base_branch, stream_callback
        )
        current_recommendation = review_result.get("recommendation", "request_changes")

        # Step 1b: Handle reviewer errors — don't treat failures as clean reviews
        if current_recommendation == "error":
            review_error = review_result.get("review_error", "unknown")
            review_errors.append(f"attempt {attempt_num}: {review_error}")
            logger.warning(
                "Review errored on attempt %d: %s", attempt_num, review_error
            )
            # Don't try to fix when we can't even review — skip to next attempt
            # so we get a fresh retry of the reviewers
            continue

        # Step 2: Check if we're done (approved on first attempt = skip fixes)
        if current_recommendation == "approve":
            logger.info("Review approved on attempt %d", attempt_num)
            return await _maybe_report(
                ReviewFixLoopResult(
                    success=True,
                    attempts=attempts,
                    issues_fixed=(),
                    issues_remaining=(),
                    final_recommendation=current_recommendation,
                    skipped=(attempt_num == 1 and skip_if_approved),
                    skip_reason="Initial review approved" if attempt_num == 1 else None,
                )
            )

        # Step 3: Check if there are issues worth fixing
        has_critical = review_result.get("has_critical", False)
        review_report = review_result.get("review_report", "")
        has_major = "MAJOR" in review_report.upper() or "### Major" in review_report

        if not has_critical and not has_major:
            logger.info("No critical/major issues, accepting current state")
            return await _maybe_report(
                ReviewFixLoopResult(
                    success=True,
                    attempts=attempts,
                    issues_fixed=(),
                    issues_remaining=(),
                    final_recommendation=current_recommendation,
                    skipped=False,
                    skip_reason=None,
                )
            )

        # Step 4: Run fixer agent (handles parallelization internally)
        # Don't fix on the last attempt - just report what's remaining
        if attempt_num < max_attempts:
            logger.info("Running review fixer agent")
            fix_result = await _run_review_fixer(
                review_result, review_input, stream_callback
            )
            if not fix_result.get("success", False):
                fix_error = fix_result.get("error", "unknown")
                logger.warning(
                    "Review fixer failed on attempt %d: %s", attempt_num, fix_error
                )
                review_errors.append(f"attempt {attempt_num} fixer: {fix_error}")
                # Continue to next iteration — the re-review will show whether
                # the fixer managed partial progress before failing

    # Max attempts exhausted — if every attempt was a reviewer error, report failure
    if review_errors and current_recommendation == "error":
        logger.error("Review loop exhausted with errors: %s", review_errors)
        current_recommendation = "request_changes"

    return await _maybe_report(
        ReviewFixLoopResult(
            success=current_recommendation == "approve",
            attempts=attempts,
            issues_fixed=(),
            issues_remaining=(),
            final_recommendation=current_recommendation,
            skipped=False,
            skip_reason=None,
        )
    )


async def _run_dual_review(
    review_input: dict[str, Any],
    base_branch: str,
    stream_callback: StreamCallback | None = None,
) -> dict[str, Any]:
    """Run completeness and correctness reviewers in parallel.

    Spawns two independent reviewer agents concurrently via asyncio.gather,
    then merges their GroupedReviewResult outputs with de-duplicated finding IDs.

    Args:
        review_input: Review context dict with review_metadata, changed_files,
            diff, cwd, and optional briefing_context.
        base_branch: Base branch for comparison
        stream_callback: Optional callback for streaming agent output text.

    Returns:
        Review result with recommendation and report
    """
    import asyncio

    try:
        from maverick.agents.reviewers import (
            CompletenessReviewerAgent,
            CorrectnessReviewerAgent,
        )

        # Build context dict for reviewers — accept both old and new key names
        review_meta = review_input.get(
            "review_metadata", review_input.get("pr_metadata", {})
        )
        if hasattr(review_meta, "to_dict"):
            review_meta = review_meta.to_dict()

        review_context: dict[str, Any] = {
            "review_metadata": review_meta,
            "changed_files": list(review_input.get("changed_files", [])),
            "diff": review_input.get("diff", ""),
            "cwd": review_input.get("cwd"),
        }

        # Thread briefing context for completeness reviewer
        briefing = review_input.get("briefing_context")
        if briefing:
            review_context["briefing_context"] = briefing

        # Run both reviewers in parallel via ACP executor
        from maverick.executor import create_default_executor
        from maverick.models.review_models import GroupedReviewResult

        completeness = CompletenessReviewerAgent()
        correctness = CorrectnessReviewerAgent()
        _executor = create_default_executor()
        try:
            completeness_task = _executor.execute(
                step_name="completeness_review",
                agent_name=completeness.name,
                prompt=review_context,
                output_schema=GroupedReviewResult,
            )
            correctness_task = _executor.execute(
                step_name="correctness_review",
                agent_name=correctness.name,
                prompt=review_context,
                output_schema=GroupedReviewResult,
            )
            completeness_result, correctness_result = await asyncio.gather(
                completeness_task, correctness_task, return_exceptions=True
            )

            # Handle individual reviewer failures gracefully
            completeness_groups: list[Any] = []
            correctness_groups: list[Any] = []
            completeness_failed = isinstance(completeness_result, Exception)
            correctness_failed = isinstance(correctness_result, Exception)

            if completeness_failed:
                logger.warning("Completeness reviewer failed: %s", completeness_result)
            elif not isinstance(completeness_result, BaseException):
                output = completeness_result.output
                if isinstance(output, GroupedReviewResult):
                    completeness_groups = list(output.groups)

            if correctness_failed:
                logger.warning("Correctness reviewer failed: %s", correctness_result)
            elif not isinstance(correctness_result, BaseException):
                output = correctness_result.output
                if isinstance(output, GroupedReviewResult):
                    correctness_groups = list(output.groups)

            # If both reviewers failed, report as error — don't
            # masquerade as "no issues found"
            if completeness_failed and correctness_failed:
                await _executor.cleanup()
                errors = [str(completeness_result), str(correctness_result)]
                return {
                    "recommendation": "error",
                    "review_report": "",
                    "has_critical": False,
                    "review_error": f"Both reviewers failed: {'; '.join(errors)}",
                }

            # Merge results — re-number correctness findings to avoid ID collisions
            max_completeness_id = 0
            for group in completeness_groups:
                for finding in group.findings:
                    # Extract numeric part of F001, F002, etc.
                    num = "".join(c for c in finding.id if c.isdigit())
                    if num:
                        max_completeness_id = max(max_completeness_id, int(num))

            renumbered_correctness_groups = []
            for group in correctness_groups:
                renumbered_findings = []
                for finding in group.findings:
                    max_completeness_id += 1
                    renumbered_findings.append(
                        finding.model_copy(update={"id": f"F{max_completeness_id:03d}"})
                    )
                if renumbered_findings:
                    from maverick.models.review_models import FindingGroup

                    renumbered_correctness_groups.append(
                        FindingGroup(
                            description=group.description,
                            findings=renumbered_findings,
                        )
                    )

            result = GroupedReviewResult(
                groups=completeness_groups + renumbered_correctness_groups
            )
        finally:
            await _executor.cleanup()

        # Check for critical/major issues
        has_critical = any(f.severity == "critical" for f in result.all_findings)
        has_major = any(f.severity == "major" for f in result.all_findings)

        # Determine recommendation
        if result.total_count == 0:
            recommendation = "approve"
        elif has_critical:
            recommendation = "request_changes"
        elif has_major:
            recommendation = "comment"
        else:
            recommendation = "approve"

        # Build report from findings
        report_lines = ["# Code Review Report", ""]
        for group in result.groups:
            report_lines.append(f"## {group.description}")
            for finding in group.findings:
                report_lines.append(
                    f"- **{finding.severity.upper()}** [{finding.category}] "
                    f"`{finding.file}:{finding.line}`: {finding.issue}"
                )
            report_lines.append("")

        return {
            "recommendation": recommendation,
            "review_report": "\n".join(report_lines),
            "has_critical": has_critical,
            "review_result": result,  # Pass through for fixer
        }

    except ImportError as e:
        logger.warning("Failed to import reviewer agents: %s", e)
        return {
            "recommendation": "error",
            "review_report": "",
            "has_critical": False,
            "review_error": str(e),
        }
    except Exception as e:
        logger.warning("Review failed: %s", e)
        return {
            "recommendation": "error",
            "review_report": "",
            "has_critical": False,
            "review_error": str(e),
        }


async def _run_review_fixer(
    review_result: dict[str, Any],
    review_input: dict[str, Any],
    stream_callback: StreamCallback | None = None,
) -> dict[str, Any]:
    """Run the review fixer agent to address issues.

    The fixer agent handles parallelization internally by spawning subagents
    for issues affecting different files.

    Args:
        review_result: Combined review result with report and recommendation
        review_input: Review context dict
        stream_callback: Optional callback for streaming agent output text.

    Returns:
        Fix result dict with outcomes for each finding
    """
    try:
        from maverick.agents.reviewers import SimpleFixerAgent

        # Get the ReviewResult from parallel reviewers
        result_obj = review_result.get("review_result")
        if result_obj is None:
            logger.warning("No review_result in review_result dict")
            return {"success": False, "error": "No findings to fix"}

        # Extract findings from all groups
        all_findings = list(result_obj.all_findings)
        if not all_findings:
            logger.info("No findings to fix")
            return {"success": True, "outcomes": [], "message": "No findings to fix"}

        # Get working directory
        cwd = review_input.get("cwd") or Path.cwd()

        # Run simple fixer via ACP executor; parse outcomes from raw text output
        from maverick.executor import create_default_executor

        fixer = SimpleFixerAgent()
        _executor = create_default_executor()
        try:
            _fix_result = await _executor.execute(
                step_name="review_fixer",
                agent_name=fixer.name,
                prompt={
                    "findings": all_findings,
                    "cwd": cwd,
                },
            )
            raw_output = str(_fix_result.output) if _fix_result.output else ""
            outcomes = fixer.parse_outcomes(raw_output, all_findings)
        finally:
            await _executor.cleanup()

        # Convert outcomes to dict for legacy callers
        return {
            "success": True,
            "outcomes": [
                {
                    "id": o.id,
                    "outcome": o.outcome,
                    "explanation": o.explanation,
                }
                for o in outcomes
            ],
        }

    except ImportError as e:
        logger.warning("Failed to import SimpleFixerAgent: %s", e)
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.warning("Review fixer failed: %s", e)
        return {"success": False, "error": str(e)}


async def _run_review_check(base_branch: str) -> dict[str, Any]:
    """Re-run the review to check if issues are resolved.

    Gathers local review context and re-runs the parallel reviewers.

    Args:
        base_branch: Base branch for comparison

    Returns:
        Review result dict with recommendation
    """
    try:
        context_result = await gather_local_review_context(
            base_branch=base_branch,
            include_spec_files=True,
        )

        if context_result.error:
            logger.warning("Failed to gather review context: %s", context_result.error)
            return {"recommendation": "request_changes"}

        review_input = {
            "review_metadata": context_result.review_metadata.to_dict(),
            "changed_files": list(context_result.changed_files),
            "diff": context_result.diff,
            "commits": list(context_result.commits),
            "spec_files": context_result.spec_files,
        }

        return await _run_dual_review(review_input, base_branch)

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

    # Only upgrade to "approve" when the loop genuinely succeeded AND the
    # final recommendation isn't already indicating a problem.  Never
    # upgrade "request_changes" or "error" to "approve" — that masks
    # reviewer/fixer failures.
    if success and final_recommendation in ("approve", "comment"):
        effective_recommendation = "approve"
    else:
        effective_recommendation = final_recommendation

    # When the loop failed (not approved), report issues_remaining > 0
    # so verify_bead_completion correctly blocks the commit.
    # We use 1 as a sentinel since we don't track individual counts.
    effective_remaining = 0 if effective_recommendation == "approve" else 1

    return ReviewAndFixReport(
        review_report="\n".join(report_lines),
        recommendation=effective_recommendation,
        issues_found=0 if effective_recommendation == "approve" else 1,
        issues_fixed=0,
        issues_remaining=effective_remaining,
        attempts=attempts,
        fix_summary=tuple(fix_summary_lines),
    )
