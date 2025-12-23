"""Unit tests for the fly CLI command.

Tests fly command functionality:
- Valid branch execution
- Task file option
- Skip review option
- Skip PR option
- Dry run option
- Error handling for nonexistent branches
- Keyboard interrupt handling
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from maverick.main import cli


def test_fly_command_with_valid_branch(
    cli_runner: CliRunner,
    temp_dir: Path,
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T030: Test fly command with valid branch - 'maverick fly feature-branch'."""
    import os

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

    with patch("maverick.cli.commands.fly.FlyWorkflow") as mock_workflow_class:
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

    with patch("maverick.cli.commands.fly.FlyWorkflow") as mock_workflow_class:
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

    with patch("maverick.cli.commands.fly.FlyWorkflow") as mock_workflow_class:
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

    with patch("maverick.cli.commands.fly.FlyWorkflow") as mock_workflow_class:
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

    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)

    # Create a git repo and feature branch
    os.system("git init > /dev/null 2>&1")
    os.system("git config user.email 'test@example.com'")
    os.system("git config user.name 'Test User'")
    os.system("git checkout -b feature-branch > /dev/null 2>&1")

    # Mock FlyWorkflow - should NOT be called in dry-run
    with patch("maverick.cli.commands.fly.FlyWorkflow") as mock_workflow_class:
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

    with patch("maverick.cli.commands.fly.FlyWorkflow") as mock_workflow_class:
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
