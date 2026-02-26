"""Unit tests for WorkspaceManager."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.jj.client import JjClient
from maverick.jj.errors import JjError
from maverick.jj.models import JjCloneResult, JjFetchResult
from maverick.runners.models import CommandResult
from maverick.workspace.errors import (
    WorkspaceBootstrapError,
    WorkspaceCloneError,
    WorkspaceError,
)
from maverick.workspace.manager import WORKSPACE_META_FILE, WorkspaceManager
from maverick.workspace.models import WorkspaceState


@pytest.fixture
def user_repo(temp_dir: Path) -> Path:
    """Create a fake user repo directory."""
    repo = temp_dir / "my-project"
    repo.mkdir()
    return repo


@pytest.fixture
def ws_root(temp_dir: Path) -> Path:
    """Create a workspace root directory."""
    root = temp_dir / "workspaces"
    root.mkdir()
    return root


@pytest.fixture
def manager(user_repo: Path, ws_root: Path) -> WorkspaceManager:
    """Create a WorkspaceManager for testing."""
    return WorkspaceManager(
        user_repo_path=user_repo,
        workspace_root=ws_root,
        setup_command="echo ok",
    )


class TestWorkspaceManagerProperties:
    """Tests for WorkspaceManager properties."""

    def test_workspace_path(
        self, user_repo: Path, ws_root: Path, manager: WorkspaceManager
    ) -> None:
        assert manager.workspace_path == ws_root.resolve() / "my-project"

    def test_exists_false_initially(self, manager: WorkspaceManager) -> None:
        assert manager.exists is False

    def test_exists_true_when_dir_present(self, manager: WorkspaceManager) -> None:
        manager.workspace_path.mkdir(parents=True)
        assert manager.exists is True


class TestWorkspaceManagerCreate:
    """Tests for WorkspaceManager.create()."""

    @pytest.mark.asyncio
    async def test_create_clones_repo(
        self, manager: WorkspaceManager, user_repo: Path
    ) -> None:
        mock_client = AsyncMock(spec=JjClient)
        mock_client.git_clone.return_value = JjCloneResult(
            success=True,
            workspace_path=str(manager.workspace_path),
        )

        with patch("maverick.workspace.manager.JjClient", return_value=mock_client):
            # We need to create the workspace dir since jj_clone would do it
            manager.workspace_path.mkdir(parents=True, exist_ok=True)
            info = await manager.create()

        assert info.workspace_path == str(manager.workspace_path)
        assert info.user_repo_path == str(user_repo.resolve())
        assert info.state == WorkspaceState.ACTIVE.value
        assert info.created_at != ""

        mock_client.git_clone.assert_called_once_with(
            source=user_repo.resolve(),
            target=manager.workspace_path,
        )

    @pytest.mark.asyncio
    async def test_create_idempotent(
        self, manager: WorkspaceManager, user_repo: Path
    ) -> None:
        """If workspace + metadata already exist, skip clone."""
        # Pre-create workspace with metadata
        ws = manager.workspace_path
        ws.mkdir(parents=True)
        meta = {
            "workspace_path": str(ws),
            "user_repo_path": str(user_repo),
            "state": "active",
            "created_at": "2026-01-01T00:00:00Z",
        }
        (ws / WORKSPACE_META_FILE).write_text(json.dumps(meta))

        info = await manager.create()

        assert info.workspace_path == str(ws)
        assert info.created_at == "2026-01-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_create_failure_raises(self, manager: WorkspaceManager) -> None:
        mock_client = AsyncMock(spec=JjClient)
        mock_client.git_clone.side_effect = JjError("clone failed")

        with (
            patch(
                "maverick.workspace.manager.JjClient",
                return_value=mock_client,
            ),
            pytest.raises(WorkspaceCloneError),
        ):
            await manager.create()


class TestWorkspaceManagerBootstrap:
    """Tests for WorkspaceManager.bootstrap()."""

    @pytest.mark.asyncio
    async def test_bootstrap_runs_setup(self, manager: WorkspaceManager) -> None:
        manager.workspace_path.mkdir(parents=True)

        mock_runner = AsyncMock()
        mock_runner.run.return_value = CommandResult(
            returncode=0, stdout="ok", stderr="", duration_ms=100
        )

        with patch(
            "maverick.workspace.manager.CommandRunner",
            return_value=mock_runner,
        ):
            result = await manager.bootstrap()

        assert result.success is True

    @pytest.mark.asyncio
    async def test_bootstrap_no_setup_command(
        self, user_repo: Path, ws_root: Path
    ) -> None:
        mgr = WorkspaceManager(
            user_repo_path=user_repo,
            workspace_root=ws_root,
            setup_command=None,
        )
        mgr.workspace_path.mkdir(parents=True)
        result = await mgr.bootstrap()
        assert result.success is True
        assert result.output == ""

    @pytest.mark.asyncio
    async def test_bootstrap_failure_raises(self, manager: WorkspaceManager) -> None:
        manager.workspace_path.mkdir(parents=True)

        mock_runner = AsyncMock()
        mock_runner.run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="command not found",
            duration_ms=50,
        )

        with (
            patch(
                "maverick.workspace.manager.CommandRunner",
                return_value=mock_runner,
            ),
            pytest.raises(WorkspaceBootstrapError),
        ):
            await manager.bootstrap()

    @pytest.mark.asyncio
    async def test_bootstrap_missing_workspace_raises(
        self, manager: WorkspaceManager
    ) -> None:
        with pytest.raises(WorkspaceError, match="does not exist"):
            await manager.bootstrap()


class TestWorkspaceManagerSync:
    """Tests for WorkspaceManager.sync_from_origin()."""

    @pytest.mark.asyncio
    async def test_sync_fetches(self, manager: WorkspaceManager) -> None:
        manager.workspace_path.mkdir(parents=True)

        mock_client = AsyncMock(spec=JjClient)
        mock_client.git_fetch.return_value = JjFetchResult(success=True)

        with patch(
            "maverick.workspace.manager.JjClient",
            return_value=mock_client,
        ):
            result = await manager.sync_from_origin()

        assert result.success is True
        mock_client.git_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_missing_workspace_raises(
        self, manager: WorkspaceManager
    ) -> None:
        with pytest.raises(WorkspaceError, match="does not exist"):
            await manager.sync_from_origin()


class TestWorkspaceManagerTeardown:
    """Tests for WorkspaceManager.teardown()."""

    @pytest.mark.asyncio
    async def test_teardown_removes_directory(self, manager: WorkspaceManager) -> None:
        ws = manager.workspace_path
        ws.mkdir(parents=True)
        (ws / "file.txt").write_text("data")

        result = await manager.teardown()

        assert result.success is True
        assert result.removed is True
        assert not ws.exists()

    @pytest.mark.asyncio
    async def test_teardown_noop_if_missing(self, manager: WorkspaceManager) -> None:
        result = await manager.teardown()

        assert result.success is True
        assert result.removed is False

    @pytest.mark.asyncio
    async def test_teardown_runs_command(self, user_repo: Path, ws_root: Path) -> None:
        mgr = WorkspaceManager(
            user_repo_path=user_repo,
            workspace_root=ws_root,
            teardown_command="echo cleanup",
        )
        mgr.workspace_path.mkdir(parents=True)

        mock_runner = AsyncMock()
        mock_runner.run.return_value = CommandResult(
            returncode=0, stdout="cleanup", stderr="", duration_ms=50
        )

        with patch(
            "maverick.workspace.manager.CommandRunner",
            return_value=mock_runner,
        ):
            result = await mgr.teardown()

        assert result.success is True
        mock_runner.run.assert_called_once()


class TestWorkspaceManagerState:
    """Tests for state management."""

    def test_get_state_none_without_meta(self, manager: WorkspaceManager) -> None:
        assert manager.get_state() is None

    def test_get_and_set_state(
        self, manager: WorkspaceManager, user_repo: Path
    ) -> None:
        ws = manager.workspace_path
        ws.mkdir(parents=True)

        # Write initial metadata
        meta = {
            "workspace_path": str(ws),
            "user_repo_path": str(user_repo),
            "state": "active",
            "created_at": "2026-01-01T00:00:00Z",
        }
        (ws / WORKSPACE_META_FILE).write_text(json.dumps(meta))

        assert manager.get_state() == WorkspaceState.ACTIVE

        manager.set_state(WorkspaceState.EJECTED)
        assert manager.get_state() == WorkspaceState.EJECTED


class TestWorkspaceManagerGetJjClient:
    """Tests for get_jj_client()."""

    def test_returns_client_with_workspace_cwd(self, manager: WorkspaceManager) -> None:
        client = manager.get_jj_client()
        assert isinstance(client, JjClient)
        assert client.cwd == manager.workspace_path
