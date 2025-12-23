"""Unit tests for git utilities.

These tests verify the utils/git.py module which delegates to GitRunner
for actual git operations while adding error handling with GitError and
auto-recovery logic.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.exceptions import GitError
from maverick.runners.git import GitResult
from maverick.utils.git import (
    create_commit,
    get_current_branch,
    get_head_sha,
    has_uncommitted_changes,
    stage_files,
    stash_changes,
    unstash_changes,
)


def make_git_result(
    success: bool = True,
    output: str = "",
    error: str | None = None,
    duration_ms: int = 10,
) -> GitResult:
    """Create a GitResult for testing."""
    return GitResult(
        success=success,
        output=output,
        error=error,
        duration_ms=duration_ms,
    )


class TestHasUncommittedChanges:
    """Tests for has_uncommitted_changes function."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_changes(self) -> None:
        """Test returns False when no uncommitted changes."""
        mock_runner = MagicMock()
        mock_runner.is_dirty = AsyncMock(return_value=False)

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            result = await has_uncommitted_changes(Path("/repo"))

        assert result is False
        mock_runner.is_dirty.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_true_when_changes_exist(self) -> None:
        """Test returns True when uncommitted changes exist."""
        mock_runner = MagicMock()
        mock_runner.is_dirty = AsyncMock(return_value=True)

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            result = await has_uncommitted_changes(Path("/repo"))

        assert result is True


class TestStashChanges:
    """Tests for stash_changes function."""

    @pytest.mark.asyncio
    async def test_stash_changes_returns_false_when_nothing_to_stash(self) -> None:
        """Test stash_changes returns False when no changes to stash."""
        mock_runner = MagicMock()
        mock_runner.is_dirty = AsyncMock(return_value=False)

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            result = await stash_changes(Path("/repo"))

        assert result is False

    @pytest.mark.asyncio
    async def test_stash_changes_returns_true_when_stashed(self) -> None:
        """Test stash_changes returns True when changes were stashed."""
        mock_runner = MagicMock()
        mock_runner.is_dirty = AsyncMock(return_value=True)
        mock_runner.stash = AsyncMock(
            return_value=make_git_result(
                success=True, output="Saved working directory")
        )

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            result = await stash_changes(Path("/repo"))

        assert result is True
        mock_runner.stash.assert_called_once_with("maverick-auto-stash")

    @pytest.mark.asyncio
    async def test_stash_changes_uses_custom_message(self) -> None:
        """Test stash_changes uses provided message."""
        mock_runner = MagicMock()
        mock_runner.is_dirty = AsyncMock(return_value=True)
        mock_runner.stash = AsyncMock(
            return_value=make_git_result(success=True))

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            await stash_changes(Path("/repo"), message="custom-message")

        mock_runner.stash.assert_called_once_with("custom-message")

    @pytest.mark.asyncio
    async def test_stash_changes_raises_git_error_on_failure(self) -> None:
        """Test stash_changes raises GitError when stash fails."""
        mock_runner = MagicMock()
        mock_runner.is_dirty = AsyncMock(return_value=True)
        mock_runner.stash = AsyncMock(
            return_value=make_git_result(success=False, error="stash failed")
        )

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            with pytest.raises(GitError) as exc_info:
                await stash_changes(Path("/repo"))

        assert "stash" in exc_info.value.operation


class TestUnstashChanges:
    """Tests for unstash_changes function."""

    @pytest.mark.asyncio
    async def test_unstash_changes_returns_false_when_no_stash_found(self) -> None:
        """Test unstash_changes returns False when stash not found."""
        mock_runner = MagicMock()
        mock_runner.stash_pop_by_message = AsyncMock(
            return_value=make_git_result(
                success=False, error="No stash found with message: maverick-auto-stash"
            )
        )

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            result = await unstash_changes(Path("/repo"))

        assert result is False

    @pytest.mark.asyncio
    async def test_unstash_changes_returns_true_when_restored(self) -> None:
        """Test unstash_changes returns True when changes restored."""
        mock_runner = MagicMock()
        mock_runner.stash_pop_by_message = AsyncMock(
            return_value=make_git_result(
                success=True, output="Dropped stash@{0}")
        )

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            result = await unstash_changes(Path("/repo"))

        assert result is True

    @pytest.mark.asyncio
    async def test_unstash_changes_matches_custom_message(self) -> None:
        """Test unstash_changes finds stash by custom message."""
        mock_runner = MagicMock()
        mock_runner.stash_pop_by_message = AsyncMock(
            return_value=make_git_result(success=True)
        )

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            result = await unstash_changes(Path("/repo"), message="custom-stash")

        assert result is True
        mock_runner.stash_pop_by_message.assert_called_once_with(
            "custom-stash")


class TestStageFiles:
    """Tests for stage_files function."""

    @pytest.mark.asyncio
    async def test_stage_single_file(self) -> None:
        """Test staging a single file."""
        mock_runner = MagicMock()
        mock_runner.add = AsyncMock(return_value=make_git_result(success=True))

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            await stage_files(Path("/repo"), "src/file.py")

        mock_runner.add.assert_called_once()
        call_kwargs = mock_runner.add.call_args[1]
        assert "src/file.py" in call_kwargs["paths"]

    @pytest.mark.asyncio
    async def test_stage_multiple_files(self) -> None:
        """Test staging multiple files."""
        mock_runner = MagicMock()
        mock_runner.add = AsyncMock(return_value=make_git_result(success=True))

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            await stage_files(Path("/repo"), "file1.py", "file2.py", "file3.py")

        call_kwargs = mock_runner.add.call_args[1]
        assert "file1.py" in call_kwargs["paths"]
        assert "file2.py" in call_kwargs["paths"]
        assert "file3.py" in call_kwargs["paths"]

    @pytest.mark.asyncio
    async def test_stage_all_changes(self) -> None:
        """Test staging all changes with '.'."""
        mock_runner = MagicMock()
        mock_runner.add = AsyncMock(return_value=make_git_result(success=True))

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            await stage_files(Path("/repo"), ".")

        call_kwargs = mock_runner.add.call_args[1]
        assert call_kwargs["add_all"] is True

    @pytest.mark.asyncio
    async def test_stage_files_raises_git_error_on_failure(self) -> None:
        """Test stage_files raises GitError on failure."""
        mock_runner = MagicMock()
        mock_runner.add = AsyncMock(
            return_value=make_git_result(success=False, error="add failed")
        )

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            with pytest.raises(GitError) as exc_info:
                await stage_files(Path("/repo"), "file.py")

        assert exc_info.value.operation == "add"


class TestCreateCommit:
    """Tests for create_commit function."""

    @pytest.mark.asyncio
    async def test_create_commit_success(self) -> None:
        """Test successful commit creation."""
        mock_runner = MagicMock()
        mock_runner.add = AsyncMock(return_value=make_git_result(success=True))
        mock_runner.commit = AsyncMock(
            return_value=make_git_result(
                success=True, output="[main abc1234] Test commit")
        )
        mock_runner.get_head_sha = AsyncMock(return_value="abc1234567890def")

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            sha = await create_commit("Test commit", Path("/repo"))

        assert sha == "abc1234567890def"
        mock_runner.commit.assert_called_once_with("Test commit")

    @pytest.mark.asyncio
    async def test_create_commit_raises_git_error_on_failure(self) -> None:
        """Test create_commit raises GitError on failure."""
        mock_runner = MagicMock()
        mock_runner.add = AsyncMock(return_value=make_git_result(success=True))
        mock_runner.commit = AsyncMock(
            return_value=make_git_result(
                success=False, error="nothing to commit")
        )

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            with pytest.raises(GitError):
                await create_commit("Test", Path("/repo"), auto_recover=False)

    @pytest.mark.asyncio
    async def test_create_commit_recovery_on_precommit_hook_failure(self) -> None:
        """Test create_commit attempts recovery on pre-commit hook failure."""
        mock_runner = MagicMock()
        mock_runner.add = AsyncMock(return_value=make_git_result(success=True))

        # First commit attempt fails with hook error, second succeeds
        mock_runner.commit = AsyncMock(
            side_effect=[
                make_git_result(success=False, error="pre-commit hook failed"),
                make_git_result(success=True, output="[main abc1234] Test"),
            ]
        )
        mock_runner.get_head_sha = AsyncMock(return_value="abc1234")

        # Mock ruff format subprocess for recovery
        mock_ruff_process = AsyncMock()
        mock_ruff_process.communicate = AsyncMock(return_value=(b"", b""))

        with (
            patch("maverick.utils.git._get_runner", return_value=mock_runner),
            patch(
                "asyncio.create_subprocess_exec", return_value=mock_ruff_process
            ),
        ):
            sha = await create_commit("Test", Path("/repo"), auto_recover=True)

        assert sha == "abc1234"
        # Should have called commit twice (first failed, second succeeded)
        assert mock_runner.commit.call_count == 2


class TestGetHeadSha:
    """Tests for get_head_sha function."""

    @pytest.mark.asyncio
    async def test_get_head_sha_returns_sha(self) -> None:
        """Test get_head_sha returns commit SHA."""
        mock_runner = MagicMock()
        mock_runner.get_head_sha = AsyncMock(
            return_value="abc1234567890def1234567890abcdef12345678"
        )

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            sha = await get_head_sha(Path("/repo"))

        assert sha == "abc1234567890def1234567890abcdef12345678"

    @pytest.mark.asyncio
    async def test_get_head_sha_delegates_to_runner(self) -> None:
        """Test get_head_sha properly delegates to GitRunner."""
        mock_runner = MagicMock()
        mock_runner.get_head_sha = AsyncMock(return_value="abc1234")

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            await get_head_sha(Path("/repo"))

        mock_runner.get_head_sha.assert_called_once()


class TestGetCurrentBranch:
    """Tests for get_current_branch function."""

    @pytest.mark.asyncio
    async def test_get_current_branch_returns_branch_name(self) -> None:
        """Test get_current_branch returns branch name."""
        mock_runner = MagicMock()
        mock_runner.get_current_branch = AsyncMock(return_value="main")

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            branch = await get_current_branch(Path("/repo"))

        assert branch == "main"

    @pytest.mark.asyncio
    async def test_get_current_branch_handles_feature_branches(self) -> None:
        """Test get_current_branch handles feature branch names."""
        mock_runner = MagicMock()
        mock_runner.get_current_branch = AsyncMock(
            return_value="feature/new-feature")

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            branch = await get_current_branch(Path("/repo"))

        assert branch == "feature/new-feature"

    @pytest.mark.asyncio
    async def test_get_current_branch_handles_detached_head(self) -> None:
        """Test get_current_branch handles detached HEAD state."""
        mock_runner = MagicMock()
        mock_runner.get_current_branch = AsyncMock(return_value="(detached)")

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            branch = await get_current_branch(Path("/repo"))

        assert branch == "(detached)"


class TestGitErrorHandling:
    """Tests for git error handling and recovery."""

    @pytest.mark.asyncio
    async def test_git_error_is_recoverable_when_dirty(self) -> None:
        """Test git errors with 'dirty' are marked recoverable."""
        mock_runner = MagicMock()
        mock_runner.add = AsyncMock(return_value=make_git_result(success=True))
        mock_runner.commit = AsyncMock(
            return_value=make_git_result(
                success=False, error="fatal: your local changes are dirty"
            )
        )

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            with pytest.raises(GitError) as exc_info:
                await create_commit("Test", Path("/repo"), auto_recover=False)

        assert exc_info.value.recoverable is True

    @pytest.mark.asyncio
    async def test_git_error_is_not_recoverable_for_other_errors(self) -> None:
        """Test git errors without recovery patterns are not recoverable."""
        mock_runner = MagicMock()
        mock_runner.add = AsyncMock(return_value=make_git_result(success=True))
        mock_runner.commit = AsyncMock(
            return_value=make_git_result(
                success=False, error="fatal: some other error"
            )
        )

        with patch("maverick.utils.git._get_runner", return_value=mock_runner):
            with pytest.raises(GitError) as exc_info:
                await create_commit("Test", Path("/repo"), auto_recover=False)

        assert exc_info.value.recoverable is False
