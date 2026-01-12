"""Unit tests for the CLI entry point.

These tests verify the Click-based CLI interface for Maverick,
including version output, help text, and exit codes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI test runner."""
    return CliRunner()


def test_version_output(cli_runner: CliRunner) -> None:
    """Test that --version outputs the correct version string."""
    from maverick import __version__
    from maverick.main import cli

    result = cli_runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_output(cli_runner: CliRunner) -> None:
    """Test that --help shows help message."""
    from maverick.main import cli

    result = cli_runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Maverick" in result.output
    assert "--version" in result.output
    assert "--verbose" in result.output or "-v" in result.output


def test_exit_code_success(cli_runner: CliRunner) -> None:
    """Test exit code 0 for successful commands."""
    from maverick.main import cli

    result = cli_runner.invoke(cli, ["--help"])
    assert result.exit_code == 0


def test_exit_code_usage_error(cli_runner: CliRunner) -> None:
    """Test exit code 2 for usage errors (invalid options)."""
    from maverick.main import cli

    result = cli_runner.invoke(cli, ["--invalid-option"])
    assert result.exit_code == 2


def test_default_verbosity_warning_level(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that default verbosity is WARNING level (no -v flags)."""
    import logging
    import os
    from unittest.mock import patch

    # Setup clean environment
    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    from maverick.main import cli

    # Mock configure_logging from maverick.logging
    with patch("maverick.main.configure_logging") as mock_configure:
        # Run CLI without -v flag (no --help, as that short-circuits)
        result = cli_runner.invoke(cli, [])

        assert result.exit_code == 0
        # configure_logging should have been called with WARNING level (30)
        mock_configure.assert_called_once()
        assert mock_configure.call_args.kwargs["level"] == logging.WARNING


def test_single_verbose_info_level(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that -v flag sets INFO level logging."""
    import logging
    import os
    from unittest.mock import patch

    # Setup clean environment
    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    from maverick.main import cli

    # Mock configure_logging from maverick.logging
    with patch("maverick.main.configure_logging") as mock_configure:
        result = cli_runner.invoke(cli, ["-v"])

        assert result.exit_code == 0
        # With -v, level should be INFO (20)
        mock_configure.assert_called_once()
        assert mock_configure.call_args.kwargs["level"] == logging.INFO


def test_double_verbose_debug_level(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that -vv flag sets DEBUG level logging."""
    import logging
    import os
    from unittest.mock import patch

    # Setup clean environment
    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    from maverick.main import cli

    # Mock configure_logging from maverick.logging
    with patch("maverick.main.configure_logging") as mock_configure:
        result = cli_runner.invoke(cli, ["-vv"])

        assert result.exit_code == 0
        # With -vv, level should be DEBUG (10)
        mock_configure.assert_called_once()
        assert mock_configure.call_args.kwargs["level"] == logging.DEBUG


def test_verbosity_from_config(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that verbosity can be set via config file."""
    import logging
    import os
    from unittest.mock import patch

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create config with verbosity set to debug
    config_path = temp_dir / "maverick.yaml"
    config_path.write_text('verbosity: "debug"\n')

    from maverick.main import cli

    # Mock configure_logging from maverick.logging
    with patch("maverick.main.configure_logging") as mock_configure:
        result = cli_runner.invoke(cli, [])

        assert result.exit_code == 0
        # Config sets debug level
        mock_configure.assert_called_once()
        assert mock_configure.call_args.kwargs["level"] == logging.DEBUG
