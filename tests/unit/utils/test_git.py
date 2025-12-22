"""Unit tests for git utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.exceptions import GitError
from maverick.utils.git import (
    create_commit,
    get_current_branch,
    get_head_sha,
    has_uncommitted_changes,
    stage_files,
    stash_changes,
    unstash_changes,
)


class TestHasUncommittedChanges:
    """Tests for has_uncommitted_changes function."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_changes(self) -> None:
        """Test returns False when no uncommitted changes."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await has_uncommitted_changes(Path("/repo"))

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_changes_exist(self) -> None:
        """Test returns True when uncommitted changes exist."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b" M src/file.py\n", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await has_uncommitted_changes(Path("/repo"))

        assert result is True

    @pytest.mark.asyncio
    async def test_ignores_git_command_errors(self) -> None:
        """Test gracefully handles git status errors."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"error"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Should not raise, just return False (treating error as "no changes")
            result = await has_uncommitted_changes(Path("/repo"))

        assert result is False


class TestStashChanges:
    """Tests for stash_changes function."""

    @pytest.mark.asyncio
    async def test_stash_changes_returns_false_when_nothing_to_stash(self) -> None:
        """Test stash_changes returns False when no changes to stash."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await stash_changes(Path("/repo"))

        assert result is False

    @pytest.mark.asyncio
    async def test_stash_changes_returns_true_when_stashed(self) -> None:
        """Test stash_changes returns True when changes were stashed."""
        # First call to has_uncommitted_changes
        mock_status_process = AsyncMock()
        mock_status_process.communicate = AsyncMock(return_value=(b" M file.py\n", b""))
        mock_status_process.returncode = 0

        # Second call to stash push
        mock_stash_process = AsyncMock()
        mock_stash_process.communicate = AsyncMock(
            return_value=(b"Saved working directory", b"")
        )
        mock_stash_process.returncode = 0

        processes = [mock_status_process, mock_stash_process]
        call_count = [0]

        def mock_exec(*args, **kwargs):
            process = processes[call_count[0]]
            call_count[0] += 1
            return process

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await stash_changes(Path("/repo"))

        assert result is True

    @pytest.mark.asyncio
    async def test_stash_changes_uses_custom_message(self) -> None:
        """Test stash_changes uses provided message."""
        mock_status_process = AsyncMock()
        mock_status_process.communicate = AsyncMock(return_value=(b" M file.py\n", b""))
        mock_status_process.returncode = 0

        mock_stash_process = AsyncMock()
        mock_stash_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_stash_process.returncode = 0

        processes = [mock_status_process, mock_stash_process]
        call_count = [0]

        def mock_exec(*args, **kwargs):
            process = processes[call_count[0]]
            call_count[0] += 1
            return process

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec) as mock:
            await stash_changes(Path("/repo"), message="custom-message")

            # Check the stash push command includes the custom message
            stash_call = mock.call_args_list[1]
            assert "custom-message" in stash_call[0]


class TestUnstashChanges:
    """Tests for unstash_changes function."""

    @pytest.mark.asyncio
    async def test_unstash_changes_returns_false_when_no_stash_found(self) -> None:
        """Test unstash_changes returns False when stash not found."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await unstash_changes(Path("/repo"))

        assert result is False

    @pytest.mark.asyncio
    async def test_unstash_changes_returns_true_when_restored(self) -> None:
        """Test unstash_changes returns True when changes restored."""
        # First call to stash list
        mock_list_process = AsyncMock()
        mock_list_process.communicate = AsyncMock(
            return_value=(b"stash@{0}: WIP on main: maverick-auto-stash\n", b"")
        )
        mock_list_process.returncode = 0

        # Second call to stash pop
        mock_pop_process = AsyncMock()
        mock_pop_process.communicate = AsyncMock(
            return_value=(b"Dropped stash@{0}", b"")
        )
        mock_pop_process.returncode = 0

        processes = [mock_list_process, mock_pop_process]
        call_count = [0]

        def mock_exec(*args, **kwargs):
            process = processes[call_count[0]]
            call_count[0] += 1
            return process

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await unstash_changes(Path("/repo"))

        assert result is True

    @pytest.mark.asyncio
    async def test_unstash_changes_matches_custom_message(self) -> None:
        """Test unstash_changes finds stash by custom message."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"stash@{0}: WIP on main: custom-stash\n", b"")
        )
        mock_process.returncode = 0

        # Matches the message, so will try to pop
        mock_pop_process = AsyncMock()
        mock_pop_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_pop_process.returncode = 0

        processes = [mock_process, mock_pop_process]
        call_count = [0]

        def mock_exec(*args, **kwargs):
            process = processes[call_count[0]]
            call_count[0] += 1
            return process

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await unstash_changes(Path("/repo"), message="custom-stash")

        assert result is True


class TestStageFiles:
    """Tests for stage_files function."""

    @pytest.mark.asyncio
    async def test_stage_single_file(self) -> None:
        """Test staging a single file."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock:
            await stage_files(Path("/repo"), "src/file.py")

            # Verify git add was called
            mock.assert_called_once()
            call_args = mock.call_args[0]
            assert call_args[0] == "git"
            assert "add" in call_args
            assert "src/file.py" in call_args

    @pytest.mark.asyncio
    async def test_stage_multiple_files(self) -> None:
        """Test staging multiple files."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock:
            await stage_files(Path("/repo"), "file1.py", "file2.py", "file3.py")

            call_args = mock.call_args[0]
            assert "file1.py" in call_args
            assert "file2.py" in call_args
            assert "file3.py" in call_args

    @pytest.mark.asyncio
    async def test_stage_all_changes(self) -> None:
        """Test staging all changes with '.'."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock:
            await stage_files(Path("/repo"), ".")

            call_args = mock.call_args[0]
            assert "." in call_args


class TestCreateCommit:
    """Tests for create_commit function."""

    @pytest.mark.asyncio
    async def test_create_commit_success(self) -> None:
        """Test successful commit creation."""
        # Mock stage_files
        with patch(
            "maverick.utils.git.stage_files", new_callable=AsyncMock
        ) as mock_stage:
            # Mock _run_git_command for commit
            mock_commit_process = AsyncMock()
            mock_commit_process.communicate = AsyncMock(
                return_value=(b"[main abc1234] Test commit", b"")
            )
            mock_commit_process.returncode = 0

            # Mock _run_git_command for get_head_sha
            mock_sha_process = AsyncMock()
            mock_sha_process.communicate = AsyncMock(
                return_value=(b"abc1234567890def", b"")
            )
            mock_sha_process.returncode = 0

            processes = [mock_commit_process, mock_sha_process]
            call_count = [0]

            def mock_exec(*args, **kwargs):
                process = processes[call_count[0]]
                call_count[0] += 1
                return process

            with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
                sha = await create_commit("Test commit", Path("/repo"))

            assert sha == "abc1234567890def"
            mock_stage.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_commit_raises_git_error_on_failure(self) -> None:
        """Test create_commit raises GitError on failure."""
        with patch("maverick.utils.git.stage_files", new_callable=AsyncMock):
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(
                return_value=(b"", b"nothing to commit")
            )
            mock_process.returncode = 1

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                with pytest.raises(GitError):
                    await create_commit("Test", Path("/repo"), auto_recover=False)

    @pytest.mark.asyncio
    async def test_create_commit_recovery_on_precommit_hook_failure(self) -> None:
        """Test create_commit attempts recovery on pre-commit hook failure."""
        # First attempt fails with hook error
        mock_fail_process = AsyncMock()
        mock_fail_process.communicate = AsyncMock(
            return_value=(b"", b"pre-commit hook failed")
        )
        mock_fail_process.returncode = 1

        # Recovery runs ruff format
        mock_ruff_process = AsyncMock()
        mock_ruff_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_ruff_process.returncode = 0

        # Second attempt succeeds
        mock_success_process = AsyncMock()
        mock_success_process.communicate = AsyncMock(
            return_value=(b"[main abc1234] Test", b"")
        )
        mock_success_process.returncode = 0

        # SHA retrieval
        mock_sha_process = AsyncMock()
        mock_sha_process.communicate = AsyncMock(return_value=(b"abc1234", b""))
        mock_sha_process.returncode = 0

        with patch("maverick.utils.git.stage_files", new_callable=AsyncMock):
            processes = [
                mock_fail_process,
                mock_ruff_process,
                mock_success_process,
                mock_sha_process,
            ]
            call_count = [0]

            def mock_exec(*args, **kwargs):
                process = processes[call_count[0]]
                call_count[0] += 1
                return process

            with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
                # Should succeed after recovery
                sha = await create_commit("Test", Path("/repo"), auto_recover=True)
                assert sha == "abc1234"


class TestGetHeadSha:
    """Tests for get_head_sha function."""

    @pytest.mark.asyncio
    async def test_get_head_sha_returns_sha(self) -> None:
        """Test get_head_sha returns commit SHA."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"abc1234567890def1234567890abcdef12345678\n", b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            sha = await get_head_sha(Path("/repo"))

        assert sha == "abc1234567890def1234567890abcdef12345678"

    @pytest.mark.asyncio
    async def test_get_head_sha_strips_whitespace(self) -> None:
        """Test get_head_sha strips whitespace from output."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"  abc1234  \n\n", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            sha = await get_head_sha(Path("/repo"))

        assert sha == "abc1234"


class TestGetCurrentBranch:
    """Tests for get_current_branch function."""

    @pytest.mark.asyncio
    async def test_get_current_branch_returns_branch_name(self) -> None:
        """Test get_current_branch returns branch name."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"main\n", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            branch = await get_current_branch(Path("/repo"))

        assert branch == "main"

    @pytest.mark.asyncio
    async def test_get_current_branch_handles_feature_branches(self) -> None:
        """Test get_current_branch handles feature branch names."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"feature/new-feature\n", b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            branch = await get_current_branch(Path("/repo"))

        assert branch == "feature/new-feature"

    @pytest.mark.asyncio
    async def test_get_current_branch_strips_whitespace(self) -> None:
        """Test get_current_branch strips whitespace."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"  main  \n", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            branch = await get_current_branch(Path("/repo"))

        assert branch == "main"


class TestGitErrorHandling:
    """Tests for git error handling and recovery."""

    @pytest.mark.asyncio
    async def test_git_error_is_recoverable_when_dirty(self) -> None:
        """Test git errors with 'dirty' are marked recoverable."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"fatal: your local changes are dirty")
        )
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(GitError) as exc_info:
                await create_commit("Test", Path("/repo"), auto_recover=False)

            assert exc_info.value.recoverable is True

    @pytest.mark.asyncio
    async def test_git_error_is_not_recoverable_for_other_errors(self) -> None:
        """Test git errors without recovery patterns are not recoverable."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"fatal: some other error")
        )
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(GitError) as exc_info:
                await create_commit("Test", Path("/repo"), auto_recover=False)

            assert exc_info.value.recoverable is False
