"""Unit tests for GitHub prerequisites verification.

Tests verify_github_prerequisites function.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


class TestVerifyPrerequisites:
    """Tests for verify_github_prerequisites function (T009)."""

    @pytest.mark.asyncio
    async def testverify_github_prerequisites_success(self) -> None:
        """Test all prerequisites checks pass successfully."""
        from maverick.tools.github import verify_github_prerequisites

        # Mock successful subprocess calls
        async def mock_subprocess_exec(*args, **kwargs):
            """Mock successful subprocess execution."""
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 0
            return mock_process

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=mock_subprocess_exec,
            ),
            patch(
                "maverick.tools.github.prereqs.run_gh_command",
                new_callable=AsyncMock,
                return_value=("Logged in as user", "", 0),
            ),
        ):
            # Should not raise any exception
            await verify_github_prerequisites()

    @pytest.mark.asyncio
    async def testverify_github_prerequisites_gh_not_installed(self) -> None:
        """Test gh CLI not found (FileNotFoundError)."""
        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import verify_github_prerequisites

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("gh command not found"),
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await verify_github_prerequisites()

            assert exc_info.value.check_failed == "gh_installed"
            assert "gh" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def testverify_github_prerequisites_gh_not_authenticated(self) -> None:
        """Test gh auth status fails."""
        from maverick.exceptions import GitHubToolsError
        from maverick.runners.models import CommandResult
        from maverick.tools.github import verify_github_prerequisites

        call_count = 0

        # Mock CommandRunner.run to succeed for gh --version but fail for gh auth status
        async def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if cmd == ["gh", "--version"]:
                return CommandResult(
                    returncode=0,
                    stdout="gh version 2.0.0",
                    stderr="",
                    duration_ms=10,
                    timed_out=False,
                )
            elif cmd == ["gh", "auth", "status"]:
                return CommandResult(
                    returncode=1,
                    stdout="",
                    stderr="You are not logged into any GitHub hosts",
                    duration_ms=10,
                    timed_out=False,
                )
            # Default success for other commands
            return CommandResult(
                returncode=0, stdout="", stderr="", duration_ms=10, timed_out=False
            )

        with patch(
            "maverick.tools.github.CommandRunner.run",
            side_effect=mock_run,
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await verify_github_prerequisites()

            assert exc_info.value.check_failed == "gh_authenticated"
            assert "authenticated" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def testverify_github_prerequisites_not_git_repo(self) -> None:
        """Test git rev-parse fails (not in git repo)."""
        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import verify_github_prerequisites

        call_count = 0

        async def mock_subprocess_exec(*args, **kwargs):
            """Mock subprocess: gh succeeds, git rev-parse fails."""
            nonlocal call_count
            call_count += 1

            mock_process = AsyncMock()
            command = args[0]

            if command == "gh":
                # gh --version succeeds
                mock_process.communicate = AsyncMock(
                    return_value=(b"gh version 2.0.0", b"")
                )
                mock_process.returncode = 0
            elif command == "git" and "rev-parse" in args:
                # git rev-parse fails
                mock_process.communicate = AsyncMock(
                    return_value=(b"", b"fatal: not a git repository")
                )
                mock_process.returncode = 128
            else:
                # Other git commands succeed
                mock_process.communicate = AsyncMock(return_value=(b"", b""))
                mock_process.returncode = 0

            return mock_process

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=mock_subprocess_exec,
            ),
            patch(
                "maverick.tools.github.prereqs.run_gh_command",
                new_callable=AsyncMock,
                return_value=("Logged in as user", "", 0),
            ),
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await verify_github_prerequisites()

            assert exc_info.value.check_failed == "git_repo"
            assert "git repository" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def testverify_github_prerequisites_no_remote(self) -> None:
        """Test git remote get-url fails (no origin)."""
        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import verify_github_prerequisites

        call_count = 0

        async def mock_subprocess_exec(*args, **kwargs):
            """Mock subprocess: gh and git rev-parse succeed, git remote fails."""
            nonlocal call_count
            call_count += 1

            mock_process = AsyncMock()
            command = args[0]

            if command == "gh":
                # gh --version succeeds
                mock_process.communicate = AsyncMock(
                    return_value=(b"gh version 2.0.0", b"")
                )
                mock_process.returncode = 0
            elif command == "git" and "remote" in args and "get-url" in args:
                # git remote get-url origin fails
                mock_process.communicate = AsyncMock(
                    return_value=(b"", b"fatal: No such remote 'origin'")
                )
                mock_process.returncode = 128
            else:
                # Other commands succeed
                mock_process.communicate = AsyncMock(return_value=(b"", b""))
                mock_process.returncode = 0

            return mock_process

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=mock_subprocess_exec,
            ),
            patch(
                "maverick.tools.github.prereqs.run_gh_command",
                new_callable=AsyncMock,
                return_value=("Logged in as user", "", 0),
            ),
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await verify_github_prerequisites()

            assert exc_info.value.check_failed == "git_remote"
            assert "remote" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def testverify_github_prerequisites_gh_timeout(self) -> None:
        """Test gh --version times out."""

        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import verify_github_prerequisites

        async def mock_subprocess_exec(*args, **kwargs):
            """Mock subprocess that times out for gh --version."""
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(side_effect=TimeoutError())
            return mock_process

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=mock_subprocess_exec,
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await verify_github_prerequisites()

            assert exc_info.value.check_failed == "gh_installed"
            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def testverify_github_prerequisites_git_not_installed(self) -> None:
        """Test git not found (FileNotFoundError)."""
        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import verify_github_prerequisites

        call_count = 0

        async def mock_subprocess_exec(*args, **kwargs):
            """Mock subprocess: gh succeeds, git fails with FileNotFoundError."""
            nonlocal call_count
            call_count += 1

            mock_process = AsyncMock()
            command = args[0]

            if command == "gh":
                # gh --version succeeds
                mock_process.communicate = AsyncMock(
                    return_value=(b"gh version 2.0.0", b"")
                )
                mock_process.returncode = 0
                return mock_process
            elif command == "git":
                # git not found
                raise FileNotFoundError("git command not found")

            return mock_process

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=mock_subprocess_exec,
            ),
            patch(
                "maverick.tools.github.prereqs.run_gh_command",
                new_callable=AsyncMock,
                return_value=("Logged in as user", "", 0),
            ),
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await verify_github_prerequisites()

            assert exc_info.value.check_failed == "git_installed"
            assert "git" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def testverify_github_prerequisites_git_timeout(self) -> None:
        """Test git rev-parse times out."""
        from maverick.exceptions import GitHubToolsError
        from maverick.runners.models import CommandResult
        from maverick.tools.github import verify_github_prerequisites

        call_count = 0

        # Mock CommandRunner.run to succeed for gh but timeout for git rev-parse
        async def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if cmd == ["gh", "--version"]:
                return CommandResult(
                    returncode=0,
                    stdout="gh version 2.0.0",
                    stderr="",
                    duration_ms=10,
                    timed_out=False,
                )
            elif cmd == ["gh", "auth", "status"]:
                return CommandResult(
                    returncode=0,
                    stdout="Logged in as user",
                    stderr="",
                    duration_ms=10,
                    timed_out=False,
                )
            elif cmd == ["git", "rev-parse", "--git-dir"]:
                return CommandResult(
                    returncode=-1,
                    stdout="",
                    stderr="",
                    duration_ms=5000,
                    timed_out=True,
                )
            # Default success for other commands
            return CommandResult(
                returncode=0, stdout="", stderr="", duration_ms=10, timed_out=False
            )

        with patch(
            "maverick.tools.github.CommandRunner.run",
            side_effect=mock_run,
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await verify_github_prerequisites()

            assert exc_info.value.check_failed == "git_repo"
            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def testverify_github_prerequisites_git_remote_timeout(self) -> None:
        """Test git remote get-url times out."""

        from maverick.exceptions import GitHubToolsError
        from maverick.runners.models import CommandResult
        from maverick.tools.github import verify_github_prerequisites

        call_count = 0

        # Mock CommandRunner.run to succeed for all checks except git remote (timeout)
        async def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if cmd == ["gh", "--version"]:
                return CommandResult(
                    returncode=0,
                    stdout="gh version 2.0.0",
                    stderr="",
                    duration_ms=10,
                    timed_out=False,
                )
            elif cmd == ["gh", "auth", "status"]:
                return CommandResult(
                    returncode=0,
                    stdout="Logged in as user",
                    stderr="",
                    duration_ms=10,
                    timed_out=False,
                )
            elif cmd == ["git", "rev-parse", "--git-dir"]:
                return CommandResult(
                    returncode=0,
                    stdout=".git",
                    stderr="",
                    duration_ms=10,
                    timed_out=False,
                )
            elif cmd == ["git", "remote", "get-url", "origin"]:
                return CommandResult(
                    returncode=-1,
                    stdout="",
                    stderr="",
                    duration_ms=5000,
                    timed_out=True,
                )
            # Default success for other commands
            return CommandResult(
                returncode=0, stdout="", stderr="", duration_ms=10, timed_out=False
            )

        with patch(
            "maverick.tools.github.CommandRunner.run",
            side_effect=mock_run,
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await verify_github_prerequisites()

            assert exc_info.value.check_failed == "git_remote"
            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def testverify_github_prerequisites_gh_returncode_nonzero(self) -> None:
        """Test gh --version returns non-zero exit code."""
        from maverick.exceptions import GitHubToolsError
        from maverick.runners.models import CommandResult
        from maverick.tools.github import verify_github_prerequisites

        # Mock CommandRunner.run to return non-zero for gh --version
        async def mock_run(cmd, **kwargs):
            if cmd == ["gh", "--version"]:
                return CommandResult(
                    returncode=1,
                    stdout="",
                    stderr="error",
                    duration_ms=10,
                    timed_out=False,
                )
            # Default success for other commands
            return CommandResult(
                returncode=0, stdout="", stderr="", duration_ms=10, timed_out=False
            )

        with patch(
            "maverick.tools.github.CommandRunner.run",
            side_effect=mock_run,
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await verify_github_prerequisites()

            assert exc_info.value.check_failed == "gh_installed"
            assert "gh" in str(exc_info.value).lower()


# =============================================================================
# create_github_tools_server Tests (T008)
# =============================================================================


class TestVerifyGitHubPrerequisites:
    """Tests for the public verify_github_prerequisites function."""

    @pytest.mark.asyncio
    async def test_verify_github_prerequisites_success(self) -> None:
        """Test verify_github_prerequisites succeeds when prerequisites are met."""
        from maverick.runners.models import CommandResult
        from maverick.tools.github import verify_github_prerequisites

        # Mock get_runner to return a mock runner
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(
            return_value=CommandResult(
                returncode=0, stdout="success", stderr="", duration_ms=100
            )
        )

        with patch(
            "maverick.tools.github.prereqs.get_runner",
            return_value=mock_runner,
        ):
            # Should complete without raising
            await verify_github_prerequisites()

    @pytest.mark.asyncio
    async def test_verify_github_prerequisites_failure(self) -> None:
        """Test verify_github_prerequisites raises when gh CLI is not found."""
        from maverick.exceptions import GitHubToolsError
        from maverick.runners.models import CommandResult
        from maverick.tools.github import verify_github_prerequisites

        # Mock get_runner to return a mock runner that returns command not found
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(
            return_value=CommandResult(
                returncode=127, stdout="", stderr="command not found", duration_ms=100
            )
        )

        with patch(
            "maverick.tools.github.prereqs.get_runner",
            return_value=mock_runner,
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await verify_github_prerequisites()

            assert exc_info.value.check_failed == "gh_installed"

    @pytest.mark.asyncio
    async def test_verify_github_prerequisites_is_async(self) -> None:
        """Test verify_github_prerequisites is a proper async function."""
        import inspect

        from maverick.tools.github import verify_github_prerequisites

        assert inspect.iscoroutinefunction(verify_github_prerequisites)

    @pytest.mark.asyncio
    async def test_verify_github_prerequisites_fail_fast_pattern(self) -> None:
        """Test the recommended fail-fast pattern works.

        Pattern:
            await verify_github_prerequisites()  # fail-fast check
            server = create_github_tools_server()  # create server
        """
        from maverick.runners.models import CommandResult
        from maverick.tools.github import (
            create_github_tools_server,
            verify_github_prerequisites,
        )

        # Mock get_runner to return a mock runner
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(
            return_value=CommandResult(
                returncode=0, stdout="gh version 2.40", stderr="", duration_ms=100
            )
        )

        with patch(
            "maverick.tools.github.prereqs.get_runner",
            return_value=mock_runner,
        ):
            # Fail-fast verification
            await verify_github_prerequisites()

            # Then create server
            server = create_github_tools_server()

            assert server is not None
            # McpSdkServerConfig has instance and name keys
            assert "instance" in server or "name" in server

    @pytest.mark.asyncio
    async def test_verify_github_prerequisites_in_nested_async(self) -> None:
        """Test verify_github_prerequisites works in nested async operations."""
        from maverick.runners.models import CommandResult
        from maverick.tools.github import verify_github_prerequisites

        # Mock get_runner to return a mock runner
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(
            return_value=CommandResult(
                returncode=0, stdout="Logged in", stderr="", duration_ms=100
            )
        )

        async def nested_verify():
            await verify_github_prerequisites()
            return True

        with patch(
            "maverick.tools.github.prereqs.get_runner",
            return_value=mock_runner,
        ):
            result = await nested_verify()
            assert result is True


# =============================================================================
# github_close_issue Tests (T042-T044)
# =============================================================================
