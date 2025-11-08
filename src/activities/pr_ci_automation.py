"""Activity for PR CI automation.

This activity creates or reuses pull requests, monitors CI status,
merges successful PRs, and returns structured failure evidence.
"""

import asyncio
import contextlib
import json
from typing import Any

from temporalio import activity

from src.models.phase_automation import PullRequestAutomationRequest, PullRequestAutomationResult
from src.utils.logging import get_structured_logger


logger = get_structured_logger("activity.pr_ci_automation")


@activity.defn(name="pr_ci_automation")
async def pr_ci_automation(request: PullRequestAutomationRequest) -> PullRequestAutomationResult:
    """Execute PR CI automation workflow.

    Creates or reuses a pull request, monitors CI status with exponential backoff,
    merges on success, or returns structured failure/timeout evidence.

    Args:
        request: PR automation configuration including source branch, target, summary

    Returns:
        PullRequestAutomationResult with terminal status and contextual metadata
    """
    import time

    from src.models.phase_automation import PollingConfiguration

    activity_start_time = time.time()

    logger.info(
        "pr_ci_automation_started",
        source_branch=request.source_branch,
        target_branch=request.target_branch,
        workflow_attempt_id=request.workflow_attempt_id,
    )

    try:
        # 1. Check remote branch exists
        branch_exists = await check_remote_branch_exists(request.source_branch)
        if not branch_exists:
            error_msg = f"Source branch '{request.source_branch}' not found on remote"
            logger.error("source_branch_missing", branch=request.source_branch)
            return PullRequestAutomationResult(
                status="error",
                polling_duration_seconds=0,
                error_detail=error_msg,
            )

        # 2. Resolve target branch
        target_branch = await resolve_target_branch(request.target_branch)

        # 3. Find or create PR
        pr_number, pr_url, created, pr_state = await find_or_create_pr(
            source_branch=request.source_branch,
            target_branch=target_branch,
            summary=request.summary,
        )

        # 3a. Check if PR is already merged (resume case)
        if pr_state == "MERGED":
            logger.info(
                "pr_already_merged",
                pr_number=pr_number,
                workflow_attempt_id=request.workflow_attempt_id,
            )
            # Get merge commit SHA for already-merged PR
            merge_sha = await get_merge_commit_sha(pr_number)
            return PullRequestAutomationResult(
                status="merged",
                polling_duration_seconds=0,
                pull_request_number=pr_number,
                pull_request_url=pr_url,
                merge_commit_sha=merge_sha,
            )

        # 4. Validate base branch alignment
        try:
            await validate_base_branch(pr_number, target_branch)
        except ValueError as e:
            logger.error("base_branch_validation_error", error=str(e))
            return PullRequestAutomationResult(
                status="error",
                polling_duration_seconds=0,
                pull_request_number=pr_number,
                pull_request_url=pr_url,
                error_detail=str(e),
                retry_advice="Update target branch to match PR base",
            )

        # 5. Update PR description if needed (non-blocking)
        if not created:
            await update_pr_description(pr_number, request.summary)

        # 6. Poll CI status with timeout
        polling_config = request.polling or PollingConfiguration()

        poll_start_time = time.time()
        result = await poll_ci_with_timeout(pr_number, polling_config)
        poll_duration = int(time.time() - poll_start_time)

        # Emit SLA metrics
        logger.info(
            "ci_poll_sla_metrics",
            pr_number=pr_number,
            poll_duration_seconds=poll_duration,
            status=result.status,
            workflow_attempt_id=request.workflow_attempt_id,
        )

        # 7. Handle terminal states
        if result.status == "ci_failed" or result.status == "timeout":
            # Return failure/timeout without merge
            return result

        if result.status == "merged":
            # Attempt merge
            try:
                merge_start_time = time.time()
                merge_sha = await merge_pull_request(pr_number)
                merge_duration = int(time.time() - merge_start_time)

                # Emit merge SLA metrics
                logger.info(
                    "pr_merge_sla_metrics",
                    pr_number=pr_number,
                    merge_duration_seconds=merge_duration,
                    merge_sha=merge_sha,
                    workflow_attempt_id=request.workflow_attempt_id,
                )

                return PullRequestAutomationResult(
                    status="merged",
                    polling_duration_seconds=poll_duration,
                    pull_request_number=pr_number,
                    pull_request_url=pr_url,
                    merge_commit_sha=merge_sha,
                )

            except RuntimeError as e:
                logger.error("merge_execution_failed", error=str(e))
                return PullRequestAutomationResult(
                    status="error",
                    polling_duration_seconds=poll_duration,
                    pull_request_number=pr_number,
                    pull_request_url=pr_url,
                    error_detail=f"Merge failed: {e}",
                    retry_advice="Check PR mergeable state",
                )

        # Unexpected status
        logger.error("unexpected_poll_status", status=result.status)
        return result

    except Exception as e:
        duration = int(time.time() - activity_start_time)
        logger.error(
            "pr_ci_automation_exception",
            error_type=type(e).__name__,
            error=str(e),
            duration_seconds=duration,
        )
        return PullRequestAutomationResult(
            status="error",
            polling_duration_seconds=duration,
            error_detail=f"Unexpected error: {e}",
            retry_advice="Check logs and retry",
        )


async def check_remote_branch_exists(branch_name: str, remote: str = "origin") -> bool:
    """Check if a branch exists on the remote repository.

    Args:
        branch_name: Name of the branch to check
        remote: Remote name (default: "origin")

    Returns:
        True if branch exists on remote, False otherwise

    Raises:
        RuntimeError: If git command fails
    """
    logger.info("checking_remote_branch", branch=branch_name, remote=remote)

    try:
        process = await asyncio.create_subprocess_exec(
            "git",
            "ls-remote",
            "--heads",
            remote,
            branch_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_output = stderr.decode("utf-8", errors="replace")
            logger.error(
                "remote_branch_check_failed",
                branch=branch_name,
                remote=remote,
                exit_code=process.returncode,
                error=error_output,
            )
            raise RuntimeError(f"Failed to check remote branch: {error_output}")

        # Parse output - if branch exists, output contains the ref
        output = stdout.decode("utf-8", errors="replace").strip()
        exists = len(output) > 0

        logger.info("remote_branch_checked", branch=branch_name, exists=exists)
        return exists

    except FileNotFoundError as e:
        logger.error("git_not_found", error=str(e))
        raise RuntimeError("git command not found") from e


async def resolve_target_branch(explicit_target: str | None = None) -> str:
    """Resolve the target branch for PR creation.

    If explicit_target is provided, uses it directly. Otherwise, queries
    the repository's default branch via gh CLI.

    Args:
        explicit_target: Explicitly specified target branch (optional)

    Returns:
        Resolved target branch name

    Raises:
        RuntimeError: If default branch resolution fails
    """
    if explicit_target:
        logger.info("using_explicit_target", target=explicit_target)
        return explicit_target

    logger.info("resolving_default_branch")

    try:
        process = await asyncio.create_subprocess_exec(
            "gh",
            "repo",
            "view",
            "--json",
            "defaultBranchRef,owner,name",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_output = stderr.decode("utf-8", errors="replace")
            logger.error(
                "default_branch_resolution_failed",
                exit_code=process.returncode,
                error=error_output,
            )
            raise RuntimeError(f"Failed to resolve default branch: {error_output}")

        # Parse JSON response
        try:
            repo_data = json.loads(stdout.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as e:
            logger.error("invalid_repo_json", error=str(e))
            raise RuntimeError(f"Failed to parse repository data: {e}") from e

        # Extract default branch name
        default_branch_ref = repo_data.get("defaultBranchRef")
        if not default_branch_ref or "name" not in default_branch_ref:
            logger.error("missing_default_branch_ref", repo_data=repo_data)
            raise RuntimeError("Missing defaultBranchRef in repository data")

        default_branch = default_branch_ref["name"]
        logger.info("default_branch_resolved", branch=default_branch)
        return default_branch

    except FileNotFoundError as e:
        logger.error("gh_not_found", error=str(e))
        raise RuntimeError("gh command not found") from e


async def find_or_create_pr(
    source_branch: str,
    target_branch: str,
    summary: str,
) -> tuple[int, str, bool, str]:
    """Find existing PR or create a new one.

    Args:
        source_branch: Head branch name
        target_branch: Base branch name
        summary: PR description body

    Returns:
        Tuple of (pr_number, pr_url, created, state) where created=True for new PRs
        and state is the PR state (OPEN, MERGED, CLOSED)

    Raises:
        RuntimeError: If gh commands fail
    """
    logger.info(
        "finding_or_creating_pr",
        source_branch=source_branch,
        target_branch=target_branch,
    )

    # Try to find existing PR
    try:
        process = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "view",
            "--head",
            source_branch,
            "--json",
            "number,state,baseRefName,headRefName,url,mergedAt,isCrossRepository",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            # PR exists - parse and return
            try:
                pr_data = json.loads(stdout.decode("utf-8", errors="replace"))
                pr_number = pr_data["number"]
                pr_url = pr_data["url"]
                pr_state = pr_data.get("state", "OPEN")

                logger.info(
                    "existing_pr_found",
                    pr_number=pr_number,
                    pr_url=pr_url,
                    state=pr_state,
                )
                return (pr_number, pr_url, False, pr_state)

            except (json.JSONDecodeError, KeyError) as e:
                logger.error("invalid_pr_json", error=str(e))
                raise RuntimeError(f"Failed to parse PR data: {e}") from e

        # PR doesn't exist - create it
        logger.info("no_existing_pr_creating_new")

    except FileNotFoundError as e:
        logger.error("gh_not_found", error=str(e))
        raise RuntimeError("gh command not found") from e

    # Create new PR
    try:
        process = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "create",
            "--title",
            "Automated PR",
            "--body",
            summary,
            "--base",
            target_branch,
            "--head",
            source_branch,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_output = stderr.decode("utf-8", errors="replace")
            logger.error(
                "pr_creation_failed",
                exit_code=process.returncode,
                error=error_output,
            )
            raise RuntimeError(f"Failed to create PR: {error_output}")

        # Parse creation response
        try:
            pr_data = json.loads(stdout.decode("utf-8", errors="replace"))
            pr_number = pr_data["number"]
            pr_url = pr_data["url"]

            logger.info(
                "pr_created",
                pr_number=pr_number,
                pr_url=pr_url,
            )
            return (pr_number, pr_url, True, "OPEN")

        except (json.JSONDecodeError, KeyError) as e:
            logger.error("invalid_pr_creation_json", error=str(e))
            raise RuntimeError(f"Failed to parse PR creation response: {e}") from e

    except FileNotFoundError as e:
        logger.error("gh_not_found", error=str(e))
        raise RuntimeError("gh command not found") from e


async def update_pr_description(pr_number: int, new_summary: str) -> None:
    """Update an existing PR's description.

    Args:
        pr_number: PR number to update
        new_summary: New description body

    Note:
        Logs warning but doesn't raise on failure to avoid blocking automation
    """
    logger.info("updating_pr_description", pr_number=pr_number)

    try:
        process = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "edit",
            str(pr_number),
            "--body",
            new_summary,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_output = stderr.decode("utf-8", errors="replace")
            logger.warning(
                "pr_description_update_failed",
                pr_number=pr_number,
                error=error_output,
            )
        else:
            logger.info("pr_description_updated", pr_number=pr_number)

    except Exception as e:
        logger.warning(
            "pr_description_update_exception",
            pr_number=pr_number,
            error=str(e),
        )


async def get_merge_commit_sha(pr_number: int) -> str:
    """Get merge commit SHA for an already-merged pull request.

    Args:
        pr_number: PR number to query

    Returns:
        Merge commit SHA

    Raises:
        RuntimeError: If query fails or PR is not merged
    """
    logger.info("getting_merge_commit_sha", pr_number=pr_number)

    try:
        process = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--json",
            "mergeCommit",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_output = stderr.decode("utf-8", errors="replace")
            logger.error(
                "merge_sha_query_failed",
                pr_number=pr_number,
                error=error_output,
            )
            raise RuntimeError(f"Failed to get merge commit SHA: {error_output}")

        # Parse response
        try:
            pr_data = json.loads(stdout.decode("utf-8", errors="replace"))
            merge_commit = pr_data.get("mergeCommit")
            if not merge_commit or "oid" not in merge_commit:
                logger.error("pr_not_merged", pr_number=pr_number)
                raise RuntimeError(f"PR {pr_number} is not merged")

            merge_sha = merge_commit["oid"]
            logger.info("merge_sha_retrieved", pr_number=pr_number, sha=merge_sha)
            return merge_sha

        except (json.JSONDecodeError, KeyError) as e:
            logger.error("invalid_pr_json", error=str(e))
            raise RuntimeError(f"Failed to parse PR data: {e}") from e

    except FileNotFoundError as e:
        logger.error("gh_not_found", error=str(e))
        raise RuntimeError("gh command not found") from e


async def validate_base_branch(pr_number: int, expected_base: str) -> None:
    """Validate that PR's base branch matches expected target.

    Args:
        pr_number: PR number to check
        expected_base: Expected base branch name

    Raises:
        ValueError: If base branches don't match
        RuntimeError: If gh command fails
    """
    logger.info(
        "validating_base_branch",
        pr_number=pr_number,
        expected_base=expected_base,
    )

    try:
        process = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--json",
            "number,state,baseRefName,headRefName,url,mergedAt,isCrossRepository",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_output = stderr.decode("utf-8", errors="replace")
            logger.error(
                "base_branch_validation_failed",
                pr_number=pr_number,
                error=error_output,
            )
            raise RuntimeError(f"Failed to fetch PR details: {error_output}")

        pr_data = json.loads(stdout.decode("utf-8", errors="replace"))
        actual_base = pr_data.get("baseRefName")

        if actual_base != expected_base:
            logger.error(
                "base_branch_mismatch",
                pr_number=pr_number,
                expected=expected_base,
                actual=actual_base,
            )
            raise ValueError(f"Base branch mismatch: PR targets '{actual_base}' but expected '{expected_base}'")

        logger.info("base_branch_validated", pr_number=pr_number, base=actual_base)

    except (json.JSONDecodeError, KeyError) as e:
        logger.error("invalid_pr_json_during_validation", error=str(e))
        raise RuntimeError(f"Failed to parse PR data: {e}") from e
    except FileNotFoundError as e:
        logger.error("gh_not_found", error=str(e))
        raise RuntimeError("gh command not found") from e


def parse_ci_failures_from_checks(checks: list[dict[str, Any]]) -> list[Any]:
    """Parse CI failure details from gh pr checks output.

    Aggregates failures by job name, keeping only the latest attempt
    for each job (based on completedAt timestamp).

    Args:
        checks: List of check run dictionaries from gh pr checks --json

    Returns:
        List of CiFailureDetail for failed/cancelled/timed_out checks
    """
    from datetime import datetime

    from src.models.phase_automation import CiFailureDetail

    # Track latest failure per job name
    failures_by_job: dict[str, CiFailureDetail] = {}

    for check in checks:
        check_conclusion_raw = check.get("conclusion")
        if not check_conclusion_raw:
            continue

        check_conclusion = check_conclusion_raw.lower()

        # Only process failure states
        if check_conclusion not in ("failure", "cancelled", "timed_out"):
            continue

        check_name = check.get("name", "unknown")
        completed_at_str = check.get("completedAt")
        completed_at = None

        if completed_at_str:
            with contextlib.suppress(ValueError):
                completed_at = datetime.fromisoformat(completed_at_str.replace("Z", "+00:00"))

        failure = CiFailureDetail(
            job_name=check_name,
            attempt=1,  # GitHub doesn't expose attempt numbers in checks API
            status=check_conclusion,  # type: ignore
            summary=check_conclusion,
            log_url=check.get("detailsUrl"),
            completed_at=completed_at,
        )

        # Keep latest attempt per job (based on completedAt)
        existing = failures_by_job.get(check_name)
        if existing is None or (
            completed_at is not None and existing.completed_at is not None and completed_at > existing.completed_at
        ):
            failures_by_job[check_name] = failure

    return list(failures_by_job.values())


async def poll_ci_status(pr_number: int) -> tuple[str, list[Any]]:
    """Poll CI status for a single attempt.

    Args:
        pr_number: PR number to check

    Returns:
        Tuple of (status, failures) where:
        - status: "success", "failure", or "in_progress"
        - failures: List of CiFailureDetail for failed checks

    Raises:
        RuntimeError: If gh command fails
    """

    logger.debug("polling_ci_status", pr_number=pr_number)

    try:
        process = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "checks",
            str(pr_number),
            "--json",
            "name,status,conclusion,completedAt,detailsUrl",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_output = stderr.decode("utf-8", errors="replace")
            logger.error(
                "ci_status_poll_failed",
                pr_number=pr_number,
                error=error_output,
            )
            raise RuntimeError(f"Failed to poll CI status: {error_output}")

        checks = json.loads(stdout.decode("utf-8", errors="replace"))

        # No checks = success (allows PRs without CI)
        if not checks:
            logger.debug("no_ci_checks_found", pr_number=pr_number)
            return ("success", [])

        # Parse failures using helper function
        failures = parse_ci_failures_from_checks(checks)

        # Check if any checks are still in progress
        all_completed = True
        for check in checks:
            check_status = check.get("status", "").lower()
            if check_status in ("queued", "in_progress"):
                all_completed = False
                break

        # Determine terminal status
        if failures:
            return ("failure", failures)
        if all_completed:
            return ("success", [])
        return ("in_progress", [])

    except (json.JSONDecodeError, KeyError) as e:
        logger.error("invalid_ci_status_json", error=str(e))
        raise RuntimeError(f"Failed to parse CI status: {e}") from e
    except FileNotFoundError as e:
        logger.error("gh_not_found", error=str(e))
        raise RuntimeError("gh command not found") from e


async def poll_ci_with_timeout(
    pr_number: int,
    polling_config: Any,
) -> Any:
    """Poll CI with exponential backoff until terminal state or timeout.

    Args:
        pr_number: PR number to monitor
        polling_config: PollingConfiguration with intervals and timeout

    Returns:
        PullRequestAutomationResult with terminal status
    """
    import time

    from src.models.phase_automation import PullRequestAutomationResult

    start_time = time.time()
    timeout_seconds = polling_config.timeout_minutes * 60
    interval = polling_config.interval_seconds
    poll_count = 0

    logger.info(
        "ci_poll_started",
        pr_number=pr_number,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval,
    )

    while True:
        poll_count += 1
        elapsed = time.time() - start_time

        # Check timeout
        if elapsed >= timeout_seconds:
            duration = int(elapsed)
            logger.warning(
                "ci_poll_timeout",
                pr_number=pr_number,
                duration_seconds=duration,
                poll_count=poll_count,
            )
            return PullRequestAutomationResult(
                status="timeout",
                polling_duration_seconds=duration,
                pull_request_number=pr_number,
                retry_advice="CI checks did not complete within timeout",
            )

        # Poll CI status
        try:
            ci_status, failures = await poll_ci_status(pr_number)

            logger.debug(
                "ci_poll_update",
                pr_number=pr_number,
                poll_count=poll_count,
                ci_status=ci_status,
                elapsed_seconds=int(elapsed),
            )

            # Terminal states
            if ci_status == "success":
                duration = int(elapsed)
                logger.info(
                    "ci_poll_completed_success",
                    pr_number=pr_number,
                    duration_seconds=duration,
                    poll_count=poll_count,
                )
                # Return temporary result - merge will be done by caller
                # Status will be set to "merged" after successful merge
                return PullRequestAutomationResult(
                    status="merged",  # Indicates CI passed, ready for merge
                    polling_duration_seconds=duration,
                    pull_request_number=pr_number,
                    merge_commit_sha="placeholder",  # Will be replaced after actual merge
                )

            if ci_status == "failure":
                duration = int(elapsed)
                logger.warning(
                    "ci_poll_completed_failure",
                    pr_number=pr_number,
                    duration_seconds=duration,
                    poll_count=poll_count,
                    failure_count=len(failures),
                )
                return PullRequestAutomationResult(
                    status="ci_failed",
                    polling_duration_seconds=duration,
                    pull_request_number=pr_number,
                    ci_failures=failures,
                )

            # Still in progress - wait and retry
            await asyncio.sleep(interval)

        except Exception as e:
            logger.error(
                "ci_poll_exception",
                pr_number=pr_number,
                error=str(e),
                poll_count=poll_count,
            )
            # Re-raise to let activity handle retry logic
            raise


async def merge_pull_request(pr_number: int) -> str:
    """Merge a pull request and return merge commit SHA.

    Args:
        pr_number: PR number to merge

    Returns:
        Merge commit SHA

    Raises:
        RuntimeError: If merge fails
    """
    logger.info("merging_pull_request", pr_number=pr_number)

    try:
        process = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "merge",
            str(pr_number),
            "--merge",
            "--auto",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_output = stderr.decode("utf-8", errors="replace")
            logger.error(
                "merge_failed",
                pr_number=pr_number,
                error=error_output,
            )
            raise RuntimeError(f"Failed to merge pull request: {error_output}")

        # Parse merge response
        try:
            merge_data = json.loads(stdout.decode("utf-8", errors="replace"))
            merge_sha = merge_data["sha"]

            logger.info(
                "pull_request_merged",
                pr_number=pr_number,
                merge_sha=merge_sha,
            )
            return merge_sha

        except (json.JSONDecodeError, KeyError) as e:
            logger.error("invalid_merge_json", error=str(e))
            raise RuntimeError(f"Failed to parse merge response: {e}") from e

    except FileNotFoundError as e:
        logger.error("gh_not_found", error=str(e))
        raise RuntimeError("gh command not found") from e
