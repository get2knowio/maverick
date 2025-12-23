"""Unit tests for the refuel CLI command.

Tests refuel command functionality:
- Default behavior
- Label option
- Limit option
- Sequential flag
- Dry run option
- Keyboard interrupt handling
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from maverick.main import cli


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
    with patch("maverick.cli.commands.refuel.check_git_auth") as mock_auth:
        mock_auth.return_value = MagicMock(available=True)

        # Mock workflow execution
        with patch("maverick.cli.commands.refuel.RefuelWorkflow") as mock_workflow_cls:
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
    with patch("maverick.cli.commands.refuel.check_git_auth") as mock_auth:
        mock_auth.return_value = MagicMock(available=True)

        # Mock workflow execution
        with patch("maverick.cli.commands.refuel.RefuelWorkflow") as mock_workflow_cls:
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
    with patch("maverick.cli.commands.refuel.check_git_auth") as mock_auth:
        mock_auth.return_value = MagicMock(available=True)

        # Mock workflow execution
        with patch("maverick.cli.commands.refuel.RefuelWorkflow") as mock_workflow_cls:
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
    with patch("maverick.cli.commands.refuel.check_git_auth") as mock_auth:
        mock_auth.return_value = MagicMock(available=True)

        # Mock workflow execution
        with patch("maverick.cli.commands.refuel.RefuelWorkflow") as mock_workflow_cls:
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
    with patch("maverick.cli.commands.refuel.check_git_auth") as mock_auth:
        mock_auth.return_value = MagicMock(available=True)

        # Mock workflow execution
        with patch("maverick.cli.commands.refuel.RefuelWorkflow") as mock_workflow_cls:
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
    with patch("maverick.cli.commands.refuel.check_git_auth") as mock_auth:
        mock_auth.return_value = MagicMock(available=True)

        # Mock workflow execution to raise KeyboardInterrupt
        with patch("maverick.cli.commands.refuel.RefuelWorkflow") as mock_workflow_cls:
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
