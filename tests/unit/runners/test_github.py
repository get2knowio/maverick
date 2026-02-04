"""Tests for GitHubCLIRunner."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maverick.exceptions import GitHubAuthError, GitHubCLINotFoundError
from maverick.runners.github import GitHubCLIRunner
from maverick.runners.models import CommandResult, GitHubIssue, PullRequest


@pytest.fixture
def mock_gh_available():
    with patch("shutil.which", return_value="/usr/bin/gh"):
        yield


class TestGitHubCLIRunner:
    def test_gh_not_installed(self):
        """Test GitHubCLINotFoundError raised when gh not installed."""
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(GitHubCLINotFoundError),
        ):
            GitHubCLIRunner()

    @pytest.mark.asyncio
    async def test_auth_check_on_first_use(self, mock_gh_available):
        """Test authentication is checked on first async operation (fail-fast)."""
        # Mock auth check failure
        auth_result = CommandResult(
            returncode=1,
            stdout="",
            stderr="Not authenticated",
            duration_ms=50,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=auth_result)
        runner._command_runner = mock_runner

        # First call to any async method should check auth and fail
        with pytest.raises(GitHubAuthError):
            await runner.get_issue(42)

        # Verify auth check was called
        mock_runner.run.assert_called_once_with(["gh", "auth", "status"])

    @pytest.mark.asyncio
    async def test_auth_check_only_once(self, mock_gh_available):
        """Test authentication is checked only once, not on every call."""
        # Mock successful auth check
        auth_result = CommandResult(
            returncode=0,
            stdout="Logged in",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        # Mock successful issue fetch
        issue_result = CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "number": 42,
                    "title": "Test",
                    "body": "",
                    "labels": [],
                    "state": "OPEN",
                    "assignees": [],
                    "url": "https://github.com/repo/issues/42",
                }
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        # First call: auth check, second call: get issue, third call: get issue again
        mock_runner.run = AsyncMock(
            side_effect=[auth_result, issue_result, issue_result]
        )
        runner._command_runner = mock_runner

        # First call should check auth
        await runner.get_issue(42)
        # Second call should NOT check auth again
        await runner.get_issue(42)

        # Verify auth check was called only once (first call)
        assert mock_runner.run.call_count == 3
        # First call was auth check
        assert mock_runner.run.call_args_list[0][0][0] == ["gh", "auth", "status"]
        # Second and third calls were issue commands
        assert mock_runner.run.call_args_list[1][0][0][0] == "gh"
        assert mock_runner.run.call_args_list[2][0][0][0] == "gh"

    @pytest.mark.asyncio
    async def test_get_issue(self, mock_gh_available):
        """Test fetching a single issue."""
        auth_result = CommandResult(
            returncode=0, stdout="Logged in", stderr="", duration_ms=50, timed_out=False
        )
        mock_result = CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "number": 42,
                    "title": "Test Issue",
                    "body": "Description",
                    "labels": [{"name": "bug"}],
                    "state": "OPEN",
                    "assignees": [{"login": "user1"}],
                    "url": "https://github.com/repo/issues/42",
                }
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(side_effect=[auth_result, mock_result])
        runner._command_runner = mock_runner

        issue = await runner.get_issue(42)

        assert isinstance(issue, GitHubIssue)
        assert issue.number == 42
        assert issue.title == "Test Issue"
        assert issue.state == "open"
        assert "bug" in issue.labels

    @pytest.mark.asyncio
    async def test_list_issues_with_filter(self, mock_gh_available):
        """Test listing issues with label filter."""
        auth_result = CommandResult(
            returncode=0, stdout="Logged in", stderr="", duration_ms=50, timed_out=False
        )
        mock_result = CommandResult(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "number": 1,
                        "title": "Issue 1",
                        "body": "",
                        "labels": [{"name": "bug"}],
                        "state": "OPEN",
                        "assignees": [],
                        "url": "https://github.com/repo/issues/1",
                    },
                ]
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(side_effect=[auth_result, mock_result])
        runner._command_runner = mock_runner

        issues = await runner.list_issues(label="bug", state="open")

        assert len(issues) == 1
        assert issues[0].number == 1

    @pytest.mark.asyncio
    async def test_create_pr(self, mock_gh_available):
        """Test creating a pull request."""
        auth_result = CommandResult(
            returncode=0, stdout="Logged in", stderr="", duration_ms=50, timed_out=False
        )
        create_result = CommandResult(
            returncode=0,
            stdout="https://github.com/repo/pull/123\n",
            stderr="",
            duration_ms=100,
            timed_out=False,
        )
        view_result = CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "number": 123,
                    "title": "Test PR",
                    "body": "PR body",
                    "state": "OPEN",
                    "url": "https://github.com/repo/pull/123",
                    "headRefName": "feature",
                    "baseRefName": "main",
                    "mergeable": True,
                    "isDraft": False,
                }
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        # Auth check, create PR, then get_pr is called which doesn't check auth again
        mock_runner.run = AsyncMock(
            side_effect=[auth_result, create_result, view_result]
        )
        runner._command_runner = mock_runner

        pr = await runner.create_pr(title="Test PR", body="PR body")

        assert isinstance(pr, PullRequest)
        assert pr.number == 123
        assert pr.title == "Test PR"

    @pytest.mark.asyncio
    async def test_get_pr_checks(self, mock_gh_available):
        """Test getting PR check statuses."""
        auth_result = CommandResult(
            returncode=0, stdout="Logged in", stderr="", duration_ms=50, timed_out=False
        )
        mock_result = CommandResult(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "test",
                        "state": "completed",
                        "conclusion": "success",
                        "detailsUrl": "https://...",
                    },
                    {
                        "name": "lint",
                        "state": "in_progress",
                        "conclusion": None,
                        "detailsUrl": None,
                    },
                ]
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(side_effect=[auth_result, mock_result])
        runner._command_runner = mock_runner

        checks = await runner.get_pr_checks(123)

        assert len(checks) == 2
        assert checks[0].name == "test"
        assert checks[0].passed is True
        assert checks[1].pending is True

    @pytest.mark.asyncio
    async def test_malformed_issue_response_validation_error(self, mock_gh_available):
        """Test that Pydantic provides clear error messages for malformed JSON."""
        auth_result = CommandResult(
            returncode=0, stdout="Logged in", stderr="", duration_ms=50, timed_out=False
        )
        # Malformed response: missing required 'number' field
        malformed_result = CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "title": "Test Issue",
                    "body": "Description",
                    "labels": [],
                    "state": "OPEN",
                    "assignees": [],
                    "url": "https://github.com/repo/issues/42",
                    # missing 'number' field
                }
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(side_effect=[auth_result, malformed_result])
        runner._command_runner = mock_runner

        # Should raise ValidationError with clear error message
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            await runner.get_issue(42)

        # Verify error message mentions the missing field
        error_msg = str(exc_info.value)
        assert "number" in error_msg.lower()
        assert "field required" in error_msg.lower() or "missing" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_type_coercion_in_issue_response(self, mock_gh_available):
        """Test that Pydantic handles type coercion automatically."""
        auth_result = CommandResult(
            returncode=0, stdout="Logged in", stderr="", duration_ms=50, timed_out=False
        )
        # Response with number as string (Pydantic should coerce to int)
        coerced_result = CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "number": "42",  # String instead of int
                    "title": "Test Issue",
                    "body": "Description",
                    "labels": [{"name": "bug"}],
                    "state": "OPEN",
                    "assignees": [],
                    "url": "https://github.com/repo/issues/42",
                }
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(side_effect=[auth_result, coerced_result])
        runner._command_runner = mock_runner

        # Should successfully parse and coerce the number field
        issue = await runner.get_issue(42)

        assert isinstance(issue.number, int)
        assert issue.number == 42
        assert issue.title == "Test Issue"


class TestErrorClassification:
    """Test suite for _classify_error() method."""

    def test_classify_auth_error_by_exit_code(self, mock_gh_available):
        """Test authentication error classification using exit code 4."""
        runner = GitHubCLIRunner()

        error_type, error_message, is_retryable = runner._classify_error(
            4, "Not authenticated"
        )

        assert error_type == "auth"
        assert "Authentication required" in error_message
        assert is_retryable is False

    def test_classify_canceled_by_exit_code(self, mock_gh_available):
        """Test command canceled classification using exit code 2."""
        runner = GitHubCLIRunner()

        error_type, error_message, is_retryable = runner._classify_error(
            2, "Operation canceled"
        )

        assert error_type == "canceled"
        assert "canceled" in error_message.lower()
        assert is_retryable is False

    def test_classify_checks_pending_by_exit_code(self, mock_gh_available):
        """Test checks pending classification using exit code 8."""
        runner = GitHubCLIRunner()

        error_type, error_message, is_retryable = runner._classify_error(
            8, "Some checks are still pending"
        )

        assert error_type == "pending"
        assert "pending" in error_message.lower()
        assert is_retryable is True

    def test_classify_network_error_by_stderr(self, mock_gh_available):
        """Test network error classification using stderr (exit code 1)."""
        runner = GitHubCLIRunner()

        error_type, error_message, is_retryable = runner._classify_error(
            1, "Could not resolve host: github.com"
        )

        assert error_type == "network"
        assert "Network error" in error_message
        assert is_retryable is True

    def test_classify_network_timeout_by_stderr(self, mock_gh_available):
        """Test network timeout classification using stderr."""
        runner = GitHubCLIRunner()

        error_type, error_message, is_retryable = runner._classify_error(
            1, "dial tcp: i/o timeout"
        )

        assert error_type == "network"
        assert "Network error" in error_message
        assert is_retryable is True

    def test_classify_rate_limit_by_stderr(self, mock_gh_available):
        """Test rate limit classification using stderr."""
        runner = GitHubCLIRunner()

        error_type, error_message, is_retryable = runner._classify_error(
            1, "API rate limit exceeded for user"
        )

        assert error_type == "rate_limit"
        assert "rate limit" in error_message.lower()
        assert is_retryable is True

    def test_classify_not_found_by_stderr(self, mock_gh_available):
        """Test not found error classification using stderr."""
        runner = GitHubCLIRunner()

        error_type, error_message, is_retryable = runner._classify_error(
            1, "pull request not found"
        )

        assert error_type == "not_found"
        assert "not found" in error_message.lower()
        assert is_retryable is False

    def test_classify_validation_error_by_stderr(self, mock_gh_available):
        """Test validation error classification using stderr."""
        runner = GitHubCLIRunner()

        error_type, error_message, is_retryable = runner._classify_error(
            1, "validation failed: title is required"
        )

        assert error_type == "validation"
        assert "Validation error" in error_message
        assert is_retryable is False

    def test_classify_auth_fallback_to_stderr(self, mock_gh_available):
        """Test auth classification falls back to stderr when exit code is 1."""
        runner = GitHubCLIRunner()

        error_type, error_message, is_retryable = runner._classify_error(
            1, "Not authenticated. Run: gh auth login"
        )

        assert error_type == "auth"
        assert "Authentication required" in error_message
        assert is_retryable is False

    def test_classify_unknown_error(self, mock_gh_available):
        """Test unknown error classification for unrecognized patterns."""
        runner = GitHubCLIRunner()

        error_type, error_message, is_retryable = runner._classify_error(
            1, "Some random error message"
        )

        assert error_type == "unknown"
        assert "exit code 1" in error_message
        assert is_retryable is False

    def test_classify_unknown_exit_code(self, mock_gh_available):
        """Test classification for unknown exit codes."""
        runner = GitHubCLIRunner()

        error_type, error_message, is_retryable = runner._classify_error(
            99, "Unexpected error"
        )

        assert error_type == "unknown"
        assert "exit code 99" in error_message
        assert is_retryable is False

    def test_exit_code_takes_precedence_over_stderr(self, mock_gh_available):
        """Test that exit code takes precedence over stderr matching."""
        runner = GitHubCLIRunner()

        # Even though stderr mentions "not found", exit code 4 should classify as auth
        error_type, error_message, is_retryable = runner._classify_error(
            4, "Token not found or expired"
        )

        assert error_type == "auth"
        assert "Authentication required" in error_message
        assert is_retryable is False


class TestErrorHandlingInCommands:
    """Test error classification integration with _run_gh_command."""

    @pytest.mark.asyncio
    async def test_auth_error_raises_immediately(self, mock_gh_available):
        """Test that auth errors (exit code 4) raise GitHubAuthError immediately."""
        runner = GitHubCLIRunner()
        runner._auth_checked = True  # Skip initial auth check

        auth_error_result = CommandResult(
            returncode=4,
            stdout="",
            stderr="Not authenticated",
            duration_ms=50,
            timed_out=False,
        )

        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=auth_error_result)
        runner._command_runner = mock_runner

        with pytest.raises(GitHubAuthError):
            await runner._run_gh_command("pr", "list")

        # Should not retry for auth errors
        mock_runner.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found_error_raises_immediately(self, mock_gh_available):
        """Test that not found errors don't retry."""
        runner = GitHubCLIRunner()
        runner._auth_checked = True

        not_found_result = CommandResult(
            returncode=1,
            stdout="",
            stderr="pull request not found",
            duration_ms=50,
            timed_out=False,
        )

        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=not_found_result)
        runner._command_runner = mock_runner

        with pytest.raises(RuntimeError) as exc_info:
            await runner._run_gh_command("pr", "view", "999")

        # Should not retry for not_found errors
        mock_runner.run.assert_called_once()
        assert "not_found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_network_error_retries(self, mock_gh_available):
        """Test that network errors are retried."""
        runner = GitHubCLIRunner()
        runner._auth_checked = True

        network_error_result = CommandResult(
            returncode=1,
            stdout="",
            stderr="Could not resolve host: github.com",
            duration_ms=50,
            timed_out=False,
        )

        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=network_error_result)
        runner._command_runner = mock_runner

        with patch("tenacity.nap.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError) as exc_info:
                await runner._run_gh_command("issue", "list")

        # Should retry 3 times for network errors
        assert mock_runner.run.call_count == 3
        assert "exit code 1" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_network_error_succeeds_on_retry(self, mock_gh_available):
        """Test that network errors succeed after retry."""
        runner = GitHubCLIRunner()
        runner._auth_checked = True

        network_error_result = CommandResult(
            returncode=1,
            stdout="",
            stderr="Connection timeout",
            duration_ms=50,
            timed_out=False,
        )
        success_result = CommandResult(
            returncode=0,
            stdout='{"issues": []}',
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        mock_runner = AsyncMock()
        # First call fails with network error, second succeeds
        mock_runner.run = AsyncMock(side_effect=[network_error_result, success_result])
        runner._command_runner = mock_runner

        with patch("tenacity.nap.sleep", new_callable=AsyncMock):
            result = await runner._run_gh_command("issue", "list")

        # Should retry and succeed
        assert mock_runner.run.call_count == 2
        assert result == '{"issues": []}'

    @pytest.mark.asyncio
    async def test_canceled_error_no_retry(self, mock_gh_available):
        """Test that canceled errors (exit code 2) don't retry."""
        runner = GitHubCLIRunner()
        runner._auth_checked = True

        canceled_result = CommandResult(
            returncode=2,
            stdout="",
            stderr="Operation canceled by user",
            duration_ms=50,
            timed_out=False,
        )

        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=canceled_result)
        runner._command_runner = mock_runner

        with pytest.raises(RuntimeError) as exc_info:
            await runner._run_gh_command("pr", "create")

        # Should not retry for canceled errors
        mock_runner.run.assert_called_once()
        assert "canceled" in str(exc_info.value)


class TestGitHubCLIRunnerValidate:
    """Tests for GitHubCLIRunner.validate()."""

    @pytest.mark.asyncio
    @patch("maverick.runners.github.shutil.which")
    async def test_validate_success(self, mock_which):
        """Test validate success with all checks passing."""
        from maverick.runners.preflight import ValidationResult

        mock_which.return_value = "/usr/bin/gh"

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()

        # Mock auth status check (success)
        auth_result = CommandResult(
            returncode=0,
            stdout="Logged in to github.com",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        # Mock auth status with --show-token (includes repo and read:org scopes)
        scope_result = CommandResult(
            returncode=0,
            stdout="Token: ghp_xxx\nScopes: repo, read:org, workflow\n",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )

        mock_runner.run = AsyncMock(side_effect=[auth_result, scope_result])
        runner._command_runner = mock_runner

        result = await runner.validate()

        assert isinstance(result, ValidationResult)
        assert result.success is True
        assert result.component == "GitHubCLIRunner"
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    @pytest.mark.asyncio
    @patch("maverick.runners.github.shutil.which")
    async def test_validate_gh_not_on_path(self, mock_which):
        """Test validate failure when gh CLI is not on PATH."""
        from maverick.runners.preflight import ValidationResult

        mock_which.return_value = None

        # Need to bypass __init__ check since it also checks for gh
        with patch("shutil.which", return_value="/usr/bin/gh"):
            runner = GitHubCLIRunner()

        # Now mock the validate method's which call
        mock_which.return_value = None

        result = await runner.validate()

        assert isinstance(result, ValidationResult)
        assert result.success is False
        assert result.component == "GitHubCLIRunner"
        assert any(
            "not installed" in error or "not on PATH" in error
            for error in result.errors
        )

    @pytest.mark.asyncio
    @patch("maverick.runners.github.shutil.which")
    async def test_validate_not_authenticated(self, mock_which):
        """Test validate failure when gh CLI is not authenticated (exit code 4)."""
        from maverick.runners.preflight import ValidationResult

        mock_which.return_value = "/usr/bin/gh"

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()

        # Mock auth status check failure with exit code 4
        auth_result = CommandResult(
            returncode=4,
            stdout="",
            stderr=(
                "You are not logged into any GitHub hosts. "
                "Run gh auth login to authenticate."
            ),
            duration_ms=50,
            timed_out=False,
        )

        mock_runner.run = AsyncMock(return_value=auth_result)
        runner._command_runner = mock_runner

        result = await runner.validate()

        assert isinstance(result, ValidationResult)
        assert result.success is False
        assert result.component == "GitHubCLIRunner"
        assert any(
            "not authenticated" in error.lower() or "gh auth login" in error
            for error in result.errors
        )

    @pytest.mark.asyncio
    @patch("maverick.runners.github.shutil.which")
    async def test_validate_token_expired(self, mock_which):
        """Test validate failure when GitHub token has expired."""
        from maverick.runners.preflight import ValidationResult

        mock_which.return_value = "/usr/bin/gh"

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()

        # Mock auth status check failure with token expired message
        auth_result = CommandResult(
            returncode=1,
            stdout="",
            stderr="Your authentication token has expired. Run gh auth refresh.",
            duration_ms=50,
            timed_out=False,
        )

        mock_runner.run = AsyncMock(return_value=auth_result)
        runner._command_runner = mock_runner

        result = await runner.validate()

        assert isinstance(result, ValidationResult)
        assert result.success is False
        assert result.component == "GitHubCLIRunner"
        assert any("expired" in error.lower() for error in result.errors)

    @pytest.mark.asyncio
    @patch("maverick.runners.github.shutil.which")
    async def test_validate_missing_scopes_warning(self, mock_which):
        """Test validate succeeds with warning when missing recommended scopes."""
        from maverick.runners.preflight import ValidationResult

        mock_which.return_value = "/usr/bin/gh"

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()

        # Mock auth status check (success)
        auth_result = CommandResult(
            returncode=0,
            stdout="Logged in to github.com",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        # Mock auth status with --show-token (missing repo and read:org scopes)
        scope_result = CommandResult(
            returncode=0,
            stdout="Token: ghp_xxx\nScopes: workflow\n",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )

        mock_runner.run = AsyncMock(side_effect=[auth_result, scope_result])
        runner._command_runner = mock_runner

        result = await runner.validate()

        assert isinstance(result, ValidationResult)
        assert result.success is False  # Missing scopes is an error per FR-004
        assert result.component == "GitHubCLIRunner"
        assert len(result.errors) > 0
        assert any(
            "missing" in error.lower() and "scope" in error.lower()
            for error in result.errors
        )

    @pytest.mark.asyncio
    @patch("maverick.runners.github.shutil.which")
    async def test_validate_returns_validation_result(self, mock_which):
        """Test that validate() returns a proper ValidationResult type."""
        from maverick.runners.preflight import ValidationResult

        mock_which.return_value = "/usr/bin/gh"

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()

        # Mock successful auth and scope checks
        auth_result = CommandResult(
            returncode=0,
            stdout="Logged in to github.com",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        scope_result = CommandResult(
            returncode=0,
            stdout="Token: ghp_xxx\nScopes: repo, read:org\n",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )

        mock_runner.run = AsyncMock(side_effect=[auth_result, scope_result])
        runner._command_runner = mock_runner

        result = await runner.validate()

        # Verify it's a proper ValidationResult with all expected attributes
        assert isinstance(result, ValidationResult)
        assert hasattr(result, "success")
        assert hasattr(result, "component")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")
        assert hasattr(result, "duration_ms")

        # Verify types
        assert isinstance(result.success, bool)
        assert isinstance(result.component, str)
        assert isinstance(result.errors, tuple)
        assert isinstance(result.warnings, tuple)
        assert isinstance(result.duration_ms, int)
        assert result.duration_ms >= 0
