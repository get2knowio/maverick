"""Tests for maverick.init.git_parser module.

This module tests the git remote URL parsing functionality including:
- SSH URL format parsing
- HTTPS URL format parsing
- Error handling for missing remotes
- Timeout handling
- Edge cases (no remote, invalid URLs, etc.)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.init.git_parser import (
    DEFAULT_TIMEOUT,
    HTTPS_PATTERN,
    SSH_PATTERN,
    _parse_remote_url,
    parse_git_remote,
)
from maverick.init.models import GitRemoteInfo


class TestParseRemoteUrl:
    """Tests for _parse_remote_url helper function."""

    def test_ssh_url_with_git_suffix(self) -> None:
        """Parse SSH URL with .git suffix."""
        owner, repo = _parse_remote_url("git@github.com:owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    def test_ssh_url_without_git_suffix(self) -> None:
        """Parse SSH URL without .git suffix."""
        owner, repo = _parse_remote_url("git@github.com:owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_ssh_url_with_enterprise_host(self) -> None:
        """Parse SSH URL with enterprise GitHub host."""
        owner, repo = _parse_remote_url("git@github.enterprise.com:org/project.git")
        assert owner == "org"
        assert repo == "project"

    def test_ssh_url_with_gitlab(self) -> None:
        """Parse SSH URL from GitLab."""
        owner, repo = _parse_remote_url("git@gitlab.com:group/project.git")
        assert owner == "group"
        assert repo == "project"

    def test_https_url_with_git_suffix(self) -> None:
        """Parse HTTPS URL with .git suffix."""
        owner, repo = _parse_remote_url("https://github.com/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    def test_https_url_without_git_suffix(self) -> None:
        """Parse HTTPS URL without .git suffix."""
        owner, repo = _parse_remote_url("https://github.com/owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_http_url(self) -> None:
        """Parse HTTP URL (not HTTPS)."""
        owner, repo = _parse_remote_url("http://github.com/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    def test_https_url_with_enterprise_host(self) -> None:
        """Parse HTTPS URL with enterprise host."""
        owner, repo = _parse_remote_url("https://git.company.com/team/project.git")
        assert owner == "team"
        assert repo == "project"

    def test_invalid_url_returns_none(self) -> None:
        """Invalid URL returns (None, None)."""
        owner, repo = _parse_remote_url("not-a-valid-url")
        assert owner is None
        assert repo is None

    def test_empty_string_returns_none(self) -> None:
        """Empty string returns (None, None)."""
        owner, repo = _parse_remote_url("")
        assert owner is None
        assert repo is None

    def test_partial_url_returns_none(self) -> None:
        """Partial URL without repo returns (None, None)."""
        owner, repo = _parse_remote_url("git@github.com:owner")
        assert owner is None
        assert repo is None

    def test_https_url_with_port(self) -> None:
        """HTTPS URL with port number.

        The regex pattern `[^/]+` matches the host:port combo, so this still works.
        """
        owner, repo = _parse_remote_url("https://github.com:8443/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"


class TestSshPattern:
    """Test the SSH_PATTERN regex directly."""

    def test_standard_github(self) -> None:
        """Match standard GitHub SSH URL."""
        match = SSH_PATTERN.match("git@github.com:owner/repo.git")
        assert match is not None
        assert match.group(1) == "owner"
        assert match.group(2) == "repo"

    def test_no_match_for_https(self) -> None:
        """SSH pattern does not match HTTPS URLs."""
        match = SSH_PATTERN.match("https://github.com/owner/repo.git")
        assert match is None


class TestHttpsPattern:
    """Test the HTTPS_PATTERN regex directly."""

    def test_standard_github(self) -> None:
        """Match standard GitHub HTTPS URL."""
        match = HTTPS_PATTERN.match("https://github.com/owner/repo.git")
        assert match is not None
        assert match.group(1) == "owner"
        assert match.group(2) == "repo"

    def test_no_match_for_ssh(self) -> None:
        """HTTPS pattern does not match SSH URLs."""
        match = HTTPS_PATTERN.match("git@github.com:owner/repo.git")
        assert match is None


class TestParseGitRemote:
    """Tests for parse_git_remote async function."""

    @pytest.mark.asyncio
    async def test_parse_ssh_remote(self) -> None:
        """Parse SSH remote URL successfully."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"git@github.com:owner/repo.git\n", b"")
        )
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await parse_git_remote(Path("/project"))

        assert isinstance(result, GitRemoteInfo)
        assert result.owner == "owner"
        assert result.repo == "repo"
        assert result.remote_url == "git@github.com:owner/repo.git"
        assert result.remote_name == "origin"
        assert result.full_name == "owner/repo"

    @pytest.mark.asyncio
    async def test_parse_https_remote(self) -> None:
        """Parse HTTPS remote URL successfully."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"https://github.com/org/project.git\n", b"")
        )
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await parse_git_remote(Path("/project"))

        assert result.owner == "org"
        assert result.repo == "project"
        assert result.remote_url == "https://github.com/org/project.git"
        assert result.full_name == "org/project"

    @pytest.mark.asyncio
    async def test_custom_remote_name(self) -> None:
        """Parse custom remote name."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"git@github.com:owner/repo.git\n", b"")
        )
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            result = await parse_git_remote(Path("/project"), remote_name="upstream")

        assert result.remote_name == "upstream"
        # Verify git command was called with correct remote name
        call_args = mock_exec.call_args
        assert "upstream" in call_args[0]

    @pytest.mark.asyncio
    async def test_remote_not_found(self) -> None:
        """Handle remote not found error."""
        mock_process = AsyncMock()
        mock_process.returncode = 128
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"fatal: No such remote 'origin'\n")
        )
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await parse_git_remote(Path("/project"))

        assert result.owner is None
        assert result.repo is None
        assert result.remote_url is None
        assert result.remote_name == "origin"
        assert result.full_name is None

    @pytest.mark.asyncio
    async def test_unparseable_url(self) -> None:
        """Handle unparseable remote URL."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"file:///local/repo\n", b"")
        )
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await parse_git_remote(Path("/project"))

        assert result.owner is None
        assert result.repo is None
        assert result.remote_url == "file:///local/repo"
        assert result.remote_name == "origin"

    @pytest.mark.asyncio
    async def test_empty_remote_url(self) -> None:
        """Handle empty remote URL response."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"\n", b""))
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await parse_git_remote(Path("/project"))

        assert result.owner is None
        assert result.repo is None
        assert result.remote_url is None
        assert result.remote_name == "origin"

    @pytest.mark.asyncio
    async def test_timeout_handling(self) -> None:
        """Handle git command timeout."""
        mock_process = AsyncMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=TimeoutError())

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", side_effect=TimeoutError()):
                result = await parse_git_remote(Path("/project"), timeout=0.1)

        assert result.owner is None
        assert result.repo is None
        assert result.remote_url is None
        assert result.remote_name == "origin"
        # Verify process was killed
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_git_not_found(self) -> None:
        """Handle git command not found."""
        with patch(
            "asyncio.create_subprocess_exec", side_effect=FileNotFoundError("git")
        ):
            result = await parse_git_remote(Path("/project"))

        assert result.owner is None
        assert result.repo is None
        assert result.remote_url is None
        assert result.remote_name == "origin"

    @pytest.mark.asyncio
    async def test_os_error(self) -> None:
        """Handle OS error during git execution."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=OSError("Permission denied"),
        ):
            result = await parse_git_remote(Path("/project"))

        assert result.owner is None
        assert result.repo is None
        assert result.remote_url is None
        assert result.remote_name == "origin"

    @pytest.mark.asyncio
    async def test_project_path_passed_to_subprocess(self) -> None:
        """Verify project path is passed as cwd to subprocess."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"git@github.com:owner/repo.git\n", b"")
        )
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        project_path = Path("/my/project")

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            await parse_git_remote(project_path)

        # Check that cwd was set correctly
        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs["cwd"] == project_path


class TestDefaultTimeout:
    """Test DEFAULT_TIMEOUT constant."""

    def test_default_timeout_value(self) -> None:
        """Verify default timeout is 5 seconds."""
        assert DEFAULT_TIMEOUT == 5.0
