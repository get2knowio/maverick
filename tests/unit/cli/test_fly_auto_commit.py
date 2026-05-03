"""Tests for fly's --auto-commit path against jj vs plain-git repos.

The fly workflow's snapshot step runs through
:func:`maverick.library.actions.jj.snapshot_uncommitted_changes`, which
detects which VCS the cwd has and dispatches accordingly. Earlier
revisions wired ``jj diff --stat`` straight into the workflow, which
crashed on plain-git user repos (the sample-maverick-project case) and
on any non-colocated maverick project.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.library.actions.jj import (
    _is_jj_repo,
    snapshot_uncommitted_changes,
)

# ── Detection ─────────────────────────────────────────────────────


def test_is_jj_repo_true_when_jj_dir_present(tmp_path: Path) -> None:
    (tmp_path / ".jj").mkdir()
    assert _is_jj_repo(tmp_path) is True


def test_is_jj_repo_true_for_subdirectory(tmp_path: Path) -> None:
    """``.jj`` resolution walks up the tree like jj itself."""
    (tmp_path / ".jj").mkdir()
    sub = tmp_path / "src" / "deep"
    sub.mkdir(parents=True)
    assert _is_jj_repo(sub) is True


def test_is_jj_repo_false_for_plain_git(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert _is_jj_repo(tmp_path) is False


def test_is_jj_repo_false_for_empty_dir(tmp_path: Path) -> None:
    assert _is_jj_repo(tmp_path) is False


# ── Plain-git snapshot path ────────────────────────────────────────


@pytest.mark.asyncio
async def test_plain_git_snapshot_no_changes(tmp_path: Path) -> None:
    """Empty plain-git working tree → committed=False, success=True."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

    result = await snapshot_uncommitted_changes(cwd=tmp_path)

    assert result.success is True
    assert result.committed is False


@pytest.mark.asyncio
async def test_plain_git_snapshot_with_changes(tmp_path: Path) -> None:
    """Plain-git tree with uncommitted edits → ``git add -A && git commit``
    runs and produces a HEAD sha."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

    # Introduce an uncommitted change.
    (tmp_path / "README.md").write_text("hello world\n")
    (tmp_path / "new.txt").write_text("untracked\n")

    result = await snapshot_uncommitted_changes(
        message="chore: snapshot",
        cwd=tmp_path,
    )

    assert result.success is True
    assert result.committed is True
    assert result.commit_sha
    # New content should now be in HEAD.
    log = subprocess.run(
        ["git", "log", "-1", "--name-only", "--pretty=format:"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "README.md" in log.stdout
    assert "new.txt" in log.stdout


# ── jj dispatch ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jj_repo_dispatches_to_jj_snapshot(tmp_path: Path) -> None:
    """When ``.jj/`` is present, snapshot_uncommitted_changes must route
    through jj_snapshot_changes — not the plain-git path."""
    (tmp_path / ".jj").mkdir()

    with patch(
        "maverick.library.actions.jj.jj_snapshot_changes",
        new=AsyncMock(),
    ) as mock_jj:
        from maverick.library.actions.git_models import SnapshotResult

        mock_jj.return_value = SnapshotResult(success=True, committed=False)
        await snapshot_uncommitted_changes(cwd=tmp_path)

    mock_jj.assert_awaited_once()
    kwargs = mock_jj.await_args.kwargs
    assert kwargs["cwd"] == tmp_path.resolve()
