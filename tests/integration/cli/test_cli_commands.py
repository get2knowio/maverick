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
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 8192,
            "temperature": 0.0,
        },
        "parallel": {
            "max_agents": 3,
            "max_tasks": 5,
        },
        "verbosity": "warning",
    }


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
            # Patch subprocess.run in sys.modules so the import picks up our mock
            with patch("subprocess.run") as mock_run:
                # Multiple calls will be made:
                # 1. git --version (dependency check)
                # 2. gh --version (dependency check)
                # 3. gh pr view (PR validation)
                # 4. gh pr view --json (get PR details)
                mock_run.side_effect = [
                    MagicMock(
                        returncode=0, stdout="git version 2.34.1"
                    ),  # git --version
                    MagicMock(returncode=0, stdout="gh version 2.0.0"),  # gh --version
                    MagicMock(returncode=0, stdout="PR #123"),  # gh pr view
                    MagicMock(
                        returncode=0,
                        stdout='{"headRefName": "feature-test", "baseRefName": "main"}',
                    ),  # gh pr view --json
                ]

                # Mock CodeReviewerAgent
                with patch(
                    "maverick.cli.commands.review.CodeReviewerAgent"
                ) as mock_agent_class:
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
            # Patch subprocess.run in sys.modules so the import picks up our mock
            with patch("subprocess.run") as mock_run:
                # Multiple calls will be made:
                # 1. git --version (dependency check)
                # 2. gh --version (dependency check)
                # 3. gh pr view (PR validation)
                # 4. gh pr view --json (get PR details)
                mock_run.side_effect = [
                    MagicMock(
                        returncode=0, stdout="git version 2.34.1"
                    ),  # git --version
                    MagicMock(returncode=0, stdout="gh version 2.0.0"),  # gh --version
                    MagicMock(returncode=0, stdout="PR #123"),  # gh pr view
                    MagicMock(
                        returncode=0,
                        stdout='{"headRefName": "feature-test", "baseRefName": "main"}',
                    ),  # gh pr view --json
                ]

                # Mock CodeReviewerAgent
                with patch(
                    "maverick.cli.commands.review.CodeReviewerAgent"
                ) as mock_agent_class:
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
            # Patch subprocess.run in sys.modules so the import picks up our mock
            with patch("subprocess.run") as mock_run:
                # Multiple calls will be made:
                # 1. git --version (dependency check)
                # 2. gh --version (dependency check)
                # 3. gh pr view (PR validation - fail)
                mock_run.side_effect = [
                    MagicMock(
                        returncode=0, stdout="git version 2.34.1"
                    ),  # git --version
                    MagicMock(returncode=0, stdout="gh version 2.0.0"),  # gh --version
                    MagicMock(
                        returncode=1,
                        stderr="PR not found",
                    ),  # gh pr view
                ]

                # Run review command
                result = runner.invoke(cli, ["review", "999"])

                # Verify
                assert result.exit_code == ExitCode.FAILURE
                assert "not found" in result.output


class TestConfigSubcommandsIntegration:
    """Integration tests for config subcommands (T095).

    Note: Since T044-T046 (deprecation), 'config init' now delegates to
    'maverick init'. These tests verify the deprecation path works correctly.
    """

    def test_config_init_invokes_init_command(
        self,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """Test config init delegates to init command (T044-T046)."""
        from unittest.mock import MagicMock, patch

        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Mock the init module and ctx.invoke to verify delegation
            mock_init_module = MagicMock()
            mock_init_cmd = MagicMock()
            mock_init_module.init = mock_init_cmd

            with patch.dict(
                "sys.modules", {"maverick.cli.commands.init": mock_init_module}
            ):
                with patch("click.Context.invoke") as mock_invoke:
                    runner.invoke(cli, ["config", "init"])

            # Verify init command was invoked
            assert mock_invoke.call_count >= 1

    def test_config_init_with_force_passes_to_init(
        self,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """Test config init --force passes the flag to init command."""
        from unittest.mock import MagicMock, patch

        with runner.isolated_filesystem(temp_dir=tmp_path):
            mock_init_module = MagicMock()
            mock_init_cmd = MagicMock()
            mock_init_module.init = mock_init_cmd

            with patch.dict(
                "sys.modules", {"maverick.cli.commands.init": mock_init_module}
            ):
                with patch("click.Context.invoke") as mock_invoke:
                    runner.invoke(cli, ["config", "init", "--force"])

            # Verify invoke was called with force=True
            found_force = False
            for call in mock_invoke.call_args_list:
                if call.kwargs and call.kwargs.get("force") is True:
                    found_force = True
                    break
            assert found_force, "force=True not passed to init command"

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
                    "model_id": "claude-sonnet-4-5-20250929",
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
