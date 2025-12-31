"""Unit tests for maverick.init.prereqs module.

Tests cover:
- Individual prerequisite check functions
- Helper functions (redact_api_key, _run_command)
- verify_prerequisites orchestration
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.init.models import PreflightStatus
from maverick.init.prereqs import (
    check_anthropic_key_set,
    check_gh_authenticated,
    check_gh_installed,
    check_git_installed,
    check_in_git_repo,
    redact_api_key,
    verify_prerequisites,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Tests for redact_api_key helper
# =============================================================================


class TestRedactApiKey:
    """Tests for the redact_api_key helper function."""

    def test_empty_key(self) -> None:
        """Empty key returns empty string."""
        assert redact_api_key("") == ""

    def test_short_key(self) -> None:
        """Short key shows only last 4 chars."""
        assert redact_api_key("short") == "...hort"

    def test_standard_anthropic_key(self) -> None:
        """Standard Anthropic key format is redacted correctly."""
        key = "sk-ant-abc123xyz789defghijklmnop"
        result = redact_api_key(key)
        # Shows prefix (sk-ant-) and last 4 chars
        assert result == "sk-ant-...mnop"
        assert "abc123" not in result

    def test_very_short_key(self) -> None:
        """Very short key (< 4 chars) shows what's available."""
        assert redact_api_key("abc") == "...abc"
        assert redact_api_key("a") == "...a"

    def test_non_anthropic_prefix(self) -> None:
        """Keys without sk-ant- prefix still get redacted."""
        result = redact_api_key("other-api-key-12345")
        # No sk-ant- prefix, just shows ...last4
        assert result == "...2345"
        assert "other" not in result


# =============================================================================
# Tests for check_git_installed
# =============================================================================


class TestCheckGitInstalled:
    """Tests for check_git_installed function."""

    @pytest.fixture
    def mock_run_command(self) -> AsyncMock:
        """Create mock for _run_command."""
        return AsyncMock()

    async def test_git_installed_success(self) -> None:
        """Successfully detects git installation."""
        with patch(
            "maverick.init.prereqs._run_command",
            new_callable=AsyncMock,
        ) as mock_cmd:
            mock_cmd.return_value = (0, "git version 2.39.1", "")

            result = await check_git_installed()

            assert result.status == PreflightStatus.PASS
            assert result.name == "git_installed"
            assert "2.39.1" in result.message
            assert result.remediation is None

    async def test_git_not_found(self) -> None:
        """Handles git not installed."""
        with patch(
            "maverick.init.prereqs._run_command",
            new_callable=AsyncMock,
        ) as mock_cmd:
            mock_cmd.return_value = (127, "", "Command not found: git")

            result = await check_git_installed()

            assert result.status == PreflightStatus.FAIL
            assert "not installed" in result.message
            assert result.remediation is not None
            assert "git-scm.com" in result.remediation

    async def test_git_command_error(self) -> None:
        """Handles git command failure."""
        with patch(
            "maverick.init.prereqs._run_command",
            new_callable=AsyncMock,
        ) as mock_cmd:
            mock_cmd.return_value = (1, "", "some error")

            result = await check_git_installed()

            assert result.status == PreflightStatus.FAIL
            assert "failed" in result.message


# =============================================================================
# Tests for check_in_git_repo
# =============================================================================


class TestCheckInGitRepo:
    """Tests for check_in_git_repo function."""

    async def test_in_git_repo_success(self) -> None:
        """Successfully detects git repository."""
        with patch(
            "maverick.init.prereqs._run_command",
            new_callable=AsyncMock,
        ) as mock_cmd:
            mock_cmd.return_value = (0, ".git", "")

            result = await check_in_git_repo()

            assert result.status == PreflightStatus.PASS
            assert result.name == "in_git_repo"
            assert ".git" in result.message

    async def test_not_in_git_repo(self) -> None:
        """Handles not being in a git repository."""
        with patch(
            "maverick.init.prereqs._run_command",
            new_callable=AsyncMock,
        ) as mock_cmd:
            mock_cmd.return_value = (
                128,
                "",
                "fatal: not a git repository",
            )

            result = await check_in_git_repo()

            assert result.status == PreflightStatus.FAIL
            assert "Not in a git repository" in result.message
            assert "git init" in result.remediation

    async def test_with_custom_cwd(self) -> None:
        """Passes cwd to _run_command."""
        custom_path = Path("/custom/path")
        with patch(
            "maverick.init.prereqs._run_command",
            new_callable=AsyncMock,
        ) as mock_cmd:
            mock_cmd.return_value = (0, ".git", "")

            await check_in_git_repo(cwd=custom_path)

            mock_cmd.assert_called_once()
            call_kwargs = mock_cmd.call_args
            assert call_kwargs.kwargs["cwd"] == custom_path


# =============================================================================
# Tests for check_gh_installed
# =============================================================================


class TestCheckGhInstalled:
    """Tests for check_gh_installed function."""

    async def test_gh_installed_success(self) -> None:
        """Successfully detects gh installation."""
        with patch(
            "maverick.init.prereqs._run_command",
            new_callable=AsyncMock,
        ) as mock_cmd:
            mock_cmd.return_value = (0, "gh version 2.40.0 (2024-01-01)\n", "")

            result = await check_gh_installed()

            assert result.status == PreflightStatus.PASS
            assert result.name == "gh_installed"
            assert "2.40.0" in result.message

    async def test_gh_not_found(self) -> None:
        """Handles gh not installed."""
        with patch(
            "maverick.init.prereqs._run_command",
            new_callable=AsyncMock,
        ) as mock_cmd:
            mock_cmd.return_value = (127, "", "Command not found: gh")

            result = await check_gh_installed()

            assert result.status == PreflightStatus.FAIL
            assert "not installed" in result.message
            assert "cli.github.com" in result.remediation


# =============================================================================
# Tests for check_gh_authenticated
# =============================================================================


class TestCheckGhAuthenticated:
    """Tests for check_gh_authenticated function."""

    async def test_gh_authenticated_success(self) -> None:
        """Successfully detects gh authentication."""
        with patch(
            "maverick.init.prereqs._run_command",
            new_callable=AsyncMock,
        ) as mock_cmd:
            mock_cmd.return_value = (
                0,
                "Logged in to github.com as testuser (oauth_token)",
                "",
            )

            result = await check_gh_authenticated()

            assert result.status == PreflightStatus.PASS
            assert result.name == "gh_authenticated"
            assert "testuser" in result.message

    async def test_gh_not_authenticated(self) -> None:
        """Handles gh not authenticated."""
        with patch(
            "maverick.init.prereqs._run_command",
            new_callable=AsyncMock,
        ) as mock_cmd:
            mock_cmd.return_value = (
                1,
                "",
                "You are not logged into any GitHub hosts.",
            )

            result = await check_gh_authenticated()

            assert result.status == PreflightStatus.FAIL
            assert "Not authenticated" in result.message
            assert "gh auth login" in result.remediation


# =============================================================================
# Tests for check_anthropic_key_set
# =============================================================================


class TestCheckAnthropicKeySet:
    """Tests for check_anthropic_key_set function."""

    def test_api_key_set(self) -> None:
        """Successfully detects API key is set."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test123xyz"}):
            result = check_anthropic_key_set()

            assert result.status == PreflightStatus.PASS
            assert result.name == "anthropic_key_set"
            assert "API key" in result.message
            assert "sk-ant-" in result.message
            # Should be redacted
            assert "test123xyz" not in result.message

    def test_oauth_token_set(self) -> None:
        """Successfully detects OAuth token is set."""
        with patch.dict(
            os.environ,
            {"CLAUDE_CODE_OAUTH_TOKEN": "oauth-token-12345"},
            clear=True,
        ):
            result = check_anthropic_key_set()

            assert result.status == PreflightStatus.PASS
            assert result.name == "anthropic_key_set"
            assert "OAuth token" in result.message
            # Should be redacted
            assert "oauth-token-12345" not in result.message

    def test_api_key_preferred_over_oauth(self) -> None:
        """API key is preferred when both are set."""
        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "sk-ant-test123xyz",
                "CLAUDE_CODE_OAUTH_TOKEN": "oauth-token-12345",
            },
        ):
            result = check_anthropic_key_set()

            assert result.status == PreflightStatus.PASS
            assert "API key" in result.message
            assert "OAuth token" not in result.message

    def test_no_credentials_set(self) -> None:
        """Handles neither credential set."""
        with patch.dict(os.environ, {}, clear=True):
            # Make sure neither credential is in environment
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

            result = check_anthropic_key_set()

            assert result.status == PreflightStatus.FAIL
            assert "is set" in result.message  # "Neither X nor Y is set"
            assert "ANTHROPIC_API_KEY" in result.message
            assert "CLAUDE_CODE_OAUTH_TOKEN" in result.message
            assert "ANTHROPIC_API_KEY" in result.remediation


# =============================================================================
# Tests for check_anthropic_api_accessible
# =============================================================================


class TestCheckAnthropicApiAccessible:
    """Tests for check_anthropic_api_accessible function."""

    async def test_api_accessible(self) -> None:
        """Successfully validates API access."""
        from collections.abc import AsyncIterator
        from typing import Any

        async def mock_query_gen(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
            yield MagicMock()

        # Need to patch where it's imported from (claude_agent_sdk)
        mock_query = MagicMock(side_effect=lambda *args, **kwargs: mock_query_gen())
        mock_options = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "claude_agent_sdk": MagicMock(
                    query=mock_query,
                    ClaudeAgentOptions=mock_options,
                )
            },
        ):
            # Re-import to pick up the patched module
            import importlib

            import maverick.init.prereqs

            importlib.reload(maverick.init.prereqs)

            from maverick.init.prereqs import check_anthropic_api_accessible

            result = await check_anthropic_api_accessible(timeout=5.0)

            assert result.status == PreflightStatus.PASS
            assert result.name == "anthropic_api_accessible"
            assert "accessible" in result.message

    async def test_api_timeout(self) -> None:
        """Handles API request timeout."""
        import asyncio
        from collections.abc import AsyncIterator
        from typing import Any

        async def slow_query(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
            await asyncio.sleep(10)  # Will trigger timeout
            yield MagicMock()

        mock_query = MagicMock(side_effect=lambda *args, **kwargs: slow_query())
        mock_options = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "claude_agent_sdk": MagicMock(
                    query=mock_query,
                    ClaudeAgentOptions=mock_options,
                )
            },
        ):
            import importlib

            import maverick.init.prereqs

            importlib.reload(maverick.init.prereqs)

            from maverick.init.prereqs import check_anthropic_api_accessible

            result = await check_anthropic_api_accessible(timeout=0.01)

            assert result.status == PreflightStatus.FAIL
            assert "timed out" in result.message
            assert "network connectivity" in result.remediation

    async def test_api_auth_error(self) -> None:
        """Handles authentication error (401)."""

        class MockAuthError(Exception):
            pass

        # Rename the class to include AuthenticationError
        MockAuthError.__name__ = "AuthenticationError"

        mock_query = MagicMock(side_effect=MockAuthError("401: Invalid API key"))
        mock_options = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "claude_agent_sdk": MagicMock(
                    query=mock_query,
                    ClaudeAgentOptions=mock_options,
                )
            },
        ):
            import importlib

            import maverick.init.prereqs

            importlib.reload(maverick.init.prereqs)

            from maverick.init.prereqs import check_anthropic_api_accessible

            result = await check_anthropic_api_accessible()

            assert result.status == PreflightStatus.FAIL
            assert "Invalid API key" in result.message


# =============================================================================
# Tests for verify_prerequisites
# =============================================================================


class TestVerifyPrerequisites:
    """Tests for verify_prerequisites orchestration function."""

    async def test_all_checks_pass(self) -> None:
        """All checks pass scenario."""
        with (
            patch(
                "maverick.init.prereqs.check_git_installed",
                new_callable=AsyncMock,
            ) as mock_git,
            patch(
                "maverick.init.prereqs.check_in_git_repo",
                new_callable=AsyncMock,
            ) as mock_repo,
            patch(
                "maverick.init.prereqs.check_gh_installed",
                new_callable=AsyncMock,
            ) as mock_gh,
            patch(
                "maverick.init.prereqs.check_gh_authenticated",
                new_callable=AsyncMock,
            ) as mock_gh_auth,
            patch(
                "maverick.init.prereqs.check_anthropic_key_set",
            ) as mock_key,
            patch(
                "maverick.init.prereqs.check_anthropic_api_accessible",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            from maverick.init.models import PreflightStatus, PrerequisiteCheck

            # Mock all checks to pass
            mock_git.return_value = PrerequisiteCheck(
                name="git_installed",
                display_name="Git",
                status=PreflightStatus.PASS,
                message="git version 2.39.1",
            )
            mock_repo.return_value = PrerequisiteCheck(
                name="in_git_repo",
                display_name="Git Repository",
                status=PreflightStatus.PASS,
                message="Git directory: .git",
            )
            mock_gh.return_value = PrerequisiteCheck(
                name="gh_installed",
                display_name="GitHub CLI",
                status=PreflightStatus.PASS,
                message="gh version 2.40.0",
            )
            mock_gh_auth.return_value = PrerequisiteCheck(
                name="gh_authenticated",
                display_name="GitHub Auth",
                status=PreflightStatus.PASS,
                message="Authenticated as testuser",
            )
            mock_key.return_value = PrerequisiteCheck(
                name="anthropic_key_set",
                display_name="Anthropic API Key",
                status=PreflightStatus.PASS,
                message="API key configured (sk-ant-...xyz)",
            )
            mock_api.return_value = PrerequisiteCheck(
                name="anthropic_api_accessible",
                display_name="Anthropic API",
                status=PreflightStatus.PASS,
                message="API accessible",
            )

            result = await verify_prerequisites()

            assert result.success is True
            assert len(result.checks) == 6
            assert len(result.failed_checks) == 0

    async def test_git_not_installed_early_termination(self) -> None:
        """Early termination when git is not installed."""
        with patch(
            "maverick.init.prereqs.check_git_installed",
            new_callable=AsyncMock,
        ) as mock_git:
            from maverick.init.models import PreflightStatus, PrerequisiteCheck

            mock_git.return_value = PrerequisiteCheck(
                name="git_installed",
                display_name="Git",
                status=PreflightStatus.FAIL,
                message="git is not installed",
                remediation="Install git",
            )

            result = await verify_prerequisites()

            assert result.success is False
            # Only git check should have run
            assert len(result.checks) == 1
            assert "git_installed" in result.failed_checks

    async def test_skip_api_check(self) -> None:
        """API check is skipped when skip_api_check=True."""
        with (
            patch(
                "maverick.init.prereqs.check_git_installed",
                new_callable=AsyncMock,
            ) as mock_git,
            patch(
                "maverick.init.prereqs.check_in_git_repo",
                new_callable=AsyncMock,
            ) as mock_repo,
            patch(
                "maverick.init.prereqs.check_gh_installed",
                new_callable=AsyncMock,
            ) as mock_gh,
            patch(
                "maverick.init.prereqs.check_gh_authenticated",
                new_callable=AsyncMock,
            ) as mock_gh_auth,
            patch(
                "maverick.init.prereqs.check_anthropic_key_set",
            ) as mock_key,
            patch(
                "maverick.init.prereqs.check_anthropic_api_accessible",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            from maverick.init.models import PreflightStatus, PrerequisiteCheck

            mock_git.return_value = PrerequisiteCheck(
                name="git_installed",
                display_name="Git",
                status=PreflightStatus.PASS,
                message="git version 2.39.1",
            )
            mock_repo.return_value = PrerequisiteCheck(
                name="in_git_repo",
                display_name="Git Repository",
                status=PreflightStatus.PASS,
                message="Git directory: .git",
            )
            mock_gh.return_value = PrerequisiteCheck(
                name="gh_installed",
                display_name="GitHub CLI",
                status=PreflightStatus.PASS,
                message="gh version 2.40.0",
            )
            mock_gh_auth.return_value = PrerequisiteCheck(
                name="gh_authenticated",
                display_name="GitHub Auth",
                status=PreflightStatus.PASS,
                message="Authenticated as testuser",
            )
            mock_key.return_value = PrerequisiteCheck(
                name="anthropic_key_set",
                display_name="Anthropic API Key",
                status=PreflightStatus.PASS,
                message="API key configured",
            )

            result = await verify_prerequisites(skip_api_check=True)

            # API check should not have been called
            mock_api.assert_not_called()

            # Find the API check
            api_check = next(
                (c for c in result.checks if c.name == "anthropic_api_accessible"),
                None,
            )
            assert api_check is not None
            assert api_check.status == PreflightStatus.SKIP
            assert "--no-detect" in api_check.message

    async def test_gh_auth_skipped_when_gh_not_installed(self) -> None:
        """gh auth check is skipped when gh is not installed."""
        with (
            patch(
                "maverick.init.prereqs.check_git_installed",
                new_callable=AsyncMock,
            ) as mock_git,
            patch(
                "maverick.init.prereqs.check_in_git_repo",
                new_callable=AsyncMock,
            ) as mock_repo,
            patch(
                "maverick.init.prereqs.check_gh_installed",
                new_callable=AsyncMock,
            ) as mock_gh,
            patch(
                "maverick.init.prereqs.check_anthropic_key_set",
            ) as mock_key,
            patch(
                "maverick.init.prereqs.check_anthropic_api_accessible",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            from maverick.init.models import PreflightStatus, PrerequisiteCheck

            mock_git.return_value = PrerequisiteCheck(
                name="git_installed",
                display_name="Git",
                status=PreflightStatus.PASS,
                message="git version 2.39.1",
            )
            mock_repo.return_value = PrerequisiteCheck(
                name="in_git_repo",
                display_name="Git Repository",
                status=PreflightStatus.PASS,
                message="Git directory: .git",
            )
            mock_gh.return_value = PrerequisiteCheck(
                name="gh_installed",
                display_name="GitHub CLI",
                status=PreflightStatus.FAIL,
                message="gh is not installed",
                remediation="Install gh",
            )
            mock_key.return_value = PrerequisiteCheck(
                name="anthropic_key_set",
                display_name="Anthropic API Key",
                status=PreflightStatus.PASS,
                message="API key configured",
            )
            mock_api.return_value = PrerequisiteCheck(
                name="anthropic_api_accessible",
                display_name="Anthropic API",
                status=PreflightStatus.PASS,
                message="API accessible",
            )

            result = await verify_prerequisites()

            # gh auth should be skipped
            gh_auth_check = next(
                (c for c in result.checks if c.name == "gh_authenticated"),
                None,
            )
            assert gh_auth_check is not None
            assert gh_auth_check.status == PreflightStatus.SKIP

            # gh_installed should be in failed_checks
            assert "gh_installed" in result.failed_checks
