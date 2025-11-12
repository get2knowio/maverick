"""Git helpers for CLI operations.

Provides functions to check git repository status including
current branch detection and dirty working tree checks.
"""

from pathlib import Path

from src.common.logging import get_logger
from src.utils.git_cli import GitCommandError, run_git_command


logger = get_logger(__name__)


def get_current_branch(repo_root: Path) -> str:
    """Get the current git branch name.

    Args:
        repo_root: Absolute path to repository root

    Returns:
        Current branch name

    Raises:
        GitCommandError: If unable to determine current branch
        ValueError: If repo_root is invalid
    """
    if not repo_root.exists():
        raise ValueError(f"Repository root does not exist: {repo_root}")

    if not repo_root.is_dir():
        raise ValueError(f"Repository root is not a directory: {repo_root}")

    logger.debug(f"Getting current branch for repo: {repo_root}")

    try:
        result = run_git_command(
            ["rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_root),
            timeout=5,
        )

        if not result.success:
            raise GitCommandError(
                f"Failed to get current branch: {result.stderr.strip()}"
            )

        branch_name = result.stdout.strip()

        if not branch_name:
            raise GitCommandError("Current branch name is empty")

        logger.info(f"Current branch: {branch_name}")
        return branch_name

    except GitCommandError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting current branch: {e}")
        raise GitCommandError(f"Failed to get current branch: {e}") from e


def is_working_tree_dirty(repo_root: Path) -> bool:
    """Check if working tree has uncommitted changes.

    Uses `git status --porcelain` to detect any changes in the working tree,
    including untracked files.

    Args:
        repo_root: Absolute path to repository root

    Returns:
        True if working tree has changes, False if clean

    Raises:
        GitCommandError: If unable to check git status
        ValueError: If repo_root is invalid
    """
    if not repo_root.exists():
        raise ValueError(f"Repository root does not exist: {repo_root}")

    if not repo_root.is_dir():
        raise ValueError(f"Repository root is not a directory: {repo_root}")

    logger.debug(f"Checking working tree status for repo: {repo_root}")

    try:
        result = run_git_command(
            ["status", "--porcelain"],
            cwd=str(repo_root),
            timeout=10,
        )

        if not result.success:
            raise GitCommandError(
                f"Failed to check working tree status: {result.stderr.strip()}"
            )

        # If output is non-empty, working tree is dirty
        is_dirty = bool(result.stdout.strip())

        if is_dirty:
            logger.warning("Working tree is dirty")
            # Log first few lines of status for context
            status_lines = result.stdout.strip().split("\n")[:5]
            for line in status_lines:
                logger.debug(f"  {line}")
        else:
            logger.info("Working tree is clean")

        return is_dirty

    except GitCommandError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error checking working tree status: {e}")
        raise GitCommandError(f"Failed to check working tree status: {e}") from e


def validate_repo_root(repo_root: Path) -> None:
    """Validate that a path is a git repository root.

    Args:
        repo_root: Path to validate

    Raises:
        ValueError: If path is not a valid git repository root
        GitCommandError: If unable to verify git repository
    """
    if not repo_root.exists():
        raise ValueError(f"Path does not exist: {repo_root}")

    if not repo_root.is_dir():
        raise ValueError(f"Path is not a directory: {repo_root}")

    # Check if .git directory exists
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        raise ValueError(f"Not a git repository (no .git directory): {repo_root}")

    # Verify with git command
    try:
        result = run_git_command(
            ["rev-parse", "--git-dir"],
            cwd=str(repo_root),
            timeout=5,
        )

        if not result.success:
            raise ValueError(
                f"Not a valid git repository: {result.stderr.strip()}"
            )

        logger.debug(f"Validated git repository: {repo_root}")

    except GitCommandError as e:
        raise ValueError(f"Failed to validate git repository: {e}") from e


def derive_branch_name_hint(task_id: str) -> str:
    """Derive a git-safe branch name hint from task ID.

    Replaces non-alphanumeric characters with dashes, converts to lowercase,
    and truncates to 50 characters.

    Args:
        task_id: Task identifier to derive branch name from

    Returns:
        Git-safe branch name hint

    Raises:
        ValueError: If task_id is empty
    """
    if not task_id or not task_id.strip():
        raise ValueError("task_id must be non-empty")

    # Replace non-alphanumeric with dashes
    import re

    safe_name = re.sub(r"[^a-zA-Z0-9._/-]", "-", task_id)

    # Convert to lowercase
    safe_name = safe_name.lower()

    # Truncate to 50 chars
    safe_name = safe_name[:50]

    # Remove trailing dashes
    safe_name = safe_name.rstrip("-")

    if not safe_name:
        raise ValueError(f"Derived branch name is empty from task_id: {task_id}")

    logger.debug(f"Derived branch name hint: {safe_name} from task_id: {task_id}")

    return safe_name
