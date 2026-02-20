"""Unit tests for workspace initialization actions.

Tests the workspace.py action module including:
- init_workspace action with branch creation and checkout
- Workspace cleanliness validation
- Task file auto-detection
- create_fly_workspace action for isolated jj workspace
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.library.actions.workspace import create_fly_workspace, init_workspace
from maverick.runners.models import CommandResult
from maverick.workspace.models import WorkspaceInfo


def make_result(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    duration_ms: float = 10.0,
    timed_out: bool = False,
) -> CommandResult:
    """Create a CommandResult for test mocking."""
    return CommandResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )


class TestInitWorkspace:
    """Tests for init_workspace action."""

    @pytest.mark.asyncio
    async def test_creates_new_branch_when_does_not_exist(self, tmp_path: Path) -> None:
        """Test creates new branch when it doesn't exist."""
        branch_name = "feature/new-feature"

        with patch("maverick.library.actions.workspace._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                side_effect=[
                    make_result(returncode=1),  # Branch doesn't exist
                    make_result(returncode=0),  # Checkout -b success
                    make_result(returncode=0, stdout=""),  # Status clean
                ]
            )

            result = await init_workspace(branch_name)

            assert result.branch_name == branch_name
            assert result.base_branch == "main"
            assert result.is_clean is True
            assert result.synced_with_base is True

            # Verify git checkout -b was called
            checkout_call = mock_runner.run.call_args_list[1]
            assert checkout_call[0][0] == ["git", "checkout", "-b", branch_name]

    @pytest.mark.asyncio
    async def test_checks_out_existing_branch(self, tmp_path: Path) -> None:
        """Test checks out existing branch instead of creating new one."""
        branch_name = "feature/existing"

        with patch("maverick.library.actions.workspace._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                side_effect=[
                    make_result(returncode=0),  # Branch exists
                    make_result(returncode=0),  # Checkout success
                    make_result(returncode=0, stdout=""),  # Status clean
                ]
            )

            result = await init_workspace(branch_name)

            assert result.branch_name == branch_name

            # Verify git checkout was called (not checkout -b)
            checkout_call = mock_runner.run.call_args_list[1]
            assert checkout_call[0][0] == ["git", "checkout", branch_name]

    @pytest.mark.asyncio
    async def test_detects_clean_workspace(self, tmp_path: Path) -> None:
        """Test detects when workspace is clean."""
        branch_name = "feature/test"

        with patch("maverick.library.actions.workspace._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                side_effect=[
                    make_result(returncode=0),  # Branch exists
                    make_result(returncode=0),  # Checkout success
                    # Status clean (empty output)
                    make_result(returncode=0, stdout=""),
                ]
            )

            result = await init_workspace(branch_name)

            assert result.is_clean is True

    async def test_detects_dirty_workspace(self, tmp_path: Path) -> None:
        """Test detects when workspace has uncommitted changes."""
        branch_name = "feature/test"

        with patch("maverick.library.actions.workspace._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                side_effect=[
                    make_result(returncode=0),  # Branch exists
                    make_result(returncode=0),  # Checkout success
                    make_result(
                        returncode=0, stdout=" M src/file.py\n ?? new_file.py\n"
                    ),  # Dirty
                ]
            )

            result = await init_workspace(branch_name)

            assert result.is_clean is False

    async def test_auto_detects_task_file_in_specs_directory(
        self, tmp_path: Path
    ) -> None:
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

            with patch("maverick.library.actions.workspace._runner") as mock_runner:
                mock_runner.run = AsyncMock(
                    side_effect=[
                        make_result(returncode=0),  # Branch exists
                        make_result(returncode=0),  # Checkout success
                        make_result(returncode=0, stdout=""),  # Status clean
                    ]
                )

                result = await init_workspace(branch_name)

                assert result.task_file_path == Path(f"specs/{branch_name}/tasks.md")
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

            with patch("maverick.library.actions.workspace._runner") as mock_runner:
                mock_runner.run = AsyncMock(
                    side_effect=[
                        make_result(returncode=0),  # Branch exists
                        make_result(returncode=0),  # Checkout success
                        make_result(returncode=0, stdout=""),  # Status clean
                    ]
                )

                result = await init_workspace(branch_name)

                assert result.task_file_path == Path("tasks.md")
        finally:
            os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_returns_none_when_no_task_file_found(self, tmp_path: Path) -> None:
        """Test returns None for task_file_path when no task file exists."""
        import os

        branch_name = "feature-test"
        original_cwd = os.getcwd()

        try:
            # Use tmp_path which has no task files
            os.chdir(tmp_path)

            with patch("maverick.library.actions.workspace._runner") as mock_runner:
                mock_runner.run = AsyncMock(
                    side_effect=[
                        make_result(returncode=0),  # Branch exists
                        make_result(returncode=0),  # Checkout success
                        make_result(returncode=0, stdout=""),  # Status clean
                    ]
                )

                result = await init_workspace(branch_name)

                # No task file in tmp_path, so should be None
                assert result.task_file_path is None
        finally:
            os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_handles_git_errors_gracefully(self, tmp_path: Path) -> None:
        """Test handles git command errors gracefully."""
        branch_name = "feature/test"

        with patch("maverick.library.actions.workspace._runner") as mock_runner:
            # Simulate a failure result from git
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    returncode=1,
                    stderr="fatal: not a git repository",
                )
            )

            result = await init_workspace(branch_name)

            assert result.branch_name == branch_name
            assert result.is_clean is False
            assert result.synced_with_base is False
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_returns_correct_base_branch(self, tmp_path: Path) -> None:
        """Test always returns 'main' as base_branch."""
        branch_name = "feature/test"

        with patch("maverick.library.actions.workspace._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                side_effect=[
                    make_result(returncode=0),  # Branch exists
                    make_result(returncode=0),  # Checkout success
                    make_result(returncode=0, stdout=""),  # Status clean
                ]
            )

            result = await init_workspace(branch_name)

            assert result.base_branch == "main"

    @pytest.mark.asyncio
    async def test_returns_synced_with_base_true(self, tmp_path: Path) -> None:
        """Test returns synced_with_base as True (simplified implementation)."""
        branch_name = "feature/test"

        with patch("maverick.library.actions.workspace._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                side_effect=[
                    make_result(returncode=0),  # Branch exists
                    make_result(returncode=0),  # Checkout success
                    make_result(returncode=0, stdout=""),  # Status clean
                ]
            )

            result = await init_workspace(branch_name)

            # Current simplified implementation always returns True
            assert result.synced_with_base is True


class TestCreateFlyWorkspace:
    """Tests for create_fly_workspace action."""

    @pytest.mark.asyncio
    async def test_creates_workspace(self, tmp_path: Path) -> None:
        """Test creates a new workspace via WorkspaceManager."""
        ws_path = tmp_path / "workspaces" / "my-project"
        mock_manager = AsyncMock()
        mock_manager.exists = False
        mock_manager.workspace_path = ws_path
        mock_manager.create_and_bootstrap.return_value = WorkspaceInfo(
            workspace_path=str(ws_path),
            user_repo_path=str(tmp_path),
            state="active",
            created_at="2026-01-01T00:00:00Z",
        )

        with (
            patch(
                "maverick.library.actions.workspace.WorkspaceManager",
                return_value=mock_manager,
            ),
            patch("maverick.library.actions.workspace.Path") as mock_path_cls,
        ):
            mock_path_cls.cwd.return_value.resolve.return_value = tmp_path
            result = await create_fly_workspace()

        assert result["success"] is True
        assert result["workspace_path"] == str(ws_path)
        assert result["user_repo_path"] == str(tmp_path)
        assert result["created"] is True
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_reuses_existing_workspace(self, tmp_path: Path) -> None:
        """Test reuses an existing workspace."""
        ws_path = tmp_path / "workspaces" / "my-project"
        mock_manager = AsyncMock()
        mock_manager.exists = True
        mock_manager.workspace_path = ws_path
        mock_manager.create_and_bootstrap.return_value = WorkspaceInfo(
            workspace_path=str(ws_path),
            user_repo_path=str(tmp_path),
            state="active",
            created_at="2026-01-01T00:00:00Z",
        )

        with (
            patch(
                "maverick.library.actions.workspace.WorkspaceManager",
                return_value=mock_manager,
            ),
            patch("maverick.library.actions.workspace.Path") as mock_path_cls,
        ):
            mock_path_cls.cwd.return_value.resolve.return_value = tmp_path
            result = await create_fly_workspace()

        assert result["success"] is True
        assert result["created"] is False

    @pytest.mark.asyncio
    async def test_passes_setup_command(self, tmp_path: Path) -> None:
        """Test passes setup_command to WorkspaceManager."""
        mock_manager = AsyncMock()
        mock_manager.exists = False
        mock_manager.workspace_path = tmp_path / "ws"
        mock_manager.create_and_bootstrap.return_value = WorkspaceInfo(
            workspace_path=str(tmp_path / "ws"),
            user_repo_path=str(tmp_path),
            state="active",
            created_at="2026-01-01T00:00:00Z",
        )

        with (
            patch(
                "maverick.library.actions.workspace.WorkspaceManager",
                return_value=mock_manager,
            ) as mock_ws_cls,
            patch("maverick.library.actions.workspace.Path") as mock_path_cls,
        ):
            mock_path_cls.cwd.return_value.resolve.return_value = tmp_path
            await create_fly_workspace(setup_command="uv sync")

        mock_ws_cls.assert_called_once_with(
            user_repo_path=tmp_path,
            setup_command="uv sync",
        )

    @pytest.mark.asyncio
    async def test_handles_failure(self, tmp_path: Path) -> None:
        """Test handles workspace creation failure."""
        with (
            patch(
                "maverick.library.actions.workspace.WorkspaceManager",
                side_effect=RuntimeError("clone failed"),
            ),
            patch("maverick.library.actions.workspace.Path") as mock_path_cls,
        ):
            mock_path_cls.cwd.return_value.resolve.return_value = tmp_path
            result = await create_fly_workspace()

        assert result["success"] is False
        assert result["workspace_path"] is None
        assert "clone failed" in result["error"]
