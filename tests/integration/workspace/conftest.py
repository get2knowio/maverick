"""Shared fixtures for `tests/integration/workspace/`.

A real, throwaway jj-colocated checkout plus a `home=` override — this
repository is not itself jj-colocated, so every jj integration test needs
its own scratch fixture (tasks.md's Path Conventions), and no test here may
write under the developer's real ``~/.maverick/workspaces``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from maverick.jj.client import JjClient


def _run(cmd: list[str], *, cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def colocated_repo(tmp_path: Path) -> JjClient:
    """A real, jj-colocated checkout with tracked files and a gitignored
    path, returned as a `JjClient` bound to it.

    Seeds:
    - `tracked.txt`, `README.md` — ordinary tracked files.
    - `ignored-build/artifact.bin` — a gitignored path (`ignored-build/`),
      to exercise fold-back's ignored-path exclusion (FR-010).
    - `.maverick/runs/.keep` — the orchestrator-state directory fold-back
      must always exclude regardless of the fileset (FR-011).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], cwd=repo)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "Test"], cwd=repo)
    _run(["jj", "git", "init", "--colocate"], cwd=repo)

    (repo / ".gitignore").write_text(
        "ignored-build/\n*.jsonl\n.maverick/\n.beads/\n", encoding="utf-8"
    )
    (repo / "README.md").write_text("# repo\n", encoding="utf-8")
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")

    ignored_dir = repo / "ignored-build"
    ignored_dir.mkdir()
    (ignored_dir / "artifact.bin").write_text("artifact\n", encoding="utf-8")

    maverick_runs = repo / ".maverick" / "runs"
    maverick_runs.mkdir(parents=True)
    (maverick_runs / ".keep").write_text("", encoding="utf-8")

    _run(["jj", "commit", "-m", "initial checkout"], cwd=repo)

    return JjClient(cwd=repo)


@pytest.fixture
def isolation_home(tmp_path: Path) -> Path:
    """A throwaway ``home=`` override so no test writes under the
    developer's real ``~/.maverick/workspaces``."""
    home = tmp_path / "fake-home"
    home.mkdir()
    return home
