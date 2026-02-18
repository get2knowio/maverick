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

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.jj.client import JjClient
from maverick.jj.errors import JjError
from maverick.jj.models import (
    JjAbsorbResult,
    JjChangeInfo,
    JjDescribeResult,
    JjDiffResult,
    JjDiffStatResult,
    JjLogResult,
    JjNewResult,
    JjRestoreResult,
    JjSnapshotResult,
    JjSquashResult,
)
from maverick.library.actions.jj import (
    curate_history,
    execute_curation_plan,
    gather_curation_context,
    jj_absorb,
    jj_commit_bead,
    jj_describe,
    jj_diff,
    jj_log,
    jj_restore_operation,
    jj_snapshot_operation,
    jj_squash,
)
from maverick.runners.models import CommandResult

MOCK_CLIENT = "maverick.library.actions.jj._make_client"


def make_mock_client() -> AsyncMock:
    """Create a mock JjClient with all methods as AsyncMock."""
    client = AsyncMock(spec=JjClient)
    # Set default cwd property
    client.cwd = None
    # Set up the _runner mock for execute_curation_plan
    client._runner = AsyncMock()
    return client


class TestJjDescribe:
    """Tests for jj_describe action."""

    @pytest.mark.asyncio
    async def test_describes_current_change(self) -> None:
        """Test sets description on current change."""
        mock_client = make_mock_client()
        mock_client.describe.return_value = JjDescribeResult(
            success=True, message="WIP bead(42): auth feature"
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_describe("WIP bead(42): auth feature")

        assert result["success"] is True
        assert result["error"] is None
        mock_client.describe.assert_called_once_with(
            "WIP bead(42): auth feature"
        )

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles jj describe failure."""
        mock_client = make_mock_client()
        mock_client.describe.side_effect = JjError("jj describe failed: no repo")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_describe("msg")

        assert result["success"] is False
        assert result["error"] is not None


class TestJjSnapshotOperation:
    """Tests for jj_snapshot_operation action."""

    @pytest.mark.asyncio
    async def test_captures_operation_id(self) -> None:
        """Test captures current operation ID."""
        op_id = "abc123def456"
        mock_client = make_mock_client()
        mock_client.snapshot_operation.return_value = JjSnapshotResult(
            success=True, operation_id=op_id
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_snapshot_operation()

        assert result["success"] is True
        assert result["operation_id"] == op_id
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles jj op log failure."""
        mock_client = make_mock_client()
        mock_client.snapshot_operation.side_effect = JjError("not a jj repo")

        with patch(MOCK_CLIENT, return_value=mock_client):
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
        mock_client = make_mock_client()
        mock_client.restore_operation.return_value = JjRestoreResult(success=True)

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_restore_operation(op_id)

        assert result["success"] is True
        assert result["error"] is None
        mock_client.restore_operation.assert_called_once_with(op_id)

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles restore failure."""
        mock_client = make_mock_client()
        mock_client.restore_operation.side_effect = JjError("operation not found")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_restore_operation("bad-id")

        assert result["success"] is False
        assert result["error"] is not None


class TestJjSquash:
    """Tests for jj_squash action."""

    @pytest.mark.asyncio
    async def test_squashes_into_parent(self) -> None:
        """Test squashes into parent by default."""
        mock_client = make_mock_client()
        mock_client.squash.return_value = JjSquashResult(success=True)

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_squash()

        assert result["success"] is True
        # into="@-" maps to into=None (default parent behavior)
        mock_client.squash.assert_called_once_with(into=None)

    @pytest.mark.asyncio
    async def test_squashes_into_specific_revision(self) -> None:
        """Test squashes into specified revision."""
        mock_client = make_mock_client()
        mock_client.squash.return_value = JjSquashResult(success=True)

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_squash(into="abc123")

        assert result["success"] is True
        mock_client.squash.assert_called_once_with(into="abc123")

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles squash failure."""
        mock_client = make_mock_client()
        mock_client.squash.side_effect = JjError("nothing to squash")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_squash()

        assert result["success"] is False
        assert result["error"] is not None


class TestJjAbsorb:
    """Tests for jj_absorb action."""

    @pytest.mark.asyncio
    async def test_absorbs_changes(self) -> None:
        """Test absorbs working copy changes."""
        mock_client = make_mock_client()
        mock_client.absorb.return_value = JjAbsorbResult(success=True)

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_absorb()

        assert result["success"] is True
        mock_client.absorb.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles absorb failure."""
        mock_client = make_mock_client()
        mock_client.absorb.side_effect = JjError("absorb failed")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_absorb()

        assert result["success"] is False
        assert result["error"] is not None


class TestJjLog:
    """Tests for jj_log action."""

    @pytest.mark.asyncio
    async def test_shows_log(self) -> None:
        """Test shows jj log output."""
        log_output = "@ abc123 user description\n"
        mock_client = make_mock_client()
        mock_client.log.return_value = JjLogResult(
            success=True, output=log_output
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_log()

        assert result["success"] is True
        assert result["output"] == log_output

    @pytest.mark.asyncio
    async def test_custom_revset(self) -> None:
        """Test uses custom revset and limit."""
        mock_client = make_mock_client()
        mock_client.log.return_value = JjLogResult(
            success=True, output="output\n"
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_log(revset="::@", limit=5)

        assert result["success"] is True
        mock_client.log.assert_called_once_with(revset="::@", limit=5)

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles jj log failure."""
        mock_client = make_mock_client()
        mock_client.log.side_effect = JjError("bad revset")

        with patch(MOCK_CLIENT, return_value=mock_client):
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
        mock_client = make_mock_client()
        mock_client.diff.return_value = JjDiffResult(
            success=True, output=diff_output
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_diff()

        assert result["success"] is True
        assert result["output"] == diff_output

    @pytest.mark.asyncio
    async def test_custom_revision(self) -> None:
        """Test uses custom revision."""
        mock_client = make_mock_client()
        mock_client.diff.return_value = JjDiffResult(
            success=True, output="diff output\n"
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_diff(revision="@-")

        assert result["success"] is True
        mock_client.diff.assert_called_once_with(revision="@-")

    @pytest.mark.asyncio
    async def test_handles_failure(self) -> None:
        """Test handles jj diff failure."""
        mock_client = make_mock_client()
        mock_client.diff.side_effect = JjError("bad revision")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_diff(revision="bad")

        assert result["success"] is False
        assert result["output"] == ""
        assert result["error"] is not None


class TestJjCommitBead:
    """Tests for jj_commit_bead action."""

    @pytest.mark.asyncio
    async def test_describes_and_creates_new(self) -> None:
        """Test describe + new is called in sequence."""
        mock_client = make_mock_client()
        mock_client.describe.return_value = JjDescribeResult(success=True)
        mock_client.new.return_value = JjNewResult(
            success=True, change_id="kxyz"
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_commit_bead("bead(42): add feature")

        assert result["success"] is True
        assert result["message"] == "bead(42): add feature"
        assert result["change_id"] == "kxyz"
        assert result["error"] is None
        mock_client.describe.assert_called_once_with("bead(42): add feature")
        mock_client.new.assert_called_once()

    @pytest.mark.asyncio
    async def test_accepts_cwd_as_string(self) -> None:
        """Test cwd parameter works when passed as string."""
        mock_client = make_mock_client()
        mock_client.describe.return_value = JjDescribeResult(success=True)
        mock_client.new.return_value = JjNewResult(success=True)

        with patch(MOCK_CLIENT, return_value=mock_client) as mock_make:
            await jj_commit_bead("msg", cwd="/tmp/workspace")

        # _make_client should be called with a Path
        call_args = mock_make.call_args
        assert call_args[0][0] == Path("/tmp/workspace")

    @pytest.mark.asyncio
    async def test_handles_describe_failure(self) -> None:
        """Test handles describe failure."""
        mock_client = make_mock_client()
        mock_client.describe.side_effect = JjError("describe failed")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_commit_bead("msg")

        assert result["success"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_handles_new_failure(self) -> None:
        """Test handles jj new failure."""
        mock_client = make_mock_client()
        mock_client.describe.return_value = JjDescribeResult(success=True)
        mock_client.new.side_effect = JjError("new failed")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await jj_commit_bead("msg")

        assert result["success"] is False
        assert result["error"] is not None


class TestCurateHistory:
    """Tests for curate_history action."""

    @pytest.mark.asyncio
    async def test_runs_absorb_and_squashes_fix_beads(self) -> None:
        """Test absorb runs and fix beads are squashed."""
        mock_client = make_mock_client()
        mock_client.absorb.return_value = JjAbsorbResult(success=True)
        mock_client.log.return_value = JjLogResult(
            success=True,
            output="",
            changes=(
                JjChangeInfo(
                    change_id="abc123",
                    commit_id="c1",
                    description="bead(5): fix lint errors",
                ),
                JjChangeInfo(
                    change_id="def456",
                    commit_id="c2",
                    description="bead(4): add user auth",
                ),
            ),
        )
        mock_client.squash.return_value = JjSquashResult(success=True)

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await curate_history()

        assert result["success"] is True
        assert result["absorb_ran"] is True
        assert result["squashed_count"] == 1
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_no_fix_beads_means_zero_squashes(self) -> None:
        """Test no squashing when no fix beads exist."""
        mock_client = make_mock_client()
        mock_client.absorb.return_value = JjAbsorbResult(success=True)
        mock_client.log.return_value = JjLogResult(
            success=True,
            output="",
            changes=(
                JjChangeInfo(
                    change_id="abc123",
                    commit_id="c1",
                    description="bead(4): add user auth",
                ),
                JjChangeInfo(
                    change_id="def456",
                    commit_id="c2",
                    description="bead(3): add login page",
                ),
            ),
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await curate_history()

        assert result["success"] is True
        assert result["squashed_count"] == 0

    @pytest.mark.asyncio
    async def test_absorb_failure_is_non_fatal(self) -> None:
        """Test absorb failing doesn't stop curation."""
        mock_client = make_mock_client()
        mock_client.absorb.side_effect = JjError("nothing to absorb")
        mock_client.log.return_value = JjLogResult(
            success=True,
            output="",
            changes=(
                JjChangeInfo(
                    change_id="abc123",
                    commit_id="c1",
                    description="bead(2): add feature",
                ),
            ),
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await curate_history()

        assert result["success"] is True
        assert result["absorb_ran"] is False
        assert result["squashed_count"] == 0

    @pytest.mark.asyncio
    async def test_empty_revset_returns_early(self) -> None:
        """Test empty revset (no commits) returns cleanly."""
        mock_client = make_mock_client()
        mock_client.absorb.return_value = JjAbsorbResult(success=True)
        mock_client.log.side_effect = JjError("empty revset")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await curate_history()

        assert result["success"] is True
        assert result["squashed_count"] == 0

    @pytest.mark.asyncio
    async def test_squash_failure_is_non_fatal(self) -> None:
        """Test individual squash failure doesn't stop iteration."""
        mock_client = make_mock_client()
        mock_client.absorb.return_value = JjAbsorbResult(success=True)
        mock_client.log.return_value = JjLogResult(
            success=True,
            output="",
            changes=(
                JjChangeInfo(
                    change_id="abc123",
                    commit_id="c1",
                    description="bead(5): fix typecheck errors",
                ),
                JjChangeInfo(
                    change_id="def456",
                    commit_id="c2",
                    description="bead(4): fixup formatting",
                ),
            ),
        )
        mock_client.squash.side_effect = [
            JjError("conflict"),  # first squash fails
            JjSquashResult(success=True),  # second squash succeeds
        ]

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await curate_history()

        assert result["success"] is True
        assert result["squashed_count"] == 1

    @pytest.mark.asyncio
    async def test_detects_fix_keywords(self) -> None:
        """Test detects various fix-related keywords."""
        mock_client = make_mock_client()
        mock_client.absorb.return_value = JjAbsorbResult(success=True)
        mock_client.log.return_value = JjLogResult(
            success=True,
            output="",
            changes=(
                JjChangeInfo(change_id="a1", commit_id="c1",
                             description="bead(10): fix test failures"),
                JjChangeInfo(change_id="a2", commit_id="c2",
                             description="bead(9): fixup import order"),
                JjChangeInfo(change_id="a3", commit_id="c3",
                             description="bead(8): lint cleanup"),
                JjChangeInfo(change_id="a4", commit_id="c4",
                             description="bead(7): format code"),
                JjChangeInfo(change_id="a5", commit_id="c5",
                             description="bead(6): typecheck corrections"),
                JjChangeInfo(change_id="a6", commit_id="c6",
                             description="bead(5): add new feature"),
            ),
        )
        mock_client.squash.return_value = JjSquashResult(success=True)

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await curate_history()

        assert result["success"] is True
        assert result["squashed_count"] == 5

    @pytest.mark.asyncio
    async def test_os_error_returns_failure(self) -> None:
        """Test OSError returns graceful failure."""
        mock_client = make_mock_client()
        mock_client.absorb.side_effect = OSError("jj not found")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await curate_history()

        assert result["success"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_custom_base_revision(self) -> None:
        """Test uses custom base revision in revset."""
        mock_client = make_mock_client()
        mock_client.absorb.return_value = JjAbsorbResult(success=True)
        mock_client.log.return_value = JjLogResult(
            success=True, output="", changes=()
        )

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await curate_history(base_revision="develop")

        assert result["success"] is True
        # Verify the revset used "develop"
        mock_client.log.assert_called_once_with(
            revset="develop..@-", limit=1000
        )


class TestGatherCurationContext:
    """Tests for gather_curation_context action."""

    @pytest.mark.asyncio
    async def test_success_returns_commits(self) -> None:
        """Test gathers commit list with per-commit stats."""
        mock_client = make_mock_client()
        mock_client.log.return_value = JjLogResult(
            success=True,
            output="",
            changes=(
                JjChangeInfo(change_id="abc123", commit_id="c1",
                             description="add user auth"),
                JjChangeInfo(change_id="def456", commit_id="c2",
                             description="add login page"),
            ),
        )
        mock_client.diff_stat.side_effect = [
            # Summary stat
            JjDiffStatResult(success=True, output="summary stats"),
            # Per-commit stats
            JjDiffStatResult(
                success=True, output=" src/auth.py | 50 ++++\n"
            ),
            JjDiffStatResult(
                success=True, output=" src/login.py | 30 ++++\n"
            ),
        ]

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await gather_curation_context()

        assert result["success"] is True
        assert len(result["commits"]) == 2
        assert result["commits"][0]["change_id"] == "abc123"
        assert result["commits"][0]["description"] == "add user auth"
        assert result["commits"][1]["change_id"] == "def456"
        assert result["log_summary"] == "summary stats"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_empty_revset_returns_empty(self) -> None:
        """Test returns empty commits list when revset has no results."""
        mock_client = make_mock_client()
        mock_client.log.side_effect = JjError("empty revset")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await gather_curation_context()

        assert result["success"] is True
        assert result["commits"] == []
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_os_error_returns_failure(self) -> None:
        """Test OSError returns graceful failure."""
        mock_client = make_mock_client()
        mock_client.log.side_effect = OSError("jj not found")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await gather_curation_context()

        assert result["success"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_custom_base_revision(self) -> None:
        """Test uses custom base revision."""
        mock_client = make_mock_client()
        mock_client.log.side_effect = JjError("empty")

        with patch(MOCK_CLIENT, return_value=mock_client):
            result = await gather_curation_context(
                base_revision="develop"
            )

        assert result["success"] is True
        mock_client.log.assert_called_once_with(
            revset="develop..@-", limit=1000
        )


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

        mock_client = make_mock_client()
        mock_client._runner.run.return_value = CommandResult(
            returncode=0, stdout="", stderr="", duration_ms=50
        )

        with (
            patch(MOCK_CLIENT, return_value=mock_client),
            patch(
                "maverick.library.actions.jj.jj_snapshot_operation",
            ) as mock_snap,
            patch(
                "maverick.library.actions.jj.jj_restore_operation",
            ),
        ):
            mock_snap.return_value = {
                "success": True,
                "operation_id": "snap123",
                "error": None,
            }

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
            {
                "command": "squash",
                "args": ["-r", "bad456"],
                "reason": "will fail",
            },
        ]

        mock_client = make_mock_client()
        mock_client._runner.run.side_effect = [
            # jj squash -r abc123 (succeeds)
            CommandResult(
                returncode=0, stdout="", stderr="", duration_ms=50
            ),
            # jj squash -r bad456 (fails)
            CommandResult(
                returncode=1, stdout="", stderr="conflict", duration_ms=50
            ),
        ]

        with (
            patch(MOCK_CLIENT, return_value=mock_client),
            patch(
                "maverick.library.actions.jj.jj_snapshot_operation",
            ) as mock_snap,
            patch(
                "maverick.library.actions.jj.jj_restore_operation",
            ) as mock_restore,
        ):
            mock_snap.return_value = {
                "success": True,
                "operation_id": "snap123",
                "error": None,
            }
            mock_restore.return_value = {"success": True, "error": None}

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

        with patch(
            "maverick.library.actions.jj.jj_snapshot_operation",
        ) as mock_snap:
            mock_snap.return_value = {
                "success": False,
                "operation_id": None,
                "error": "not a jj repo",
            }

            result = await execute_curation_plan(plan)

        assert result["success"] is False
        assert result["snapshot_id"] is None
        assert "snapshot" in result["error"].lower()
