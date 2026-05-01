"""Unit tests for git actions.

Now scoped to the read and merge-fallback surface that survives Architecture A:
- git_merge (used by land's plain-git fallback path)
- _parse_untracked_conflicts (helper used by git_merge)

Write-path helpers (git_commit/git_push/git_add/git_stage_all/
git_check_and_stage/create_git_branch) were deleted in the cleanup phase;
their tests are gone with them.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maverick.library.actions.git import (
    _parse_untracked_conflicts,
    git_merge,
)


def create_mock_process(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
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


class TestGitMerge:
    """Tests for git_merge action."""

    @pytest.mark.asyncio
    async def test_merges_branch_successfully(self) -> None:
        """Test merges a branch into current branch."""
        branch = "feature/test"
        merge_sha = "abc123merge"

        with patch("maverick.library.actions.git.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="Merge made\n"),  # git merge
                create_mock_process(0, stdout=f"{merge_sha}\n"),  # git rev-parse HEAD
            ]

            result = await git_merge(branch)

            assert result.success is True
            assert result.branch == branch
            assert result.merge_commit == merge_sha
            assert result.error is None

    @pytest.mark.asyncio
    async def test_merge_uses_no_ff_flag(self) -> None:
        """Test passes --no-ff flag when requested."""
        branch = "feature/no-ff"

        with patch("maverick.library.actions.git.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="Merge made\n"),  # git merge --no-ff
                create_mock_process(0, stdout="sha456\n"),  # git rev-parse HEAD
            ]

            result = await git_merge(branch, no_ff=True)

            assert result.success is True

            merge_call = mock_exec.call_args_list[0]
            assert merge_call[0] == ("git", "merge", "--no-ff", branch)

    @pytest.mark.asyncio
    async def test_merge_without_no_ff(self) -> None:
        """Test does not pass --no-ff by default."""
        branch = "feature/fast-forward"

        with patch("maverick.library.actions.git.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout="Fast-forward\n"),  # git merge
                create_mock_process(0, stdout="sha789\n"),  # git rev-parse HEAD
            ]

            result = await git_merge(branch)

            assert result.success is True

            merge_call = mock_exec.call_args_list[0]
            assert merge_call[0] == ("git", "merge", branch)

    @pytest.mark.asyncio
    async def test_handles_merge_conflict(self) -> None:
        """Test handles merge failure (e.g., conflict) gracefully."""
        branch = "feature/conflict"

        with patch("maverick.library.actions.git.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr="CONFLICT (content): Merge conflict in file.py"),
            ]

            result = await git_merge(branch)

            assert result.success is False
            assert result.branch == branch
            assert result.merge_commit is None
            assert result.error is not None
            assert "CONFLICT" in result.error

    @pytest.mark.asyncio
    async def test_handles_os_error(self) -> None:
        """Test handles OSError (e.g., git not found) gracefully."""
        with patch("maverick.library.actions.git.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = OSError("git not found")

            result = await git_merge("some-branch")

            assert result.success is False
            assert result.merge_commit is None
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_retries_after_removing_untracked_conflicts(self) -> None:
        """Test removes untracked files and retries merge on conflict."""
        branch = "feature/beads"
        untracked_error = (
            "error: The following untracked working tree files "
            "would be overwritten by merge:\n"
            "\t.beads/issues.jsonl\n"
            "Please move or remove them before you merge.\n"
            "Aborting\n"
        )

        with patch("maverick.library.actions.git.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr=untracked_error),  # first merge fails
                create_mock_process(0),  # rm -f .beads/issues.jsonl
                create_mock_process(0, stdout="Merge made\n"),  # retry merge
                create_mock_process(0, stdout="abc123\n"),  # git rev-parse HEAD
            ]

            result = await git_merge(branch)

            assert result.success is True
            assert result.merge_commit == "abc123"

            rm_call = mock_exec.call_args_list[1]
            assert rm_call[0] == ("rm", "-f", ".beads/issues.jsonl")

    @pytest.mark.asyncio
    async def test_resolves_dolt_modify_delete_by_accepting_deletion(self) -> None:
        """``.beads/*`` modify/delete conflicts are auto-resolved by ``git rm``
        because bd regenerates the JSONL view from the shared dolt DB
        (FUTURE.md §4.4). The merge then completes via ``git commit
        --no-edit`` using the auto-generated MERGE_MSG.
        """
        branch = "maverick/sample-project"
        modify_delete_error = (
            "CONFLICT (modify/delete): .beads/issues.jsonl deleted in "
            f"{branch} and modified in HEAD. Version HEAD of "
            ".beads/issues.jsonl left in tree.\n"
            "Automatic merge failed; fix conflicts and then commit the result.\n"
        )
        unmerged_status = "UD .beads/issues.jsonl\n"

        with patch("maverick.library.actions.git.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr=modify_delete_error),  # merge fails
                create_mock_process(0, stdout=unmerged_status),  # git status
                create_mock_process(0),  # git rm -f .beads/issues.jsonl
                create_mock_process(0, stdout="Merge made\n"),  # git commit --no-edit
                create_mock_process(0, stdout="abc123\n"),  # git rev-parse HEAD
            ]

            result = await git_merge(branch)

            assert result.success is True
            assert result.merge_commit == "abc123"

            status_call = mock_exec.call_args_list[1]
            assert status_call[0] == ("git", "status", "--porcelain=v1")
            rm_call = mock_exec.call_args_list[2]
            assert rm_call[0] == ("git", "rm", "-f", ".beads/issues.jsonl")
            commit_call = mock_exec.call_args_list[3]
            assert commit_call[0] == ("git", "commit", "--no-edit")

    @pytest.mark.asyncio
    async def test_aborts_when_non_dolt_path_also_conflicts(self) -> None:
        """If a real source-tree conflict accompanies the spurious
        ``.beads/*`` one, the merge is aborted (so the working tree is
        clean) and the original error is surfaced — we never silently
        drop a real conflict.
        """
        branch = "maverick/sample-project"
        modify_delete_error = (
            "CONFLICT (modify/delete): .beads/issues.jsonl deleted in "
            f"{branch} and modified in HEAD.\n"
            "CONFLICT (content): Merge conflict in src/main.py\n"
        )
        unmerged_status = "UD .beads/issues.jsonl\nUU src/main.py\n"

        with patch("maverick.library.actions.git.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr=modify_delete_error),  # merge fails
                create_mock_process(0, stdout=unmerged_status),  # git status
                create_mock_process(0),  # git merge --abort
            ]

            result = await git_merge(branch)

            assert result.success is False
            assert result.error is not None
            assert "src/main.py" in result.error

            abort_call = mock_exec.call_args_list[2]
            assert abort_call[0] == ("git", "merge", "--abort")
            assert all(
                call[0][0:2] != ("git", "rm") and call[0][0:2] != ("git", "commit")
                for call in mock_exec.call_args_list
            )

    @pytest.mark.asyncio
    async def test_resolves_dolt_modify_delete_in_either_direction(self) -> None:
        """Whether ours or theirs deleted the dolt file, the resolution
        is the same: accept deletion. Tests the DU code path (deleted
        by us, modified by them) — the inverse of the FUTURE.md case.
        """
        branch = "maverick/other-project"
        modify_delete_error = (
            "CONFLICT (modify/delete): .beads/issues.jsonl deleted in "
            f"HEAD and modified in {branch}.\n"
        )
        unmerged_status = "DU .beads/issues.jsonl\n"

        with patch("maverick.library.actions.git.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr=modify_delete_error),
                create_mock_process(0, stdout=unmerged_status),
                create_mock_process(0),  # git rm -f
                create_mock_process(0, stdout="Merge made\n"),  # git commit
                create_mock_process(0, stdout="def456\n"),  # rev-parse
            ]

            result = await git_merge(branch)

            assert result.success is True
            assert result.merge_commit == "def456"


class TestParseUntrackedConflicts:
    """Tests for _parse_untracked_conflicts helper."""

    def test_parses_single_file(self) -> None:
        output = (
            "error: The following untracked working tree files "
            "would be overwritten by merge:\n"
            "\t.beads/issues.jsonl\n"
            "Please move or remove them before you merge.\n"
        )
        assert _parse_untracked_conflicts(output) == [".beads/issues.jsonl"]

    def test_parses_multiple_files(self) -> None:
        output = (
            "error: The following untracked working tree files "
            "would be overwritten by merge:\n"
            "\t.beads/issues.jsonl\n"
            "\t.beads/config.yaml\n"
            "\tREADME.md\n"
            "Please move or remove them before you merge.\n"
        )
        assert _parse_untracked_conflicts(output) == [
            ".beads/issues.jsonl",
            ".beads/config.yaml",
            "README.md",
        ]

    def test_returns_empty_for_unrelated_error(self) -> None:
        output = "CONFLICT (content): Merge conflict in file.py"
        assert _parse_untracked_conflicts(output) == []


class TestStartNewSession:
    """Verify git_merge spawns subprocesses with start_new_session=True.

    ``start_new_session=True`` puts git subprocesses in their own process
    group so ``_reap_if_running`` can kill the whole tree on cancel/timeout
    without also killing the parent.
    """

    @pytest.mark.asyncio
    async def test_git_merge_passes_start_new_session(self) -> None:
        with patch("maverick.library.actions.git.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0),  # merge
                create_mock_process(0, stdout="sha\n"),  # rev-parse
            ]
            await git_merge("feature")
            for call in mock_exec.call_args_list:
                assert call.kwargs.get("start_new_session") is True
