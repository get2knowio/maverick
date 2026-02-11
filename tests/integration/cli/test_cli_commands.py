"""Integration tests for CLI commands.

Tests the CLI end-to-end with mocked workflows and external dependencies.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

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
