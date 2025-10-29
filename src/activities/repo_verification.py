"""GitHub repository verification activity using gh CLI."""

import asyncio
import time
from dataclasses import asdict

from temporalio import activity

from src.models.parameters import Parameters
from src.models.verification_result import VerificationResult
from src.utils.logging import get_structured_logger
from src.utils.param_accessor import ParameterAccessError, get_required_param
from src.utils.url_normalization import URLNormalizationError, normalize_github_url, validate_github_host


# Structured logger for this activity
logger = get_structured_logger("activity.repo_verification")

# Configuration
GH_TIMEOUT_SECONDS = 2.0  # Per-attempt timeout for gh commands
RETRY_BACKOFF_MS = 400    # Backoff between retry attempts


@activity.defn(name="verify_repository")
async def verify_repository(params: Parameters) -> VerificationResult:
    """Verify GitHub repository exists and is accessible.

    Uses gh CLI to check authentication status and repository visibility.
    Follows gh CLI behavior: requires gh to be installed and authenticated.

    Args:
        params: Workflow parameters containing github_repo_url

    Returns:
        VerificationResult with pass/fail status and details
    """
    start_time = time.time()
    attempts = 0

    # Step 0: Extract github_repo_url using typed parameter accessor
    try:
        github_repo_url = get_required_param(
            asdict(params),
            "github_repo_url",
            str,
            "GitHub repository URL (HTTPS or SSH format)"
        )
    except ParameterAccessError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "parameter_access_failed",
            error=str(e),
            duration_ms=duration_ms
        )
        return VerificationResult(
            tool="gh",
            status="fail",
            message=f"Parameter error: {e}",
            host="",
            repo_slug="",
            error_code="validation_error",
            attempts=1,
            duration_ms=duration_ms
        )

    logger.info(
        "verification_started",
        repo_url=github_repo_url
    )

    # Step 1: Normalize and validate URL
    try:
        normalized = normalize_github_url(github_repo_url)
        validate_github_host(normalized.host)

        logger.info(
            "url_normalized",
            host=normalized.host,
            repo_slug=normalized.repo_slug
        )
    except URLNormalizationError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "validation_failed",
            error=str(e),
            duration_ms=duration_ms
        )
        return VerificationResult(
            tool="gh",
            status="fail",
            message=f"Invalid GitHub URL: {e}",
            host="",
            repo_slug="",
            error_code="validation_error",
            attempts=1,
            duration_ms=duration_ms
        )

    # Step 2: Check gh authentication
    auth_result = await _check_gh_auth(normalized.host)
    if not auth_result["authenticated"]:
        duration_ms = int((time.time() - start_time) * 1000)

        # Map auth check result to appropriate error_code
        if auth_result["code"] == "unauthenticated":
            error_code = "auth_error"
        elif auth_result["code"] in ["timeout", "error"]:
            error_code = "transient_error"
        else:
            # Fallback for unexpected codes
            error_code = "transient_error"

        logger.error(
            "auth_check_failed",
            host=normalized.host,
            reason=auth_result["message"],
            auth_code=auth_result["code"],
            error_code=error_code,
            duration_ms=duration_ms
        )
        return VerificationResult(
            tool="gh",
            status="fail",
            message=auth_result["message"],
            host=normalized.host,
            repo_slug=normalized.repo_slug,
            error_code=error_code,
            attempts=1,
            duration_ms=duration_ms
        )

    logger.info(
        "auth_check_passed",
        host=normalized.host
    )

    # Step 3: Verify repository with retry logic
    max_attempts = 2
    last_error = None

    for attempt in range(1, max_attempts + 1):
        attempts = attempt

        logger.info(
            "repo_verification_attempt",
            attempt=attempt,
            repo_slug=normalized.repo_slug,
            host=normalized.host
        )

        try:
            result = await _verify_repo_with_gh(normalized.host, normalized.repo_slug)

            if result["success"]:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    "verification_passed",
                    repo_slug=normalized.repo_slug,
                    host=normalized.host,
                    attempts=attempts,
                    duration_ms=duration_ms
                )
                return VerificationResult(
                    tool="gh",
                    status="pass",
                    message=f"Repository {normalized.repo_slug} verified successfully",
                    host=normalized.host,
                    repo_slug=normalized.repo_slug,
                    error_code="none",
                    attempts=attempts,
                    duration_ms=duration_ms
                )

            # Non-transient failure - don't retry
            if result["error_code"] in ["not_found", "access_denied"]:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "verification_failed_permanent",
                    repo_slug=normalized.repo_slug,
                    error_code=result["error_code"],
                    attempts=attempts,
                    duration_ms=duration_ms
                )
                return VerificationResult(
                    tool="gh",
                    status="fail",
                    message=result["message"],
                    host=normalized.host,
                    repo_slug=normalized.repo_slug,
                    error_code=result["error_code"],
                    attempts=attempts,
                    duration_ms=duration_ms
                )

            # Transient error - may retry
            last_error = result

            if attempt < max_attempts:
                logger.info(
                    "retrying_after_transient_error",
                    error_code=result["error_code"],
                    backoff_ms=RETRY_BACKOFF_MS,
                    next_attempt=attempt + 1
                )
                await asyncio.sleep(RETRY_BACKOFF_MS / 1000.0)

        except Exception as e:
            logger.error(
                "verification_exception",
                attempt=attempt,
                error=str(e)
            )
            last_error = {
                "success": False,
                "error_code": "transient_error",
                "message": f"Unexpected error: {e}"
            }

            if attempt < max_attempts:
                await asyncio.sleep(RETRY_BACKOFF_MS / 1000.0)

    # All attempts exhausted
    duration_ms = int((time.time() - start_time) * 1000)
    logger.error(
        "verification_failed_after_retries",
        repo_slug=normalized.repo_slug,
        attempts=attempts,
        duration_ms=duration_ms
    )

    return VerificationResult(
        tool="gh",
        status="fail",
        message=last_error["message"] if last_error else "Verification failed",
        host=normalized.host,
        repo_slug=normalized.repo_slug,
        error_code=last_error["error_code"] if last_error else "transient_error",
        attempts=attempts,
        duration_ms=duration_ms
    )


async def _check_gh_auth(host: str) -> dict:
    """Check if gh CLI is authenticated for the given host.

    Args:
        host: GitHub host to check (e.g., github.com)

    Returns:
        Dict with 'authenticated' (bool), 'code' (str), and 'message' (str)
        code can be: 'authenticated', 'unauthenticated', 'timeout', 'error'
    """
    try:
        # Check if gh is installed
        gh_check = await asyncio.create_subprocess_exec(
            "which", "gh",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await asyncio.wait_for(gh_check.communicate(), timeout=1.0)

        if gh_check.returncode != 0:
            return {
                "authenticated": False,
                "code": "unauthenticated",
                "message": "gh CLI not found. Please install gh and run 'gh auth login'"
            }

        # Check auth status for host
        cmd = ["gh", "auth", "status", "-h", host]

        auth_check = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(
            auth_check.communicate(),
            timeout=GH_TIMEOUT_SECONDS
        )

        # gh auth status returns 0 when authenticated
        if auth_check.returncode == 0:
            return {
                "authenticated": True,
                "code": "authenticated",
                "message": f"Authenticated to {host}"
            }
        else:
            return {
                "authenticated": False,
                "code": "unauthenticated",
                "message": f"Not authenticated to {host}. Please run 'gh auth login -h {host}'"
            }

    except TimeoutError:
        return {
            "authenticated": False,
            "code": "timeout",
            "message": f"Timeout checking authentication status for {host}"
        }
    except Exception as e:
        return {
            "authenticated": False,
            "code": "error",
            "message": f"Error checking gh authentication: {e}"
        }


async def _verify_repo_with_gh(host: str, repo_slug: str) -> dict:
    """Verify repository exists using gh repo view.

    Args:
        host: GitHub host
        repo_slug: Repository in owner/repo format

    Returns:
        Dict with 'success' (bool), 'error_code', and 'message'
    """
    try:
        # Use HOST/OWNER/REPO format for all hosts
        # For github.com, the host prefix is optional but we include it for consistency
        repo_with_host = f"{host}/{repo_slug}"
        cmd = ["gh", "repo", "view", repo_with_host]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=GH_TIMEOUT_SECONDS
        )

        if process.returncode == 0:
            return {
                "success": True,
                "error_code": "none",
                "message": f"Repository {repo_slug} exists"
            }

        # Parse stderr for specific errors
        error_output = stderr.decode('utf-8', errors='replace').lower()

        if "not found" in error_output or "could not resolve" in error_output:
            return {
                "success": False,
                "error_code": "not_found",
                "message": f"Repository {repo_slug} not found on {host}"
            }

        if "forbidden" in error_output or "access denied" in error_output:
            return {
                "success": False,
                "error_code": "access_denied",
                "message": f"Access denied to repository {repo_slug} on {host}"
            }

        # Assume transient error for other failures
        # Log raw stderr for debugging, but use user-friendly message
        stderr_text = stderr.decode('utf-8', errors='replace')
        logger.debug(
            "gh_repo_view_failed",
            repo_slug=repo_slug,
            host=host,
            stderr=stderr_text
        )
        return {
            "success": False,
            "error_code": "transient_error",
            "message": f"GitHub CLI returned an error while viewing repository {repo_slug}. Please retry later or check rate limits."
        }

    except TimeoutError:
        return {
            "success": False,
            "error_code": "transient_error",
            "message": f"Timeout verifying repository {repo_slug}"
        }
    except Exception as e:
        return {
            "success": False,
            "error_code": "transient_error",
            "message": f"Error verifying repository: {e}"
        }
