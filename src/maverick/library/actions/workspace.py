"""Workspace initialization actions."""

from __future__ import annotations

from pathlib import Path

from maverick.library.actions.types import WorkspaceState
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner

logger = get_logger(__name__)

# Shared runner instance for workspace actions
_runner = CommandRunner(timeout=30.0)


async def init_workspace(branch_name: str) -> WorkspaceState:
    """Initialize workspace for workflow execution.

    Args:
        branch_name: Feature branch name to create/checkout

    Returns:
        WorkspaceState with branch info and task file detection
    """
    base_branch = "main"

    try:
        # Check if branch exists
        result = await _runner.run(
            ["git", "rev-parse", "--verify", branch_name],
        )
        branch_exists = result.returncode == 0

        if branch_exists:
            # Checkout existing branch
            checkout_result = await _runner.run(["git", "checkout", branch_name])
            if not checkout_result.success:
                raise RuntimeError(
                    f"Failed to checkout branch: {checkout_result.stderr}"
                )
        else:
            # Create new branch from base
            checkout_result = await _runner.run(["git", "checkout", "-b", branch_name])
            if not checkout_result.success:
                raise RuntimeError(f"Failed to create branch: {checkout_result.stderr}")

        # Check if workspace is clean
        status_result = await _runner.run(
            ["git", "status", "--porcelain"],
        )
        is_clean = len(status_result.stdout.strip()) == 0

        # Try to detect task file
        task_file_path = None
        for candidate in [
            f"specs/{branch_name}/tasks.md",
            "tasks.md",
        ]:
            if Path(candidate).exists():
                task_file_path = Path(candidate)
                break

        state = WorkspaceState(
            branch_name=branch_name,
            base_branch=base_branch,
            is_clean=is_clean,
            synced_with_base=True,  # Simplified for initial implementation
            task_file_path=task_file_path,
            error=None,
        )

        return state

    except Exception as e:
        logger.error(f"Git command failed: {e}")
        return WorkspaceState(
            branch_name=branch_name,
            base_branch=base_branch,
            is_clean=False,
            synced_with_base=False,
            task_file_path=None,
            error=str(e),
        )
