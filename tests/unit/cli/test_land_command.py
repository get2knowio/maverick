"""Unit tests for the ``maverick land`` CLI command."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from maverick.cli.commands.land import (
    _approve,
    _display_plan,
    _eject,
    _finalize,
    land,
)
from maverick.cli.context import ExitCode


def _mock_command_runner() -> patch:
    """Patch CommandRunner so branch cleanup succeeds in tests."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.stderr = ""
    mock_runner = AsyncMock()
    mock_runner.run.return_value = mock_result
    return patch(
        "maverick.runners.command.CommandRunner",
        return_value=mock_runner,
    )


# ── Help-text tests ──────────────────────────────────────────────────


class TestLandHelp:
    """Verify all CLI options appear in help output."""

    def test_land_in_cli(self) -> None:
        """land command is registered and shows in help."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        assert "curate" in result.output.lower()

    def test_land_help_shows_all_options(self) -> None:
        """Help output shows all options."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        for option in [
            "--no-curate",
            "--dry-run",
            "--yes",
            "--base",
            "--heuristic-only",
            "--eject",
            "--finalize",
            "--branch",
        ]:
            assert option in result.output, f"Missing option: {option}"

    def test_yes_short_flag(self) -> None:
        """--yes has -y short form."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert "-y" in result.output

    def test_base_default(self) -> None:
        """--base defaults to 'main'."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert "main" in result.output

    def test_is_command_not_group(self) -> None:
        """land should be a direct command, not a group."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert "Commands:" not in result.output

    def test_eject_help_text(self) -> None:
        """--eject description mentions preview branch."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert "preview branch" in result.output.lower()

    def test_finalize_help_text(self) -> None:
        """--finalize description mentions merge and cleanup."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        lower = result.output.lower()
        assert "finalize" in lower
        assert "merge" in lower or "cleanup" in lower


# ── Approve path tests ───────────────────────────────────────────────


class TestApprovePath:
    """Tests for _approve(): bookmark, push to local, merge, teardown."""

    @pytest.mark.asyncio
    async def test_approve_with_yes_merges_locally(self) -> None:
        """--yes skips prompt, pushes via JjClient, merges locally."""
        mock_client = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.exists = True

        with (
            patch(
                "maverick.jj.client.JjClient",
                return_value=mock_client,
            ),
            patch(
                "maverick.library.actions.git.git_merge",
                new_callable=AsyncMock,
                return_value={"success": True, "merge_commit": "abc123"},
            ) as mock_merge,
            _mock_command_runner(),
        ):
            await _approve(
                manager=mock_manager,
                project_name="myproject",
                base="main",
                commits=["c1", "c2"],
                branch=None,
                yes=True,
                cwd=Path("/tmp/workspace"),
            )

        mock_client.bookmark_set.assert_awaited_once_with("maverick/myproject", revision="@-")
        mock_client.git_push.assert_awaited_once_with(bookmark="maverick/myproject")
        mock_merge.assert_awaited_once()
        mock_manager.teardown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approve_custom_branch(self) -> None:
        """Explicit --branch overrides default branch name."""
        mock_client = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.exists = False

        with (
            patch(
                "maverick.jj.client.JjClient",
                return_value=mock_client,
            ),
            patch(
                "maverick.library.actions.git.git_merge",
                new_callable=AsyncMock,
                return_value={"success": True, "merge_commit": "abc"},
            ),
            _mock_command_runner(),
        ):
            await _approve(
                manager=mock_manager,
                project_name="myproject",
                base="main",
                commits=["c1"],
                branch="custom/branch",
                yes=True,
                cwd=Path("/tmp/workspace"),
            )

        mock_client.bookmark_set.assert_awaited_once_with("custom/branch", revision="@-")

    @pytest.mark.asyncio
    async def test_approve_no_workspace_returns_early(self) -> None:
        """When cwd is None, approve returns with nothing to merge."""
        mock_manager = AsyncMock()
        mock_manager.exists = False

        # Should not raise — just prints "nothing to merge"
        await _approve(
            manager=mock_manager,
            project_name="myproject",
            base="main",
            commits=["c1"],
            branch=None,
            yes=True,
            cwd=None,
        )

    @pytest.mark.asyncio
    async def test_approve_push_failure_exits(self) -> None:
        """Push failure raises SystemExit with FAILURE code."""
        mock_client = AsyncMock()
        mock_client.bookmark_set.side_effect = RuntimeError("push failed")
        mock_manager = AsyncMock()
        mock_manager.exists = True

        with (
            patch(
                "maverick.jj.client.JjClient",
                return_value=mock_client,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            await _approve(
                manager=mock_manager,
                project_name="myproject",
                base="main",
                commits=["c1"],
                branch=None,
                yes=True,
                cwd=Path("/tmp/workspace"),
            )

        assert exc_info.value.code == ExitCode.FAILURE

    @pytest.mark.asyncio
    async def test_approve_merge_failure_exits(self) -> None:
        """Merge failure raises SystemExit with FAILURE code."""
        mock_client = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.exists = True

        with (
            patch(
                "maverick.jj.client.JjClient",
                return_value=mock_client,
            ),
            patch(
                "maverick.library.actions.git.git_merge",
                new_callable=AsyncMock,
                return_value={
                    "success": False,
                    "error": "merge conflict",
                },
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            await _approve(
                manager=mock_manager,
                project_name="myproject",
                base="main",
                commits=["c1"],
                branch=None,
                yes=True,
                cwd=Path("/tmp/workspace"),
            )

        assert exc_info.value.code == ExitCode.FAILURE

    @pytest.mark.asyncio
    async def test_approve_teardown_only_when_workspace_exists(
        self,
    ) -> None:
        """Teardown is skipped when manager.exists is False."""
        mock_manager = AsyncMock()
        mock_manager.exists = False

        await _approve(
            manager=mock_manager,
            project_name="myproject",
            base="main",
            commits=["c1"],
            branch=None,
            yes=True,
            cwd=None,
        )

        mock_manager.teardown.assert_not_awaited()


# ── Eject path tests ─────────────────────────────────────────────────


class TestEjectPath:
    """Tests for _eject(): push to local preview branch, keep workspace."""

    @pytest.mark.asyncio
    async def test_eject_pushes_preview_branch(self) -> None:
        """Eject pushes to maverick/preview/<project> by default."""
        mock_client = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.set_state = MagicMock()

        with patch(
            "maverick.jj.client.JjClient",
            return_value=mock_client,
        ):
            await _eject(
                manager=mock_manager,
                project_name="myproject",
                base="main",
                commits=["c1"],
                branch=None,
                cwd=Path("/tmp/workspace"),
            )

        mock_client.bookmark_set.assert_awaited_once_with(
            "maverick/preview/myproject", revision="@-"
        )
        mock_client.git_push.assert_awaited_once_with(bookmark="maverick/preview/myproject")

    @pytest.mark.asyncio
    async def test_eject_custom_branch(self) -> None:
        """Explicit --branch overrides preview branch name."""
        mock_client = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.set_state = MagicMock()

        with patch(
            "maverick.jj.client.JjClient",
            return_value=mock_client,
        ):
            await _eject(
                manager=mock_manager,
                project_name="myproject",
                base="main",
                commits=["c1"],
                branch="my/preview",
                cwd=Path("/tmp/workspace"),
            )

        mock_client.bookmark_set.assert_awaited_once_with("my/preview", revision="@-")

    @pytest.mark.asyncio
    async def test_eject_sets_workspace_state_to_ejected(self) -> None:
        """Eject sets workspace state to EJECTED."""
        from maverick.workspace.models import WorkspaceState

        mock_client = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.set_state = MagicMock()

        with patch(
            "maverick.jj.client.JjClient",
            return_value=mock_client,
        ):
            await _eject(
                manager=mock_manager,
                project_name="myproject",
                base="main",
                commits=["c1"],
                branch=None,
                cwd=Path("/tmp/workspace"),
            )

        mock_manager.set_state.assert_called_once_with(WorkspaceState.EJECTED)

    @pytest.mark.asyncio
    async def test_eject_does_not_teardown(self) -> None:
        """Eject never tears down the workspace."""
        mock_client = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.set_state = MagicMock()

        with patch(
            "maverick.jj.client.JjClient",
            return_value=mock_client,
        ):
            await _eject(
                manager=mock_manager,
                project_name="myproject",
                base="main",
                commits=["c1"],
                branch=None,
                cwd=Path("/tmp/workspace"),
            )

        mock_manager.teardown.assert_not_called()

    @pytest.mark.asyncio
    async def test_eject_push_failure_exits(self) -> None:
        """Eject push failure raises SystemExit."""
        mock_client = AsyncMock()
        mock_client.bookmark_set.side_effect = RuntimeError("network error")
        mock_manager = AsyncMock()

        with (
            patch(
                "maverick.jj.client.JjClient",
                return_value=mock_client,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            await _eject(
                manager=mock_manager,
                project_name="myproject",
                base="main",
                commits=["c1"],
                branch=None,
                cwd=Path("/tmp/workspace"),
            )

        assert exc_info.value.code == ExitCode.FAILURE

    @pytest.mark.asyncio
    async def test_eject_no_workspace_returns_early(self) -> None:
        """When cwd is None, eject returns with nothing to do."""
        mock_manager = AsyncMock()

        # Should not raise
        await _eject(
            manager=mock_manager,
            project_name="myproject",
            base="main",
            commits=["c1"],
            branch=None,
            cwd=None,
        )


# ── Finalize path tests ──────────────────────────────────────────────


class TestFinalizePath:
    """Tests for _finalize(): merge preview branch locally, cleanup."""

    @pytest.mark.asyncio
    async def test_finalize_merges_locally(self) -> None:
        """Finalize merges preview branch into current branch."""
        mock_manager = AsyncMock()
        mock_manager.exists = False

        with (
            patch(
                "maverick.library.actions.git.git_merge",
                new_callable=AsyncMock,
                return_value={
                    "success": True,
                    "merge_commit": "abc123",
                },
            ) as mock_merge,
            patch(
                "maverick.workspace.manager.WorkspaceManager",
                return_value=mock_manager,
            ),
            patch("maverick.cli.commands.land.Path") as mock_path,
            _mock_command_runner(),
        ):
            mock_path.cwd.return_value.resolve.return_value = Path("/home/user/myproject")
            await _finalize(base="main", branch=None)

        mock_merge.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_finalize_custom_branch(self) -> None:
        """Explicit --branch overrides default preview branch."""
        mock_manager = AsyncMock()
        mock_manager.exists = False

        with (
            patch(
                "maverick.library.actions.git.git_merge",
                new_callable=AsyncMock,
                return_value={"success": True, "merge_commit": "x"},
            ),
            patch(
                "maverick.workspace.manager.WorkspaceManager",
                return_value=mock_manager,
            ),
            patch("maverick.cli.commands.land.Path") as mock_path,
            _mock_command_runner(),
        ):
            mock_path.cwd.return_value.resolve.return_value = Path("/home/user/proj")
            # Should not raise — custom branch accepted
            await _finalize(base="main", branch="my/custom-branch")

    @pytest.mark.asyncio
    async def test_finalize_tears_down_workspace_if_exists(self) -> None:
        """Finalize tears down workspace when it exists."""
        mock_manager = AsyncMock()
        mock_manager.exists = True

        with (
            patch(
                "maverick.library.actions.git.git_merge",
                new_callable=AsyncMock,
                return_value={"success": True, "merge_commit": "x"},
            ),
            patch(
                "maverick.workspace.manager.WorkspaceManager",
                return_value=mock_manager,
            ),
            patch("maverick.cli.commands.land.Path") as mock_path,
            _mock_command_runner(),
        ):
            mock_path.cwd.return_value.resolve.return_value = Path("/home/user/proj")
            await _finalize(base="main", branch=None)

        mock_manager.teardown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_finalize_skips_teardown_when_no_workspace(self) -> None:
        """Finalize skips teardown when workspace doesn't exist."""
        mock_manager = AsyncMock()
        mock_manager.exists = False

        with (
            patch(
                "maverick.library.actions.git.git_merge",
                new_callable=AsyncMock,
                return_value={"success": True, "merge_commit": "x"},
            ),
            patch(
                "maverick.workspace.manager.WorkspaceManager",
                return_value=mock_manager,
            ),
            patch("maverick.cli.commands.land.Path") as mock_path,
            _mock_command_runner(),
        ):
            mock_path.cwd.return_value.resolve.return_value = Path("/home/user/proj")
            await _finalize(base="main", branch=None)

        mock_manager.teardown.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_finalize_merge_failure_exits(self) -> None:
        """Finalize raises SystemExit when merge fails."""
        mock_manager = AsyncMock()
        mock_manager.exists = False

        with (
            patch(
                "maverick.library.actions.git.git_merge",
                new_callable=AsyncMock,
                return_value={
                    "success": False,
                    "error": "conflict",
                },
            ),
            patch(
                "maverick.workspace.manager.WorkspaceManager",
                return_value=mock_manager,
            ),
            patch("maverick.cli.commands.land.Path") as mock_path,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_path.cwd.return_value.resolve.return_value = Path("/home/user/proj")
            await _finalize(base="main", branch=None)

        assert exc_info.value.code == ExitCode.FAILURE


# ── Display plan tests ───────────────────────────────────────────────


class TestDisplayPlan:
    """Tests for _display_plan() Rich rendering."""

    def test_renders_plan_steps(self) -> None:
        """Plan steps are rendered without errors."""
        plan: list[dict[str, Any]] = [
            {
                "command": "squash",
                "args": ["-r", "abc123"],
                "reason": "Merge WIP commits",
            },
            {
                "command": "describe",
                "args": ["-m", "feat: add feature"],
                "reason": "Clean commit message",
            },
        ]
        # Should not raise
        _display_plan(plan)

    def test_handles_empty_plan(self) -> None:
        """Empty plan renders without error."""
        _display_plan([])

    def test_handles_step_without_args(self) -> None:
        """Plan step with no args key renders gracefully."""
        plan: list[dict[str, Any]] = [
            {"command": "absorb", "reason": "Absorb changes"},
        ]
        _display_plan(plan)

    def test_handles_step_without_reason(self) -> None:
        """Plan step with no reason key renders gracefully."""
        plan: list[dict[str, Any]] = [
            {"command": "squash", "args": ["-r", "xyz"]},
        ]
        _display_plan(plan)
