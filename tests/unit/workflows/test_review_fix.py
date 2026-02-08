"""Tests for review_fix._get_repo_name.

Validates that _get_repo_name uses AsyncGitRepository (not raw subprocess)
and correctly parses GitHub remote URLs to owner/repo format.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.workflows.review_fix import _get_repo_name


class TestGetRepoName:
    """Tests for _get_repo_name helper."""

    @pytest.mark.asyncio
    async def test_parses_https_url(self) -> None:
        """Test _get_repo_name parses HTTPS GitHub URL correctly."""
        mock_repo = AsyncMock()
        mock_repo.get_remote_url = AsyncMock(
            return_value="https://github.com/owner/repo.git"
        )

        with patch(
            "maverick.git.AsyncGitRepository",
            return_value=mock_repo,
        ) as mock_cls:
            result = await _get_repo_name(Path("/fake/path"))

        assert result == "owner/repo"
        mock_cls.assert_called_once_with(Path("/fake/path"))
        mock_repo.get_remote_url.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_parses_https_url_without_dot_git(self) -> None:
        """Test _get_repo_name parses HTTPS URL without .git suffix."""
        mock_repo = AsyncMock()
        mock_repo.get_remote_url = AsyncMock(
            return_value="https://github.com/owner/repo"
        )

        with patch(
            "maverick.git.AsyncGitRepository",
            return_value=mock_repo,
        ):
            result = await _get_repo_name(Path("/fake/path"))

        assert result == "owner/repo"

    @pytest.mark.asyncio
    async def test_parses_ssh_url(self) -> None:
        """Test _get_repo_name parses SSH GitHub URL correctly."""
        mock_repo = AsyncMock()
        mock_repo.get_remote_url = AsyncMock(
            return_value="git@github.com:owner/repo.git"
        )

        with patch(
            "maverick.git.AsyncGitRepository",
            return_value=mock_repo,
        ):
            result = await _get_repo_name(Path("/fake/path"))

        assert result == "owner/repo"

    @pytest.mark.asyncio
    async def test_parses_ssh_url_without_dot_git(self) -> None:
        """Test _get_repo_name parses SSH URL without .git suffix."""
        mock_repo = AsyncMock()
        mock_repo.get_remote_url = AsyncMock(return_value="git@github.com:owner/repo")

        with patch(
            "maverick.git.AsyncGitRepository",
            return_value=mock_repo,
        ):
            result = await _get_repo_name(Path("/fake/path"))

        assert result == "owner/repo"

    @pytest.mark.asyncio
    async def test_raises_when_no_remote(self) -> None:
        """Test _get_repo_name raises ValueError when remote URL is None."""
        mock_repo = AsyncMock()
        mock_repo.get_remote_url = AsyncMock(return_value=None)

        with (
            patch(
                "maverick.git.AsyncGitRepository",
                return_value=mock_repo,
            ),
            pytest.raises(ValueError, match="Failed to get git remote URL"),
        ):
            await _get_repo_name(Path("/fake/path"))

    @pytest.mark.asyncio
    async def test_raises_for_unparseable_url(self) -> None:
        """Test _get_repo_name raises ValueError for non-GitHub URLs."""
        mock_repo = AsyncMock()
        mock_repo.get_remote_url = AsyncMock(
            return_value="https://gitlab.com/owner/repo.git"
        )

        with (
            patch(
                "maverick.git.AsyncGitRepository",
                return_value=mock_repo,
            ),
            pytest.raises(ValueError, match="Could not parse repo name from URL"),
        ):
            await _get_repo_name(Path("/fake/path"))

    @pytest.mark.asyncio
    async def test_uses_async_git_repository_not_subprocess(self) -> None:
        """Test _get_repo_name uses AsyncGitRepository, not raw subprocess.

        This is the key test for issue #38: ensuring Architectural Guardrail #6
        is satisfied.
        """
        mock_repo = AsyncMock()
        mock_repo.get_remote_url = AsyncMock(
            return_value="https://github.com/get2knowio/maverick.git"
        )

        with patch(
            "maverick.git.AsyncGitRepository",
            return_value=mock_repo,
        ) as mock_cls:
            result = await _get_repo_name(Path("/fake/path"))

        # Verify AsyncGitRepository was used
        mock_cls.assert_called_once_with(Path("/fake/path"))
        mock_repo.get_remote_url.assert_awaited_once()
        assert result == "get2knowio/maverick"
