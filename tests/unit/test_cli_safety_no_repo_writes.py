"""Safety tests for CLI - no repository writes.

Verifies that CLI commands do not perform git write operations per FR-011.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_cli_discovery_no_git_writes(tmp_path: Path):
    """Test that discovery does not invoke any git write commands."""
    from src.cli._discovery import discover_tasks

    # Setup test repository
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    specs_dir = repo_root / "specs"
    specs_dir.mkdir()

    # Create a task file
    feature_dir = specs_dir / "001-test"
    feature_dir.mkdir()
    (feature_dir / "tasks.md").write_text("# Test Tasks\n")

    # Patch subprocess to track git commands
    with patch("subprocess.run") as mock_run:
        # Allow read operations but fail on write operations
        def side_effect(cmd, *args, **kwargs):
            # Parse command
            if isinstance(cmd, list):
                git_cmd = cmd
            else:
                git_cmd = cmd.split()

            # Check for git write commands
            write_commands = [
                "checkout", "commit", "merge", "rebase", "push",
                "branch", "tag", "reset", "revert", "cherry-pick",
                "stash", "add", "rm", "mv"
            ]

            if len(git_cmd) > 1 and git_cmd[0] == "git":
                if git_cmd[1] in write_commands:
                    raise AssertionError(
                        f"CLI attempted git write operation: {' '.join(git_cmd)}"
                    )

            # Return mock result for allowed operations
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        mock_run.side_effect = side_effect

        # Execute discovery
        discovered = discover_tasks(repo_root, target_task_file=None)

        # Verify discovery worked
        assert len(discovered) == 1


def test_cli_git_helpers_no_writes(tmp_path: Path):
    """Test that git helper functions only perform read operations."""
    from src.cli._git import get_current_branch, is_working_tree_dirty

    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    # Track git commands
    git_commands_called = []

    def track_git_command(cmd, *args, **kwargs):
        git_commands_called.append(cmd)

        # Check for write commands
        write_commands = [
            "checkout", "commit", "merge", "rebase", "push",
            "branch", "tag", "reset", "revert", "cherry-pick",
            "stash", "add", "rm", "mv"
        ]

        if isinstance(cmd, list) and len(cmd) > 1:
            if cmd[0] == "git" and cmd[1] in write_commands:
                raise AssertionError(
                    f"Git helper attempted write operation: {' '.join(cmd)}"
                )

        # Mock successful read operations
        result = MagicMock()
        result.returncode = 0

        if "branch" in cmd or "symbolic-ref" in cmd:
            result.stdout = b"main\n"
        elif "status" in cmd:
            result.stdout = b""

        result.stderr = b""
        return result

    with patch("src.utils.git_cli.subprocess.run", side_effect=track_git_command):
        # Call git helper functions
        try:
            get_current_branch(repo_root)
        except Exception:
            pass  # May fail due to mock, but we're checking commands

        try:
            is_working_tree_dirty(repo_root)
        except Exception:
            pass  # May fail due to mock, but we're checking commands

    # Verify only read commands were called
    for cmd in git_commands_called:
        if isinstance(cmd, list) and "git" in cmd:
            # Should only see status, branch, or other read commands
            assert not any(
                write_cmd in cmd
                for write_cmd in ["checkout", "commit", "merge", "rebase"]
            ), f"Write command detected: {cmd}"


def test_cli_adapter_no_git_operations(tmp_path: Path):
    """Test that adapter does not invoke git commands at all."""
    from src.cli._adapter import adapt_to_orchestration_input, build_cli_descriptor

    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()

    spec_root = repo_root / "specs" / "001-test"
    spec_root.mkdir(parents=True)

    tasks_file = spec_root / "tasks.md"
    tasks_file.write_text("# Test Tasks\n")

    # Track subprocess calls
    subprocess_called = []

    def track_subprocess(cmd, *args, **kwargs):
        subprocess_called.append(cmd)
        raise AssertionError(f"Adapter should not call subprocess: {cmd}")

    with patch("subprocess.run", side_effect=track_subprocess):
        # Build descriptor
        descriptor = build_cli_descriptor(
            task_file=tasks_file,
            spec_root=spec_root,
            repo_root=repo_root,
            return_to_branch="main",
            interactive=False,
        )

        # Verify descriptor created without subprocess calls
        assert descriptor.task_id == "001-test-tasks"
        assert not subprocess_called, "Adapter should not call subprocess"

        # Adapt to orchestration input
        cli_descriptors = [descriptor]
        orchestration_input = adapt_to_orchestration_input(
            cli_descriptors=cli_descriptors,
            repo_root=str(repo_root),
            return_to_branch="main",
            interactive_mode=False,
        )

        # Verify adaptation worked without subprocess
        assert orchestration_input is not None
        assert not subprocess_called, "Adapter should not call subprocess"


@pytest.mark.asyncio
async def test_cli_run_command_no_git_writes(tmp_path: Path):
    """Test that CLI run command does not perform git write operations."""
    from unittest.mock import AsyncMock

    from src.cli.maverick import _run_workflow

    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    specs_dir = repo_root / "specs" / "001-test"
    specs_dir.mkdir(parents=True)
    (specs_dir / "tasks.md").write_text("# Test\n")

    # Track git commands
    git_write_commands = []

    def track_git_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and len(cmd) > 1:
            if cmd[0] == "git":
                write_ops = ["checkout", "commit", "merge", "rebase", "push"]
                if cmd[1] in write_ops:
                    git_write_commands.append(cmd)

        # Return mock for allowed operations
        result = MagicMock()
        result.returncode = 0
        result.stdout = b"main\n"
        result.stderr = b""
        return result

    with patch("subprocess.run", side_effect=track_git_run), \
         patch("src.utils.git_cli.subprocess.run", side_effect=track_git_run), \
         patch("src.cli.maverick.Client") as mock_client_class:

        # Mock Temporal client
        mock_client = AsyncMock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        mock_handle = AsyncMock()
        mock_handle.id = "test-wf"
        mock_handle.result_run_id = "test-run"
        mock_handle.describe = AsyncMock(return_value=MagicMock(
            status=MagicMock(name="COMPLETED")
        ))
        mock_handle.query = AsyncMock(return_value={})
        mock_client.start_workflow = AsyncMock(return_value=mock_handle)

        # Run CLI workflow
        try:
            await _run_workflow(
                task=None,
                interactive=False,
                dry_run=True,  # Dry run to avoid Temporal calls
                json_output=True,
                allow_dirty=True,
                compact=False,
                use_rich=False,
            )
        except Exception:
            pass  # Ignore errors, we're checking git commands

        # Verify no git write commands were called
        assert not git_write_commands, (
            f"CLI attempted git write operations: {git_write_commands}"
        )


def test_cli_models_no_side_effects():
    """Test that CLI models do not have side effects."""
    from src.cli._models import CLITaskDescriptor, DryRunResult

    # Creating models should not trigger any I/O or subprocess calls
    with patch("subprocess.run") as mock_run:
        # Create descriptor
        descriptor = CLITaskDescriptor(
            task_id="test-id",
            task_file="/path/to/tasks.md",
            spec_root="/path/to/spec",
            branch_name="test-branch",
            return_to_branch="main",
            repo_root="/path/to/repo",
            interactive=False,
        )

        # Create dry run result
        dry_run = DryRunResult(
            task_count=1,
            discovery_ms=42,
            descriptors=[descriptor],
        )

        # Verify no subprocess calls
        assert not mock_run.called, "Models should not trigger subprocess calls"

        # Verify models are valid
        assert descriptor.task_id == "test-id"
        assert dry_run.task_count == 1
