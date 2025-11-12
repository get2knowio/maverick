"""Integration tests for maverick run command.

Tests the run command with mocked Temporal client to verify
workflow starting and progress streaming without requiring
a live Temporal server.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli.maverick import cli


@pytest.fixture
def mock_temporal_client():
    """Mock Temporal client for testing."""
    client = AsyncMock()

    # Mock workflow handle
    handle = AsyncMock()
    handle.id = "test-workflow-123"
    handle.result_run_id = "test-run-456"

    # Mock workflow description
    workflow_info = MagicMock()
    workflow_info.status.name = "COMPLETED"
    handle.describe.return_value = workflow_info

    # Mock query responses
    handle.query.side_effect = lambda query_name: {
        "get_progress": {"current_task": "task-1", "current_phase": "phase-1"},
        "get_task_results": [{"task_id": "task-1", "status": "success"}],
    }.get(query_name, {})

    client.start_workflow.return_value = handle

    return client


@pytest.fixture
def temp_task_file(tmp_path):
    """Create a temporary task file for testing."""
    specs_dir = tmp_path / "specs" / "001-test-feature"
    specs_dir.mkdir(parents=True)

    tasks_file = specs_dir / "tasks.md"
    tasks_file.write_text("# Test Tasks\n\n- [ ] Task 1\n")

    # Create .git directory to simulate git repo
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    return tmp_path, tasks_file


class TestRunCommand:
    """Test suite for maverick run command."""

    @patch("src.cli.maverick.Client.connect")
    @patch("src.cli.maverick.validate_repo_root")
    @patch("src.cli.maverick.is_working_tree_dirty")
    @patch("src.cli.maverick.get_current_branch")
    @patch("src.cli.maverick.discover_tasks")
    def test_run_dry_run_json(
        self,
        mock_discover,
        mock_branch,
        mock_dirty,
        mock_validate,
        mock_connect,
        tmp_path,
    ):
        """Test dry-run mode with JSON output."""
        # Create minimal task file structure FIRST
        specs_dir = tmp_path / "specs" / "001-test"
        specs_dir.mkdir(parents=True)
        tasks_file = specs_dir / "tasks.md"
        tasks_file.write_text("# Test\n")

        # Setup mocks
        mock_validate.return_value = None
        mock_dirty.return_value = False
        mock_branch.return_value = "main"

        # Mock discovered task (files must exist before creating DiscoveredTask)
        from src.cli._models import DiscoveredTask
        mock_discover.return_value = [
            DiscoveredTask(
                file_path=str(tasks_file),
                spec_dir=str(specs_dir),
                numeric_prefix=1,
                directory_name="001-test",
            )
        ]

        runner = CliRunner()
        # Change to tmp_path directory so CLI uses it as repo root
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(cli, ["run", "--dry-run", "--json"])
        finally:
            os.chdir(old_cwd)

        # Assertions
        assert result.exit_code == 0

        output = json.loads(result.output)
        assert "task_count" in output
        assert output["task_count"] == 1
        assert "discovery_ms" in output
        assert "tasks" in output
        assert len(output["tasks"]) == 1
        assert output["tasks"][0]["task_id"] == "001-test-tasks"

    @patch("src.cli.maverick.Client.connect")
    @patch("src.cli.maverick.validate_repo_root")
    @patch("src.cli.maverick.is_working_tree_dirty")
    @patch("src.cli.maverick.get_current_branch")
    @patch("src.cli.maverick.discover_tasks")
    def test_run_dirty_tree_blocked(
        self,
        mock_discover,
        mock_branch,
        mock_dirty,
        mock_validate,
        mock_connect,
    ):
        """Test that dirty working tree blocks execution without --allow-dirty."""
        # Setup mocks
        mock_validate.return_value = None
        mock_dirty.return_value = True
        mock_branch.return_value = "main"

        runner = CliRunner()
        result = runner.invoke(cli, ["run"])

        # Should fail with dirty tree message
        assert result.exit_code != 0
        assert "uncommitted changes" in result.output.lower()

    @patch("src.cli.maverick.Client.connect")
    @patch("src.cli.maverick.validate_repo_root")
    @patch("src.cli.maverick.is_working_tree_dirty")
    @patch("src.cli.maverick.get_current_branch")
    @patch("src.cli.maverick.discover_tasks")
    def test_run_dirty_tree_blocked_interactive(
        self,
        mock_discover,
        mock_branch,
        mock_dirty,
        mock_validate,
        mock_connect,
    ):
        """Interactive mode should still enforce dirty tree guard."""
        mock_validate.return_value = None
        mock_dirty.return_value = True
        mock_branch.return_value = "main"

        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--interactive"])

        assert result.exit_code != 0
        assert "uncommitted changes" in result.output.lower()

    @patch("src.cli.maverick.Client.connect")
    @patch("src.cli.maverick.validate_repo_root")
    @patch("src.cli.maverick.is_working_tree_dirty")
    @patch("src.cli.maverick.get_current_branch")
    @patch("src.cli.maverick.discover_tasks")
    def test_run_allow_dirty(
        self,
        mock_discover,
        mock_branch,
        mock_dirty,
        mock_validate,
        mock_connect,
        tmp_path,
    ):
        """Test that --allow-dirty bypasses dirty tree check."""
        # Create task file FIRST
        specs_dir = tmp_path / "specs" / "001-test"
        specs_dir.mkdir(parents=True)
        tasks_file = specs_dir / "tasks.md"
        tasks_file.write_text("# Test\n")

        # Setup mocks
        mock_validate.return_value = None
        mock_dirty.return_value = True
        mock_branch.return_value = "main"

        # Mock discovered task
        from src.cli._models import DiscoveredTask
        mock_discover.return_value = [
            DiscoveredTask(
                file_path=str(tasks_file),
                spec_dir=str(specs_dir),
                numeric_prefix=1,
                directory_name="001-test",
            )
        ]

        runner = CliRunner()
        # Change to tmp_path directory so CLI uses it as repo root
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(cli, ["run", "--allow-dirty", "--dry-run"])
        finally:
            os.chdir(old_cwd)

        # Should succeed with --allow-dirty
        assert result.exit_code == 0

    @patch("src.cli.maverick.Client.connect")
    @patch("src.cli.maverick.validate_repo_root")
    @patch("src.cli.maverick.is_working_tree_dirty")
    @patch("src.cli.maverick.get_current_branch")
    @patch("src.cli.maverick.discover_tasks")
    def test_run_workflow_start(
        self,
        mock_discover,
        mock_branch,
        mock_dirty,
        mock_validate,
        mock_connect,
        mock_temporal_client,
        tmp_path,
    ):
        """Test workflow start with mocked Temporal client."""
        # Create task file FIRST
        specs_dir = tmp_path / "specs" / "001-test"
        specs_dir.mkdir(parents=True)
        tasks_file = specs_dir / "tasks.md"
        tasks_file.write_text("# Test\n")

        # Setup mocks
        mock_validate.return_value = None
        mock_dirty.return_value = False
        mock_branch.return_value = "main"
        mock_connect.return_value = mock_temporal_client

        # Mock discovered task
        from src.cli._models import DiscoveredTask
        mock_discover.return_value = [
            DiscoveredTask(
                file_path=str(tasks_file),
                spec_dir=str(specs_dir),
                numeric_prefix=1,
                directory_name="001-test",
            )
        ]

        runner = CliRunner()
        # Change to tmp_path directory so CLI uses it as repo root
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(cli, ["run", "--json"])
        finally:
            os.chdir(old_cwd)

        # Should start workflow successfully
        assert result.exit_code == 0

        # Check JSON output contains workflow info
        lines = result.output.strip().split("\n")
        first_output = json.loads(lines[0])

        assert "workflow_id" in first_output
        assert "run_id" in first_output
        assert "task_count" in first_output
        assert first_output["workflow_id"] == "test-workflow-123"
        assert first_output["run_id"] == "test-run-456"

    @patch("src.cli.maverick.validate_repo_root")
    @patch("src.cli.maverick.is_working_tree_dirty")
    @patch("src.cli.maverick.get_current_branch")
    def test_run_no_tasks_discovered(self, mock_branch, mock_dirty, mock_validate, tmp_path):
        """Test behavior when no tasks are discovered."""
        mock_validate.return_value = None
        mock_dirty.return_value = False
        mock_branch.return_value = "main"

        # Create empty specs directory
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir(parents=True)

        runner = CliRunner()
        # Change to tmp_path directory so CLI uses it as repo root
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(cli, ["run"])
        finally:
            os.chdir(old_cwd)

        # Should exit non-zero with clear message
        assert result.exit_code != 0
        assert "no tasks" in result.output.lower()

    @patch("src.cli.maverick.validate_repo_root")
    @patch("src.cli.maverick.is_working_tree_dirty")
    @patch("src.cli.maverick.get_current_branch")
    def test_run_no_tasks_discovered_json(self, mock_branch, mock_dirty, mock_validate, tmp_path):
        """JSON output should include error payload when no tasks exist."""
        mock_validate.return_value = None
        mock_dirty.return_value = False
        mock_branch.return_value = "main"

        specs_dir = tmp_path / "specs"
        specs_dir.mkdir(parents=True)

        runner = CliRunner()
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(cli, ["run", "--json"])
        finally:
            os.chdir(old_cwd)

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"].lower().startswith("no tasks")
        assert payload["error_type"] == "NoTasksDiscoveredError"
        assert payload["task_count"] == 0
        assert payload["tasks"] == []

    @patch("src.cli.maverick.validate_repo_root")
    def test_run_not_git_repo(self, mock_validate, tmp_path):
        """Test error when not in a git repository."""
        mock_validate.side_effect = ValueError("Not a git repository")

        runner = CliRunner()
        result = runner.invoke(cli, ["run"])

        # Should fail with git repo error
        assert result.exit_code != 0
        assert "not a git repository" in result.output.lower()


class TestRunCommandProgress:
    """Test suite for progress streaming."""

    @patch("src.cli.maverick.Client.connect")
    @patch("src.cli.maverick.validate_repo_root")
    @patch("src.cli.maverick.is_working_tree_dirty")
    @patch("src.cli.maverick.get_current_branch")
    @patch("src.cli.maverick.discover_tasks")
    def test_progress_streaming_json(
        self,
        mock_discover,
        mock_branch,
        mock_dirty,
        mock_validate,
        mock_connect,
        mock_temporal_client,
        tmp_path,
    ):
        """Test progress streaming with JSON output."""
        # Create task file FIRST
        specs_dir = tmp_path / "specs" / "001-test"
        specs_dir.mkdir(parents=True)
        tasks_file = specs_dir / "tasks.md"
        tasks_file.write_text("# Test\n")

        # Setup mocks
        mock_validate.return_value = None
        mock_dirty.return_value = False
        mock_branch.return_value = "main"
        mock_connect.return_value = mock_temporal_client

        # Mock discovered task
        from src.cli._models import DiscoveredTask
        mock_discover.return_value = [
            DiscoveredTask(
                file_path=str(tasks_file),
                spec_dir=str(specs_dir),
                numeric_prefix=1,
                directory_name="001-test",
            )
        ]

        runner = CliRunner()
        # Change to tmp_path directory so CLI uses it as repo root
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(cli, ["run", "--json"])
        finally:
            os.chdir(old_cwd)

        # Should complete successfully
        assert result.exit_code == 0

        # Parse JSON outputs
        lines = [line for line in result.output.strip().split("\n") if line]
        assert len(lines) >= 2  # At least start + completion messages

        # Check completion message
        completion_output = json.loads(lines[-1])
        assert completion_output["status"] == "completed"
        assert "status_poll_latency_ms_p95" in completion_output
        assert "errors_count" in completion_output


class TestRunCommandEdgeCases:
    """Test edge cases and error handling."""

    def test_run_help(self):
        """Test that --help displays command documentation."""
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])

        assert result.exit_code == 0
        assert "maverick run" in result.output.lower() or "discover and run" in result.output.lower()
        assert "--task" in result.output
        assert "--interactive" in result.output
        assert "--dry-run" in result.output
        assert "--json" in result.output

    @patch("src.cli.maverick.validate_repo_root")
    @patch("src.cli.maverick.get_current_branch")
    def test_run_git_error(self, mock_branch, mock_validate):
        """Test error handling when git commands fail."""
        mock_validate.return_value = None
        mock_branch.side_effect = Exception("Git command failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["run"])

        # Should fail with git error
        assert result.exit_code != 0
        assert "git" in result.output.lower() or "branch" in result.output.lower()
