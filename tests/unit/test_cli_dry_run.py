"""Unit tests for CLI dry-run functionality.

Tests the --dry-run flag behavior, including descriptor output,
JSON structure validation, and exit code verification.

Note: These tests mock higher-level git functions rather than run_git_command
to avoid complex mock setup. The dry-run behavior itself is tested end-to-end
in integration tests.
"""

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from src.cli.maverick import cli


@contextmanager
def change_dir(path: str):
    """Context manager to temporarily change directory."""
    original_cwd = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(original_cwd)


def test_dry_run_with_allow_dirty():
    """Test dry-run works with --allow-dirty flag."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        spec_dir = specs_dir / "001-test-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks\n\n## Phase 1\n\n- [ ] Task 1")

        # Create .git directory to simulate git repo
        (repo_root / ".git").mkdir()

        # Mock git helpers to avoid complex git command mocking
        with patch("src.cli.maverick.validate_repo_root"):
            with patch("src.cli.maverick.get_current_branch", return_value="main"):
                with change_dir(str(repo_root)):
                    runner = CliRunner()
                    result = runner.invoke(
                        cli,
                        ["run", "--dry-run", "--allow-dirty"],
                        catch_exceptions=False,
                    )

                # Should exit successfully
                assert result.exit_code == 0

                # Should contain dry-run indication
                assert "Dry run" in result.output
                assert "would execute" in result.output
                assert "001-test-feature" in result.output


def test_dry_run_json_output_with_allow_dirty():
    """Test dry-run --json outputs correct JSON structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        spec_dir = specs_dir / "002-another-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks\n\n## Phase 1\n\n- [ ] Task 1")

        # Create .git directory
        (repo_root / ".git").mkdir()

        with patch("src.cli.maverick.validate_repo_root"):
            with patch("src.cli.maverick.get_current_branch", return_value="main"):
                with change_dir(str(repo_root)):
                    runner = CliRunner()
                    result = runner.invoke(
                        cli,
                        ["run", "--dry-run", "--allow-dirty", "--json"],
                        catch_exceptions=False,
                    )

                assert result.exit_code == 0

                # Parse JSON output
                output = json.loads(result.output)

                # Verify required fields exist
                assert "task_count" in output
                assert "discovery_ms" in output
                assert "tasks" in output

                # Verify types
                assert isinstance(output["task_count"], int)
                assert isinstance(output["discovery_ms"], int)
                assert isinstance(output["tasks"], list)

                # Verify task count
                assert output["task_count"] == 1

                # Verify task structure
                task = output["tasks"][0]
                assert "task_id" in task
                assert "task_file" in task
                assert "spec_root" in task
                assert "branch_name" in task
                assert "interactive" in task

                # Verify task values
                assert task["task_id"] == "002-another-feature-tasks"
                assert "002-another-feature" in task["task_file"]
                assert task["interactive"] is False


def test_dry_run_exits_without_temporal_call():
    """Test dry-run exits without making Temporal client connection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        spec_dir = specs_dir / "001-test"
        spec_dir.mkdir(parents=True)
        (spec_dir / "tasks.md").write_text("# Tasks\n\n- [ ] Task 1")

        (repo_root / ".git").mkdir()

        with patch("src.cli.maverick.validate_repo_root"):
            with patch("src.cli.maverick.get_current_branch", return_value="main"):
                # Mock Client.connect to verify it's NOT called
                with patch("src.cli.maverick.Client.connect") as mock_connect:
                    with change_dir(str(repo_root)):
                        runner = CliRunner()
                        result = runner.invoke(
                            cli,
                            ["run", "--dry-run", "--allow-dirty"],
                            catch_exceptions=False,
                        )

                    assert result.exit_code == 0
                    # Verify Temporal client was never called
                    mock_connect.assert_not_called()


def test_dry_run_no_tasks_discovered():
    """Test dry-run with no tasks discovered."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        specs_dir.mkdir(parents=True)
        # No tasks.md files created

        (repo_root / ".git").mkdir()

        with patch("src.cli.maverick.validate_repo_root"):
            with patch("src.cli.maverick.get_current_branch", return_value="main"):
                with change_dir(str(repo_root)):
                    runner = CliRunner()
                    result = runner.invoke(
                        cli,
                        ["run", "--dry-run", "--allow-dirty", "--json"],
                        catch_exceptions=False,
                    )

                assert result.exit_code == 0

                output = json.loads(result.output)
                assert output["task_count"] == 0
                assert output["tasks"] == []


def test_dry_run_discovery_time_reported():
    """Test dry-run reports discovery time in milliseconds."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        specs_dir = repo_root / "specs"
        spec_dir = specs_dir / "001-test"
        spec_dir.mkdir(parents=True)
        (spec_dir / "tasks.md").write_text("# Tasks\n\n- [ ] Task 1")

        (repo_root / ".git").mkdir()

        with patch("src.cli.maverick.validate_repo_root"):
            with patch("src.cli.maverick.get_current_branch", return_value="main"):
                with change_dir(str(repo_root)):
                    runner = CliRunner()
                    result = runner.invoke(
                        cli,
                        ["run", "--dry-run", "--allow-dirty", "--json"],
                        catch_exceptions=False,
                    )

                assert result.exit_code == 0

                output = json.loads(result.output)
                # discovery_ms should be a non-negative integer
                assert output["discovery_ms"] >= 0
                assert isinstance(output["discovery_ms"], int)
