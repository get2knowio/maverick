"""GitHub CLI runner for interacting with GitHub via gh CLI."""

from __future__ import annotations

import shutil
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, TypeAdapter
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

if TYPE_CHECKING:
    from maverick.runners.preflight import ValidationResult

from maverick.exceptions import GitHubAuthError, GitHubCLINotFoundError
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner
from maverick.runners.models import CheckStatus, GitHubIssue, PullRequest

__all__ = ["GitHubCLIRunner", "RetryableGitHubError"]

logger = get_logger(__name__)


class RetryableGitHubError(Exception):
    """Exception raised when a GitHub CLI command fails with a retryable error.

    This exception is used internally by GitHubCLIRunner to signal that a
    gh command execution failed but should be retried (e.g., network errors,
    rate limits).
    """

    def __init__(
        self, exit_code: int, stderr: str, message: str = "GitHub CLI command failed"
    ) -> None:
        """Initialize the RetryableGitHubError.

        Args:
            exit_code: The exit code from the gh CLI command.
            stderr: The stderr output from the failed command.
            message: Human-readable error message.
        """
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


# =============================================================================
# GitHub CLI Exit Codes
# =============================================================================
# Based on gh CLI documentation: https://cli.github.com/manual/gh_help_exit-codes
# Standard exit codes:
#   0: Success
#   1: General error (network, API, command-specific errors)
#   2: Command canceled (e.g., user canceled interactive prompt)
#   4: Authentication required (not logged in or token expired)
# Command-specific exit codes:
#   8: Checks pending (gh pr checks)
# =============================================================================

GH_EXIT_CODES = {
    0: "success",
    1: "general_error",
    2: "canceled",
    4: "auth_required",
    8: "checks_pending",
}


# =============================================================================
# Response Models (Internal - for parsing GitHub CLI JSON output)
# =============================================================================


class GitHubLabelResponse(BaseModel):
    """GitHub API label response."""

    name: str


class GitHubUserResponse(BaseModel):
    """GitHub API user response."""

    login: str


class GitHubIssueResponse(BaseModel):
    """GitHub API issue response.

    Parses JSON output from 'gh issue view/list --json ...' commands.
    """

    number: int
    title: str
    body: str
    state: str
    url: str
    labels: list[GitHubLabelResponse] = Field(default_factory=list)
    assignees: list[GitHubUserResponse] = Field(default_factory=list)


class GitHubPRResponse(BaseModel):
    """GitHub API pull request response.

    Parses JSON output from 'gh pr view --json ...' commands.
    """

    number: int
    title: str
    body: str
    state: str
    url: str
    head_ref_name: str = Field(alias="headRefName")
    base_ref_name: str = Field(alias="baseRefName")
    is_draft: bool = Field(alias="isDraft")
    mergeable: bool | None = None


class GitHubCheckResponse(BaseModel):
    """GitHub API check response.

    Parses JSON output from 'gh pr checks --json ...' commands.
    """

    name: str
    state: str
    conclusion: str | None = None
    details_url: str | None = Field(default=None, alias="detailsUrl")


class GitHubCLIRunner:
    """Execute GitHub operations via the gh CLI."""

    def __init__(self) -> None:
        """Initialize the GitHubCLIRunner.

        Raises:
            GitHubCLINotFoundError: If gh CLI is not installed.
            GitHubAuthError: If gh CLI is not authenticated (checked on first use).
        """
        self._command_runner = CommandRunner()
        self._check_gh_available()
        self._auth_checked = False

    def _check_gh_available(self) -> None:
        """Check if gh CLI is installed."""
        if shutil.which("gh") is None:
            raise GitHubCLINotFoundError()

    async def _check_gh_auth(self) -> None:
        """Check if gh CLI is authenticated."""
        result = await self._command_runner.run(["gh", "auth", "status"])
        if not result.success:
            raise GitHubAuthError()

    def _classify_error(self, exit_code: int, stderr: str) -> tuple[str, str, bool]:
        """Classify gh CLI error using exit codes and stderr content.

        Uses exit codes as the primary classification method, falling back to
        stderr string matching only when the exit code is ambiguous (exit code 1).

        Args:
            exit_code: The gh CLI process exit code.
            stderr: The stderr output from the gh CLI command.

        Returns:
            A tuple of (error_type, error_message, is_retryable):
                - error_type: One of "auth", "not_found", "network", "rate_limit",
                              "validation", "canceled", or "unknown"
                - error_message: Human-readable error description
                - is_retryable: True if the error might succeed on retry

        Examples:
            >>> _classify_error(4, "Not authenticated")
            ('auth', 'Authentication required', False)

            >>> _classify_error(1, "Could not resolve host: github.com")
            ('network', 'Network error', True)

            >>> _classify_error(2, "Operation canceled")
            ('canceled', 'Command canceled', False)
        """
        # Primary classification: use exit code
        error_type = GH_EXIT_CODES.get(exit_code, "general_error")

        # Handle specific exit codes
        if error_type == "auth_required":
            return ("auth", "Authentication required", False)

        if error_type == "canceled":
            return ("canceled", "Command canceled by user", False)

        if error_type == "checks_pending":
            return ("pending", "Checks are still pending", True)

        # Exit code 1 is ambiguous - use stderr pattern matching as fallback
        if error_type == "general_error":
            stderr_lower = stderr.lower()

            # Authentication errors (should be exit code 4, but check anyway)
            if any(
                phrase in stderr_lower
                for phrase in [
                    "not authenticated",
                    "authentication required",
                    "token",
                    "unauthorized",
                ]
            ):
                return ("auth", "Authentication required", False)

            # Network errors (transient)
            if any(
                phrase in stderr_lower
                for phrase in [
                    "could not resolve",
                    "connection",
                    "network",
                    "timeout",
                    "timed out",
                    "dial tcp",
                ]
            ):
                return ("network", "Network error", True)

            # Rate limiting (transient)
            if any(
                phrase in stderr_lower
                for phrase in ["rate limit", "api rate limit", "too many requests"]
            ):
                return ("rate_limit", "API rate limit exceeded", True)

            # Resource not found (non-retryable)
            if any(
                phrase in stderr_lower
                for phrase in [
                    "not found",
                    "could not find",
                    "does not exist",
                    "no such",
                ]
            ):
                return ("not_found", "Resource not found", False)

            # Validation errors (non-retryable)
            if any(
                phrase in stderr_lower
                for phrase in [
                    "invalid",
                    "validation failed",
                    "required field",
                    "must be",
                ]
            ):
                return ("validation", "Validation error", False)

        # Unknown error type
        return ("unknown", f"Unknown error (exit code {exit_code})", False)

    async def _ensure_authenticated(self) -> None:
        """Check authentication status on first use (fail-fast).

        Raises:
            GitHubAuthError: If gh CLI is not authenticated.
        """
        if not self._auth_checked:
            await self._check_gh_auth()
            self._auth_checked = True

    async def _run_gh_command(self, *args: str) -> str:
        """Run gh command and return raw JSON output.

        Uses Tenacity for retry logic with exponential backoff for transient errors
        (network issues, rate limits). Non-retryable errors (auth, not found) fail
        immediately.

        Returns:
            Raw JSON string from gh CLI stdout.

        Raises:
            RuntimeError: If gh command fails after all retries.
            GitHubAuthError: If authentication is required (exit code 4).
        """
        max_retries = 3
        last_error: str | None = None
        last_exit_code: int | None = None

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(multiplier=1, min=1, max=8),
                retry=retry_if_exception_type(RetryableGitHubError),
            ):
                with attempt:
                    result = await self._command_runner.run(["gh", *args])
                    if result.success:
                        return result.stdout.strip() if result.stdout.strip() else "{}"

                    # Classify the error using exit code (primary) and stderr (fallback)
                    error_type, error_message, is_retryable = self._classify_error(
                        result.returncode, result.stderr
                    )

                    last_error = result.stderr
                    last_exit_code = result.returncode

                    # Log error with classification
                    attempt_num = attempt.retry_state.attempt_number
                    logger.warning(
                        f"gh command failed (attempt {attempt_num}/{max_retries}): "
                        f"[{error_type}] {error_message} - {result.stderr}"
                    )

                    # Raise immediately for non-retryable errors
                    if error_type == "auth":
                        raise GitHubAuthError()
                    if not is_retryable:
                        raise RuntimeError(
                            f"gh command failed ({error_type}): {result.stderr}"
                        )

                    # Raise retryable error to trigger retry
                    raise RetryableGitHubError(
                        exit_code=result.returncode,
                        stderr=result.stderr,
                        message=f"[{error_type}] {error_message}",
                    )

        except RetryError as err:
            # All retries exhausted
            raise RuntimeError(
                f"gh command failed after {max_retries} attempts "
                f"(exit code {last_exit_code}): {last_error}"
            ) from err

        # This should not be reached, but satisfies the type checker
        return "{}"

    async def get_issue(self, number: int) -> GitHubIssue:
        """Get a single issue by number.

        Args:
            number: GitHub issue number to fetch.

        Returns:
            GitHubIssue instance with parsed issue data.

        Raises:
            RuntimeError: If gh command fails.
            pydantic.ValidationError: If response JSON doesn't match expected schema.
        """
        await self._ensure_authenticated()
        json_output = await self._run_gh_command(
            "issue",
            "view",
            str(number),
            "--json",
            "number,title,body,labels,state,assignees,url",
        )
        # Parse response using Pydantic
        response = GitHubIssueResponse.model_validate_json(json_output)

        return GitHubIssue(
            number=response.number,
            title=response.title,
            body=response.body,
            labels=tuple(label.name for label in response.labels),
            state=response.state.lower(),
            assignees=tuple(user.login for user in response.assignees),
            url=response.url,
        )

    async def list_issues(
        self,
        label: str | None = None,
        state: str = "open",
        limit: int = 30,
    ) -> list[GitHubIssue]:
        """List issues with optional filters.

        Args:
            label: Filter by label name (optional).
            state: Filter by state ("open", "closed", or "all").
            limit: Maximum number of issues to return.

        Returns:
            List of GitHubIssue instances.

        Raises:
            RuntimeError: If gh command fails.
            pydantic.ValidationError: If response JSON doesn't match expected schema.
        """
        await self._ensure_authenticated()
        fields = "number,title,body,labels,state,assignees,url"
        args = ["issue", "list", "--json", fields]
        args.extend(["--state", state, "--limit", str(limit)])
        if label:
            args.extend(["--label", label])

        json_output = await self._run_gh_command(*args)
        # Parse response list using Pydantic TypeAdapter
        adapter = TypeAdapter(list[GitHubIssueResponse])
        responses = adapter.validate_json(json_output)

        return [
            GitHubIssue(
                number=response.number,
                title=response.title,
                body=response.body,
                labels=tuple(label.name for label in response.labels),
                state=response.state.lower(),
                assignees=tuple(user.login for user in response.assignees),
                url=response.url,
            )
            for response in responses
        ]

    async def validate(self) -> ValidationResult:
        """Validate GitHub CLI runner prerequisites.

        Checks:
            1. gh CLI is on PATH
            2. gh CLI is authenticated
            3. Required scopes (repo, read:org) are present
            4. Token is not expired

        Returns:
            ValidationResult with success status, errors, and warnings.
        """
        from maverick.runners.preflight import ValidationResult

        start_time = time.monotonic()
        errors: list[str] = []
        warnings: list[str] = []

        # Check 1: gh CLI is on PATH
        if shutil.which("gh") is None:
            errors.append(
                "gh CLI is not installed or not on PATH. "
                "Install: brew install gh (macOS), apt install gh (Ubuntu), "
                "or visit https://cli.github.com/"
            )
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return ValidationResult(
                success=False,
                component="GitHubCLIRunner",
                errors=tuple(errors),
                warnings=tuple(warnings),
                duration_ms=duration_ms,
            )

        # Check 2: gh CLI is authenticated
        try:
            auth_result = await self._command_runner.run(["gh", "auth", "status"])
            if not auth_result.success:
                # Check for specific error conditions
                stderr_lower = auth_result.stderr.lower()
                if "not logged" in stderr_lower or auth_result.returncode == 4:
                    errors.append("gh CLI is not authenticated. Run 'gh auth login'.")
                elif "token" in stderr_lower and "expired" in stderr_lower:
                    errors.append(
                        "GitHub token has expired. Run 'gh auth refresh' to renew."
                    )
                else:
                    errors.append(
                        f"gh auth status failed: {auth_result.stderr.strip()}"
                    )
                duration_ms = int((time.monotonic() - start_time) * 1000)
                return ValidationResult(
                    success=False,
                    component="GitHubCLIRunner",
                    errors=tuple(errors),
                    warnings=tuple(warnings),
                    duration_ms=duration_ms,
                )
        except Exception as e:
            errors.append(f"Failed to check gh auth status: {e}")
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return ValidationResult(
                success=False,
                component="GitHubCLIRunner",
                errors=tuple(errors),
                warnings=tuple(warnings),
                duration_ms=duration_ms,
            )

        # Check 3: Required scopes (repo, read:org)
        # Use 'gh auth status' output which shows token scopes
        try:
            # Get detailed auth status with token info
            scope_result = await self._command_runner.run(
                ["gh", "auth", "status", "--show-token"]
            )
            # Parse output for scopes - gh auth status shows scopes in output
            output = scope_result.stdout + scope_result.stderr
            output_lower = output.lower()

            # Required scopes for full functionality
            required_scopes = ["repo", "read:org"]
            missing_scopes: list[str] = []

            for scope in required_scopes:
                # Check if scope appears in output (scopes listed in auth status)
                if scope not in output_lower:
                    missing_scopes.append(scope)

            if missing_scopes:
                scope_list = ", ".join(missing_scopes)
                errors.append(
                    f"Missing required scopes: {scope_list}. "
                    "Run 'gh auth refresh -s repo,read:org'."
                )

            # Check for token expiration warnings in output
            if "expir" in output_lower and "soon" in output_lower:
                warnings.append(
                    "GitHub token will expire soon. Consider running 'gh auth refresh'."
                )

        except Exception as e:
            # Scope check failure is a warning, not an error
            warnings.append(f"Could not verify token scopes: {e}")

        duration_ms = int((time.monotonic() - start_time) * 1000)
        return ValidationResult(
            success=len(errors) == 0,
            component="GitHubCLIRunner",
            errors=tuple(errors),
            warnings=tuple(warnings),
            duration_ms=duration_ms,
        )

    async def create_pr(
        self,
        title: str,
        body: str,
        base: str = "main",
        head: str | None = None,
        draft: bool = False,
    ) -> PullRequest:
        """Create a new pull request.

        Args:
            title: PR title.
            body: PR body/description.
            base: Target branch name.
            head: Source branch name (default: current branch).
            draft: Whether to create as draft PR.

        Returns:
            PullRequest instance with parsed PR data.

        Raises:
            RuntimeError: If gh command fails.
            GitHubAuthError: If authentication is required.
        """
        await self._ensure_authenticated()
        args = ["pr", "create", "--title", title, "--body", body, "--base", base]
        if head:
            args.extend(["--head", head])
        if draft:
            args.append("--draft")

        # Create PR and get JSON output
        result = await self._command_runner.run(["gh", *args])
        if not result.success:
            raise RuntimeError(f"Failed to create PR: {result.stderr}")

        # The create command outputs the PR URL, need to get full details
        pr_url = result.stdout.strip()
        # Extract PR number from URL
        pr_number = int(pr_url.split("/")[-1])

        return await self.get_pr(pr_number)

    async def get_pr(self, number: int) -> PullRequest:
        """Get a pull request by number.

        Args:
            number: Pull request number to fetch.

        Returns:
            PullRequest instance with parsed PR data.

        Raises:
            RuntimeError: If gh command fails.
            pydantic.ValidationError: If response JSON doesn't match expected schema.
        """
        await self._ensure_authenticated()
        fields = "number,title,body,state,url,headRefName,baseRefName,mergeable,isDraft"
        json_output = await self._run_gh_command(
            "pr", "view", str(number), "--json", fields
        )
        # Parse response using Pydantic
        response = GitHubPRResponse.model_validate_json(json_output)

        return PullRequest(
            number=response.number,
            title=response.title,
            body=response.body,
            state=response.state.lower(),
            url=response.url,
            head_branch=response.head_ref_name,
            base_branch=response.base_ref_name,
            mergeable=response.mergeable,
            draft=response.is_draft,
        )

    async def get_pr_checks(self, pr_number: int) -> list[CheckStatus]:
        """Get CI check statuses for a PR.

        Args:
            pr_number: Pull request number to get checks for.

        Returns:
            List of CheckStatus instances.

        Raises:
            RuntimeError: If gh command fails.
            pydantic.ValidationError: If response JSON doesn't match expected schema.
        """
        await self._ensure_authenticated()
        json_output = await self._run_gh_command(
            "pr", "checks", str(pr_number), "--json", "name,state,conclusion,detailsUrl"
        )
        # Parse response list using Pydantic TypeAdapter
        adapter = TypeAdapter(list[GitHubCheckResponse])
        responses = adapter.validate_json(json_output)

        return [
            CheckStatus(
                name=response.name,
                status=(
                    "completed"
                    if response.conclusion
                    else response.state.lower()
                    if response.state
                    else "queued"
                ),
                conclusion=response.conclusion.lower() if response.conclusion else None,
                url=response.details_url if response.details_url else None,
            )
            for response in responses
        ]
