"""Example CLI command tests demonstrating testing patterns.

This file shows simple, focused examples of how to test Click commands
using CliRunner. For comprehensive integration tests, see test_cli_commands.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from maverick.main import cli


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Create a minimal valid configuration for testing."""
    return {
        "github": {
            "owner": "example-org",
            "repo": "example-repo",
            "default_branch": "main",
        },
        "model": {
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 4096,
            "temperature": 0.0,
        },
        "verbosity": "warning",
    }


class TestBasicCLIPatterns:
    """Examples of basic CLI testing patterns."""

    def test_version_flag(self, cli_runner: CliRunner) -> None:
        """Example: Test --version flag shows version information.

        Pattern: Testing flags without requiring config or setup.
        """
        # Invoke the CLI with --version
        result = cli_runner.invoke(cli, ["--version"])

        # Assert exit code is success (0)
        assert result.exit_code == 0

        # Assert output contains expected text
        assert "maverick, version" in result.output

    def test_help_flag(self, cli_runner: CliRunner) -> None:
        """Example: Test --help flag shows usage information.

        Pattern: Testing help output for documentation.
        """
        # Invoke with --help
        result = cli_runner.invoke(cli, ["--help"])

        # Verify successful exit
        assert result.exit_code == 0

        # Verify help content is present
        assert "Maverick - AI-powered development" in result.output
        assert "Commands:" in result.output

    def test_no_command_shows_help(self, cli_runner: CliRunner) -> None:
        """Example: Test that running CLI without command shows help.

        Pattern: Testing default behavior.
        """
        result = cli_runner.invoke(cli, [])

        # Should still exit successfully
        assert result.exit_code == 0

        # Should show help text
        assert "Usage:" in result.output


class TestFlyCommandExamples:
    """Examples of testing fly command."""

    def test_fly_help(self, cli_runner: CliRunner) -> None:
        """Example: Test fly --help shows bead-driven options.

        Pattern: Verifying command help output.
        """
        result = cli_runner.invoke(cli, ["fly", "--help"])

        assert result.exit_code == 0
        assert "--epic" in result.output
        assert "--dry-run" in result.output


class TestVerbosityOptions:
    """Examples of testing CLI verbosity options."""

    def test_verbose_flag(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        sample_config: dict[str, Any],
    ) -> None:
        """Example: Test -v verbose flag.

        Pattern: Testing option flags.
        """
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            # Create config
            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(sample_config, f)

            # Run with -v flag
            result = cli_runner.invoke(cli, ["-v", "--help"])

            # Should succeed
            assert result.exit_code == 0

    def test_quiet_flag(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        sample_config: dict[str, Any],
    ) -> None:
        """Example: Test --quiet flag.

        Pattern: Testing boolean flags.
        """
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            # Create config
            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(sample_config, f)

            # Run with --quiet flag
            result = cli_runner.invoke(cli, ["--quiet", "--help"])

            # Should succeed
            assert result.exit_code == 0


class TestErrorHandling:
    """Examples of testing error handling patterns."""

    def test_invalid_command(self, cli_runner: CliRunner) -> None:
        """Example: Test invalid command shows error.

        Pattern: Testing error messages for invalid input.
        """
        # Run with non-existent command
        result = cli_runner.invoke(cli, ["nonexistent-command"])

        # Should fail
        assert result.exit_code != 0

        # Should show error message
        assert "Error" in result.output or "No such command" in result.output

    def test_missing_required_argument(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        sample_config: dict[str, Any],
    ) -> None:
        """Example: Test missing required argument shows usage.

        Pattern: Testing argument validation.
        """
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            # Create config
            config_file = Path("maverick.yaml")
            with open(config_file, "w") as f:
                yaml.dump(sample_config, f)

            # Run refuel speckit without required spec_dir argument
            result = cli_runner.invoke(cli, ["refuel", "speckit"])

            # Should fail with usage error
            assert result.exit_code != 0
            assert "Error" in result.output or "Usage" in result.output


# Key Testing Patterns Summary:
#
# 1. Use cli_runner fixture from conftest.py
#    - Provides CliRunner instance for testing Click commands
#
# 2. Assert exit codes using ExitCode enum
#    - ExitCode.SUCCESS (0) for success
#    - ExitCode.FAILURE (1) for errors
#
# 3. Check output using 'in result.output'
#    - result.output contains stdout
#    - result.stderr available if needed
#
# 4. Use isolated_filesystem for file operations
#    - Prevents test pollution
#    - Automatically cleaned up
#
# 5. Setup test data as fixtures
#    - Reusable across tests
#    - Clear separation of setup and test logic
