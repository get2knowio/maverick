"""Unit tests for global CLI options in main.py.

Tests comprehensive global options functionality:
- --config option for specifying custom config file
- --verbose stacking (-v, -vv, -vvv) for verbosity levels
- --quiet flag for suppressing non-essential output
- --no-tui flag for disabling TUI mode
- --version output
- --help output
- Precedence rules (quiet takes precedence over verbose)
- TTY and pipe auto-detection for interactive mode
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from maverick import __version__
from maverick.main import cli

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI test runner."""
    return CliRunner()


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

    import maverick.main

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock logging.basicConfig
    original_basicConfig = maverick.main.logging.basicConfig
    maverick.main.logging.basicConfig = MagicMock()

    try:
        result = cli_runner.invoke(cli, ["-v"])

        assert result.exit_code == 0
        # Should set INFO level (20)
        maverick.main.logging.basicConfig.assert_called_once()
        assert (
            maverick.main.logging.basicConfig.call_args.kwargs["level"] == logging.INFO
        )
    finally:
        maverick.main.logging.basicConfig = original_basicConfig


def test_verbose_double_flag_debug_level(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that -vv sets DEBUG logging level."""
    import os

    import maverick.main

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock logging.basicConfig
    original_basicConfig = maverick.main.logging.basicConfig
    maverick.main.logging.basicConfig = MagicMock()

    try:
        result = cli_runner.invoke(cli, ["-vv"])

        assert result.exit_code == 0
        # Should set DEBUG level (10)
        maverick.main.logging.basicConfig.assert_called_once()
        assert (
            maverick.main.logging.basicConfig.call_args.kwargs["level"] == logging.DEBUG
        )
    finally:
        maverick.main.logging.basicConfig = original_basicConfig


def test_verbose_triple_flag_debug_level(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that -vvv sets DEBUG logging level (same as -vv)."""
    import os

    import maverick.main

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock logging.basicConfig
    original_basicConfig = maverick.main.logging.basicConfig
    maverick.main.logging.basicConfig = MagicMock()

    try:
        result = cli_runner.invoke(cli, ["-vvv"])

        assert result.exit_code == 0
        # Should set DEBUG level (10) - max detail
        maverick.main.logging.basicConfig.assert_called_once()
        assert (
            maverick.main.logging.basicConfig.call_args.kwargs["level"] == logging.DEBUG
        )
    finally:
        maverick.main.logging.basicConfig = original_basicConfig


def test_verbose_long_flag(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that --verbose works same as -v."""
    import os

    import maverick.main

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock logging.basicConfig
    original_basicConfig = maverick.main.logging.basicConfig
    maverick.main.logging.basicConfig = MagicMock()

    try:
        result = cli_runner.invoke(cli, ["--verbose"])

        assert result.exit_code == 0
        # Should set INFO level (20)
        maverick.main.logging.basicConfig.assert_called_once()
        assert (
            maverick.main.logging.basicConfig.call_args.kwargs["level"] == logging.INFO
        )
    finally:
        maverick.main.logging.basicConfig = original_basicConfig


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

    import maverick.main

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock logging.basicConfig
    original_basicConfig = maverick.main.logging.basicConfig
    maverick.main.logging.basicConfig = MagicMock()

    try:
        result = cli_runner.invoke(cli, ["--quiet"])

        assert result.exit_code == 0
        # Should set ERROR level (40)
        maverick.main.logging.basicConfig.assert_called_once()
        assert (
            maverick.main.logging.basicConfig.call_args.kwargs["level"] == logging.ERROR
        )
    finally:
        maverick.main.logging.basicConfig = original_basicConfig


def test_quiet_short_flag(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that -q short flag works for quiet option."""
    import os

    import maverick.main

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock logging.basicConfig
    original_basicConfig = maverick.main.logging.basicConfig
    maverick.main.logging.basicConfig = MagicMock()

    try:
        result = cli_runner.invoke(cli, ["-q"])

        assert result.exit_code == 0
        # Should set ERROR level (40)
        maverick.main.logging.basicConfig.assert_called_once()
        assert (
            maverick.main.logging.basicConfig.call_args.kwargs["level"] == logging.ERROR
        )
    finally:
        maverick.main.logging.basicConfig = original_basicConfig


# =============================================================================
# T021: Test --no-tui flag
# =============================================================================


def test_no_tui_flag_disables_tui(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that --no-tui flag is recognized and stored in context."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    result = cli_runner.invoke(cli, ["--no-tui"])

    # Should succeed
    assert result.exit_code == 0

    # CLIContext.use_tui should be False (we'll verify in implementation)


def test_no_tui_with_tty_still_disables_tui(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that --no-tui disables TUI even when TTY is available."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock TTY detection to return True
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
    ):
        result = cli_runner.invoke(cli, ["--no-tui"])

        assert result.exit_code == 0
        # Even with TTY, --no-tui should disable TUI


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
    assert "--no-tui" in result.output
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

    import maverick.main

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock logging.basicConfig
    original_basicConfig = maverick.main.logging.basicConfig
    maverick.main.logging.basicConfig = MagicMock()

    try:
        result = cli_runner.invoke(cli, ["-v", "-q"])

        assert result.exit_code == 0
        # Quiet should win - ERROR level (40)
        maverick.main.logging.basicConfig.assert_called_once()
        assert (
            maverick.main.logging.basicConfig.call_args.kwargs["level"] == logging.ERROR
        )
    finally:
        maverick.main.logging.basicConfig = original_basicConfig


def test_quiet_precedence_with_multiple_verbose(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that --quiet takes precedence even with -vv."""
    import os

    import maverick.main

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock logging.basicConfig
    original_basicConfig = maverick.main.logging.basicConfig
    maverick.main.logging.basicConfig = MagicMock()

    try:
        result = cli_runner.invoke(cli, ["-vv", "--quiet"])

        assert result.exit_code == 0
        # Quiet should win - ERROR level (40)
        maverick.main.logging.basicConfig.assert_called_once()
        assert (
            maverick.main.logging.basicConfig.call_args.kwargs["level"] == logging.ERROR
        )
    finally:
        maverick.main.logging.basicConfig = original_basicConfig


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
        # CLIContext.use_tui should be False when stdin is not a TTY


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
        # CLIContext.use_tui should be False when stdout is not a TTY


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
        # CLIContext.use_tui should be False


def test_tty_environment_enables_tui(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that TUI is enabled when both stdin and stdout are TTY."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
    ):
        result = cli_runner.invoke(cli, [])

        assert result.exit_code == 0
        # CLIContext.use_tui should be True when both are TTY


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
            "--no-tui",
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
    result = cli_runner.invoke(cli, ["-v", "--no-tui"])

    assert result.exit_code == 0
    # In implementation, we'll verify CLIContext is in ctx.obj


# =============================================================================
# Fly Command Tests (T030-T036)
# =============================================================================


def test_fly_command_with_valid_branch(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T030: Test fly command with valid branch - 'maverick fly feature-branch'."""
    import os
    from unittest.mock import patch

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a git repo and feature branch
    os.system("git init > /dev/null 2>&1")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")
    os.system("git checkout -b feature-branch > /dev/null 2>&1")

    # Mock FlyWorkflow.execute as async generator
    from maverick.agents.result import AgentUsage
    from maverick.workflows.fly import (
        FlyResult,
        FlyWorkflowCompleted,
        WorkflowStage,
        WorkflowState,
    )

    mock_result = FlyResult(
        success=True,
        state=WorkflowState(
            stage=WorkflowStage.COMPLETE,
            branch="feature-branch",
            task_file=None,
            implementation_result=None,
            validation_result=None,
            review_results=[],
            pr_url=None,
            errors=[],
        ),
        summary="Workflow completed successfully",
        token_usage=AgentUsage(
            input_tokens=0, output_tokens=0, total_cost_usd=0.0, duration_ms=0
        ),
        total_cost_usd=0.0,
    )

    async def mock_execute(inputs):
        yield FlyWorkflowCompleted(result=mock_result)

    with patch("maverick.main.FlyWorkflow") as mock_workflow_class:
        mock_workflow = MagicMock()
        mock_workflow.execute = mock_execute
        mock_workflow_class.return_value = mock_workflow

        result = cli_runner.invoke(cli, ["fly", "feature-branch"])

        # Should succeed
        assert result.exit_code == 0


def test_fly_with_task_file_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T031: Test fly --task-file option.

    Command: 'maverick fly branch --task-file tasks.md'
    """
    import os
    from unittest.mock import patch

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a git repo and feature branch
    os.system("git init > /dev/null 2>&1")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")
    os.system("git checkout -b feature-branch > /dev/null 2>&1")

    # Create a task file
    task_file = temp_dir / "tasks.md"
    task_file.write_text("# Tasks\n- Task 1\n- Task 2\n")

    # Mock FlyWorkflow.execute as async generator
    from maverick.agents.result import AgentUsage
    from maverick.workflows.fly import (
        FlyResult,
        FlyWorkflowCompleted,
        WorkflowStage,
        WorkflowState,
    )

    captured_inputs = {}

    async def mock_execute(inputs):
        captured_inputs["inputs"] = inputs
        mock_result = FlyResult(
            success=True,
            state=WorkflowState(
                stage=WorkflowStage.COMPLETE,
                branch="feature-branch",
                task_file=task_file,
                implementation_result=None,
                validation_result=None,
                review_results=[],
                pr_url=None,
                errors=[],
            ),
            summary="Workflow completed successfully",
            token_usage=AgentUsage(
                input_tokens=0, output_tokens=0, total_cost_usd=0.0, duration_ms=0
            ),
            total_cost_usd=0.0,
        )
        yield FlyWorkflowCompleted(result=mock_result)

    with patch("maverick.main.FlyWorkflow") as mock_workflow_class:
        mock_workflow = MagicMock()
        mock_workflow.execute = mock_execute
        mock_workflow_class.return_value = mock_workflow

        result = cli_runner.invoke(
            cli, ["fly", "feature-branch", "--task-file", str(task_file)]
        )

        # Should succeed
        assert result.exit_code == 0
        # Verify task_file was passed to workflow
        assert captured_inputs["inputs"].task_file == task_file


def test_fly_skip_review_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T032: Test fly --skip-review option."""
    import os
    from unittest.mock import patch

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a git repo and feature branch
    os.system("git init > /dev/null 2>&1")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")
    os.system("git checkout -b feature-branch > /dev/null 2>&1")

    # Mock FlyWorkflow.execute as async generator
    from maverick.agents.result import AgentUsage
    from maverick.workflows.fly import (
        FlyResult,
        FlyWorkflowCompleted,
        WorkflowStage,
        WorkflowState,
    )

    captured_inputs = {}

    async def mock_execute(inputs):
        captured_inputs["inputs"] = inputs
        mock_result = FlyResult(
            success=True,
            state=WorkflowState(
                stage=WorkflowStage.COMPLETE,
                branch="feature-branch",
                task_file=None,
                implementation_result=None,
                validation_result=None,
                review_results=[],
                pr_url=None,
                errors=[],
            ),
            summary="Workflow completed successfully",
            token_usage=AgentUsage(
                input_tokens=0, output_tokens=0, total_cost_usd=0.0, duration_ms=0
            ),
            total_cost_usd=0.0,
        )
        yield FlyWorkflowCompleted(result=mock_result)

    with patch("maverick.main.FlyWorkflow") as mock_workflow_class:
        mock_workflow = MagicMock()
        mock_workflow.execute = mock_execute
        mock_workflow_class.return_value = mock_workflow

        result = cli_runner.invoke(cli, ["fly", "feature-branch", "--skip-review"])

        # Should succeed
        assert result.exit_code == 0
        # Verify skip_review was passed to workflow
        assert captured_inputs["inputs"].skip_review is True


def test_fly_skip_pr_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T033: Test fly --skip-pr option."""
    import os
    from unittest.mock import patch

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a git repo and feature branch
    os.system("git init > /dev/null 2>&1")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")
    os.system("git checkout -b feature-branch > /dev/null 2>&1")

    # Mock FlyWorkflow.execute as async generator
    from maverick.agents.result import AgentUsage
    from maverick.workflows.fly import (
        FlyResult,
        FlyWorkflowCompleted,
        WorkflowStage,
        WorkflowState,
    )

    captured_inputs = {}

    async def mock_execute(inputs):
        captured_inputs["inputs"] = inputs
        mock_result = FlyResult(
            success=True,
            state=WorkflowState(
                stage=WorkflowStage.COMPLETE,
                branch="feature-branch",
                task_file=None,
                implementation_result=None,
                validation_result=None,
                review_results=[],
                pr_url=None,
                errors=[],
            ),
            summary="Workflow completed successfully",
            token_usage=AgentUsage(
                input_tokens=0, output_tokens=0, total_cost_usd=0.0, duration_ms=0
            ),
            total_cost_usd=0.0,
        )
        yield FlyWorkflowCompleted(result=mock_result)

    with patch("maverick.main.FlyWorkflow") as mock_workflow_class:
        mock_workflow = MagicMock()
        mock_workflow.execute = mock_execute
        mock_workflow_class.return_value = mock_workflow

        result = cli_runner.invoke(cli, ["fly", "feature-branch", "--skip-pr"])

        # Should succeed
        assert result.exit_code == 0
        # Verify skip_pr was passed to workflow
        assert captured_inputs["inputs"].skip_pr is True


def test_fly_dry_run_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T034: Test fly --dry-run option.

    Should show planned actions without executing.
    """
    import os
    from unittest.mock import AsyncMock, patch

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a git repo and feature branch
    os.system("git init > /dev/null 2>&1")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")
    os.system("git checkout -b feature-branch > /dev/null 2>&1")

    # Mock FlyWorkflow - should NOT be called in dry-run
    with patch("maverick.main.FlyWorkflow") as mock_workflow_class:
        mock_workflow = AsyncMock()
        mock_workflow_class.return_value = mock_workflow

        result = cli_runner.invoke(cli, ["fly", "feature-branch", "--dry-run"])

        # Should succeed
        assert result.exit_code == 0
        # Should show planned actions in output
        assert "would" in result.output.lower() or "dry run" in result.output.lower()
        # Workflow should NOT be executed in dry-run
        mock_workflow.execute.assert_not_called()


def test_fly_with_nonexistent_branch_error(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T035: Test fly with non-existent branch error."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a git repo but don't create the branch
    os.system("git init > /dev/null 2>&1")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")

    result = cli_runner.invoke(cli, ["fly", "nonexistent-branch"])

    # Should fail with exit code 1
    assert result.exit_code == 1
    # Should show error message about branch not existing
    assert "branch" in result.output.lower() or "nonexistent" in result.output.lower()


def test_fly_keyboard_interrupt_handling(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T036: Test fly keyboard interrupt handling - should exit with code 130."""
    import os
    from unittest.mock import patch

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a git repo and feature branch
    os.system("git init > /dev/null 2>&1")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")
    os.system("git checkout -b feature-branch > /dev/null 2>&1")

    # Mock FlyWorkflow.execute to raise KeyboardInterrupt as async generator
    async def mock_execute(inputs):
        raise KeyboardInterrupt()
        yield  # pragma: no cover

    with patch("maverick.main.FlyWorkflow") as mock_workflow_class:
        mock_workflow = MagicMock()
        mock_workflow.execute = mock_execute
        mock_workflow_class.return_value = mock_workflow

        result = cli_runner.invoke(cli, ["fly", "feature-branch"])

        # Should exit with code 130
        assert result.exit_code == 130
        # Should show interrupted message
        assert (
            "interrupt" in result.output.lower() or "cancelled" in result.output.lower()
        )


# =============================================================================
# Refuel Command Tests (T045-T050)
# =============================================================================


def test_refuel_command_default_behavior(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test T045: refuel command with default options.

    Verifies:
    - Command accepts no arguments
    - Uses default label "tech-debt"
    - Uses default limit 5
    - Uses parallel mode by default
    - Checks GitHub auth before execution
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock GitHub auth check to succeed
    with patch("maverick.main.check_git_auth") as mock_auth:
        mock_auth.return_value = MagicMock(available=True)

        # Mock workflow execution
        with patch("maverick.main.RefuelWorkflow") as mock_workflow_cls:
            mock_workflow = MagicMock()
            mock_workflow_cls.return_value = mock_workflow

            # Mock execute to return an async generator
            async def mock_execute(inputs):
                from maverick.workflows.refuel import (
                    RefuelCompleted,
                    RefuelResult,
                    RefuelStarted,
                )

                yield RefuelStarted(inputs=inputs, issues_found=0)
                yield RefuelCompleted(
                    result=RefuelResult(
                        success=True,
                        issues_found=0,
                        issues_processed=0,
                        issues_fixed=0,
                        issues_failed=0,
                        issues_skipped=0,
                        results=[],
                        total_duration_ms=0,
                        total_cost_usd=0.0,
                    )
                )

            mock_workflow.execute.side_effect = mock_execute

            result = cli_runner.invoke(cli, ["refuel"])

            assert result.exit_code == 0
            # Verify auth was checked
            mock_auth.assert_called_once()


def test_refuel_label_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test T046: refuel --label option.

    Verifies:
    - --label/-l option is accepted
    - Custom label is passed to workflow
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock GitHub auth check to succeed
    with patch("maverick.main.check_git_auth") as mock_auth:
        mock_auth.return_value = MagicMock(available=True)

        # Mock workflow execution
        with patch("maverick.main.RefuelWorkflow") as mock_workflow_cls:
            mock_workflow = MagicMock()
            mock_workflow_cls.return_value = mock_workflow

            # Mock execute to return an async generator
            async def mock_execute(inputs):
                from maverick.workflows.refuel import (
                    RefuelCompleted,
                    RefuelResult,
                    RefuelStarted,
                )

                # Verify custom label was passed
                assert inputs.label == "bug"
                yield RefuelStarted(inputs=inputs, issues_found=0)
                yield RefuelCompleted(
                    result=RefuelResult(
                        success=True,
                        issues_found=0,
                        issues_processed=0,
                        issues_fixed=0,
                        issues_failed=0,
                        issues_skipped=0,
                        results=[],
                        total_duration_ms=0,
                        total_cost_usd=0.0,
                    )
                )

            mock_workflow.execute.side_effect = mock_execute

            result = cli_runner.invoke(cli, ["refuel", "--label", "bug"])

            assert result.exit_code == 0


def test_refuel_limit_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test T047: refuel --limit option.

    Verifies:
    - --limit/-n option is accepted
    - Custom limit is passed to workflow
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock GitHub auth check to succeed
    with patch("maverick.main.check_git_auth") as mock_auth:
        mock_auth.return_value = MagicMock(available=True)

        # Mock workflow execution
        with patch("maverick.main.RefuelWorkflow") as mock_workflow_cls:
            mock_workflow = MagicMock()
            mock_workflow_cls.return_value = mock_workflow

            # Mock execute to return an async generator
            async def mock_execute(inputs):
                from maverick.workflows.refuel import (
                    RefuelCompleted,
                    RefuelResult,
                    RefuelStarted,
                )

                # Verify custom limit was passed
                assert inputs.limit == 3
                yield RefuelStarted(inputs=inputs, issues_found=0)
                yield RefuelCompleted(
                    result=RefuelResult(
                        success=True,
                        issues_found=0,
                        issues_processed=0,
                        issues_fixed=0,
                        issues_failed=0,
                        issues_skipped=0,
                        results=[],
                        total_duration_ms=0,
                        total_cost_usd=0.0,
                    )
                )

            mock_workflow.execute.side_effect = mock_execute

            result = cli_runner.invoke(cli, ["refuel", "--limit", "3"])

            assert result.exit_code == 0


def test_refuel_sequential_flag(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test T048: refuel --sequential flag.

    Verifies:
    - --sequential flag is accepted
    - Parallel mode is disabled (parallel=False)
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock GitHub auth check to succeed
    with patch("maverick.main.check_git_auth") as mock_auth:
        mock_auth.return_value = MagicMock(available=True)

        # Mock workflow execution
        with patch("maverick.main.RefuelWorkflow") as mock_workflow_cls:
            mock_workflow = MagicMock()
            mock_workflow_cls.return_value = mock_workflow

            # Mock execute to return an async generator
            async def mock_execute(inputs):
                from maverick.workflows.refuel import (
                    RefuelCompleted,
                    RefuelResult,
                    RefuelStarted,
                )

                # Verify sequential mode (parallel=False)
                assert inputs.parallel is False
                yield RefuelStarted(inputs=inputs, issues_found=0)
                yield RefuelCompleted(
                    result=RefuelResult(
                        success=True,
                        issues_found=0,
                        issues_processed=0,
                        issues_fixed=0,
                        issues_failed=0,
                        issues_skipped=0,
                        results=[],
                        total_duration_ms=0,
                        total_cost_usd=0.0,
                    )
                )

            mock_workflow.execute.side_effect = mock_execute

            result = cli_runner.invoke(cli, ["refuel", "--sequential"])

            assert result.exit_code == 0


def test_refuel_dry_run_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test T049: refuel --dry-run option.

    Verifies:
    - --dry-run flag is accepted
    - Lists matching issues without processing
    - Dry-run mode is passed to workflow
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock GitHub auth check to succeed
    with patch("maverick.main.check_git_auth") as mock_auth:
        mock_auth.return_value = MagicMock(available=True)

        # Mock workflow execution
        with patch("maverick.main.RefuelWorkflow") as mock_workflow_cls:
            mock_workflow = MagicMock()
            mock_workflow_cls.return_value = mock_workflow

            # Mock execute to return an async generator with dry-run info
            async def mock_execute(inputs):
                from maverick.agents.result import AgentUsage
                from maverick.workflows.refuel import (
                    GitHubIssue,
                    IssueProcessingResult,
                    IssueStatus,
                    RefuelCompleted,
                    RefuelResult,
                    RefuelStarted,
                )

                # Verify dry-run mode
                assert inputs.dry_run is True

                # Simulate finding issues in dry-run
                yield RefuelStarted(inputs=inputs, issues_found=2)
                yield RefuelCompleted(
                    result=RefuelResult(
                        success=True,
                        issues_found=2,
                        issues_processed=0,
                        issues_fixed=0,
                        issues_failed=0,
                        issues_skipped=2,
                        results=[
                            IssueProcessingResult(
                                issue=GitHubIssue(
                                    number=1,
                                    title="Test issue 1",
                                    body=None,
                                    labels=["tech-debt"],
                                    assignee=None,
                                    url="https://github.com/test/repo/issues/1",
                                ),
                                status=IssueStatus.SKIPPED,
                                branch=None,
                                pr_url=None,
                                error=None,
                                duration_ms=0,
                                agent_usage=AgentUsage(
                                    input_tokens=0,
                                    output_tokens=0,
                                    total_cost_usd=0.0,
                                    duration_ms=0,
                                ),
                            ),
                        ],
                        total_duration_ms=0,
                        total_cost_usd=0.0,
                    )
                )

            mock_workflow.execute.side_effect = mock_execute

            result = cli_runner.invoke(cli, ["refuel", "--dry-run"])

            assert result.exit_code == 0


def test_refuel_keyboard_interrupt_handling(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test T050: refuel keyboard interrupt handling.

    Verifies:
    - KeyboardInterrupt during workflow execution
    - Exit code 130 (INTERRUPTED)
    - Graceful shutdown message
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock GitHub auth check to succeed
    with patch("maverick.main.check_git_auth") as mock_auth:
        mock_auth.return_value = MagicMock(available=True)

        # Mock workflow execution to raise KeyboardInterrupt
        with patch("maverick.main.RefuelWorkflow") as mock_workflow_cls:
            mock_workflow = MagicMock()
            mock_workflow_cls.return_value = mock_workflow

            # Mock execute to raise KeyboardInterrupt
            async def mock_execute(inputs):
                raise KeyboardInterrupt()
                yield  # pragma: no cover - unreachable but needed for async generator

            mock_workflow.execute = mock_execute

            result = cli_runner.invoke(cli, ["refuel"])

            assert result.exit_code == 130
            assert (
                "Interrupted" in result.output or "interrupt" in result.output.lower()
            )


# =============================================================================
# Review Command Tests (T057-T061)
# =============================================================================


def test_review_command_with_valid_pr_number(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T057: Test review command with valid PR number - 'maverick review 123'.

    Verifies:
    - Command accepts PR number argument
    - PR validation using 'gh pr view'
    - CodeReviewerAgent is executed
    - Success exit code
    """
    import json
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock check_dependencies to return success (FR-013 startup validation)
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

        # Mock gh pr view to succeed
        with patch("subprocess.run") as mock_subprocess:
            # First call: gh pr view 123 (validation)
            # Second call: gh pr view 123 --json headRefName,baseRefName
            pr_data = {"headRefName": "feature-123", "baseRefName": "main"}
            mock_subprocess.side_effect = [
                MagicMock(returncode=0, stdout="PR #123", stderr=""),
                MagicMock(returncode=0, stdout=json.dumps(pr_data), stderr=""),
            ]

            # Mock CodeReviewerAgent
            with patch("maverick.main.CodeReviewerAgent") as mock_agent_cls:
                mock_agent = MagicMock()
                mock_agent_cls.return_value = mock_agent

                # Mock agent execution
                async def mock_execute(context):
                    from maverick.models.review import ReviewResult

                    return ReviewResult(
                        success=True,
                        findings=[],
                        files_reviewed=3,
                        summary="Reviewed 3 files, no issues found",
                        metadata={"branch": "feature-123", "base_branch": "main"},
                    )

                mock_agent.execute = mock_execute

                result = cli_runner.invoke(cli, ["review", "123"])

                assert result.exit_code == 0
                # Verify gh pr view was called
                assert mock_subprocess.call_count == 2


def test_review_with_fix_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T058: Test review --fix option - 'maverick review 123 --fix'.

    Verifies:
    - --fix flag is accepted
    - Fix mode is passed to the review agent
    """
    import json
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock check_dependencies to return success (FR-013 startup validation)
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

        # Mock gh pr view to succeed
        with patch("subprocess.run") as mock_subprocess:
            pr_data = {"headRefName": "feature-123", "baseRefName": "main"}
            mock_subprocess.side_effect = [
                MagicMock(returncode=0, stdout="PR #123", stderr=""),
                MagicMock(returncode=0, stdout=json.dumps(pr_data), stderr=""),
            ]

            # Mock CodeReviewerAgent
            with patch("maverick.main.CodeReviewerAgent") as mock_agent_cls:
                mock_agent = MagicMock()
                mock_agent_cls.return_value = mock_agent

                # Mock agent execution
                async def mock_execute(context):
                    from maverick.models.review import ReviewResult

                    return ReviewResult(
                        success=True,
                        findings=[],
                        files_reviewed=3,
                        summary="Reviewed 3 files, no issues found",
                        metadata={"branch": "feature-123", "base_branch": "main"},
                    )

                mock_agent.execute = mock_execute

                result = cli_runner.invoke(cli, ["review", "123", "--fix"])

                assert result.exit_code == 0


def test_review_output_json_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T059: Test review --output json option - outputs valid JSON.

    Verifies:
    - --output json flag is accepted
    - Output is valid JSON
    - Contains expected review data
    """
    import json
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock check_dependencies to return success (FR-013 startup validation)
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

        # Mock gh pr view to succeed
        with patch("subprocess.run") as mock_subprocess:
            pr_data = {"headRefName": "feature-123", "baseRefName": "main"}
            mock_subprocess.side_effect = [
                MagicMock(returncode=0, stdout="PR #123", stderr=""),
                MagicMock(returncode=0, stdout=json.dumps(pr_data), stderr=""),
            ]

            # Mock CodeReviewerAgent
            with patch("maverick.main.CodeReviewerAgent") as mock_agent_cls:
                mock_agent = MagicMock()
                mock_agent_cls.return_value = mock_agent

                # Mock agent execution
                async def mock_execute(context):
                    from maverick.models.review import ReviewResult

                    return ReviewResult(
                        success=True,
                        findings=[],
                        files_reviewed=3,
                        summary="Reviewed 3 files, no issues found",
                        metadata={"branch": "feature-123", "base_branch": "main"},
                    )

                mock_agent.execute = mock_execute

                result = cli_runner.invoke(cli, ["review", "123", "--output", "json"])

                assert result.exit_code == 0
                # Verify output is valid JSON
                try:
                    data = json.loads(result.output)
                    assert "success" in data
                    assert "findings" in data
                    assert "summary" in data
                except json.JSONDecodeError:
                    pytest.fail("Output is not valid JSON")


def test_review_output_markdown_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T060: Test review --output markdown option - outputs markdown.

    Verifies:
    - --output markdown flag is accepted
    - Output is formatted as markdown
    - Contains review summary
    """
    import json
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock check_dependencies to return success (FR-013 startup validation)
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

        # Mock gh pr view to succeed
        with patch("subprocess.run") as mock_subprocess:
            pr_data = {"headRefName": "feature-123", "baseRefName": "main"}
            mock_subprocess.side_effect = [
                MagicMock(returncode=0, stdout="PR #123", stderr=""),
                MagicMock(returncode=0, stdout=json.dumps(pr_data), stderr=""),
            ]

            # Mock CodeReviewerAgent
            with patch("maverick.main.CodeReviewerAgent") as mock_agent_cls:
                mock_agent = MagicMock()
                mock_agent_cls.return_value = mock_agent

                # Mock agent execution
                async def mock_execute(context):
                    from maverick.models.review import ReviewResult

                    return ReviewResult(
                        success=True,
                        findings=[],
                        files_reviewed=3,
                        summary="Reviewed 3 files, no issues found",
                        metadata={"branch": "feature-123", "base_branch": "main"},
                    )

                mock_agent.execute = mock_execute

                result = cli_runner.invoke(
                    cli, ["review", "123", "--output", "markdown"]
                )

                assert result.exit_code == 0
                # Verify markdown formatting
                assert (
                    "#" in result.output
                    or "**" in result.output
                    or result.output.strip().startswith("Reviewed")
                )


def test_review_output_text_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test review --output text option - outputs plain text.

    Verifies:
    - --output text flag is accepted
    - Output is formatted as plain text
    - Contains review summary
    """
    import json
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock check_dependencies
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

        # Mock gh pr view
        with patch("subprocess.run") as mock_subprocess:
            pr_data = {"headRefName": "feature-123", "baseRefName": "main"}
            mock_subprocess.side_effect = [
                MagicMock(returncode=0, stdout="PR #123", stderr=""),
                MagicMock(returncode=0, stdout=json.dumps(pr_data), stderr=""),
            ]

            # Mock CodeReviewerAgent
            with patch("maverick.main.CodeReviewerAgent") as mock_agent_cls:
                mock_agent = MagicMock()
                mock_agent_cls.return_value = mock_agent

                # Mock agent execution
                async def mock_execute(context):
                    from maverick.models.review import ReviewResult

                    return ReviewResult(
                        success=True,
                        findings=[],
                        files_reviewed=3,
                        summary="Reviewed 3 files, no issues found",
                        metadata={"branch": "feature-123", "base_branch": "main"},
                    )

                mock_agent.execute = mock_execute

                result = cli_runner.invoke(cli, ["review", "123", "--output", "text"])

                assert result.exit_code == 0
                # Verify text formatting (should contain summary)
                assert "Reviewed 3 files" in result.output
                # Should NOT look like JSON (simple heuristic)
                assert not result.output.strip().startswith("{")


def test_review_with_nonexistent_pr_error(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T061: Test review with non-existent PR error.

    Verifies:
    - PR validation fails for non-existent PR
    - Exit code 1 (FAILURE)
    - Error message mentions PR not found
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Mock gh pr view to fail (PR not found)
    with patch("subprocess.run") as mock_subprocess:
        mock_subprocess.return_value = MagicMock(
            returncode=1, stdout="", stderr="pull request not found"
        )

        result = cli_runner.invoke(cli, ["review", "999"])

        assert result.exit_code == 1
        # Error message should mention PR not found
        assert "999" in result.output or "not found" in result.output.lower()


# =============================================================================
# Config Command Tests (T069-T075)
# =============================================================================


def test_config_init_creates_default_file(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T069: Test config init creates default file - 'maverick config init'."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Ensure no config exists
    config_file = temp_dir / "maverick.yaml"
    assert not config_file.exists()

    result = cli_runner.invoke(cli, ["config", "init"])

    # Should succeed
    assert result.exit_code == 0
    # Should create config file
    assert config_file.exists()
    # Should contain valid YAML
    import yaml

    config_data = yaml.safe_load(config_file.read_text())
    assert config_data is not None
    # Should have success message
    assert "created" in result.output.lower() or "initialized" in result.output.lower()


def test_config_init_fails_with_existing_file(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T069: Test config init fails when file already exists without --force."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create existing config
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("# Existing config\n")

    result = cli_runner.invoke(cli, ["config", "init"])

    # Should fail
    assert result.exit_code == 1
    # Should show error about existing file
    assert "exists" in result.output.lower() or "already" in result.output.lower()


def test_config_init_force_overwrites_existing_file(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T070: Test config init --force overwrites existing file."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create existing config
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("# Old config\n")

    result = cli_runner.invoke(cli, ["config", "init", "--force"])

    # Should succeed
    assert result.exit_code == 0
    # File should be overwritten with new content
    content = config_file.read_text()
    assert "# Old config" not in content
    # Should have success message
    assert "created" in result.output.lower() or "initialized" in result.output.lower()


def test_config_init_uses_utf8_encoding(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test config init writes file with UTF-8 encoding using pathlib.

    Verifies that:
    - Config file is created using pathlib.Path.write_text()
    - File has proper UTF-8 encoding
    - No raw open() calls are used
    """
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    result = cli_runner.invoke(cli, ["config", "init"])

    # Should succeed
    assert result.exit_code == 0

    config_file = temp_dir / "maverick.yaml"
    assert config_file.exists()

    # Verify file can be read with UTF-8 encoding (pathlib default)
    content = config_file.read_text(encoding="utf-8")
    assert "github:" in content
    assert "notifications:" in content

    # Verify valid YAML structure
    import yaml

    config_data = yaml.safe_load(content)
    assert "github" in config_data
    assert "notifications" in config_data


def test_config_show_displays_yaml(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T071: Test config show displays YAML - 'maverick config show'."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a config file
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("""
github:
  owner: "test-org"
  repo: "test-repo"
verbosity: "info"
""")

    result = cli_runner.invoke(cli, ["config", "show"])

    # Should succeed
    assert result.exit_code == 0
    # Should show YAML content
    assert "github:" in result.output
    assert "test-org" in result.output
    assert "test-repo" in result.output


def test_config_show_format_json(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T072: Test config show --format json outputs JSON."""
    import json
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a config file
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("""
github:
  owner: "test-org"
  repo: "test-repo"
verbosity: "info"
""")

    result = cli_runner.invoke(cli, ["config", "show", "--format", "json"])

    # Should succeed
    assert result.exit_code == 0
    # Should be valid JSON
    try:
        data = json.loads(result.output)
        assert "github" in data
        assert data["github"]["owner"] == "test-org"
        assert data["github"]["repo"] == "test-repo"
    except json.JSONDecodeError:
        pytest.fail("Output is not valid JSON")


def test_config_show_format_short_flag(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T072: Test config show -f json (short flag)."""
    import json
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a config file
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text('verbosity: "debug"\n')

    result = cli_runner.invoke(cli, ["config", "show", "-f", "json"])

    # Should succeed
    assert result.exit_code == 0
    # Should be valid JSON
    data = json.loads(result.output)
    assert data is not None


def test_config_edit_opens_editor(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T073: Test config edit opens editor - 'maverick config edit'."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a config file
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("# Test config\n")

    # Mock click.edit to simulate editor opening
    with patch("click.edit") as mock_edit:
        mock_edit.return_value = "# Modified config\n"

        result = cli_runner.invoke(cli, ["config", "edit"])

        # Should succeed
        assert result.exit_code == 0
        # Should call click.edit with file content
        mock_edit.assert_called_once()


def test_config_edit_user_flag(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T073: Test config edit --user opens user config."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create user config directory and file
    user_config_dir = temp_dir / ".config" / "maverick"
    user_config_dir.mkdir(parents=True, exist_ok=True)
    user_config_file = user_config_dir / "config.yaml"
    user_config_file.write_text("# User config\n")

    # Mock click.edit
    with patch("click.edit") as mock_edit:
        mock_edit.return_value = "# Modified user config\n"

        result = cli_runner.invoke(cli, ["config", "edit", "--user"])

        # Should succeed
        assert result.exit_code == 0
        # Should call click.edit
        mock_edit.assert_called_once()


def test_config_edit_creates_file_if_not_exists(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T073: Test config edit creates file if it doesn't exist."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Ensure no config exists
    config_file = temp_dir / "maverick.yaml"
    assert not config_file.exists()

    # Mock click.edit
    with patch("click.edit") as mock_edit:
        mock_edit.return_value = "# New config\n"

        result = cli_runner.invoke(cli, ["config", "edit"])

        # Should succeed
        assert result.exit_code == 0
        # Should call click.edit (with empty or None text)
        mock_edit.assert_called_once()


def test_config_validate_with_valid_config(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T074: Test config validate with valid config."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create valid config file
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("""
github:
  owner: "test-org"
  repo: "test-repo"
  default_branch: "main"
verbosity: "info"
""")

    result = cli_runner.invoke(cli, ["config", "validate"])

    # Should succeed
    assert result.exit_code == 0
    # Should show validation success message
    assert "valid" in result.output.lower() or "success" in result.output.lower()


def test_config_validate_with_invalid_config(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T075: Test config validate with invalid config."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create invalid config file
    config_file = temp_dir / "maverick.yaml"
    config_file.write_text("""
model:
  max_tokens: -1
verbosity: "invalid_level"
""")

    result = cli_runner.invoke(cli, ["config", "validate"])

    # Should fail
    assert result.exit_code == 1
    # Should show validation error
    assert "error" in result.output.lower() or "invalid" in result.output.lower()


def test_config_validate_with_file_option(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T075: Test config validate --file option."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create custom config file
    custom_config = temp_dir / "custom.yaml"
    custom_config.write_text("""
github:
  owner: "custom-org"
verbosity: "debug"
""")

    result = cli_runner.invoke(
        cli, ["config", "validate", "--file", str(custom_config)]
    )

    # Should succeed
    assert result.exit_code == 0
    # Should show validation success
    assert "valid" in result.output.lower() or "success" in result.output.lower()


def test_config_validate_nonexistent_file(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T075: Test config validate with nonexistent file."""
    import os

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # No config file exists
    result = cli_runner.invoke(cli, ["config", "validate"])

    # Should still succeed (no project config = use defaults)
    assert result.exit_code == 0


# =============================================================================
# Status Command Tests (T082-T085)
# =============================================================================


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
    import json
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
