"""Unit tests for jj (Jujutsu) actions.

Tests the jj.py action module including:
- jj_describe
- jj_snapshot_operation / jj_restore_operation
- jj_squash / jj_absorb
- jj_log / jj_diff
- curate_history
- gather_curation_context
- execute_curation_plan
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maverick.library.actions.jj import (
    curate_history,
    execute_curation_plan,
    gather_curation_context,
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


class TestGatherCurationContext:
    """Tests for gather_curation_context action."""

    @pytest.mark.asyncio
    async def test_success_returns_commits(self) -> None:
        """Test gathers commit list with per-commit stats."""
        log_output = "abc123\tadd user auth\ndef456\tadd login page\n"
        log_stat_output = "@ abc123 ...\n  src/auth.py | 50 +\n"
        diff_stat_1 = " src/auth.py | 50 ++++\n"
        diff_stat_2 = " src/login.py | 30 ++++\n"

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(0, stdout=log_output),  # jj log (commit list)
                create_mock_process(0, stdout=log_stat_output),  # jj log --stat
                create_mock_process(0, stdout=diff_stat_1),  # jj diff --stat abc123
                create_mock_process(0, stdout=diff_stat_2),  # jj diff --stat def456
            ]

            result = await gather_curation_context()

            assert result["success"] is True
            assert len(result["commits"]) == 2
            assert result["commits"][0]["change_id"] == "abc123"
            assert result["commits"][0]["description"] == "add user auth"
            assert result["commits"][1]["change_id"] == "def456"
            assert result["log_summary"] == log_stat_output
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_empty_revset_returns_empty(self) -> None:
        """Test returns empty commits list when revset has no results."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr="empty revset"),  # jj log fails
            ]

            result = await gather_curation_context()

            assert result["success"] is True
            assert result["commits"] == []
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_os_error_returns_failure(self) -> None:
        """Test OSError returns graceful failure."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = OSError("jj not found")

            result = await gather_curation_context()

            assert result["success"] is False
            assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_custom_base_revision(self) -> None:
        """Test uses custom base revision."""
        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                create_mock_process(1, stderr="empty"),  # jj log fails (no commits)
            ]

            result = await gather_curation_context(base_revision="develop")

            assert result["success"] is True
            # Verify the revset used "develop"
            log_call = mock_exec.call_args_list[0]
            assert log_call[0][3] == "develop..@-"


class TestExecuteCurationPlan:
    """Tests for execute_curation_plan action."""

    @pytest.mark.asyncio
    async def test_success_all_steps(self) -> None:
        """Test all steps execute successfully."""
        plan = [
            {
                "command": "squash",
                "args": ["-r", "abc123"],
                "reason": "fix into parent",
            },
            {
                "command": "describe",
                "args": ["-r", "def456", "-m", "better msg"],
                "reason": "clarity",
            },
        ]

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                # jj op log (snapshot)
                create_mock_process(0, stdout="snap123\n"),
                # jj squash -r abc123
                create_mock_process(0),
                # jj describe -r def456 -m "better msg"
                create_mock_process(0),
            ]

            result = await execute_curation_plan(plan)

            assert result["success"] is True
            assert result["executed_count"] == 2
            assert result["total_count"] == 2
            assert result["snapshot_id"] == "snap123"
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_rollback_on_failure(self) -> None:
        """Test snapshot is restored when a step fails."""
        plan = [
            {"command": "squash", "args": ["-r", "abc123"], "reason": "ok"},
            {"command": "squash", "args": ["-r", "bad456"], "reason": "will fail"},
        ]

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                # jj op log (snapshot)
                create_mock_process(0, stdout="snap123\n"),
                # jj squash -r abc123 (succeeds)
                create_mock_process(0),
                # jj squash -r bad456 (fails)
                create_mock_process(1, stderr="conflict"),
                # jj op restore snap123 (rollback)
                create_mock_process(0),
            ]

            result = await execute_curation_plan(plan)

            assert result["success"] is False
            assert result["executed_count"] == 1
            assert result["total_count"] == 2
            assert result["snapshot_id"] == "snap123"
            assert "conflict" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_plan_is_noop(self) -> None:
        """Test empty plan returns immediately with success."""
        result = await execute_curation_plan([])

        assert result["success"] is True
        assert result["executed_count"] == 0
        assert result["total_count"] == 0
        assert result["snapshot_id"] is None

    @pytest.mark.asyncio
    async def test_snapshot_failure(self) -> None:
        """Test failure if snapshot cannot be created."""
        plan = [{"command": "squash", "args": [], "reason": "test"}]

        with patch(MOCK_TARGET) as mock_exec:
            mock_exec.side_effect = [
                # jj op log fails
                create_mock_process(1, stderr="not a jj repo"),
            ]

            result = await execute_curation_plan(plan)

            assert result["success"] is False
            assert result["snapshot_id"] is None
            assert "snapshot" in result["error"].lower()
