"""Unit tests for jj (Jujutsu) actions.

Tests the jj.py action module including:
- git_has_changes (jj diff --stat)
- git_stage_all (no-op)
- git_add (no-op / jj file track)
- git_check_and_stage (delegates to git_has_changes)
- git_commit (jj describe + jj new)
- git_push (jj git push)
- git_merge (jj new @ <branch>)
- create_git_branch (jj bookmark)
- jj_describe
- jj_snapshot_operation / jj_restore_operation
- jj_squash / jj_absorb
- jj_log / jj_diff
- curate_history
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maverick.library.actions.jj import (
    create_git_branch,
    curate_history,
    git_add,
    git_check_and_stage,
    git_commit,
    git_has_changes,
    git_merge,
    git_push,
    git_stage_all,
    jj_absorb,
    jj_describe,
    jj_diff,
    jj_log,
    jj_restore_operation,
    jj_snapshot_operation,
    jj_squash,
)

MOCK_TARGET = "maverick.library.actions.jj.asyncio.create_subprocess_exec"


def create_mock_process(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> MagicMock:
    """Create a mock subprocess with configured return values."""
    mock_proc = MagicMock()
    mock_proc.returncode = returncode
    mock_proc.stdout = MagicMock()
    mock_proc.stderr = MagicMock()

    async def mock_communicate():
        return (stdout.encode(), stderr.encode())

    mock_proc.communicate = mock_communicate

    async def mock_wait():
        return returncode

    mock_proc.wait = mock_wait

    async def mock_read_stderr():
        return stderr.encode()

    mock_proc.stderr.read = mock_read_stderr

    return mock_proc


class TestGitHasChanges:
    """Tests for git_has_changes action (jj diff --stat)."""

    @pytest.mark.asyncio
    async def test_detects_changes(self) -> None:
        """Test detects changes via non-empty jj diff --stat."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="file.py | 2 +-\n1 file changed\n"),
            ]

            result = await git_has_changes()

            assert result["has_any"] is True
            assert result["has_staged"] is False  # always False in jj
            assert result["has_unstaged"] is True
            assert result["has_untracked"] is True

    @pytest.mark.asyncio
    async def test_detects_no_changes(self) -> None:
        """Test detects no changes via empty jj diff --stat."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout=""),
            ]

            result = await git_has_changes()

            assert result["has_any"] is False
            assert result["has_staged"] is False
            assert result["has_unstaged"] is False
            assert result["has_untracked"] is False

    @pytest.mark.asyncio
    async def test_handles_error(self) -> None:
        """Test assumes changes exist on error."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = OSError("jj not found")

            result = await git_has_changes()

            assert result["has_any"] is True


class TestGitStageAll:
    """Tests for git_stage_all action (no-op in jj)."""

    @pytest.mark.asyncio
    async def test_is_noop(self) -> None:
        """Test is a no-op that always succeeds."""
        result = await git_stage_all()

        assert result["success"] is True
        assert result["error"] is None


class TestGitCheckAndStage:
    """Tests for git_check_and_stage action."""

    @pytest.mark.asyncio
    async def test_delegates_to_has_changes(self) -> None:
        """Test delegates to git_has_changes without staging."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="file.py | 2 +-\n"),
            ]

            result = await git_check_and_stage()

            assert result["has_any"] is True
            # Only 1 call (jj diff --stat), no staging call
            assert mock_exec.call_count == 1

    @pytest.mark.asyncio
    async def test_no_changes(self) -> None:
        """Test returns no changes when working copy is clean."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout=""),
            ]

            result = await git_check_and_stage()

            assert result["has_any"] is False


class TestGitAdd:
    """Tests for git_add action."""

    @pytest.mark.asyncio
    async def test_noop_without_force(self) -> None:
        """Test is a no-op when force=False."""
        result = await git_add(paths=["file.py"])

        assert result["success"] is True
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_tracks_with_force(self) -> None:
        """Test uses jj file track when force=True."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [create_mock_process(0)]

            result = await git_add(paths=[".beads/issues.jsonl"], force=True)

            assert result["success"] is True
            call_args = mock_exec.call_args_list[0][0]
            assert call_args == ("jj", "file", "track", ".beads/issues.jsonl")

    @pytest.mark.asyncio
    async def test_force_default_paths(self) -> None:
        """Test uses '.' as default path with force."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [create_mock_process(0)]

            result = await git_add(force=True)

            assert result["success"] is True
            call_args = mock_exec.call_args_list[0][0]
            assert call_args == ("jj", "file", "track", ".")

    @pytest.mark.asyncio
    async def test_force_failure(self) -> None:
        """Test handles jj file track failure."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr="error: no such file")
            ]

            result = await git_add(paths=["missing.txt"], force=True)

            assert result["success"] is False
            assert result["error"] is not None


class TestGitCommit:
    """Tests for git_commit action (jj describe + new)."""

    @pytest.mark.asyncio
    async def test_creates_commit_with_message(self) -> None:
        """Test creates commit via jj describe + jj new."""
        message = "feat: add new feature"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="file.py | 2 +-\n"),  # jj diff --stat
                create_mock_process(0),  # jj describe
                create_mock_process(0),  # jj new
                create_mock_process(0, stdout="abc123def456\n"),  # jj log -r @-
                create_mock_process(0, stdout="M src/file.py\n"),  # jj diff -r @-
            ]

            result = await git_commit(message)

            assert result["success"] is True
            assert result["commit_sha"] == "abc123def456"
            assert result["message"] == message
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_includes_attribution_by_default(self) -> None:
        """Test includes Claude attribution by default."""
        message = "feat: new feature"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="file.py | 1 +\n"),  # jj diff --stat
                create_mock_process(0),  # jj describe
                create_mock_process(0),  # jj new
                create_mock_process(0, stdout="sha789\n"),  # jj log
                create_mock_process(0, stdout=""),  # jj diff
            ]

            result = await git_commit(message)

            assert result["success"] is True

            # Check describe call includes attribution
            describe_call = mock_exec.call_args_list[1]
            describe_message = describe_call[0][3]  # jj describe -m MESSAGE
            assert "Generated with Claude Code" in describe_message
            assert "Co-Authored-By: Claude" in describe_message

    @pytest.mark.asyncio
    async def test_excludes_attribution_when_disabled(self) -> None:
        """Test excludes attribution when include_attribution=False."""
        message = "fix: bug fix"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="file.py | 1 +\n"),  # jj diff --stat
                create_mock_process(0),  # jj describe
                create_mock_process(0),  # jj new
                create_mock_process(0, stdout="sha999\n"),  # jj log
                create_mock_process(0, stdout=""),  # jj diff
            ]

            result = await git_commit(message, include_attribution=False)

            assert result["success"] is True

            # Check describe call does NOT include attribution
            describe_call = mock_exec.call_args_list[1]
            describe_message = describe_call[0][3]
            assert describe_message == message
            assert "Claude" not in describe_message

    @pytest.mark.asyncio
    async def test_handles_nothing_to_commit(self) -> None:
        """Test returns nothing_to_commit when diff is empty."""
        message = "feat: new feature"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout=""),  # jj diff --stat (empty)
            ]

            result = await git_commit(message)

            assert result["success"] is True
            assert result["commit_sha"] is None
            assert result["nothing_to_commit"] is True
            assert result["message"] == message

    @pytest.mark.asyncio
    async def test_returns_files_committed(self) -> None:
        """Test returns list of files committed."""
        message = "feat: update files"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="3 files\n"),  # jj diff --stat
                create_mock_process(0),  # jj describe
                create_mock_process(0),  # jj new
                create_mock_process(0, stdout="sha\n"),  # jj log
                create_mock_process(
                    0, stdout="M src/file1.py\nA src/file2.py\nM tests/test.py\n"
                ),  # jj diff --summary
            ]

            result = await git_commit(message)

            assert result["files_committed"] == (
                "src/file1.py",
                "src/file2.py",
                "tests/test.py",
            )

    @pytest.mark.asyncio
    async def test_handles_describe_failure(self) -> None:
        """Test handles jj describe failure."""
        message = "feat: new feature"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="file.py | 1 +\n"),  # jj diff --stat
                create_mock_process(
                    1, stderr="error: could not describe"
                ),  # jj describe
            ]

            result = await git_commit(message)

            assert result["success"] is False
            assert result["commit_sha"] is None
            assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_handles_empty_files_list(self) -> None:
        """Test handles commit with no files in diff summary."""
        message = "chore: update"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="1 file\n"),  # jj diff --stat
                create_mock_process(0),  # jj describe
                create_mock_process(0),  # jj new
                create_mock_process(0, stdout="sha\n"),  # jj log
                create_mock_process(0, stdout=""),  # jj diff --summary (empty)
            ]

            result = await git_commit(message)

            assert result["files_committed"] == ()


class TestGitPush:
    """Tests for git_push action (jj git push)."""

    @pytest.mark.asyncio
    async def test_pushes_current_bookmark(self) -> None:
        """Test pushes current bookmark to origin."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="feature/test\n"),  # jj log bookmarks
                create_mock_process(0),  # jj git push
            ]

            result = await git_push()

            assert result["success"] is True
            assert result["branch"] == "feature/test"
            assert result["remote"] == "origin"
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_handles_bookmark_with_remote_suffix(self) -> None:
        """Test strips @origin suffix from bookmark name."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="main@origin\n"),  # jj log bookmarks
                create_mock_process(0),  # jj git push
            ]

            result = await git_push()

            assert result["success"] is True
            assert result["branch"] == "main"

    @pytest.mark.asyncio
    async def test_handles_no_bookmark(self) -> None:
        """Test handles missing bookmark."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout=""),  # jj log bookmarks (empty)
            ]

            result = await git_push()

            assert result["success"] is False
            assert result["branch"] == ""
            assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_handles_push_failure(self) -> None:
        """Test handles jj git push failure."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="main\n"),  # jj log bookmarks
                create_mock_process(1, stderr="error: push rejected"),  # jj git push
            ]

            result = await git_push()

            assert result["success"] is False
            assert result["upstream_set"] is False
            assert result["error"] is not None


class TestGitMerge:
    """Tests for git_merge action (jj new @ <branch>)."""

    @pytest.mark.asyncio
    async def test_merges_branch_successfully(self) -> None:
        """Test merges a branch via jj new with two parents."""
        branch = "feature/test"
        merge_sha = "abc123merge"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # jj new @ branch
                create_mock_process(0, stdout=""),  # jj resolve --list (no conflicts)
                create_mock_process(0),  # jj describe
                create_mock_process(0),  # jj new
                create_mock_process(0, stdout=f"{merge_sha}\n"),  # jj log
            ]

            result = await git_merge(branch)

            assert result["success"] is True
            assert result["branch"] == branch
            assert result["merge_commit"] == merge_sha
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_handles_merge_conflict(self) -> None:
        """Test handles merge with conflicts."""
        branch = "feature/conflict"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # jj new @ branch
                create_mock_process(
                    0, stdout="file.py 2-sided conflict\n"
                ),  # jj resolve --list
            ]

            result = await git_merge(branch)

            assert result["success"] is False
            assert result["branch"] == branch
            assert result["merge_commit"] is None
            assert "conflicts" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_handles_new_failure(self) -> None:
        """Test handles jj new failure."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(
                    1, stderr="error: revision not found"
                ),  # jj new fails
            ]

            result = await git_merge("nonexistent")

            assert result["success"] is False
            assert result["merge_commit"] is None
            assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_handles_os_error(self) -> None:
        """Test handles OSError gracefully."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = OSError("jj not found")

            result = await git_merge("some-branch")

            assert result["success"] is False
            assert result["merge_commit"] is None
            assert result["error"] is not None


class TestCreateGitBranch:
    """Tests for create_git_branch action (jj bookmark)."""

    @pytest.mark.asyncio
    async def test_creates_new_bookmark(self) -> None:
        """Test creates new bookmark when it doesn't exist."""
        branch_name = "feature/new"
        base = "main"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="main: abc123\n"),  # jj bookmark list
                create_mock_process(0),  # jj new main
                create_mock_process(0),  # jj bookmark create
            ]

            result = await create_git_branch(branch_name, base)

            assert result["success"] is True
            assert result["branch_name"] == branch_name
            assert result["base_branch"] == base
            assert result["created"] is True
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_switches_to_existing_bookmark(self) -> None:
        """Test switches to existing bookmark via jj edit."""
        branch_name = "feature/existing"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(
                    0, stdout="feature/existing: def456 some description\n"
                ),  # jj bookmark list
                create_mock_process(0),  # jj edit
            ]

            result = await create_git_branch(branch_name)

            assert result["success"] is True
            assert result["branch_name"] == branch_name
            assert result["created"] is False

            # Verify jj edit was called
            edit_call = mock_exec.call_args_list[1]
            assert edit_call[0] == ("jj", "edit", branch_name)

    @pytest.mark.asyncio
    async def test_uses_default_base_branch(self) -> None:
        """Test uses 'main' as default base branch."""
        branch_name = "feature/test"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout=""),  # jj bookmark list (empty)
                create_mock_process(0),  # jj new main
                create_mock_process(0),  # jj bookmark create
            ]

            result = await create_git_branch(branch_name)

            assert result["success"] is True
            assert result["base_branch"] == "main"

            # Verify jj new main was called
            new_call = mock_exec.call_args_list[1]
            assert new_call[0] == ("jj", "new", "main")

    @pytest.mark.asyncio
    async def test_uses_custom_base_branch(self) -> None:
        """Test uses custom base branch when provided."""
        branch_name = "feature/test"
        base = "develop"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout=""),  # jj bookmark list (empty)
                create_mock_process(0),  # jj new develop
                create_mock_process(0),  # jj bookmark create
            ]

            result = await create_git_branch(branch_name, base)

            assert result["success"] is True
            assert result["base_branch"] == "develop"

            new_call = mock_exec.call_args_list[1]
            assert new_call[0] == ("jj", "new", "develop")

    @pytest.mark.asyncio
    async def test_handles_bookmark_create_failure(self) -> None:
        """Test handles jj bookmark create failure."""
        branch_name = "feature/test"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout=""),  # jj bookmark list
                create_mock_process(0),  # jj new main
                create_mock_process(
                    1, stderr="error: bookmark already exists"
                ),  # jj bookmark create fails
            ]

            result = await create_git_branch(branch_name)

            assert result["success"] is False
            assert result["created"] is False
            assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_handles_edit_failure(self) -> None:
        """Test handles jj edit failure for existing bookmark."""
        branch_name = "feature/existing"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(
                    0, stdout="feature/existing: abc123\n"
                ),  # jj bookmark list
                create_mock_process(1, stderr="error: cannot edit"),  # jj edit fails
            ]

            result = await create_git_branch(branch_name)

            assert result["success"] is False
            assert result["created"] is False
            assert result["error"] is not None


class TestJjSnapshotOperation:
    """Tests for jj_snapshot_operation action."""

    @pytest.mark.asyncio
    async def test_captures_operation_id(self) -> None:
        """Test captures current operation ID."""
        op_id = "abc123def456"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout=f"{op_id}\n"),
            ]

            result = await jj_snapshot_operation()

            assert result["success"] is True
            assert result["operation_id"] == op_id
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles jj op log failure."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr="error: not a jj repo"),
            ]

            result = await jj_snapshot_operation()

            assert result["success"] is False
            assert result["operation_id"] is None
            assert result["error"] is not None


class TestJjRestoreOperation:
    """Tests for jj_restore_operation action."""

    @pytest.mark.asyncio
    async def test_restores_operation(self) -> None:
        """Test restores to a previous operation."""
        op_id = "abc123def456"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),
            ]

            result = await jj_restore_operation(op_id)

            assert result["success"] is True
            assert result["error"] is None

            call_args = mock_exec.call_args_list[0][0]
            assert call_args == ("jj", "op", "restore", op_id)

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles restore failure."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr="error: operation not found"),
            ]

            result = await jj_restore_operation("bad-id")

            assert result["success"] is False
            assert result["error"] is not None


class TestJjSquash:
    """Tests for jj_squash action."""

    @pytest.mark.asyncio
    async def test_squashes_into_parent(self) -> None:
        """Test squashes into parent by default."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [create_mock_process(0)]

            result = await jj_squash()

            assert result["success"] is True
            call_args = mock_exec.call_args_list[0][0]
            assert call_args == ("jj", "squash")

    @pytest.mark.asyncio
    async def test_squashes_into_specific_revision(self) -> None:
        """Test squashes into specified revision."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [create_mock_process(0)]

            result = await jj_squash(into="abc123")

            assert result["success"] is True
            call_args = mock_exec.call_args_list[0][0]
            assert call_args == ("jj", "squash", "--into", "abc123")

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles squash failure."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr="error: nothing to squash")
            ]

            result = await jj_squash()

            assert result["success"] is False
            assert result["error"] is not None


class TestJjAbsorb:
    """Tests for jj_absorb action."""

    @pytest.mark.asyncio
    async def test_absorbs_changes(self) -> None:
        """Test absorbs working copy changes."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [create_mock_process(0)]

            result = await jj_absorb()

            assert result["success"] is True
            call_args = mock_exec.call_args_list[0][0]
            assert call_args == ("jj", "absorb")

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles absorb failure."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr="error: absorb failed")
            ]

            result = await jj_absorb()

            assert result["success"] is False
            assert result["error"] is not None


class TestJjLog:
    """Tests for jj_log action."""

    @pytest.mark.asyncio
    async def test_shows_log(self) -> None:
        """Test shows jj log output."""
        log_output = "@ abc123 user description\n"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout=log_output),
            ]

            result = await jj_log()

            assert result["success"] is True
            assert result["output"] == log_output

    @pytest.mark.asyncio
    async def test_custom_revset(self) -> None:
        """Test uses custom revset and limit."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="output\n"),
            ]

            result = await jj_log(revset="::@", limit=5)

            assert result["success"] is True
            call_args = mock_exec.call_args_list[0][0]
            assert call_args == ("jj", "log", "-r", "::@", "--limit", "5")

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles jj log failure."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [create_mock_process(1, stderr="error: bad revset")]

            result = await jj_log(revset="bad")

            assert result["success"] is False
            assert result["output"] == ""
            assert result["error"] is not None


class TestJjDiff:
    """Tests for jj_diff action."""

    @pytest.mark.asyncio
    async def test_shows_diff(self) -> None:
        """Test shows diff in git format."""
        diff_output = "diff --git a/file.py b/file.py\n"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout=diff_output),
            ]

            result = await jj_diff()

            assert result["success"] is True
            assert result["output"] == diff_output

    @pytest.mark.asyncio
    async def test_custom_revision(self) -> None:
        """Test uses custom revision."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="diff output\n"),
            ]

            result = await jj_diff(revision="@-")

            assert result["success"] is True
            call_args = mock_exec.call_args_list[0][0]
            assert call_args == ("jj", "diff", "-r", "@-", "--git")

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles jj diff failure."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr="error: bad revision")
            ]

            result = await jj_diff(revision="bad")

            assert result["success"] is False
            assert result["output"] == ""
            assert result["error"] is not None


class TestJjDescribe:
    """Tests for jj_describe action."""

    @pytest.mark.asyncio
    async def test_describes_current_change(self) -> None:
        """Test sets description on current change."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [create_mock_process(0)]

            result = await jj_describe("WIP bead(42): auth feature")

            assert result["success"] is True
            assert result["error"] is None
            call_args = mock_exec.call_args_list[0][0]
            assert call_args == (
                "jj",
                "describe",
                "-m",
                "WIP bead(42): auth feature",
            )

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles jj describe failure."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [create_mock_process(1, stderr="error: no repo")]

            result = await jj_describe("msg")

            assert result["success"] is False
            assert result["error"] is not None


class TestCurateHistory:
    """Tests for curate_history action."""

    @pytest.mark.asyncio
    async def test_runs_absorb_and_squashes_fix_beads(self) -> None:
        """Test absorb runs and fix beads are squashed."""
        log_output = (
            "abc123\tbead(5): fix lint errors\ndef456\tbead(4): add user auth\n"
        )

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # jj absorb
                create_mock_process(0, stdout=log_output),  # jj log
                # squash abc123 (fix bead) — newest first
                create_mock_process(0),
            ]

            result = await curate_history()

            assert result["success"] is True
            assert result["absorb_ran"] is True
            assert result["squashed_count"] == 1
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_no_fix_beads_means_zero_squashes(self) -> None:
        """Test no squashing when no fix beads exist."""
        log_output = "abc123\tbead(4): add user auth\ndef456\tbead(3): add login page\n"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # jj absorb
                create_mock_process(0, stdout=log_output),  # jj log
                # no squash calls expected
            ]

            result = await curate_history()

            assert result["success"] is True
            assert result["squashed_count"] == 0

    @pytest.mark.asyncio
    async def test_absorb_failure_is_non_fatal(self) -> None:
        """Test absorb failing doesn't stop curation."""
        log_output = "abc123\tbead(2): add feature\n"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                # jj absorb fails (non-fatal)
                create_mock_process(1, stderr="nothing to absorb"),
                create_mock_process(0, stdout=log_output),  # jj log
            ]

            result = await curate_history()

            assert result["success"] is True
            assert result["absorb_ran"] is False
            assert result["squashed_count"] == 0

    @pytest.mark.asyncio
    async def test_empty_revset_returns_early(self) -> None:
        """Test empty revset (no commits) returns cleanly."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # jj absorb
                # jj log fails (empty revset)
                create_mock_process(1, stderr="empty revset"),
            ]

            result = await curate_history()

            assert result["success"] is True
            assert result["squashed_count"] == 0

    @pytest.mark.asyncio
    async def test_squash_failure_is_non_fatal(self) -> None:
        """Test individual squash failure doesn't stop iteration."""
        log_output = (
            "abc123\tbead(5): fix typecheck errors\ndef456\tbead(4): fixup formatting\n"
        )

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # jj absorb
                create_mock_process(0, stdout=log_output),  # jj log
                # squash abc123 fails
                create_mock_process(1, stderr="conflict"),
                # squash def456 succeeds
                create_mock_process(0),
            ]

            result = await curate_history()

            assert result["success"] is True
            assert result["squashed_count"] == 1

    @pytest.mark.asyncio
    async def test_detects_fix_keywords(self) -> None:
        """Test detects various fix-related keywords."""
        log_output = (
            "a1\tbead(10): fix test failures\n"
            "a2\tbead(9): fixup import order\n"
            "a3\tbead(8): lint cleanup\n"
            "a4\tbead(7): format code\n"
            "a5\tbead(6): typecheck corrections\n"
            "a6\tbead(5): add new feature\n"
        )

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # jj absorb
                create_mock_process(0, stdout=log_output),  # jj log
                create_mock_process(0),  # squash a1 (fix)
                create_mock_process(0),  # squash a2 (fixup)
                create_mock_process(0),  # squash a3 (lint)
                create_mock_process(0),  # squash a4 (format)
                create_mock_process(0),  # squash a5 (typecheck)
                # a6 is NOT squashed (no fix keyword)
            ]

            result = await curate_history()

            assert result["success"] is True
            assert result["squashed_count"] == 5

    @pytest.mark.asyncio
    async def test_os_error_returns_failure(self) -> None:
        """Test OSError returns graceful failure."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = OSError("jj not found")

            result = await curate_history()

            assert result["success"] is False
            assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_custom_base_revision(self) -> None:
        """Test uses custom base revision in revset."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # jj absorb
                create_mock_process(0, stdout=""),  # jj log (empty)
            ]

            result = await curate_history(base_revision="develop")

            assert result["success"] is True
            # Verify the revset used "develop"
            log_call = mock_exec.call_args_list[1]
            assert log_call[0][3] == "develop..@-"
