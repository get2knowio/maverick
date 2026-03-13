"""Unit tests for maverick.init.prereqs module.

Tests cover:
- Individual prerequisite check functions
- Helper functions (_run_command)
- verify_prerequisites orchestration
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from maverick.init.models import PreflightStatus
from maverick.init.prereqs import (
    check_gh_authenticated,
    check_gh_installed,
    check_git_installed,
    check_in_git_repo,
    verify_prerequisites,
)

if TYPE_CHECKING:
    pass


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

            result = await verify_prerequisites()

            assert result.success is True
            assert len(result.checks) == 4
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
