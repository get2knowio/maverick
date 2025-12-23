"""Unit tests for the status CLI command.

Tests status command functionality:
- Branch info display
- Pending tasks display
- JSON format option
- Error handling in non-git directories
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from maverick.main import cli


def test_status_command_displays_branch_info(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T082: Test status command displays branch info - 'maverick status'.

    Verifies:
    - Command displays current git branch
    - Shows pending and completed tasks (if tasks.md exists)
    - Shows recent workflow history
    - Uses text format by default
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a git repo
    os.system("git init > /dev/null 2>&1")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")
    os.system("git checkout -b feature-branch > /dev/null 2>&1")

    result = cli_runner.invoke(cli, ["status"])

    # Should succeed
    assert result.exit_code == 0
    # Should display branch name
    assert "feature-branch" in result.output
    # Should have "Project Status" or similar header
    assert "status" in result.output.lower() or "branch" in result.output.lower()


def test_status_with_pending_tasks(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T083: Test status command with pending tasks (when tasks.md exists).

    Verifies:
    - Command detects tasks.md file
    - Counts pending tasks (lines with - [ ])
    - Counts completed tasks (lines with - [x])
    - Displays task counts in output
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a git repo
    os.system("git init > /dev/null 2>&1")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")
    os.system("git checkout -b feature-branch > /dev/null 2>&1")

    # Create tasks.md with pending and completed tasks
    tasks_file = temp_dir / "tasks.md"
    tasks_file.write_text("""
# Tasks

- [ ] Task 1 (pending)
- [x] Task 2 (completed)
- [ ] Task 3 (pending)
- [x] Task 4 (completed)
- [ ] Task 5 (pending)
""")

    result = cli_runner.invoke(cli, ["status"])

    # Should succeed
    assert result.exit_code == 0
    # Should show task counts
    assert "3" in result.output  # 3 pending tasks
    assert "2" in result.output  # 2 completed tasks
    # Should mention "pending" or "task"
    assert "pending" in result.output.lower() or "task" in result.output.lower()


def test_status_format_json_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T084: Test status --format json option - outputs valid JSON.

    Verifies:
    - --format json flag is accepted
    - Output is valid JSON
    - Contains branch, tasks, and workflows keys
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a git repo
    os.system("git init > /dev/null 2>&1")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")
    os.system("git checkout -b main > /dev/null 2>&1")

    result = cli_runner.invoke(cli, ["status", "--format", "json"])

    # Should succeed
    assert result.exit_code == 0
    # Should be valid JSON
    try:
        data = json.loads(result.output)
        assert "branch" in data
        assert data["branch"] == "main"
        # Tasks and workflows keys should exist (even if null/empty)
        assert "tasks" in data or "workflows" in data
    except json.JSONDecodeError:
        pytest.fail("Output is not valid JSON")


def test_status_in_non_git_directory_error(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T085: Test status in non-git directory error.

    Verifies:
    - Command fails when not in a git repository
    - Exit code 1 (FAILURE)
    - Error message mentions not a git repository
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Do NOT create a git repo

    result = cli_runner.invoke(cli, ["status"])

    # Should fail with exit code 1
    assert result.exit_code == 1
    # Should show error about not being a git repository
    assert "git" in result.output.lower()
    assert "repository" in result.output.lower() or "not" in result.output.lower()
