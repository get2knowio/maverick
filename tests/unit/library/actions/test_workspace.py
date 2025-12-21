"""Unit tests for workspace initialization actions.

Tests the workspace.py action module including:
- init_workspace action with branch creation and checkout
- Workspace cleanliness validation
- Task file auto-detection
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from subprocess import CalledProcessError

import pytest

from maverick.library.actions.workspace import init_workspace


class TestInitWorkspace:
    """Tests for init_workspace action."""

    @pytest.mark.asyncio
    async def test_creates_new_branch_when_does_not_exist(self, tmp_path: Path) -> None:
        """Test creates new branch when it doesn't exist."""
        branch_name = "feature/new-feature"

        with patch("maverick.library.actions.workspace.subprocess.run") as mock_run:
            # First call: git rev-parse (branch doesn't exist)
            # Second call: git checkout -b
            # Third call: git status --porcelain
            mock_run.side_effect = [
                MagicMock(returncode=1),  # Branch doesn't exist
                MagicMock(returncode=0),  # Checkout -b success
                MagicMock(returncode=0, stdout=""),  # Status clean
            ]

            result = await init_workspace(branch_name)

            assert result["branch_name"] == branch_name
            assert result["base_branch"] == "main"
            assert result["is_clean"] is True
            assert result["synced_with_base"] is True

            # Verify git checkout -b was called
            checkout_call = mock_run.call_args_list[1]
            assert checkout_call[0][0] == ["git", "checkout", "-b", branch_name]

    @pytest.mark.asyncio
    async def test_checks_out_existing_branch(self, tmp_path: Path) -> None:
        """Test checks out existing branch instead of creating new one."""
        branch_name = "feature/existing"

        with patch("maverick.library.actions.workspace.subprocess.run") as mock_run:
            # First call: git rev-parse (branch exists)
            # Second call: git checkout
            # Third call: git status --porcelain
            mock_run.side_effect = [
                MagicMock(returncode=0),  # Branch exists
                MagicMock(returncode=0),  # Checkout success
                MagicMock(returncode=0, stdout=""),  # Status clean
            ]

            result = await init_workspace(branch_name)

            assert result["branch_name"] == branch_name

            # Verify git checkout was called (not checkout -b)
            checkout_call = mock_run.call_args_list[1]
            assert checkout_call[0][0] == ["git", "checkout", branch_name]

    @pytest.mark.asyncio
    async def test_detects_clean_workspace(self, tmp_path: Path) -> None:
        """Test detects when workspace is clean."""
        branch_name = "feature/test"

        with patch("maverick.library.actions.workspace.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # Branch exists
                MagicMock(returncode=0),  # Checkout success
                MagicMock(returncode=0, stdout=""),  # Status clean (empty output)
            ]

            result = await init_workspace(branch_name)

            assert result["is_clean"] is True

    @pytest.mark.asyncio
    async def test_detects_dirty_workspace(self, tmp_path: Path) -> None:
        """Test detects when workspace has uncommitted changes."""
        branch_name = "feature/test"

        with patch("maverick.library.actions.workspace.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # Branch exists
                MagicMock(returncode=0),  # Checkout success
                MagicMock(returncode=0, stdout=" M src/file.py\n ?? new_file.py\n"),  # Dirty
            ]

            result = await init_workspace(branch_name)

            assert result["is_clean"] is False

    @pytest.mark.asyncio
    async def test_auto_detects_task_file_in_specs_directory(self, tmp_path: Path) -> None:
        """Test auto-detects task file in specs/{branch_name}/tasks.md."""
        import os

        branch_name = "026-dsl-builtin-workflows"

        # Create the task file
        specs_dir = tmp_path / "specs" / branch_name
        specs_dir.mkdir(parents=True, exist_ok=True)
        task_file = specs_dir / "tasks.md"
        task_file.write_text("- [ ] Task 1")

        # Change to tmp directory so file paths work
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            with patch("maverick.library.actions.workspace.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # Branch exists
                    MagicMock(returncode=0),  # Checkout success
                    MagicMock(returncode=0, stdout=""),  # Status clean
                ]

                result = await init_workspace(branch_name)

                assert result["task_file_path"] == f"specs/{branch_name}/tasks.md"
        finally:
            os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auto_detects_task_file_in_specify_directory(self, tmp_path: Path) -> None:
        """Test auto-detects task file in .specify/{branch_name}/tasks.md."""
        import os

        branch_name = "feature-test"

        # Create the task file
        specify_dir = tmp_path / ".specify" / branch_name
        specify_dir.mkdir(parents=True, exist_ok=True)
        task_file = specify_dir / "tasks.md"
        task_file.write_text("- [ ] Task 1")

        # Change to tmp directory so file paths work
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            with patch("maverick.library.actions.workspace.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # Branch exists
                    MagicMock(returncode=0),  # Checkout success
                    MagicMock(returncode=0, stdout=""),  # Status clean
                ]

                result = await init_workspace(branch_name)

                assert result["task_file_path"] == f".specify/{branch_name}/tasks.md"
        finally:
            os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_auto_detects_task_file_in_root(self, tmp_path: Path) -> None:
        """Test auto-detects task file in root tasks.md as fallback."""
        import os

        branch_name = "feature-test"

        # Create the task file in root
        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] Task 1")

        # Change to tmp directory so file paths work
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            with patch("maverick.library.actions.workspace.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # Branch exists
                    MagicMock(returncode=0),  # Checkout success
                    MagicMock(returncode=0, stdout=""),  # Status clean
                ]

                result = await init_workspace(branch_name)

                assert result["task_file_path"] == "tasks.md"
        finally:
            os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_returns_none_when_no_task_file_found(self, tmp_path: Path) -> None:
        """Test returns None for task_file_path when no task file exists."""
        branch_name = "feature-test"

        with (
            patch("maverick.library.actions.workspace.subprocess.run") as mock_run,
            patch("pathlib.Path") as mock_path_class,
        ):
            mock_run.side_effect = [
                MagicMock(returncode=0),  # Branch exists
                MagicMock(returncode=0),  # Checkout success
                MagicMock(returncode=0, stdout=""),  # Status clean
            ]

            # Mock Path to simulate no files exist
            def path_factory(path_str):
                mock_p = MagicMock(spec=Path)
                mock_p.__str__ = lambda s: path_str
                mock_p.exists.return_value = False
                return mock_p

            mock_path_class.side_effect = path_factory

            result = await init_workspace(branch_name)

            assert result["task_file_path"] is None

    @pytest.mark.asyncio
    async def test_handles_git_errors_gracefully(self, tmp_path: Path) -> None:
        """Test handles git command errors gracefully."""
        branch_name = "feature/test"

        with patch("maverick.library.actions.workspace.subprocess.run") as mock_run:
            mock_run.side_effect = CalledProcessError(
                returncode=1,
                cmd=["git", "checkout", "-b", branch_name],
                stderr="fatal: not a git repository",
            )

            result = await init_workspace(branch_name)

            assert result["branch_name"] == branch_name
            assert result["is_clean"] is False
            assert result["synced_with_base"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_returns_correct_base_branch(self, tmp_path: Path) -> None:
        """Test always returns 'main' as base_branch."""
        branch_name = "feature/test"

        with patch("maverick.library.actions.workspace.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # Branch exists
                MagicMock(returncode=0),  # Checkout success
                MagicMock(returncode=0, stdout=""),  # Status clean
            ]

            result = await init_workspace(branch_name)

            assert result["base_branch"] == "main"

    @pytest.mark.asyncio
    async def test_returns_synced_with_base_true(self, tmp_path: Path) -> None:
        """Test returns synced_with_base as True (simplified implementation)."""
        branch_name = "feature/test"

        with patch("maverick.library.actions.workspace.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # Branch exists
                MagicMock(returncode=0),  # Checkout success
                MagicMock(returncode=0, stdout=""),  # Status clean
            ]

            result = await init_workspace(branch_name)

            # Current simplified implementation always returns True
            assert result["synced_with_base"] is True
