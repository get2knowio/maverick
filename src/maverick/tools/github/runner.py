from __future__ import annotations

from pathlib import Path

from maverick.runners.command import CommandRunner

# =============================================================================
# Constants
# =============================================================================

#: Default timeout for GitHub CLI operations in seconds
DEFAULT_TIMEOUT: float = 30.0

#: Maximum retries for transient failures
MAX_RETRIES: int = 3

#: Initial retry delay in seconds
RETRY_DELAY: float = 1.0


def get_runner(cwd: Path | None = None) -> CommandRunner:
    """Get a CommandRunner instance for gh commands.

    Args:
        cwd: Working directory for command execution.

    Returns:
        CommandRunner instance configured for GitHub operations.
    """
    return CommandRunner(cwd=cwd, timeout=DEFAULT_TIMEOUT)


async def run_gh_command(
    *args: str,
    cwd: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str, str, int]:
    """Run a gh CLI command asynchronously.

    Args:
        *args: gh command arguments (without 'gh' prefix).
        cwd: Working directory for the command.
        timeout: Timeout in seconds.

    Returns:
        Tuple of (stdout, stderr, return_code).
    """
    runner = get_runner(cwd)
    result = await runner.run(
        ["gh", *args],
        timeout=timeout,
        max_retries=MAX_RETRIES,
        retry_delay=RETRY_DELAY,
    )
    return result.stdout, result.stderr, result.returncode
