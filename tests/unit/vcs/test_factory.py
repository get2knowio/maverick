"""Unit tests for VCS factory and protocol."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.git.repository import AsyncGitRepository
from maverick.jj.client import JjClient
from maverick.jj.repository import JjRepository
from maverick.vcs.factory import _is_jj_workspace, create_vcs_repository
from maverick.vcs.protocol import VcsRepository

# =====================================================================
# Protocol conformance
# =====================================================================


class TestVcsRepositoryProtocol:
    """Tests for VcsRepository protocol structural typing."""

    def test_jj_repository_satisfies_protocol(self, temp_dir: Path) -> None:
        mock_client = AsyncMock(spec=JjClient)
        repo = JjRepository(path=temp_dir, client=mock_client)
        assert isinstance(repo, VcsRepository)

    def test_async_git_repository_satisfies_protocol(
        self, temp_dir: Path
    ) -> None:
        with patch("maverick.git.repository.Repo"):
            repo = AsyncGitRepository(temp_dir)
        assert isinstance(repo, VcsRepository)


# =====================================================================
# _is_jj_workspace helper
# =====================================================================


class TestIsJjWorkspace:
    """Tests for the _is_jj_workspace detection helper."""

    def test_jj_only(self, temp_dir: Path) -> None:
        (temp_dir / ".jj").mkdir()
        assert _is_jj_workspace(temp_dir) is True

    def test_git_only(self, temp_dir: Path) -> None:
        (temp_dir / ".git").mkdir()
        assert _is_jj_workspace(temp_dir) is False

    def test_colocated_jj_and_git(self, temp_dir: Path) -> None:
        """Colocated repos have both .jj/ and .git/ — prefer git."""
        (temp_dir / ".jj").mkdir()
        (temp_dir / ".git").mkdir()
        assert _is_jj_workspace(temp_dir) is False

    def test_neither(self, temp_dir: Path) -> None:
        assert _is_jj_workspace(temp_dir) is False


# =====================================================================
# create_vcs_repository factory
# =====================================================================


class TestCreateVcsRepository:
    """Tests for the factory function."""

    def test_explicit_jj_backend(self, temp_dir: Path) -> None:
        repo = create_vcs_repository(temp_dir, backend="jj")
        assert isinstance(repo, JjRepository)

    def test_explicit_git_backend(self, temp_dir: Path) -> None:
        with patch("maverick.git.repository.Repo"):
            repo = create_vcs_repository(temp_dir, backend="git")
        assert isinstance(repo, AsyncGitRepository)

    def test_auto_detects_jj(self, temp_dir: Path) -> None:
        (temp_dir / ".jj").mkdir()
        repo = create_vcs_repository(temp_dir, backend="auto")
        assert isinstance(repo, JjRepository)

    def test_auto_defaults_to_git(self, temp_dir: Path) -> None:
        with patch("maverick.git.repository.Repo"):
            repo = create_vcs_repository(temp_dir, backend="auto")
        assert isinstance(repo, AsyncGitRepository)

    def test_auto_colocated_uses_git(self, temp_dir: Path) -> None:
        """Colocated repos (.jj + .git) should use git backend."""
        (temp_dir / ".jj").mkdir()
        (temp_dir / ".git").mkdir()
        with patch("maverick.git.repository.Repo"):
            repo = create_vcs_repository(temp_dir, backend="auto")
        assert isinstance(repo, AsyncGitRepository)

    def test_unknown_backend_raises(self, temp_dir: Path) -> None:
        with pytest.raises(ValueError, match="Unknown VCS backend"):
            create_vcs_repository(temp_dir, backend="svn")

    def test_factory_returns_vcs_repository(self, temp_dir: Path) -> None:
        repo = create_vcs_repository(temp_dir, backend="jj")
        assert isinstance(repo, VcsRepository)
