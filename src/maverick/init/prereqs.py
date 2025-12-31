"""Prerequisite check functions for maverick init.

This module provides async functions to validate all prerequisites
required for maverick init: git installation, repository detection,
GitHub CLI installation and authentication, and Anthropic API access.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.constants import CLAUDE_HAIKU_LATEST
from maverick.exceptions.init import AnthropicAPIError
from maverick.init.models import InitPreflightResult, PreflightStatus, PrerequisiteCheck
from maverick.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "check_git_installed",
    "check_in_git_repo",
    "check_gh_installed",
    "check_gh_authenticated",
    "check_anthropic_key_set",
    "check_anthropic_api_accessible",
    "verify_prerequisites",
    "redact_api_key",
]

# =============================================================================
# Module Logger
# =============================================================================

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

#: Pattern to extract version from git --version output
GIT_VERSION_PATTERN = re.compile(r"git version (\d+\.\d+(?:\.\d+)?)")

#: Pattern to extract version from gh --version output
GH_VERSION_PATTERN = re.compile(r"gh version (\d+\.\d+(?:\.\d+)?)")

#: Pattern to extract username from gh auth status output
GH_USERNAME_PATTERN = re.compile(r"Logged in to [^\s]+ as ([^\s]+)")

#: Default model for API validation (haiku is cheapest/fastest)
DEFAULT_API_CHECK_MODEL = CLAUDE_HAIKU_LATEST

#: Grace period for subprocess termination before SIGKILL
TERMINATION_GRACE_PERIOD: float = 2.0


# =============================================================================
# Helper Functions
# =============================================================================


def redact_api_key(key: str) -> str:
    """Redact API key showing only prefix and last 4 chars.

    Args:
        key: The API key to redact.

    Returns:
        Redacted key in format "prefix...last4".

    Example:
        >>> redact_api_key("sk-ant-abc123xyz789")
        'sk-ant-...9789'
        >>> redact_api_key("short")
        '...ort'
    """
    if not key:
        return ""

    # Find the prefix (e.g., "sk-ant-")
    prefix_match = re.match(r"^(sk-ant-)", key)
    prefix = prefix_match.group(1) if prefix_match else ""

    # Get last 4 characters
    suffix_len = min(4, len(key))
    suffix = key[-suffix_len:] if suffix_len > 0 else ""

    return f"{prefix}...{suffix}"


async def _run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: float = 5.0,
) -> tuple[int, str, str]:
    """Run a command asynchronously with timeout handling.

    Args:
        command: Command and arguments to execute.
        cwd: Working directory for command execution.
        timeout: Timeout in seconds.

    Returns:
        Tuple of (returncode, stdout, stderr).
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            returncode = process.returncode or 0
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            return returncode, stdout, stderr

        except TimeoutError:
            # Graceful termination: SIGTERM first
            process.terminate()
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=TERMINATION_GRACE_PERIOD,
                )
            except TimeoutError:
                # Force kill if still running
                process.kill()
                await process.wait()
            return -1, "", "Command timed out"

    except FileNotFoundError:
        return 127, "", f"Command not found: {command[0]}"
    except PermissionError:
        return 126, "", f"Permission denied: {command[0]}"


# =============================================================================
# Prerequisite Check Functions
# =============================================================================


async def check_git_installed(timeout: float = 5.0) -> PrerequisiteCheck:
    """Check if git is installed and accessible.

    Runs `git --version` and extracts the version number.

    Args:
        timeout: Timeout in seconds for the git command.

    Returns:
        PrerequisiteCheck with PASS status and version info,
        or FAIL status with remediation instructions.
    """
    start = time.monotonic()

    returncode, stdout, stderr = await _run_command(
        ["git", "--version"],
        timeout=timeout,
    )

    duration_ms = int((time.monotonic() - start) * 1000)

    if returncode == 127:
        # git not found
        return PrerequisiteCheck(
            name="git_installed",
            display_name="Git",
            status=PreflightStatus.FAIL,
            message="git is not installed",
            remediation="Install git: https://git-scm.com/downloads",
            duration_ms=duration_ms,
        )

    if returncode != 0:
        return PrerequisiteCheck(
            name="git_installed",
            display_name="Git",
            status=PreflightStatus.FAIL,
            message=f"git command failed: {stderr.strip() or 'unknown error'}",
            remediation="Ensure git is properly installed and in PATH",
            duration_ms=duration_ms,
        )

    # Extract version
    version_match = GIT_VERSION_PATTERN.search(stdout)
    version = version_match.group(1) if version_match else "unknown"

    return PrerequisiteCheck(
        name="git_installed",
        display_name="Git",
        status=PreflightStatus.PASS,
        message=f"git version {version}",
        duration_ms=duration_ms,
    )


async def check_in_git_repo(
    cwd: Path | None = None,
    timeout: float = 5.0,
) -> PrerequisiteCheck:
    """Check if current directory is inside a git repository.

    Runs `git rev-parse --git-dir` to verify git repository presence.

    Args:
        cwd: Working directory to check. Defaults to current directory.
        timeout: Timeout in seconds for the git command.

    Returns:
        PrerequisiteCheck with PASS status if in a git repo,
        or FAIL status with remediation instructions.
    """
    start = time.monotonic()

    returncode, stdout, stderr = await _run_command(
        ["git", "rev-parse", "--git-dir"],
        cwd=cwd,
        timeout=timeout,
    )

    duration_ms = int((time.monotonic() - start) * 1000)

    if returncode == 127:
        # git not found - this should have been caught by check_git_installed
        return PrerequisiteCheck(
            name="in_git_repo",
            display_name="Git Repository",
            status=PreflightStatus.FAIL,
            message="git is not installed",
            remediation="Install git first",
            duration_ms=duration_ms,
        )

    if returncode != 0:
        # Not a git repository
        return PrerequisiteCheck(
            name="in_git_repo",
            display_name="Git Repository",
            status=PreflightStatus.FAIL,
            message="Not in a git repository",
            remediation="Run 'git init' to initialize a repository",
            duration_ms=duration_ms,
        )

    git_dir = stdout.strip()
    return PrerequisiteCheck(
        name="in_git_repo",
        display_name="Git Repository",
        status=PreflightStatus.PASS,
        message=f"Git directory: {git_dir}",
        duration_ms=duration_ms,
    )


async def check_gh_installed(timeout: float = 5.0) -> PrerequisiteCheck:
    """Check if GitHub CLI is installed.

    Runs `gh --version` and extracts the version number.

    Args:
        timeout: Timeout in seconds for the gh command.

    Returns:
        PrerequisiteCheck with PASS status and version info,
        or FAIL status with remediation instructions.
    """
    start = time.monotonic()

    returncode, stdout, stderr = await _run_command(
        ["gh", "--version"],
        timeout=timeout,
    )

    duration_ms = int((time.monotonic() - start) * 1000)

    if returncode == 127:
        # gh not found
        return PrerequisiteCheck(
            name="gh_installed",
            display_name="GitHub CLI",
            status=PreflightStatus.FAIL,
            message="GitHub CLI (gh) is not installed",
            remediation="Install gh: https://cli.github.com",
            duration_ms=duration_ms,
        )

    if returncode != 0:
        return PrerequisiteCheck(
            name="gh_installed",
            display_name="GitHub CLI",
            status=PreflightStatus.FAIL,
            message=f"gh command failed: {stderr.strip() or 'unknown error'}",
            remediation="Ensure gh is properly installed and in PATH",
            duration_ms=duration_ms,
        )

    # Extract version
    version_match = GH_VERSION_PATTERN.search(stdout)
    version = version_match.group(1) if version_match else "unknown"

    return PrerequisiteCheck(
        name="gh_installed",
        display_name="GitHub CLI",
        status=PreflightStatus.PASS,
        message=f"gh version {version}",
        duration_ms=duration_ms,
    )


async def check_gh_authenticated(timeout: float = 10.0) -> PrerequisiteCheck:
    """Check if GitHub CLI is authenticated.

    Runs `gh auth status` to verify authentication and extract username.

    Args:
        timeout: Timeout in seconds for the gh command.

    Returns:
        PrerequisiteCheck with PASS status and username,
        or FAIL status with remediation instructions.
    """
    start = time.monotonic()

    returncode, stdout, stderr = await _run_command(
        ["gh", "auth", "status"],
        timeout=timeout,
    )

    duration_ms = int((time.monotonic() - start) * 1000)

    if returncode == 127:
        # gh not found - should have been caught by check_gh_installed
        return PrerequisiteCheck(
            name="gh_authenticated",
            display_name="GitHub Auth",
            status=PreflightStatus.FAIL,
            message="GitHub CLI (gh) is not installed",
            remediation="Install gh first",
            duration_ms=duration_ms,
        )

    # gh auth status outputs to stderr on failure, stdout on success
    # But in some versions, it may use stderr for both
    combined_output = f"{stdout}\n{stderr}"

    if returncode != 0:
        return PrerequisiteCheck(
            name="gh_authenticated",
            display_name="GitHub Auth",
            status=PreflightStatus.FAIL,
            message="Not authenticated with GitHub",
            remediation="Run 'gh auth login' to authenticate",
            duration_ms=duration_ms,
        )

    # Extract username from output
    username_match = GH_USERNAME_PATTERN.search(combined_output)
    username = username_match.group(1) if username_match else "authenticated"

    return PrerequisiteCheck(
        name="gh_authenticated",
        display_name="GitHub Auth",
        status=PreflightStatus.PASS,
        message=f"Authenticated as {username}",
        duration_ms=duration_ms,
    )


def check_anthropic_key_set() -> PrerequisiteCheck:
    """Check if Anthropic API credentials are set.

    Checks for either ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN
    environment variable. Either credential type is acceptable.

    This is a synchronous check that only validates the presence
    of credentials, not their validity.

    Returns:
        PrerequisiteCheck with PASS status and redacted key,
        or FAIL status with remediation instructions.
    """
    start = time.monotonic()

    # Check for either credential type
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")

    duration_ms = int((time.monotonic() - start) * 1000)

    if not api_key and not oauth_token:
        return PrerequisiteCheck(
            name="anthropic_key_set",
            display_name="Anthropic API Key",
            status=PreflightStatus.FAIL,
            message=(
                "Neither ANTHROPIC_API_KEY nor CLAUDE_CODE_OAUTH_TOKEN "
                "environment variable is set"
            ),
            remediation=(
                "Set ANTHROPIC_API_KEY: export ANTHROPIC_API_KEY=<your-key> "
                "or use Claude Code OAuth authentication"
            ),
            duration_ms=duration_ms,
        )

    # Prefer API key for display, fall back to OAuth token
    if api_key:
        redacted = redact_api_key(api_key)
        credential_type = "API key"
    else:
        redacted = redact_api_key(oauth_token)
        credential_type = "OAuth token"

    return PrerequisiteCheck(
        name="anthropic_key_set",
        display_name="Anthropic API Key",
        status=PreflightStatus.PASS,
        message=f"{credential_type} configured ({redacted})",
        duration_ms=duration_ms,
    )


async def check_anthropic_api_accessible(
    model: str = DEFAULT_API_CHECK_MODEL,
    timeout: float = 10.0,
) -> PrerequisiteCheck:
    """Validate Anthropic API access with a minimal request.

    Sends a minimal "Hi" request to the Claude API to verify
    that the API key is valid and the model is accessible.

    Args:
        model: Claude model to validate access for.
        timeout: Request timeout in seconds.

    Returns:
        PrerequisiteCheck with PASS status if API is accessible,
        or FAIL status with specific error discrimination:
        - 401: Invalid API key
        - 403: Model not accessible (plan limits)
        - 429: Rate limit exceeded
        - Timeout: Network connectivity issues

    Raises:
        AnthropicAPIError: For unexpected API failures.
    """
    start = time.monotonic()

    try:
        # Import claude_agent_sdk here to avoid import errors if not installed
        from claude_agent_sdk import ClaudeAgentOptions, query

        options = ClaudeAgentOptions(
            system_prompt="Respond with exactly 'OK'.",
            model=model,
            max_turns=1,
            allowed_tools=[],
        )

        # Use asyncio.wait_for for timeout
        async def make_request() -> None:
            async for _ in query(prompt="Hi", options=options):
                pass

        await asyncio.wait_for(make_request(), timeout=timeout)

        duration_ms = int((time.monotonic() - start) * 1000)

        return PrerequisiteCheck(
            name="anthropic_api_accessible",
            display_name="Anthropic API",
            status=PreflightStatus.PASS,
            message=f"API accessible (model: {model})",
            duration_ms=duration_ms,
        )

    except TimeoutError:
        duration_ms = int((time.monotonic() - start) * 1000)
        return PrerequisiteCheck(
            name="anthropic_api_accessible",
            display_name="Anthropic API",
            status=PreflightStatus.FAIL,
            message="API request timed out",
            remediation="Check network connectivity and try again",
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        error_type = type(e).__name__
        error_message = str(e)

        # Discriminate error types based on exception class name and message
        # since we don't want to import anthropic package directly
        if "AuthenticationError" in error_type or "401" in error_message:
            return PrerequisiteCheck(
                name="anthropic_api_accessible",
                display_name="Anthropic API",
                status=PreflightStatus.FAIL,
                message="Invalid API key",
                remediation="Verify ANTHROPIC_API_KEY is correct",
                duration_ms=duration_ms,
            )

        if "PermissionDeniedError" in error_type or "403" in error_message:
            return PrerequisiteCheck(
                name="anthropic_api_accessible",
                display_name="Anthropic API",
                status=PreflightStatus.FAIL,
                message=f"Model not accessible: {model}",
                remediation="Check your Anthropic plan limits or use a different model",
                duration_ms=duration_ms,
            )

        if "RateLimitError" in error_type or "429" in error_message:
            return PrerequisiteCheck(
                name="anthropic_api_accessible",
                display_name="Anthropic API",
                status=PreflightStatus.FAIL,
                message="Rate limit exceeded",
                remediation="Wait a moment and try again",
                duration_ms=duration_ms,
            )

        # Log unexpected errors for debugging
        logger.error(
            "anthropic_api_check_failed",
            error_type=error_type,
            error_message=error_message,
        )

        # Raise AnthropicAPIError for unexpected failures
        raise AnthropicAPIError(
            f"Anthropic API error: {error_message}",
            status_code=None,
        ) from e


async def verify_prerequisites(
    *,
    skip_api_check: bool = False,
    timeout_per_check: float = 10.0,
    cwd: Path | None = None,
) -> InitPreflightResult:
    """Verify all prerequisites for maverick init.

    Orchestrates all prerequisite checks in sequence, with early
    termination on critical failures (git not installed, not in repo).

    Args:
        skip_api_check: Skip Anthropic API validation (for --no-detect).
        timeout_per_check: Timeout in seconds for each check.
        cwd: Working directory for git repository check.

    Returns:
        InitPreflightResult with all check results and summary.
    """
    start = time.monotonic()
    checks: list[PrerequisiteCheck] = []
    failed_checks: list[str] = []
    warnings: list[str] = []

    # 1. Check git installed (critical)
    git_check = await check_git_installed(timeout=timeout_per_check)
    checks.append(git_check)
    if git_check.status == PreflightStatus.FAIL:
        failed_checks.append(git_check.name)
        # Early termination - git is required for everything
        total_duration_ms = int((time.monotonic() - start) * 1000)
        return InitPreflightResult(
            success=False,
            checks=tuple(checks),
            total_duration_ms=total_duration_ms,
            failed_checks=tuple(failed_checks),
            warnings=tuple(warnings),
        )

    # 2. Check in git repository (critical)
    repo_check = await check_in_git_repo(cwd=cwd, timeout=timeout_per_check)
    checks.append(repo_check)
    if repo_check.status == PreflightStatus.FAIL:
        failed_checks.append(repo_check.name)
        # Early termination - must be in a git repository
        total_duration_ms = int((time.monotonic() - start) * 1000)
        return InitPreflightResult(
            success=False,
            checks=tuple(checks),
            total_duration_ms=total_duration_ms,
            failed_checks=tuple(failed_checks),
            warnings=tuple(warnings),
        )

    # 3. Check gh installed
    gh_installed_check = await check_gh_installed(timeout=timeout_per_check)
    checks.append(gh_installed_check)
    if gh_installed_check.status == PreflightStatus.FAIL:
        failed_checks.append(gh_installed_check.name)

    # 4. Check gh authenticated (only if gh is installed)
    if gh_installed_check.status == PreflightStatus.PASS:
        gh_auth_check = await check_gh_authenticated(timeout=timeout_per_check)
        checks.append(gh_auth_check)
        if gh_auth_check.status == PreflightStatus.FAIL:
            failed_checks.append(gh_auth_check.name)
    else:
        # Add skipped check for authentication
        checks.append(
            PrerequisiteCheck(
                name="gh_authenticated",
                display_name="GitHub Auth",
                status=PreflightStatus.SKIP,
                message="Skipped (gh not installed)",
                duration_ms=0,
            )
        )

    # 5. Check Anthropic API key set
    api_key_check = check_anthropic_key_set()
    checks.append(api_key_check)
    if api_key_check.status == PreflightStatus.FAIL:
        failed_checks.append(api_key_check.name)

    # 6. Check Anthropic API accessible (only if key is set and not skipped)
    if skip_api_check:
        checks.append(
            PrerequisiteCheck(
                name="anthropic_api_accessible",
                display_name="Anthropic API",
                status=PreflightStatus.SKIP,
                message="Skipped (--no-detect)",
                duration_ms=0,
            )
        )
    elif api_key_check.status == PreflightStatus.PASS:
        try:
            api_check = await check_anthropic_api_accessible(
                timeout=timeout_per_check,
            )
            checks.append(api_check)
            if api_check.status == PreflightStatus.FAIL:
                failed_checks.append(api_check.name)
        except AnthropicAPIError as e:
            # Convert exception to failed check
            checks.append(
                PrerequisiteCheck(
                    name="anthropic_api_accessible",
                    display_name="Anthropic API",
                    status=PreflightStatus.FAIL,
                    message=str(e),
                    remediation="Check https://status.anthropic.com for API status",
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            )
            failed_checks.append("anthropic_api_accessible")
    else:
        # Skip API check if key is not set
        checks.append(
            PrerequisiteCheck(
                name="anthropic_api_accessible",
                display_name="Anthropic API",
                status=PreflightStatus.SKIP,
                message="Skipped (API key not set)",
                duration_ms=0,
            )
        )

    total_duration_ms = int((time.monotonic() - start) * 1000)

    # Determine success: no failed checks
    success = len(failed_checks) == 0

    return InitPreflightResult(
        success=success,
        checks=tuple(checks),
        total_duration_ms=total_duration_ms,
        failed_checks=tuple(failed_checks),
        warnings=tuple(warnings),
    )
