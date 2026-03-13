"""Workspace initialization actions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.library.actions.types import WorkspaceState
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner
from maverick.workspace.manager import WorkspaceManager

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
        logger.debug(f"Git command failed: {e}")
        return WorkspaceState(
            branch_name=branch_name,
            base_branch=base_branch,
            is_clean=False,
            synced_with_base=False,
            task_file_path=None,
            error=str(e),
        )


async def _propagate_git_identity(user_repo: Path, workspace_path: Path) -> None:
    """Copy git user.name / user.email from the user repo into the workspace.

    jj reads author info from its own config, so we write the identity
    into the workspace's local jj config so that ``jj describe`` /
    ``jj new`` produce commits with the correct author.
    """
    runner = CommandRunner(timeout=10.0)

    for key in ("user.name", "user.email"):
        result = await runner.run(
            ["git", "config", key],
            cwd=user_repo,
        )
        value = result.stdout.strip()
        if not value:
            continue
        await runner.run(
            ["jj", "config", "set", "--repo", key, value],
            cwd=workspace_path,
        )
        logger.debug("propagated_git_identity", key=key, value=value)


async def create_fly_workspace(
    setup_command: str | None = None,
) -> dict[str, Any]:
    """Create an isolated jj workspace for a fly session.

    Clones the user's repo (cwd) into ``~/.maverick/workspaces/<project>/``
    via ``jj git clone``.  If the workspace already exists, the clone is
    skipped (idempotent).

    Args:
        setup_command: Optional command to run after cloning (e.g. ``"uv sync"``).

    Returns:
        Dict with:
        - success: True if workspace is ready
        - workspace_path: Absolute path to the workspace directory
        - user_repo_path: Absolute path to the original user repo
        - created: True if a fresh clone was made, False if reused
        - error: Error message if workspace creation failed
    """
    user_repo = Path.cwd().resolve()

    try:
        manager = WorkspaceManager(
            user_repo_path=user_repo,
            setup_command=setup_command,
        )

        already_exists = manager.exists
        info = await manager.create_and_bootstrap()

        # Propagate git identity so jj commits have author set
        ws_path = Path(info.workspace_path)
        await _propagate_git_identity(user_repo, ws_path)

        logger.info(
            "fly_workspace_ready",
            workspace_path=info.workspace_path,
            reused=already_exists,
        )

        return {
            "success": True,
            "workspace_path": info.workspace_path,
            "user_repo_path": info.user_repo_path,
            "created": not already_exists,
            "error": None,
        }

    except Exception as e:
        logger.debug("create_fly_workspace_failed", error=str(e))
        return {
            "success": False,
            "workspace_path": None,
            "user_repo_path": str(user_repo),
            "created": False,
            "error": str(e),
        }
