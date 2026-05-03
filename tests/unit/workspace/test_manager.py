"""Tests for the lean :class:`WorkspaceManager`.

These tests exercise the colocate + ``jj workspace add`` lifecycle
against real on-disk git repos created in pytest's ``tmp_path``. The
``jj`` binary is required on PATH (the surrounding maverick CI image
provides it). Tests skip cleanly when jj is unavailable.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from maverick.jj.errors import JjError
from maverick.workspace import WorkspaceManager

pytestmark = pytest.mark.skipif(
    shutil.which("jj") is None,
    reason="jj binary not on PATH",
)


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=path,
        check=True,
    )
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


@pytest.fixture
def user_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "user-repo"
    _init_git_repo(repo)
    return repo


@pytest.fixture
def workspaces_root(tmp_path: Path) -> Path:
    return tmp_path / "ws-root"


# ── colocate ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_colocated_creates_jj_dir(user_repo: Path, workspaces_root: Path) -> None:
    manager = WorkspaceManager(user_repo_path=user_repo, workspaces_root=workspaces_root)
    assert not (user_repo / ".jj").exists()

    await manager.ensure_colocated()

    assert (user_repo / ".jj").exists()
    assert manager.is_colocated()


@pytest.mark.asyncio
async def test_ensure_colocated_idempotent(user_repo: Path, workspaces_root: Path) -> None:
    manager = WorkspaceManager(user_repo_path=user_repo, workspaces_root=workspaces_root)
    await manager.ensure_colocated()
    # Second call must succeed without error.
    await manager.ensure_colocated()
    assert manager.is_colocated()


@pytest.mark.asyncio
async def test_ensure_colocated_rejects_non_git(tmp_path: Path, workspaces_root: Path) -> None:
    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    manager = WorkspaceManager(user_repo_path=bare, workspaces_root=workspaces_root)
    with pytest.raises(JjError, match="not a git repo"):
        await manager.ensure_colocated()


# ── workspace lifecycle ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_or_create_creates_workspace(user_repo: Path, workspaces_root: Path) -> None:
    manager = WorkspaceManager(user_repo_path=user_repo, workspaces_root=workspaces_root)
    assert not manager.exists

    workspace_path = await manager.find_or_create()

    assert workspace_path == manager.workspace_path
    assert manager.exists
    assert (workspace_path / ".jj").exists()
    # The shared backing repo means the user repo also got colocated.
    assert (user_repo / ".jj").exists()


@pytest.mark.asyncio
async def test_find_or_create_idempotent(user_repo: Path, workspaces_root: Path) -> None:
    manager = WorkspaceManager(user_repo_path=user_repo, workspaces_root=workspaces_root)
    first = await manager.find_or_create()
    second = await manager.find_or_create()
    assert first == second
    assert manager.exists


@pytest.mark.asyncio
async def test_workspace_shares_backing_repo(user_repo: Path, workspaces_root: Path) -> None:
    """A commit made in the workspace must be visible from the user
    repo's ``jj log`` (proof that the backing op log is shared)."""
    manager = WorkspaceManager(user_repo_path=user_repo, workspaces_root=workspaces_root)
    workspace_path = await manager.find_or_create()

    (workspace_path / "feature.txt").write_text("from workspace\n")
    subprocess.run(
        ["jj", "commit", "-m", "ws: add feature.txt"],
        cwd=workspace_path,
        check=True,
    )

    user_log = subprocess.run(
        ["jj", "log", "-r", "all()", "--no-graph", "-T", "description"],
        cwd=user_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ws: add feature.txt" in user_log.stdout


# ── teardown ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_teardown_removes_workspace(user_repo: Path, workspaces_root: Path) -> None:
    manager = WorkspaceManager(user_repo_path=user_repo, workspaces_root=workspaces_root)
    workspace_path = await manager.find_or_create()
    assert workspace_path.exists()

    await manager.teardown()

    assert not workspace_path.exists()
    assert not manager.exists


@pytest.mark.asyncio
async def test_teardown_noop_when_workspace_absent(user_repo: Path, workspaces_root: Path) -> None:
    manager = WorkspaceManager(user_repo_path=user_repo, workspaces_root=workspaces_root)
    # Must not raise.
    await manager.teardown()


@pytest.mark.asyncio
async def test_teardown_preserves_committed_history(
    user_repo: Path, workspaces_root: Path
) -> None:
    """Workspace teardown does NOT undo commits in the shared op log
    — they remain visible from the user repo."""
    manager = WorkspaceManager(user_repo_path=user_repo, workspaces_root=workspaces_root)
    workspace_path = await manager.find_or_create()
    (workspace_path / "feature.txt").write_text("from workspace\n")
    subprocess.run(
        ["jj", "commit", "-m", "ws: add feature.txt"],
        cwd=workspace_path,
        check=True,
    )

    await manager.teardown()

    user_log = subprocess.run(
        ["jj", "log", "-r", "all()", "--no-graph", "-T", "description"],
        cwd=user_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ws: add feature.txt" in user_log.stdout
