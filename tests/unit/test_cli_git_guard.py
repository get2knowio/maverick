"""Unit tests for CLI git helpers.

Tests dirty tree detection, current branch detection, and validation.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.cli._git import (
    derive_branch_name_hint,
    get_current_branch,
    is_working_tree_dirty,
    validate_repo_root,
)
from src.utils.git_cli import GitCommandError, GitCommandResult


def test_get_current_branch_success():
    """Test getting current branch name successfully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)

        mock_result = GitCommandResult(
            success=True,
            stdout="main\n",
            stderr="",
            returncode=0,
        )

        with patch("src.cli._git.run_git_command", return_value=mock_result):
            branch = get_current_branch(repo_root)

            assert branch == "main"


def test_get_current_branch_with_whitespace():
    """Test getting current branch trims whitespace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)

        mock_result = GitCommandResult(
            success=True,
            stdout="  feature-branch  \n",
            stderr="",
            returncode=0,
        )

        with patch("src.cli._git.run_git_command", return_value=mock_result):
            branch = get_current_branch(repo_root)

            assert branch == "feature-branch"


def test_get_current_branch_command_fails():
    """Test error handling when git command fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)

        mock_result = GitCommandResult(
            success=False,
            stdout="",
            stderr="fatal: not a git repository",
            returncode=128,
        )

        with patch("src.cli._git.run_git_command", return_value=mock_result):
            with pytest.raises(GitCommandError, match="Failed to get current branch"):
                get_current_branch(repo_root)


def test_get_current_branch_empty_output():
    """Test error handling when branch name is empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)

        mock_result = GitCommandResult(
            success=True,
            stdout="",
            stderr="",
            returncode=0,
        )

        with patch("src.cli._git.run_git_command", return_value=mock_result):
            with pytest.raises(GitCommandError, match="Current branch name is empty"):
                get_current_branch(repo_root)


def test_get_current_branch_invalid_repo_root():
    """Test error handling for invalid repo root."""
    with pytest.raises(ValueError, match="Repository root does not exist"):
        get_current_branch(Path("/nonexistent/path"))


def test_get_current_branch_repo_root_is_file():
    """Test error handling when repo root is a file."""
    with tempfile.NamedTemporaryFile() as tmpfile:
        with pytest.raises(ValueError, match="Repository root is not a directory"):
            get_current_branch(Path(tmpfile.name))


def test_is_working_tree_dirty_clean():
    """Test detecting clean working tree."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)

        mock_result = GitCommandResult(
            success=True,
            stdout="",
            stderr="",
            returncode=0,
        )

        with patch("src.cli._git.run_git_command", return_value=mock_result):
            is_dirty = is_working_tree_dirty(repo_root)

            assert is_dirty is False


def test_is_working_tree_dirty_has_changes():
    """Test detecting dirty working tree with changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)

        mock_result = GitCommandResult(
            success=True,
            stdout=" M src/file.py\n?? new_file.py\n",
            stderr="",
            returncode=0,
        )

        with patch("src.cli._git.run_git_command", return_value=mock_result):
            is_dirty = is_working_tree_dirty(repo_root)

            assert is_dirty is True


def test_is_working_tree_dirty_command_fails():
    """Test error handling when git status fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)

        mock_result = GitCommandResult(
            success=False,
            stdout="",
            stderr="fatal: not a git repository",
            returncode=128,
        )

        with patch("src.cli._git.run_git_command", return_value=mock_result), pytest.raises(
            GitCommandError, match="Failed to check working tree status"
        ):
            is_working_tree_dirty(repo_root)


def test_is_working_tree_dirty_invalid_repo_root():
    """Test error handling for invalid repo root."""
    with pytest.raises(ValueError, match="Repository root does not exist"):
        is_working_tree_dirty(Path("/nonexistent/path"))


def test_validate_repo_root_success():
    """Test validating a valid git repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        git_dir = repo_root / ".git"
        git_dir.mkdir()

        mock_result = GitCommandResult(
            success=True,
            stdout=".git\n",
            stderr="",
            returncode=0,
        )

        with patch("src.cli._git.run_git_command", return_value=mock_result):
            # Should not raise
            validate_repo_root(repo_root)


def test_validate_repo_root_no_git_dir():
    """Test validation fails when .git directory missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)

        with pytest.raises(ValueError, match="Not a git repository"):
            validate_repo_root(repo_root)


def test_validate_repo_root_git_command_fails():
    """Test validation fails when git command fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        git_dir = repo_root / ".git"
        git_dir.mkdir()

        mock_result = GitCommandResult(
            success=False,
            stdout="",
            stderr="fatal: not a git repository",
            returncode=128,
        )

        with patch("src.cli._git.run_git_command", return_value=mock_result):
            with pytest.raises(ValueError, match="Not a valid git repository"):
                validate_repo_root(repo_root)


def test_validate_repo_root_path_not_exists():
    """Test validation fails for non-existent path."""
    with pytest.raises(ValueError, match="Path does not exist"):
        validate_repo_root(Path("/nonexistent/path"))


def test_validate_repo_root_path_is_file():
    """Test validation fails when path is a file."""
    with tempfile.NamedTemporaryFile() as tmpfile, pytest.raises(ValueError, match="Path is not a directory"):
        validate_repo_root(Path(tmpfile.name))


def test_derive_branch_name_hint_basic():
    """Test deriving branch name from task ID."""
    result = derive_branch_name_hint("001-feature-task")
    assert result == "001-feature-task"


def test_derive_branch_name_hint_with_special_chars():
    """Test deriving branch name replaces special characters."""
    result = derive_branch_name_hint("001 feature@task#123")
    assert result == "001-feature-task-123"


def test_derive_branch_name_hint_uppercase():
    """Test deriving branch name converts to lowercase."""
    result = derive_branch_name_hint("001-Feature-Task")
    assert result == "001-feature-task"


def test_derive_branch_name_hint_truncation():
    """Test deriving branch name truncates to 50 chars."""
    long_task_id = "a" * 100
    result = derive_branch_name_hint(long_task_id)
    assert len(result) == 50
    assert result == "a" * 50


def test_derive_branch_name_hint_trailing_dashes():
    """Test deriving branch name removes trailing dashes."""
    result = derive_branch_name_hint("001-feature---")
    assert result == "001-feature"


def test_derive_branch_name_hint_preserves_safe_chars():
    """Test deriving branch name preserves dots, underscores, slashes."""
    result = derive_branch_name_hint("001.feature_task/subtask")
    assert result == "001.feature_task/subtask"


def test_derive_branch_name_hint_empty_input():
    """Test deriving branch name raises error for empty input."""
    with pytest.raises(ValueError, match="task_id must be non-empty"):
        derive_branch_name_hint("")


def test_derive_branch_name_hint_whitespace_only():
    """Test deriving branch name raises error for whitespace-only input."""
    with pytest.raises(ValueError, match="task_id must be non-empty"):
        derive_branch_name_hint("   ")


def test_derive_branch_name_hint_all_special_chars():
    """Test deriving branch name raises error for all special characters."""
    # All special chars result in empty string after processing
    with pytest.raises(ValueError, match="Derived branch name is empty"):
        derive_branch_name_hint("@#$%^&*()")
