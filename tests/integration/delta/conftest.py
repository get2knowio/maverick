"""Shared fixtures for delta-layer integration tests.

Mirrors ``tests/integration/test_speckit_refuel.py``'s pattern: skip
entirely when ``bd`` isn't on PATH, provide a real initialized ``bd``
database in a tmp directory.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

if shutil.which("bd") is None:
    pytest.skip("bd CLI not available on PATH", allow_module_level=True)

_SPEC_MD = """\
# Feature Specification: Delta Integration Sample

### Functional Requirements

- **FR-002**: The gate MUST evaluate the frontier before curating.
- **FR-021**: The gate MUST offer a `--force` bypass for operators.

### Key Entities
"""

_TASKS_MD = """\
## Phase 1: Setup

- [ ] T017 An in-flight task in src/x.py
- [ ] T019 A closed task in src/y.py
- [ ] T020 An open, unstarted task in src/z.py
"""


@pytest.fixture
def bd_repo(tmp_path: Path) -> Path:
    """A tmp directory with a real, initialized ``bd`` database, also a
    git repo so refusal tests can snapshot ``git status --porcelain``."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(
        ["bd", "init", "--non-interactive"], cwd=tmp_path, check=True, capture_output=True
    )
    return tmp_path


def make_feature_dir(cwd: Path, name: str = "052-conditional-landing") -> Path:
    feature_dir = cwd / "specs" / name
    (feature_dir / "deltas").mkdir(parents=True)
    (feature_dir / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    (feature_dir / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    return feature_dir


def git_commit_all(cwd: Path, message: str = "initial") -> None:
    subprocess.run(["git", "add", "-A"], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", message], cwd=cwd, check=True, capture_output=True
    )


def git_status_porcelain(cwd: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout
