"""Unit tests for git actions.

Tests the git.py action module including:
- git_commit action with message and add_all options
- git_push action with set_upstream option
- create_git_branch action with base branch
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maverick.library.actions.git import (
    create_git_branch,
    git_check_and_stage,
    git_commit,
    git_merge,
    git_push,
    git_stage_all,
)


def create_mock_process(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> MagicMock:
    """Create a mock subprocess with configured return values."""
    mock_proc = MagicMock()
    mock_proc.returncode = returncode
    mock_proc.stdout = MagicMock()
    mock_proc.stderr = MagicMock()

    # For communicate()
    async def mock_communicate():
        return (stdout.encode(), stderr.encode())

    mock_proc.communicate = mock_communicate

    # For wait()
    async def mock_wait():
        return returncode

    mock_proc.wait = mock_wait

    # For reading stderr directly
    async def mock_read_stderr():
        return stderr.encode()

    mock_proc.stderr.read = mock_read_stderr

    return mock_proc


class TestGitCommit:
    """Tests for git_commit action."""

    @pytest.mark.asyncio
    async def test_creates_commit_with_message(self) -> None:
        """Test creates commit with provided message."""
        message = "feat: add new feature"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # git add .
                create_mock_process(0),  # git commit
                create_mock_process(0, stdout="abc123def456\n"),  # git rev-parse HEAD
                create_mock_process(0, stdout="file1.py\nfile2.py\n"),  # git diff-tree
            ]

            result = await git_commit(message)

            assert result["success"] is True
            assert result["commit_sha"] == "abc123def456"
            assert result["message"] == message
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_stages_all_changes_when_add_all_true(self) -> None:
        """Test stages all changes with 'git add .' when add_all=True."""
        message = "fix: bug fix"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # git add .
                create_mock_process(0),  # git commit
                create_mock_process(0, stdout="sha123\n"),  # git rev-parse HEAD
                create_mock_process(0, stdout=""),  # git diff-tree
            ]

            result = await git_commit(message, add_all=True)

            assert result["success"] is True

            # Verify git add . was called
            add_call = mock_exec.call_args_list[0]
            assert add_call[0] == ("git", "add", ".")

    @pytest.mark.asyncio
    async def test_skips_staging_when_add_all_false(self) -> None:
        """Test skips 'git add .' when add_all=False."""
        message = "chore: cleanup"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # git commit (no add)
                create_mock_process(0, stdout="sha456\n"),  # git rev-parse HEAD
                create_mock_process(0, stdout=""),  # git diff-tree
            ]

            result = await git_commit(message, add_all=False)

            assert result["success"] is True

            # Verify first call is git commit, not git add
            first_call = mock_exec.call_args_list[0]
            assert first_call[0][0:2] == ("git", "commit")

    @pytest.mark.asyncio
    async def test_includes_attribution_by_default(self) -> None:
        """Test includes Claude attribution by default."""
        message = "feat: new feature"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # git add .
                create_mock_process(0),  # git commit
                create_mock_process(0, stdout="sha789\n"),  # git rev-parse HEAD
                create_mock_process(0, stdout=""),  # git diff-tree
            ]

            result = await git_commit(message)

            assert result["success"] is True

            # Check commit call includes attribution
            commit_call = mock_exec.call_args_list[1]
            commit_message = commit_call[0][3]  # git commit -m MESSAGE
            assert "Generated with Claude Code" in commit_message
            assert "Co-Authored-By: Claude" in commit_message

    @pytest.mark.asyncio
    async def test_excludes_attribution_when_disabled(self) -> None:
        """Test excludes attribution when include_attribution=False."""
        message = "fix: bug fix"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # git add .
                create_mock_process(0),  # git commit
                create_mock_process(0, stdout="sha999\n"),  # git rev-parse HEAD
                create_mock_process(0, stdout=""),  # git diff-tree
            ]

            result = await git_commit(message, include_attribution=False)

            assert result["success"] is True

            # Check commit call does NOT include attribution
            commit_call = mock_exec.call_args_list[1]
            commit_message = commit_call[0][3]  # git commit -m MESSAGE
            assert commit_message == message
            assert "Claude" not in commit_message

    @pytest.mark.asyncio
    async def test_returns_commit_sha(self) -> None:
        """Test returns commit SHA from git rev-parse HEAD."""
        message = "test: add tests"
        expected_sha = "1a2b3c4d5e6f"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # git add .
                create_mock_process(0),  # git commit
                create_mock_process(
                    0, stdout=f"{expected_sha}\n"
                ),  # git rev-parse HEAD
                create_mock_process(0, stdout=""),  # git diff-tree
            ]

            result = await git_commit(message)

            assert result["commit_sha"] == expected_sha

    @pytest.mark.asyncio
    async def test_returns_files_committed(self) -> None:
        """Test returns list of files committed."""
        message = "feat: update files"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # git add .
                create_mock_process(0),  # git commit
                create_mock_process(0, stdout="sha\n"),  # git rev-parse HEAD
                create_mock_process(
                    0, stdout="src/file1.py\nsrc/file2.py\ntests/test.py\n"
                ),
            ]

            result = await git_commit(message)

            assert result["files_committed"] == (
                "src/file1.py",
                "src/file2.py",
                "tests/test.py",
            )

    @pytest.mark.asyncio
    async def test_handles_empty_commit(self) -> None:
        """Test handles commit with no files changed."""
        message = "chore: update"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # git add .
                create_mock_process(0),  # git commit
                create_mock_process(0, stdout="sha\n"),  # git rev-parse HEAD
                create_mock_process(0, stdout=""),  # git diff-tree (empty)
            ]

            result = await git_commit(message)

            assert result["files_committed"] == ()

    @pytest.mark.asyncio
    async def test_handles_git_commit_failure(self) -> None:
        """Test handles git commit command failure gracefully."""
        message = "feat: new feature"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # git add .
                create_mock_process(
                    1, stderr="fatal: nothing to commit"
                ),  # git commit fails
            ]

            result = await git_commit(message)

            assert result["success"] is False
            assert result["commit_sha"] is None
            assert result["message"] == message
            assert result["files_committed"] == ()
            assert result["error"] is not None


class TestGitPush:
    """Tests for git_push action."""

    @pytest.mark.asyncio
    async def test_pushes_current_branch(self) -> None:
        """Test pushes current branch to origin."""
        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(
                    0, stdout="feature/test\n"
                ),  # git rev-parse --abbrev-ref HEAD
                create_mock_process(0),  # git push
            ]

            result = await git_push()

            assert result["success"] is True
            assert result["branch"] == "feature/test"
            assert result["remote"] == "origin"
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_sets_upstream_by_default(self) -> None:
        """Test sets upstream tracking by default."""
        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(
                    0, stdout="main\n"
                ),  # git rev-parse --abbrev-ref HEAD
                create_mock_process(0),  # git push
            ]

            result = await git_push()

            assert result["success"] is True
            assert result["upstream_set"] is True

            # Verify push command includes -u flag
            push_call = mock_exec.call_args_list[1]
            assert push_call[0] == ("git", "push", "-u", "origin", "main")

    @pytest.mark.asyncio
    async def test_skips_upstream_when_set_upstream_false(self) -> None:
        """Test skips upstream flag when set_upstream=False."""
        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="feature/branch\n"),  # git rev-parse
                create_mock_process(0),  # git push
            ]

            result = await git_push(set_upstream=False)

            assert result["success"] is True
            assert result["upstream_set"] is False

            # Verify push command does NOT include -u flag
            push_call = mock_exec.call_args_list[1]
            assert push_call[0] == ("git", "push", "origin", "feature/branch")

    @pytest.mark.asyncio
    async def test_handles_push_failure(self) -> None:
        """Test handles git push command failure gracefully."""
        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="main\n"),  # git rev-parse
                create_mock_process(
                    1, stderr="fatal: remote rejected"
                ),  # git push fails
            ]

            result = await git_push()

            assert result["success"] is False
            assert result["upstream_set"] is False
            assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_handles_branch_name_retrieval_failure(self) -> None:
        """Test handles failure to get current branch name."""
        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(128, stderr="fatal: not a git repository"),
            ]

            result = await git_push()

            assert result["success"] is False
            assert result["branch"] == ""
            assert result["error"] is not None


class TestCreateGitBranch:
    """Tests for create_git_branch action."""

    @pytest.mark.asyncio
    async def test_creates_new_branch_when_does_not_exist(self) -> None:
        """Test creates new branch when it doesn't exist."""
        branch_name = "feature/new"
        base = "main"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1),  # git rev-parse (branch doesn't exist)
                create_mock_process(0),  # git checkout base
                create_mock_process(0),  # git checkout -b branch_name
            ]

            result = await create_git_branch(branch_name, base)

            assert result["success"] is True
            assert result["branch_name"] == branch_name
            assert result["base_branch"] == base
            assert result["created"] is True
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_checks_out_existing_branch(self) -> None:
        """Test checks out existing branch instead of creating."""
        branch_name = "feature/existing"
        base = "main"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # git rev-parse (branch exists)
                create_mock_process(0),  # git checkout branch_name
            ]

            result = await create_git_branch(branch_name, base)

            assert result["success"] is True
            assert result["branch_name"] == branch_name
            assert result["created"] is False

            # Verify only checkout was called, not checkout -b
            assert mock_exec.call_count == 2
            checkout_call = mock_exec.call_args_list[1]
            assert checkout_call[0] == ("git", "checkout", branch_name)

    @pytest.mark.asyncio
    async def test_uses_default_base_branch(self) -> None:
        """Test uses 'main' as default base branch."""
        branch_name = "feature/test"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1),  # Branch doesn't exist
                create_mock_process(0),  # git checkout main
                create_mock_process(0),  # git checkout -b
            ]

            result = await create_git_branch(branch_name)

            assert result["success"] is True
            assert result["base_branch"] == "main"

            # Verify checkout main was called
            checkout_base_call = mock_exec.call_args_list[1]
            assert checkout_base_call[0] == ("git", "checkout", "main")

    @pytest.mark.asyncio
    async def test_uses_custom_base_branch(self) -> None:
        """Test uses custom base branch when provided."""
        branch_name = "feature/test"
        base = "develop"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1),  # Branch doesn't exist
                create_mock_process(0),  # git checkout develop
                create_mock_process(0),  # git checkout -b
            ]

            result = await create_git_branch(branch_name, base)

            assert result["success"] is True
            assert result["base_branch"] == "develop"

            # Verify checkout develop was called
            checkout_base_call = mock_exec.call_args_list[1]
            assert checkout_base_call[0] == ("git", "checkout", "develop")

    @pytest.mark.asyncio
    async def test_creates_branch_from_base(self) -> None:
        """Test creates new branch from specified base."""
        branch_name = "feature/new-feature"
        base = "main"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1),  # Branch doesn't exist
                create_mock_process(0),  # git checkout base
                create_mock_process(0),  # git checkout -b branch_name
            ]

            result = await create_git_branch(branch_name, base)

            assert result["success"] is True
            assert result["created"] is True

            # Verify sequence: checkout base, then checkout -b new branch
            checkout_base_call = mock_exec.call_args_list[1]
            assert checkout_base_call[0] == ("git", "checkout", base)

            create_branch_call = mock_exec.call_args_list[2]
            assert create_branch_call[0] == ("git", "checkout", "-b", branch_name)

    @pytest.mark.asyncio
    async def test_handles_checkout_failure(self) -> None:
        """Test handles git checkout failure gracefully."""
        branch_name = "feature/test"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1),  # Branch doesn't exist
                create_mock_process(0),  # git checkout main
                create_mock_process(
                    1, stderr="fatal: invalid reference"
                ),  # checkout -b fails
            ]

            result = await create_git_branch(branch_name)

            assert result["success"] is False
            assert result["created"] is False
            assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_handles_base_branch_checkout_failure(self) -> None:
        """Test handles failure when checking out base branch."""
        branch_name = "feature/test"
        base = "nonexistent"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1),  # Branch doesn't exist
                create_mock_process(
                    1, stderr=f"error: pathspec '{base}' did not match"
                ),
            ]

            result = await create_git_branch(branch_name, base)

            assert result["success"] is False
            assert result["created"] is False
            assert result["error"] is not None


class TestGitStageAll:
    """Tests for git_stage_all action."""

    @pytest.mark.asyncio
    async def test_stages_all_changes(self) -> None:
        """Test stages all changes with 'git add .'."""
        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # git add .
            ]

            result = await git_stage_all()

            assert result["success"] is True
            assert result["error"] is None

            # Verify git add . was called
            add_call = mock_exec.call_args_list[0]
            assert add_call[0] == ("git", "add", ".")

    @pytest.mark.asyncio
    async def test_handles_staging_failure(self) -> None:
        """Test handles git add failure gracefully."""
        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr="fatal: not a git repository"),
            ]

            result = await git_stage_all()

            assert result["success"] is False
            assert result["error"] is not None


class TestGitCheckAndStage:
    """Tests for git_check_and_stage action."""

    @pytest.mark.asyncio
    async def test_checks_and_stages_when_changes_exist(self) -> None:
        """Test detects changes and stages them in one call."""
        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                # git_has_changes: git diff --cached --quiet (has staged)
                create_mock_process(1),
                # git_has_changes: git diff --quiet (no unstaged)
                create_mock_process(0),
                # git_has_changes: git ls-files --others (no untracked)
                create_mock_process(0, stdout=""),
                # git_stage_all: git add .
                create_mock_process(0),
            ]

            result = await git_check_and_stage()

            assert result["has_any"] is True
            assert result["has_staged"] is True
            # Verify git add . was called (4th subprocess call)
            assert mock_exec.call_count == 4
            add_call = mock_exec.call_args_list[3]
            assert add_call[0] == ("git", "add", ".")

    @pytest.mark.asyncio
    async def test_returns_change_status_fields(self) -> None:
        """Test returns all expected status fields."""
        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # no staged
                create_mock_process(1),  # has unstaged
                create_mock_process(0, stdout="new_file.py\n"),  # has untracked
                create_mock_process(0),  # git add .
            ]

            result = await git_check_and_stage()

            assert result["has_staged"] is False
            assert result["has_unstaged"] is True
            assert result["has_untracked"] is True
            assert result["has_any"] is True

    @pytest.mark.asyncio
    async def test_skips_staging_when_no_changes(self) -> None:
        """Test skips staging when no changes detected."""
        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # no staged
                create_mock_process(0),  # no unstaged
                create_mock_process(0, stdout=""),  # no untracked
                # No git add . call expected
            ]

            result = await git_check_and_stage()

            assert result["has_any"] is False
            # Only 3 calls (the 3 checks), no staging call
            assert mock_exec.call_count == 3

    @pytest.mark.asyncio
    async def test_handles_staging_failure(self) -> None:
        """Test returns status even when staging fails."""
        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1),  # has staged
                create_mock_process(0),  # no unstaged
                create_mock_process(0, stdout=""),  # no untracked
                create_mock_process(
                    1, stderr="fatal: staging error"
                ),  # git add . fails
            ]

            result = await git_check_and_stage()

            # Should still return the status, even though staging failed
            assert result["has_any"] is True
            assert result["has_staged"] is True


class TestGitMerge:
    """Tests for git_merge action."""

    @pytest.mark.asyncio
    async def test_merges_branch_successfully(self) -> None:
        """Test merges a branch into current branch."""
        branch = "feature/test"
        merge_sha = "abc123merge"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="Merge made\n"),  # git merge
                create_mock_process(0, stdout=f"{merge_sha}\n"),  # git rev-parse HEAD
            ]

            result = await git_merge(branch)

            assert result["success"] is True
            assert result["branch"] == branch
            assert result["merge_commit"] == merge_sha
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_merge_uses_no_ff_flag(self) -> None:
        """Test passes --no-ff flag when requested."""
        branch = "feature/no-ff"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="Merge made\n"),  # git merge --no-ff
                create_mock_process(0, stdout="sha456\n"),  # git rev-parse HEAD
            ]

            result = await git_merge(branch, no_ff=True)

            assert result["success"] is True

            # Verify --no-ff was passed
            merge_call = mock_exec.call_args_list[0]
            assert merge_call[0] == ("git", "merge", "--no-ff", branch)

    @pytest.mark.asyncio
    async def test_merge_without_no_ff(self) -> None:
        """Test does not pass --no-ff by default."""
        branch = "feature/fast-forward"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="Fast-forward\n"),  # git merge
                create_mock_process(0, stdout="sha789\n"),  # git rev-parse HEAD
            ]

            result = await git_merge(branch)

            assert result["success"] is True

            # Verify --no-ff was NOT passed
            merge_call = mock_exec.call_args_list[0]
            assert merge_call[0] == ("git", "merge", branch)

    @pytest.mark.asyncio
    async def test_handles_merge_conflict(self) -> None:
        """Test handles merge failure (e.g., conflict) gracefully."""
        branch = "feature/conflict"

        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(
                    1, stderr="CONFLICT (content): Merge conflict in file.py"
                ),
            ]

            result = await git_merge(branch)

            assert result["success"] is False
            assert result["branch"] == branch
            assert result["merge_commit"] is None
            assert result["error"] is not None
            assert "CONFLICT" in result["error"]

    @pytest.mark.asyncio
    async def test_handles_os_error(self) -> None:
        """Test handles OSError (e.g., git not found) gracefully."""
        with patch(
            "maverick.library.actions.git.asyncio.create_subprocess_exec"
        ) as mock_exec:
            mock_exec.side_effect = OSError("git not found")

            result = await git_merge("some-branch")

            assert result["success"] is False
            assert result["merge_commit"] is None
            assert result["error"] is not None
