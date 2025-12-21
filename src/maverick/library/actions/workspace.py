"""Workspace initialization actions."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from maverick.library.actions.types import WorkspaceState

logger = logging.getLogger(__name__)


async def init_workspace(branch_name: str) -> dict[str, Any]:
    """Initialize workspace for workflow execution.

    Args:
        branch_name: Feature branch name to create/checkout

    Returns:
        WorkspaceState as dict with branch info and task file detection
    """
    base_branch = "main"

    try:
        # Check if branch exists
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            capture_output=True,
            text=True,
        )
        branch_exists = result.returncode == 0

        if branch_exists:
            # Checkout existing branch
            subprocess.run(["git", "checkout", branch_name], check=True)
        else:
            # Create new branch from base
            subprocess.run(["git", "checkout", "-b", branch_name], check=True)

        # Check if workspace is clean
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
        )
        is_clean = len(status_result.stdout.strip()) == 0

        # Try to detect task file
        task_file_path = None
        for candidate in [
            f"specs/{branch_name}/tasks.md",
            f".specify/{branch_name}/tasks.md",
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
        )

        return {
            "branch_name": state.branch_name,
            "base_branch": state.base_branch,
            "is_clean": state.is_clean,
            "synced_with_base": state.synced_with_base,
            "task_file_path": (
                str(state.task_file_path) if state.task_file_path else None
            ),
        }

    except subprocess.CalledProcessError as e:
        logger.error(f"Git command failed: {e}")
        return {
            "branch_name": branch_name,
            "base_branch": base_branch,
            "is_clean": False,
            "synced_with_base": False,
            "task_file_path": None,
            "error": str(e),
        }
