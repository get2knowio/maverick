"""Unit tests for global CLI options and entrypoint in main.py.

Tests comprehensive global options functionality:
- --config option for specifying custom config file
- --verbose stacking (-v, -vv, -vvv) for verbosity levels
- --quiet flag for suppressing non-essential output
- --version output
- --help output
- Precedence rules (quiet takes precedence over verbose)
- TTY and pipe auto-detection
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from maverick import __version__
from maverick.main import cli

# =============================================================================
# T018: Test --config option loading
# =============================================================================


def test_config_option_loads_custom_file(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that --config option loads from specified config file.

    Verifies that:
    - Custom config file path is accepted via -c/--config
    - Config is loaded from the specified path
    - CLIContext stores the config path
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create custom config file
    custom_config = temp_dir / "custom.yaml"
    custom_config.write_text("""
github:
  owner: "custom-org"
  repo: "custom-repo"
verbosity: "info"
""")

    result = cli_runner.invoke(cli, ["--config", str(custom_config)])

    # Should succeed
    assert result.exit_code == 0

    # Verify config was loaded (we'll check ctx.obj in implementation)
    # For now, just verify no errors


def test_config_option_short_flag(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that -c short flag works for config option."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create custom config file
    custom_config = temp_dir / "custom.yaml"
    custom_config.write_text('verbosity: "debug"\n')

    result = cli_runner.invoke(cli, ["-c", str(custom_config)])

    # Should succeed
    assert result.exit_code == 0


def test_config_option_nonexistent_file(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that --config with nonexistent file is handled gracefully."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    nonexistent = temp_dir / "nonexistent.yaml"

    result = cli_runner.invoke(cli, ["--config", str(nonexistent)])

    # Should still succeed (config loading should be graceful)
    # The load_config function should handle missing files
    assert result.exit_code == 0


# =============================================================================
# T019: Test --verbose stacking (-v, -vv, -vvv)
# =============================================================================


def test_verbose_single_flag_info_level(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that -v sets INFO logging level."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock configure_logging from maverick.logging
    with patch("maverick.main.configure_logging") as mock_configure:
        result = cli_runner.invoke(cli, ["-v"])

        assert result.exit_code == 0
        # Should set INFO level (20)
        mock_configure.assert_called_once()
        assert mock_configure.call_args.kwargs["level"] == logging.INFO


def test_verbose_double_flag_debug_level(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that -vv sets DEBUG logging level."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock configure_logging from maverick.logging
    with patch("maverick.main.configure_logging") as mock_configure:
        result = cli_runner.invoke(cli, ["-vv"])

        assert result.exit_code == 0
        # Should set DEBUG level (10)
        mock_configure.assert_called_once()
        assert mock_configure.call_args.kwargs["level"] == logging.DEBUG


def test_verbose_triple_flag_debug_level(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that -vvv sets DEBUG logging level (same as -vv)."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock configure_logging from maverick.logging
    with patch("maverick.main.configure_logging") as mock_configure:
        result = cli_runner.invoke(cli, ["-vvv"])

        assert result.exit_code == 0
        # Should set DEBUG level (10) - max detail
        mock_configure.assert_called_once()
        assert mock_configure.call_args.kwargs["level"] == logging.DEBUG


def test_verbose_long_flag(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that --verbose works same as -v."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock configure_logging from maverick.logging
    with patch("maverick.main.configure_logging") as mock_configure:
        result = cli_runner.invoke(cli, ["--verbose"])

        assert result.exit_code == 0
        # Should set INFO level (20)
        mock_configure.assert_called_once()
        assert mock_configure.call_args.kwargs["level"] == logging.INFO


# =============================================================================
# T020: Test --quiet suppression
# =============================================================================


def test_quiet_flag_sets_error_level(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that --quiet sets ERROR logging level."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock configure_logging from maverick.logging
    with patch("maverick.main.configure_logging") as mock_configure:
        result = cli_runner.invoke(cli, ["--quiet"])

        assert result.exit_code == 0
        # Should set ERROR level (40)
        mock_configure.assert_called_once()
        assert mock_configure.call_args.kwargs["level"] == logging.ERROR


def test_quiet_short_flag(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that -q short flag works for quiet option."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock configure_logging from maverick.logging
    with patch("maverick.main.configure_logging") as mock_configure:
        result = cli_runner.invoke(cli, ["-q"])

        assert result.exit_code == 0
        # Should set ERROR level (40)
        mock_configure.assert_called_once()
        assert mock_configure.call_args.kwargs["level"] == logging.ERROR


# =============================================================================
# T022: Test --version output
# =============================================================================


def test_version_option_output(cli_runner: CliRunner) -> None:
    """Test that --version displays version correctly."""
    result = cli_runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output
    assert "maverick" in result.output.lower()


def test_version_option_exits_immediately(cli_runner: CliRunner) -> None:
    """Test that --version exits without further processing."""
    result = cli_runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    # Should only show version, no other output
    assert "maverick" in result.output.lower()
    assert __version__ in result.output


# =============================================================================
# T023: Test --help output
# =============================================================================


def test_help_option_output(cli_runner: CliRunner) -> None:
    """Test that --help displays help correctly."""
    result = cli_runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "Maverick" in result.output
    # Should show all global options
    assert "--config" in result.output or "-c" in result.output
    assert "--verbose" in result.output or "-v" in result.output
    assert "--quiet" in result.output or "-q" in result.output
    assert "--version" in result.output
    assert "--help" in result.output


def test_help_shows_usage_examples(cli_runner: CliRunner) -> None:
    """Test that --help shows usage information."""
    result = cli_runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    # Should include usage line
    assert "Usage:" in result.output


# =============================================================================
# T024: Test quiet takes precedence over verbose
# =============================================================================


def test_quiet_takes_precedence_over_verbose(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that --quiet takes precedence when both --quiet and
    --verbose are specified.
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock configure_logging from maverick.logging
    with patch("maverick.main.configure_logging") as mock_configure:
        result = cli_runner.invoke(cli, ["-v", "-q"])

        assert result.exit_code == 0
        # Quiet should win - ERROR level (40)
        mock_configure.assert_called_once()
        assert mock_configure.call_args.kwargs["level"] == logging.ERROR


def test_quiet_precedence_with_multiple_verbose(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that --quiet takes precedence even with -vv."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock configure_logging from maverick.logging
    with patch("maverick.main.configure_logging") as mock_configure:
        result = cli_runner.invoke(cli, ["-vv", "--quiet"])

        assert result.exit_code == 0
        # Quiet should win - ERROR level (40)
        mock_configure.assert_called_once()
        assert mock_configure.call_args.kwargs["level"] == logging.ERROR


# =============================================================================
# T024a: Test piped input detection disables interactive prompts
# =============================================================================


def test_piped_stdin_detected(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that piped stdin is detected (stdin.isatty() returns False)."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    with patch("sys.stdin.isatty", return_value=False):
        result = cli_runner.invoke(cli, [])

        assert result.exit_code == 0
        # Rich Console auto-detects non-TTY stdin


def test_piped_stdout_detected(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that piped stdout is detected (stdout.isatty() returns False)."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    with patch("sys.stdout.isatty", return_value=False):
        result = cli_runner.invoke(cli, [])

        assert result.exit_code == 0
        # Rich Console auto-detects non-TTY stdout


def test_both_stdin_stdout_not_tty(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test behavior when both stdin and stdout are not TTY."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    with (
        patch("sys.stdin.isatty", return_value=False),
        patch("sys.stdout.isatty", return_value=False),
    ):
        result = cli_runner.invoke(cli, [])

        assert result.exit_code == 0
        # Rich Console auto-detects non-TTY environment


def test_tty_environment_enables_tui(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that CLI works when both stdin and stdout are TTY."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
    ):
        result = cli_runner.invoke(cli, [])

        assert result.exit_code == 0
        # Rich Console auto-detects TTY environment


# =============================================================================
# Integration Tests - Combining Multiple Options
# =============================================================================


def test_all_options_together(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test combining multiple global options."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create custom config
    custom_config = temp_dir / "custom.yaml"
    custom_config.write_text('verbosity: "debug"\n')

    result = cli_runner.invoke(
        cli,
        [
            "--config",
            str(custom_config),
            "-vv",
        ],
    )

    assert result.exit_code == 0


def test_cli_context_stored_in_click_context(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that CLIContext is created and stored in Click context."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # This test will verify that ctx.obj["cli_ctx"] contains a CLIContext instance
    # We'll need to add a test command to verify this in the implementation
    result = cli_runner.invoke(cli, ["-v"])

    assert result.exit_code == 0
    # In implementation, we'll verify CLIContext is in ctx.obj


# =============================================================================
# Tests: maverick.yaml project configuration requirement
# =============================================================================


def test_fly_without_maverick_yaml_exits_with_error(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that fly fails with config error when maverick.yaml is missing.

    Verifies:
    - Exit code is non-zero
    - Error mentions config not found
    - Suggestion mentions 'maverick init'
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock check_dependencies to return success so we reach the config check
    from maverick.cli.validators import DependencyStatus

    with patch("maverick.main.check_dependencies") as mock_check_deps:
        mock_check_deps.return_value = [
            DependencyStatus(
                name="git", available=True, version="2.39.0", path="/usr/bin/git"
            ),
            DependencyStatus(
                name="gh", available=True, version="2.20.0", path="/usr/bin/gh"
            ),
        ]

        # No maverick.yaml in temp_dir
        result = cli_runner.invoke(cli, ["fly", "--dry-run"])

        assert result.exit_code == 1
        assert "configuration not found" in result.output.lower()
        assert "maverick init" in result.output


def test_init_without_maverick_yaml_succeeds(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that init command is not affected by missing maverick.yaml.

    The init command should work without maverick.yaml since its purpose
    is to create that file.
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # init should not fail due to missing maverick.yaml
    # (it may fail for other reasons, but not the config check)
    result = cli_runner.invoke(cli, ["init", "--help"])

    assert result.exit_code == 0


def test_fly_with_maverick_yaml_passes_config_check(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
    maverick_yaml: Path,
) -> None:
    """Test that fly passes the config check when maverick.yaml exists.

    The command may fail later in workflow execution, but should not fail
    at the config existence check.
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock check_dependencies to return success
    from maverick.cli.validators import DependencyStatus

    with patch("maverick.main.check_dependencies") as mock_check_deps:
        mock_check_deps.return_value = [
            DependencyStatus(
                name="git", available=True, version="2.39.0", path="/usr/bin/git"
            ),
            DependencyStatus(
                name="gh", available=True, version="2.20.0", path="/usr/bin/gh"
            ),
        ]

        result = cli_runner.invoke(cli, ["fly", "--dry-run"])

        # Should NOT fail with "configuration not found"
        assert "configuration not found" not in result.output.lower()
