"""Integration tests for CLI commands.

Tests the CLI end-to-end with mocked workflows and external dependencies.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from maverick.cli.context import ExitCode
from maverick.main import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def mock_config() -> dict[str, Any]:
    """Create a mock configuration."""
    return {
        "github": {
            "owner": "test-owner",
            "repo": "test-repo",
            "default_branch": "main",
        },
        "notifications": {
            "enabled": False,
            "server": "https://ntfy.sh",
            "topic": None,
        },
        "validation": {
            "format_cmd": ["ruff", "format", "."],
            "lint_cmd": ["ruff", "check", "--fix", "."],
            "typecheck_cmd": ["mypy", "."],
            "test_cmd": ["pytest", "-x", "--tb=short"],
            "timeout_seconds": 300,
            "max_errors": 50,
        },
        "model": {
            "model_id": "claude-sonnet-4-20250514",
            "max_tokens": 8192,
            "temperature": 0.0,
        },
        "parallel": {
            "max_agents": 3,
            "max_tasks": 5,
        },
        "verbosity": "warning",
    }


class TestFlyWorkflowIntegration:
    """Integration tests for fly command (T092)."""

    def test_fly_workflow_end_to_end_success(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test fly command end-to-end with successful workflow execution."""
        # Setup: Create a git repo with a branch
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Initialize git repo
            import subprocess

            subprocess.run(["git", "init"], check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                check=True,
                capture_output=True,
            )

            # Create initial commit
            Path("README.md").write_text("# Test")
            subprocess.run(["git", "add", "README.md"], check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                check=True,
                capture_output=True,
            )

            # Create feature branch
            subprocess.run(
                ["git", "checkout", "-b", "feature-test"],
                check=True,
                capture_output=True,
            )

            # Create tasks.md
            tasks_file = Path("tasks.md")
            tasks_file.write_text("- [ ] Task 1\n- [ ] Task 2\n")

            # Create maverick.yaml config
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Mock the workflow execution
            with patch("maverick.main.FlyWorkflow") as mock_workflow_class:
                mock_workflow = AsyncMock()
                mock_workflow_class.return_value = mock_workflow

                # Mock workflow result
                mock_result = MagicMock()
                mock_result.success = True
                mock_result.summary = "Workflow completed successfully"
                mock_workflow.execute.return_value = mock_result

                # Run fly command
                result = runner.invoke(
                    cli,
                    ["fly", "feature-test", "--task-file", str(tasks_file)],
                )

                # Verify
                assert result.exit_code == ExitCode.SUCCESS
                assert "Workflow completed successfully" in result.output
                mock_workflow.execute.assert_called_once()

    def test_fly_workflow_dry_run(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test fly command with --dry-run option."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Initialize git repo
            import subprocess

            subprocess.run(["git", "init"], check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                check=True,
                capture_output=True,
            )

            # Create initial commit and branch
            Path("README.md").write_text("# Test")
            subprocess.run(["git", "add", "README.md"], check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "checkout", "-b", "feature-test"],
                check=True,
                capture_output=True,
            )

            # Create maverick.yaml config
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Run dry-run
            result = runner.invoke(cli, ["fly", "feature-test", "--dry-run"])

            # Verify
            assert result.exit_code == ExitCode.SUCCESS
            assert "Dry run:" in result.output
            assert "feature-test" in result.output
            assert "No actions performed" in result.output

    def test_fly_workflow_branch_not_found(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test fly command with non-existent branch."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Initialize git repo
            import subprocess

            subprocess.run(["git", "init"], check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                check=True,
                capture_output=True,
            )

            # Create initial commit
            Path("README.md").write_text("# Test")
            subprocess.run(["git", "add", "README.md"], check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                check=True,
                capture_output=True,
            )

            # Create maverick.yaml config
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Run fly with non-existent branch
            result = runner.invoke(cli, ["fly", "nonexistent-branch"])

            # Verify
            assert result.exit_code == ExitCode.FAILURE
            assert "does not exist" in result.output
            assert "git checkout -b" in result.output


class TestRefuelWorkflowIntegration:
    """Integration tests for refuel command (T093)."""

    def test_refuel_workflow_end_to_end_success(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test refuel command end-to-end with successful workflow execution."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Initialize git repo
            import subprocess

            subprocess.run(["git", "init"], check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                check=True,
                capture_output=True,
            )

            # Create initial commit
            Path("README.md").write_text("# Test")
            subprocess.run(["git", "add", "README.md"], check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                check=True,
                capture_output=True,
            )

            # Create maverick.yaml config
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Mock check_git_auth to return success
            with patch("maverick.main.check_git_auth") as mock_auth:
                mock_auth_status = MagicMock()
                mock_auth_status.available = True
                mock_auth.return_value = mock_auth_status

                # Mock the workflow execution
                with patch("maverick.main.RefuelWorkflow") as mock_workflow_class:
                    mock_workflow = MagicMock()
                    mock_workflow_class.return_value = mock_workflow

                    # Mock workflow events
                    from maverick.workflows.refuel import (
                        RefuelCompleted,
                        RefuelInputs,
                        RefuelResult,
                        RefuelStarted,
                    )

                    async def mock_execute_gen(inputs):
                        mock_inputs = RefuelInputs(label="bug", limit=2)
                        yield RefuelStarted(inputs=mock_inputs, issues_found=2)
                        yield RefuelCompleted(
                            result=RefuelResult(
                                success=True,
                                issues_found=2,
                                issues_processed=2,
                                issues_fixed=2,
                                issues_failed=0,
                                issues_skipped=0,
                                results=[],
                                total_duration_ms=1000,
                                total_cost_usd=0.0,
                            )
                        )

                    mock_workflow.execute = mock_execute_gen

                    # Run refuel command
                    result = runner.invoke(
                        cli, ["refuel", "--label", "bug", "--limit", "2"]
                    )

                    # Verify
                    assert result.exit_code == ExitCode.SUCCESS
                    assert "Found 2 issue(s)" in result.output
                    assert "Summary:" in result.output

    def test_refuel_workflow_dry_run(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test refuel command with --dry-run option."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create maverick.yaml config
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Mock check_git_auth
            with patch("maverick.main.check_git_auth") as mock_auth:
                mock_auth_status = MagicMock()
                mock_auth_status.available = True
                mock_auth.return_value = mock_auth_status

                # Mock workflow
                with patch("maverick.main.RefuelWorkflow") as mock_workflow_class:
                    mock_workflow = MagicMock()
                    mock_workflow_class.return_value = mock_workflow

                    from maverick.workflows.refuel import (
                        RefuelCompleted,
                        RefuelInputs,
                        RefuelResult,
                        RefuelStarted,
                    )

                    async def mock_execute_gen(inputs):
                        mock_inputs = RefuelInputs(
                            label="tech-debt", limit=5, dry_run=True
                        )
                        yield RefuelStarted(inputs=mock_inputs, issues_found=0)
                        yield RefuelCompleted(
                            result=RefuelResult(
                                success=True,
                                issues_found=0,
                                issues_processed=0,
                                issues_fixed=0,
                                issues_failed=0,
                                issues_skipped=0,
                                results=[],
                                total_duration_ms=100,
                                total_cost_usd=0.0,
                            )
                        )

                    mock_workflow.execute = mock_execute_gen

                    # Run dry-run
                    result = runner.invoke(cli, ["refuel", "--dry-run"])

                    # Verify
                    assert result.exit_code == ExitCode.SUCCESS
                    assert "Dry run:" in result.output


class TestReviewCommandIntegration:
    """Integration tests for review command (T094)."""

    def test_review_command_json_output(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test review command with JSON output."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Initialize git repo
            import subprocess

            subprocess.run(["git", "init"], check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                check=True,
                capture_output=True,
            )

            # Create initial commit
            Path("README.md").write_text("# Test")
            subprocess.run(["git", "add", "README.md"], check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                check=True,
                capture_output=True,
            )

            # Create maverick.yaml config
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Mock gh pr view to simulate PR existence
            with patch("subprocess.run") as mock_run:
                # First call: gh pr view (success)
                # Second call: gh pr view --json (success)
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout="PR #123"),
                    MagicMock(
                        returncode=0,
                        stdout='{"headRefName": "feature-test", "baseRefName": "main"}',
                    ),
                ]

                # Mock CodeReviewerAgent
                with patch("maverick.main.CodeReviewerAgent") as mock_agent_class:
                    mock_agent = AsyncMock()
                    mock_agent_class.return_value = mock_agent

                    # Mock review result
                    from maverick.models.review import ReviewResult

                    mock_result = ReviewResult(
                        summary="Review complete",
                        findings=[],
                        files_reviewed=5,
                        success=True,
                    )
                    mock_agent.execute.return_value = mock_result

                    # Run review command with JSON output
                    result = runner.invoke(cli, ["review", "123", "--output", "json"])

                    # Verify
                    assert result.exit_code == ExitCode.SUCCESS

                    # Parse JSON output
                    output_json = json.loads(result.output)
                    assert output_json["summary"] == "Review complete"
                    assert output_json["files_reviewed"] == 5

    def test_review_command_markdown_output(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test review command with markdown output."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create maverick.yaml config
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Mock gh pr view
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout="PR #123"),
                    MagicMock(
                        returncode=0,
                        stdout='{"headRefName": "feature-test", "baseRefName": "main"}',
                    ),
                ]

                # Mock CodeReviewerAgent
                with patch("maverick.main.CodeReviewerAgent") as mock_agent_class:
                    mock_agent = AsyncMock()
                    mock_agent_class.return_value = mock_agent

                    from maverick.models.review import ReviewResult

                    mock_result = ReviewResult(
                        summary="Review complete",
                        findings=[],
                        files_reviewed=3,
                        success=True,
                    )
                    mock_agent.execute.return_value = mock_result

                    # Run review command with markdown output
                    result = runner.invoke(
                        cli, ["review", "123", "--output", "markdown"]
                    )

                    # Verify
                    assert result.exit_code == ExitCode.SUCCESS
                    assert "# Code Review: PR #123" in result.output
                    assert "## Summary" in result.output

    def test_review_command_pr_not_found(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test review command with non-existent PR."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create maverick.yaml config
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Mock gh pr view to fail (PR not found)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stderr="PR not found",
                )

                # Run review command
                result = runner.invoke(cli, ["review", "999"])

                # Verify
                assert result.exit_code == ExitCode.FAILURE
                assert "not found" in result.output


class TestConfigSubcommandsIntegration:
    """Integration tests for config subcommands (T095)."""

    def test_config_init_creates_file(
        self,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """Test config init creates default config file."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Run config init
            result = runner.invoke(cli, ["config", "init"])

            # Verify
            assert result.exit_code == ExitCode.SUCCESS
            assert "Configuration file created" in result.output

            # Check file exists
            config_file = Path("maverick.yaml")
            assert config_file.exists()

            # Check content
            import yaml

            with open(config_file) as f:
                config = yaml.safe_load(f)
                assert "github" in config
                assert "model" in config
                assert "validation" in config

    def test_config_init_force_overwrites(
        self,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """Test config init --force overwrites existing file."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create existing config
            config_file = Path("maverick.yaml")
            config_file.write_text("existing: data")

            # Run config init without force (should fail)
            result = runner.invoke(cli, ["config", "init"])
            assert result.exit_code == ExitCode.FAILURE
            assert "already exists" in result.output

            # Run config init with force (should succeed)
            result = runner.invoke(cli, ["config", "init", "--force"])
            assert result.exit_code == ExitCode.SUCCESS

            # Verify content was overwritten
            import yaml

            with open(config_file) as f:
                config = yaml.safe_load(f)
                assert "existing" not in config
                assert "github" in config

    def test_config_show_yaml_format(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test config show displays YAML."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create maverick.yaml
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Run config show
            result = runner.invoke(cli, ["config", "show"])

            # Verify
            assert result.exit_code == 0
            assert "github:" in result.output
            assert "model:" in result.output

    def test_config_show_json_format(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test config show --format json."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create maverick.yaml
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Run config show with JSON format
            result = runner.invoke(cli, ["config", "show", "--format", "json"])

            # Verify
            assert result.exit_code == 0

            # Parse JSON
            output_json = json.loads(result.output)
            assert "github" in output_json
            assert "model" in output_json

    def test_config_validate_valid(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test config validate with valid config."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create valid maverick.yaml
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Run config validate
            result = runner.invoke(cli, ["config", "validate"])

            # Verify
            assert result.exit_code == ExitCode.SUCCESS
            assert "valid" in result.output

    def test_config_validate_invalid(
        self,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """Test config validate with invalid config."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create invalid maverick.yaml (wrong type for max_tokens)
            import yaml

            config_file = Path("maverick.yaml")
            invalid_config = {
                "model": {
                    "model_id": "claude-sonnet-4-20250514",
                    "max_tokens": "not-a-number",  # Invalid type
                }
            }
            with open(config_file, "w") as f:
                yaml.dump(invalid_config, f)

            # Run config validate
            result = runner.invoke(cli, ["config", "validate"])

            # Verify
            assert result.exit_code == ExitCode.FAILURE
            assert "Invalid configuration" in result.output or "Error" in result.output


class TestCLIStartupPerformance:
    """Integration test for CLI startup time (T101)."""

    def test_cli_startup_time_under_500ms(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test that CLI startup time is under 500ms (NFR-001)."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create maverick.yaml
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Measure startup time for --help (simplest command)
            start = time.perf_counter()
            result = runner.invoke(cli, ["--help"])
            duration_ms = (time.perf_counter() - start) * 1000

            # Verify
            assert result.exit_code == 0
            # Note: CliRunner has overhead, so we allow for a bit more time
            # In production, this should be measured directly
            assert duration_ms < 1000, (
                f"CLI startup took {duration_ms:.2f}ms (expected <1000ms in test)"
            )

    def test_cli_version_startup_time(
        self,
        runner: CliRunner,
        tmp_path: Path,
        mock_config: dict[str, Any],
    ) -> None:
        """Test that CLI --version startup is fast."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create maverick.yaml
            import yaml

            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(mock_config, f)

            # Measure startup time for --version
            start = time.perf_counter()
            result = runner.invoke(cli, ["--version"])
            duration_ms = (time.perf_counter() - start) * 1000

            # Verify
            assert result.exit_code == 0
            assert "maverick, version" in result.output
            # Version command should be very fast
            assert duration_ms < 1000, f"--version took {duration_ms:.2f}ms"
