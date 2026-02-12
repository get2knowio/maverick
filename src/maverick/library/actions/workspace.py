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
        # Check if bookmark exists via jj
        result = await _runner.run(
            ["jj", "bookmark", "list", "--all-remotes"],
        )
        bookmark_output = result.stdout if result.success else ""
        branch_exists = False
        for line in bookmark_output.splitlines():
            if line.startswith(f"{branch_name}:") or line.startswith(f"{branch_name} "):
                branch_exists = True
                break

        if branch_exists:
            # Switch to existing bookmark
            edit_result = await _runner.run(["jj", "edit", branch_name])
            if not edit_result.success:
                raise RuntimeError(f"Failed to edit bookmark: {edit_result.stderr}")
        else:
            # Create new change from base, then create bookmark
            new_result = await _runner.run(["jj", "new", base_branch])
            if not new_result.success:
                raise RuntimeError(f"Failed to create change: {new_result.stderr}")
            bm_result = await _runner.run(
                ["jj", "bookmark", "create", branch_name, "-r", "@"]
            )
            if not bm_result.success:
                raise RuntimeError(f"Failed to create bookmark: {bm_result.stderr}")

        # Check if workspace is clean via jj
        status_result = await _runner.run(
            ["jj", "diff", "--stat"],
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
