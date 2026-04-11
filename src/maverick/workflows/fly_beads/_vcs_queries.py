"""Git/jj read-only queries used by multiple fly-beads step modules."""

from __future__ import annotations

from pathlib import Path

from maverick.logging import get_logger

logger = get_logger(__name__)


async def _get_uncommitted_files(cwd: Path | None) -> list[str]:
    """Get files changed in the working copy (uncommitted changes).

    In jj colocated mode, ``git diff --name-only HEAD`` shows the
    working copy changes that haven't been committed yet — i.e., what
    the current bead's agent wrote.
    """
    from maverick.runners.command import CommandRunner

    try:
        runner = CommandRunner(cwd=cwd or Path.cwd())
        result = await runner.run(
            ["git", "diff", "--name-only", "HEAD"],
        )
        if result.stdout:
            return [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
    except Exception as exc:
        logger.debug("uncommitted_files_capture_failed", error=str(exc))
    return []


async def _get_files_changed(cwd: Path | None) -> list[str]:
    """Get the list of files changed by the most recent commit.

    Uses ``git diff --name-only HEAD~1`` which works in jj colocated
    mode (shared ``.git`` directory).
    """
    from maverick.runners.command import CommandRunner

    try:
        runner = CommandRunner(cwd=cwd or Path.cwd())
        result = await runner.run(
            ["git", "diff", "--name-only", "HEAD~1"],
        )
        if result.stdout:
            return [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
    except Exception as exc:
        logger.debug("files_changed_capture_failed", error=str(exc))
    return []
