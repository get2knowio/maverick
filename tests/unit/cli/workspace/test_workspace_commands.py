"""Unit tests for ``maverick workspace`` CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from maverick.cli.commands.workspace import workspace
from maverick.workspace.models import WorkspaceState


class TestWorkspaceGroup:
    """Tests for the workspace command group."""

    def test_workspace_help(self) -> None:
        """Workspace group shows help with subcommands."""
        runner = CliRunner()
        result = runner.invoke(workspace, ["--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "clean" in result.output

    def test_workspace_no_subcommand_shows_help(self) -> None:
        """Running 'workspace' without subcommand shows usage."""
        runner = CliRunner()
        result = runner.invoke(workspace, [])
        assert result.exit_code == 0
        assert "Usage:" in result.output


class TestWorkspaceStatus:
    """Tests for 'maverick workspace status'."""

    def test_status_no_workspace(self) -> None:
        """Shows warning when no workspace exists."""
        mock_manager = MagicMock()
        mock_manager.exists = False
        mock_manager.workspace_path = Path(
            "/home/user/.maverick/workspaces/proj"
        )

        with patch(
            "maverick.workspace.manager.WorkspaceManager",
            return_value=mock_manager,
        ):
            runner = CliRunner()
            result = runner.invoke(workspace, ["status"])

        assert result.exit_code == 0
        assert "no workspace" in result.output.lower()

    def test_status_active_workspace(self) -> None:
        """Shows workspace info when workspace exists."""
        mock_manager = MagicMock()
        mock_manager.exists = True
        mock_manager.workspace_path = Path(
            "/home/user/.maverick/workspaces/proj"
        )
        mock_manager.get_state.return_value = WorkspaceState.ACTIVE

        with patch(
            "maverick.workspace.manager.WorkspaceManager",
            return_value=mock_manager,
        ):
            runner = CliRunner()
            result = runner.invoke(workspace, ["status"])

        assert result.exit_code == 0
        assert "active" in result.output.lower()

    def test_status_ejected_workspace(self) -> None:
        """Shows ejected state for ejected workspace."""
        mock_manager = MagicMock()
        mock_manager.exists = True
        mock_manager.workspace_path = Path(
            "/home/user/.maverick/workspaces/proj"
        )
        mock_manager.get_state.return_value = WorkspaceState.EJECTED

        with patch(
            "maverick.workspace.manager.WorkspaceManager",
            return_value=mock_manager,
        ):
            runner = CliRunner()
            result = runner.invoke(workspace, ["status"])

        assert result.exit_code == 0
        assert "ejected" in result.output.lower()


class TestWorkspaceClean:
    """Tests for 'maverick workspace clean'."""

    def test_clean_help(self) -> None:
        """Clean subcommand shows help text."""
        runner = CliRunner()
        result = runner.invoke(workspace, ["clean", "--help"])
        assert result.exit_code == 0
        assert "--yes" in result.output
        assert "-y" in result.output

    def test_clean_no_workspace(self) -> None:
        """Shows warning when no workspace exists."""
        mock_manager = MagicMock()
        mock_manager.exists = False

        with patch(
            "maverick.workspace.manager.WorkspaceManager",
            return_value=mock_manager,
        ):
            runner = CliRunner()
            result = runner.invoke(workspace, ["clean", "--yes"])

        assert result.exit_code == 0
        assert "no workspace" in result.output.lower()

    def test_clean_with_yes_flag(self) -> None:
        """--yes skips confirmation and cleans up."""
        mock_manager = AsyncMock()
        mock_manager.exists = True
        mock_manager.workspace_path = Path(
            "/home/user/.maverick/workspaces/proj"
        )

        with patch(
            "maverick.workspace.manager.WorkspaceManager",
            return_value=mock_manager,
        ):
            runner = CliRunner()
            result = runner.invoke(workspace, ["clean", "--yes"])

        assert result.exit_code == 0
        assert "cleaned up" in result.output.lower()
