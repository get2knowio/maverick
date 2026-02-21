"""Async client for the Jujutsu (``jj``) VCS.

Wraps ``jj`` commands using :class:`~maverick.runners.command.CommandRunner`
for async-safe subprocess execution with timeouts and retries.

Follows the same pattern as :class:`~maverick.beads.client.BeadClient`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.jj.errors import (
    JjCloneError,
    JjConflictError,
    JjError,
    JjOperationError,
    JjPushError,
)
from maverick.jj.models import (
    JjAbsorbResult,
    JjBookmark,
    JjBookmarkResult,
    JjChangeInfo,
    JjCloneResult,
    JjCommitResult,
    JjDescribeResult,
    JjDiffResult,
    JjDiffStatResult,
    JjFetchResult,
    JjLogResult,
    JjNewResult,
    JjPushResult,
    JjRebaseResult,
    JjRestoreResult,
    JjShowResult,
    JjSnapshotResult,
    JjSquashResult,
    JjStatusResult,
)
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner

if TYPE_CHECKING:
    from collections.abc import Sequence

    from maverick.runners.models import CommandResult

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default timeout for normal jj operations (seconds).
JJ_TIMEOUT: float = 120.0

#: Extended timeout for network / clone operations (seconds).
JJ_CLONE_TIMEOUT: float = 600.0

#: Max retries for network operations.
JJ_NETWORK_RETRIES: int = 3

#: ASCII unit separator for parsing ``jj log`` structured output lines.
_LOG_SEPARATOR = "\x1f"
#: jj template expression that emits the separator between fields.
_TMPL_SEP = ' ++ "\\x1f" ++ '


class JjClient:
    """Async wrapper around the ``jj`` CLI for VCS operations.

    Uses :class:`CommandRunner` for subprocess execution. Supports
    dependency injection of the runner for testing.

    Args:
        cwd: Working directory for ``jj`` commands.
        runner: Optional pre-configured CommandRunner. Created if not provided.

    Example:
        ```python
        client = JjClient(cwd=Path("/project"))
        if await client.verify_available():
            result = await client.describe("wip: working on feature")
        ```
    """

    def __init__(
        self,
        cwd: Path,
        runner: CommandRunner | None = None,
    ) -> None:
        self._cwd = cwd
        self._runner = runner or CommandRunner(cwd=cwd, timeout=JJ_TIMEOUT)

    @property
    def cwd(self) -> Path:
        """Working directory for jj commands."""
        return self._cwd

    # =====================================================================
    # Internal helpers
    # =====================================================================

    async def _run_jj(
        self,
        cmd: Sequence[str],
        *,
        error_cls: type[JjError] = JjError,
        error_msg: str = "jj command failed",
        timeout: float | None = None,
        max_retries: int = 0,
        **error_kwargs: str | None,
    ) -> CommandResult:
        """Run a jj command and return the raw :class:`CommandResult`.

        Args:
            cmd: Full command list (e.g. ``["jj", "log", "-r", "@"]``).
            error_cls: Exception class to raise on failure.
            error_msg: Error message prefix.
            timeout: Override timeout for this invocation.
            max_retries: Retry count for transient failures.
            **error_kwargs: Extra keyword arguments forwarded to *error_cls*.

        Returns:
            :class:`CommandResult` on success.

        Raises:
            JjError (or subclass): If the command fails.
        """
        result = await self._runner.run(
            cmd,
            cwd=self._cwd,
            timeout=timeout,
            max_retries=max_retries,
        )
        if not result.success:
            stderr_text = result.stderr.strip()
            # Detect conflict errors from any jj command
            if "conflict" in stderr_text.lower():
                raise JjConflictError(
                    f"{error_msg}: {stderr_text}",
                    command=cmd[1] if len(cmd) > 1 else None,
                    stderr=stderr_text,
                )
            raise error_cls(
                f"{error_msg}: {stderr_text}",
                **error_kwargs,
            )
        return result

    async def _run_jj_stdout(
        self,
        cmd: Sequence[str],
        *,
        error_cls: type[JjError] = JjError,
        error_msg: str = "jj command failed",
        timeout: float | None = None,
        max_retries: int = 0,
        **error_kwargs: str | None,
    ) -> str:
        """Run a jj command and return stdout as a string."""
        result = await self._run_jj(
            cmd,
            error_cls=error_cls,
            error_msg=error_msg,
            timeout=timeout,
            max_retries=max_retries,
            **error_kwargs,
        )
        return result.stdout

    # =====================================================================
    # Lifecycle
    # =====================================================================

    async def verify_available(self) -> bool:
        """Check if ``jj`` is available in PATH.

        Returns:
            True if ``jj --version`` succeeds.
        """
        result = await self._runner.run(["jj", "--version"], cwd=self._cwd)
        if result.success:
            logger.debug("jj_available", version=result.stdout.strip())
            return True
        logger.warning("jj_not_available", stderr=result.stderr.strip())
        return False

    async def git_clone(
        self,
        source: str | Path,
        target: Path,
        *,
        colocate: bool = False,
    ) -> JjCloneResult:
        """Clone a git repository via ``jj git clone``.

        Args:
            source: Repository URL or local path to clone from.
            target: Destination directory.
            colocate: If True, create a colocated jj+git repo.

        Returns:
            :class:`JjCloneResult` with workspace path.

        Raises:
            JjCloneError: If the clone fails.
        """
        cmd: list[str] = ["jj", "git", "clone"]
        if colocate:
            cmd.append("--colocate")
        cmd.extend([str(source), str(target)])

        await self._run_jj(
            cmd,
            error_cls=JjCloneError,
            error_msg=f"jj git clone failed for {source}",
            timeout=JJ_CLONE_TIMEOUT,
            max_retries=JJ_NETWORK_RETRIES,
            source=str(source),
        )

        logger.info("jj_git_clone_completed", source=str(source), target=str(target))
        return JjCloneResult(success=True, workspace_path=str(target))

    async def git_fetch(self, remote: str = "origin") -> JjFetchResult:
        """Fetch from a git remote via ``jj git fetch``.

        Args:
            remote: Remote name (default: ``"origin"``).

        Returns:
            :class:`JjFetchResult`.

        Raises:
            JjError: If the fetch fails.
        """
        await self._run_jj(
            ["jj", "git", "fetch", "--remote", remote],
            error_msg=f"jj git fetch failed for remote {remote}",
            max_retries=JJ_NETWORK_RETRIES,
        )
        logger.info("jj_git_fetch_completed", remote=remote)
        return JjFetchResult(success=True)

    async def git_push(
        self,
        remote: str = "origin",
        bookmark: str | None = None,
    ) -> JjPushResult:
        """Push to a git remote via ``jj git push``.

        Args:
            remote: Remote name (default: ``"origin"``).
            bookmark: Specific bookmark to push. If None, pushes all
                tracked bookmarks.

        Returns:
            :class:`JjPushResult`.

        Raises:
            JjPushError: If the push fails.
        """
        cmd: list[str] = ["jj", "git", "push", "--remote", remote]
        if bookmark:
            cmd.extend(["--bookmark", bookmark])

        await self._run_jj(
            cmd,
            error_cls=JjPushError,
            error_msg=f"jj git push failed to {remote}",
            max_retries=JJ_NETWORK_RETRIES,
            remote=remote,
            bookmark=bookmark,
        )
        logger.info("jj_git_push_completed", remote=remote, bookmark=bookmark)
        return JjPushResult(success=True)

    # =====================================================================
    # Change management
    # =====================================================================

    async def describe(
        self,
        message: str,
        revision: str = "@",
    ) -> JjDescribeResult:
        """Set the description of a change.

        Args:
            message: Description to set.
            revision: Revision to describe (default: working copy ``@``).

        Returns:
            :class:`JjDescribeResult`.
        """
        await self._run_jj(
            ["jj", "describe", "-r", revision, "-m", message],
            error_msg="jj describe failed",
            command="describe",
        )
        logger.debug("jj_described", revision=revision, message=message[:80])
        return JjDescribeResult(success=True, message=message)

    async def new(
        self,
        parents: list[str] | None = None,
        message: str = "",
    ) -> JjNewResult:
        """Create a new empty change.

        Args:
            parents: Parent revisions. Defaults to ``["@"]``.
            message: Optional description for the new change.

        Returns:
            :class:`JjNewResult`.
        """
        cmd: list[str] = ["jj", "new"]
        if parents:
            for parent in parents:
                cmd.extend(["-r", parent])
        if message:
            cmd.extend(["-m", message])

        stdout = await self._run_jj_stdout(
            cmd,
            error_msg="jj new failed",
            command="new",
        )
        # jj new prints the new change ID in some configurations
        change_id = stdout.strip().split()[-1] if stdout.strip() else ""
        logger.debug("jj_new_created", parents=parents, change_id=change_id)
        return JjNewResult(success=True, change_id=change_id)

    async def commit(self, message: str) -> JjCommitResult:
        """Commit the current working-copy change (``jj commit``).

        This finalizes the current change and creates a new empty working
        copy on top.

        Args:
            message: Commit message.

        Returns:
            :class:`JjCommitResult`.
        """
        stdout = await self._run_jj_stdout(
            ["jj", "commit", "-m", message],
            error_msg="jj commit failed",
            command="commit",
        )
        change_id = stdout.strip().split()[-1] if stdout.strip() else ""
        logger.info("jj_committed", message=message[:80], change_id=change_id)
        return JjCommitResult(success=True, change_id=change_id)

    # =====================================================================
    # Read operations
    # =====================================================================

    async def diff(
        self,
        revision: str = "@",
        from_rev: str | None = None,
    ) -> JjDiffResult:
        """Show diff for a revision in git format.

        Args:
            revision: Revision to diff (default: working copy ``@``).
            from_rev: If provided, diff from this revision to *revision*.

        Returns:
            :class:`JjDiffResult`.
        """
        cmd: list[str] = ["jj", "diff", "--git"]
        if from_rev:
            cmd.extend(["--from", from_rev, "--to", revision])
        else:
            cmd.extend(["-r", revision])

        stdout = await self._run_jj_stdout(
            cmd,
            error_msg="jj diff failed",
            command="diff",
        )
        return JjDiffResult(success=True, output=stdout)

    async def diff_stat(
        self,
        revision: str = "@",
        from_rev: str | None = None,
    ) -> JjDiffStatResult:
        """Show diff statistics for a revision.

        Args:
            revision: Revision to diff (default: working copy ``@``).
            from_rev: If provided, stat from this revision to *revision*.

        Returns:
            :class:`JjDiffStatResult` with parsed statistics.
        """
        cmd: list[str] = ["jj", "diff", "--stat"]
        if from_rev:
            cmd.extend(["--from", from_rev, "--to", revision])
        else:
            cmd.extend(["-r", revision])

        stdout = await self._run_jj_stdout(
            cmd,
            error_msg="jj diff --stat failed",
            command="diff",
        )

        files_changed, insertions, deletions = _parse_diff_stat_summary(stdout)
        return JjDiffStatResult(
            success=True,
            output=stdout,
            files_changed=files_changed,
            insertions=insertions,
            deletions=deletions,
        )

    async def log(
        self,
        revset: str = "@",
        limit: int = 10,
    ) -> JjLogResult:
        """Show commit log for a revset.

        Args:
            revset: Revset expression (default: ``"@"``).
            limit: Maximum number of entries (default: 10).

        Returns:
            :class:`JjLogResult` with raw output and parsed changes.
        """
        # Use structured template for machine-readable parsing.
        # Fields are concatenated with ++ "\x1f" ++ so jj emits them
        # separated by the ASCII unit separator character.
        template = (
            _TMPL_SEP.join(
                [
                    "change_id.short()",
                    "commit_id.short()",
                    "description.first_line()",
                    "author.name()",
                    "author.email()",
                    "author.timestamp()",
                    "bookmarks",
                    "empty",
                ]
            )
            + ' ++ "\\n"'
        )

        stdout = await self._run_jj_stdout(
            [
                "jj",
                "log",
                "-r",
                revset,
                "--no-graph",
                "-T",
                template,
                "--limit",
                str(limit),
            ],
            error_msg="jj log failed",
            command="log",
        )

        changes = _parse_log_output(stdout)

        # Also get human-readable output for display
        display_result = await self._runner.run(
            ["jj", "log", "-r", revset, "--limit", str(limit)],
            cwd=self._cwd,
        )
        display_output = display_result.stdout if display_result.success else stdout

        return JjLogResult(
            success=True,
            output=display_output,
            changes=tuple(changes),
        )

    async def status(self) -> JjStatusResult:
        """Show working copy status.

        Returns:
            :class:`JjStatusResult`.
        """
        stdout = await self._run_jj_stdout(
            ["jj", "status"],
            error_msg="jj status failed",
            command="status",
        )

        # Try to parse the working copy change ID
        wc_change_id = ""
        conflict = False
        for line in stdout.splitlines():
            if "Working copy " in line:
                # e.g. "Working copy : kxyzabcd description"
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == ":":
                        if i + 1 < len(parts):
                            wc_change_id = parts[i + 1]
                        break
            if "conflict" in line.lower():
                conflict = True

        return JjStatusResult(
            success=True,
            output=stdout,
            working_copy_change_id=wc_change_id,
            conflict=conflict,
        )

    async def show(self, revision: str = "@") -> JjShowResult:
        """Show full details of a revision.

        Args:
            revision: Revision to show (default: working copy ``@``).

        Returns:
            :class:`JjShowResult`.
        """
        stdout = await self._run_jj_stdout(
            ["jj", "show", "-r", revision],
            error_msg="jj show failed",
            command="show",
        )
        return JjShowResult(success=True, output=stdout)

    # =====================================================================
    # Operation log safety
    # =====================================================================

    async def snapshot_operation(self) -> JjSnapshotResult:
        """Capture the current jj operation ID for potential rollback.

        Returns:
            :class:`JjSnapshotResult` with the current operation ID.

        Raises:
            JjOperationError: If the operation log cannot be read.
        """
        stdout = await self._run_jj_stdout(
            [
                "jj",
                "op",
                "log",
                "--no-graph",
                "-T",
                'self.id() ++ "\\n"',
                "--limit",
                "1",
            ],
            error_cls=JjOperationError,
            error_msg="jj op log failed",
            command="op log",
        )
        operation_id = stdout.strip().split("\n")[0]
        logger.debug("jj_operation_snapshot", operation_id=operation_id)
        return JjSnapshotResult(success=True, operation_id=operation_id)

    async def restore_operation(self, operation_id: str) -> JjRestoreResult:
        """Restore the repository to a previous operation state.

        Args:
            operation_id: Operation ID from :meth:`snapshot_operation`.

        Returns:
            :class:`JjRestoreResult`.

        Raises:
            JjOperationError: If the restore fails.
        """
        await self._run_jj(
            ["jj", "op", "restore", operation_id],
            error_cls=JjOperationError,
            error_msg=f"jj op restore failed for {operation_id}",
            command="op restore",
            operation_id=operation_id,
        )
        logger.info("jj_operation_restored", operation_id=operation_id)
        return JjRestoreResult(success=True)

    # =====================================================================
    # History curation
    # =====================================================================

    async def squash(
        self,
        revision: str = "@",
        into: str | None = None,
    ) -> JjSquashResult:
        """Squash a change into its parent or a specified target.

        Args:
            revision: Revision to squash (default: working copy ``@``).
            into: Target revision to squash into. If None, squashes into parent.

        Returns:
            :class:`JjSquashResult`.
        """
        cmd: list[str] = ["jj", "squash"]
        if revision != "@":
            cmd.extend(["-r", revision])
        if into:
            cmd.extend(["--into", into])

        await self._run_jj(
            cmd,
            error_msg="jj squash failed",
            command="squash",
        )
        logger.debug("jj_squashed", revision=revision, into=into)
        return JjSquashResult(success=True)

    async def absorb(self) -> JjAbsorbResult:
        """Absorb working-copy changes into relevant ancestor commits.

        Returns:
            :class:`JjAbsorbResult`.
        """
        stdout = await self._run_jj_stdout(
            ["jj", "absorb"],
            error_msg="jj absorb failed",
            command="absorb",
        )
        logger.debug("jj_absorbed")
        return JjAbsorbResult(success=True, output=stdout)

    async def rebase(
        self,
        revision: str,
        destination: str,
    ) -> JjRebaseResult:
        """Rebase a revision onto a new destination.

        Args:
            revision: Revision (or revset) to rebase.
            destination: Destination revision.

        Returns:
            :class:`JjRebaseResult`.
        """
        await self._run_jj(
            ["jj", "rebase", "-r", revision, "-d", destination],
            error_msg="jj rebase failed",
            command="rebase",
        )
        logger.debug("jj_rebased", revision=revision, destination=destination)
        return JjRebaseResult(success=True)

    # =====================================================================
    # Bookmarks
    # =====================================================================

    async def bookmark_set(
        self,
        name: str,
        revision: str = "@",
    ) -> JjBookmarkResult:
        """Create or move a bookmark to a revision.

        Args:
            name: Bookmark name.
            revision: Revision to point the bookmark at (default: ``@``).

        Returns:
            :class:`JjBookmarkResult`.
        """
        await self._run_jj(
            ["jj", "bookmark", "set", name, "-r", revision],
            error_msg=f"jj bookmark set failed for {name}",
            command="bookmark set",
        )
        logger.debug("jj_bookmark_set", name=name, revision=revision)
        return JjBookmarkResult(success=True, name=name)

    async def bookmark_list(self) -> list[JjBookmark]:
        """List all bookmarks.

        Returns:
            List of :class:`JjBookmark`.
        """
        template = (
            _TMPL_SEP.join(
                [
                    "name",
                    "present",
                ]
            )
            + ' ++ "\\n"'
        )

        stdout = await self._run_jj_stdout(
            [
                "jj",
                "bookmark",
                "list",
                "--no-graph" if False else "--all-remotes",
                "-T",
                template,
            ],
            error_msg="jj bookmark list failed",
            command="bookmark list",
        )

        bookmarks: list[JjBookmark] = []
        for line in stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(_LOG_SEPARATOR)
            name = parts[0].strip() if parts else ""
            if name:
                bookmarks.append(JjBookmark(name=name))

        return bookmarks


# ==========================================================================
# Parsing helpers (module-level)
# ==========================================================================


def _parse_log_output(raw: str) -> list[JjChangeInfo]:
    """Parse structured ``jj log`` output into :class:`JjChangeInfo` items."""
    changes: list[JjChangeInfo] = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(_LOG_SEPARATOR)
        if len(parts) < 3:
            continue

        change_id = parts[0].strip()
        commit_id = parts[1].strip()
        description = parts[2].strip()
        author = parts[3].strip() if len(parts) > 3 else ""
        email = parts[4].strip() if len(parts) > 4 else ""
        timestamp = parts[5].strip() if len(parts) > 5 else ""
        bookmarks_raw = parts[6].strip() if len(parts) > 6 else ""
        empty_raw = parts[7].strip().lower() if len(parts) > 7 else ""

        bookmark_list = tuple(b.strip() for b in bookmarks_raw.split() if b.strip())
        empty = empty_raw in ("true", "1")

        changes.append(
            JjChangeInfo(
                change_id=change_id,
                commit_id=commit_id,
                description=description,
                author=author,
                email=email,
                timestamp=timestamp,
                bookmarks=bookmark_list,
                empty=empty,
            )
        )

    return changes


_DIFF_STAT_SUMMARY_RE = re.compile(
    r"(\d+)\s+files?\s+changed"
    r"(?:,\s+(\d+)\s+insertions?\(\+\))?"
    r"(?:,\s+(\d+)\s+deletions?\(-\))?",
)


def _parse_diff_stat_summary(raw: str) -> tuple[int, int, int]:
    """Parse the summary line from ``--stat`` output.

    Returns:
        ``(files_changed, insertions, deletions)``.
    """
    match = _DIFF_STAT_SUMMARY_RE.search(raw)
    if not match:
        return (0, 0, 0)
    files = int(match.group(1))
    ins = int(match.group(2)) if match.group(2) else 0
    dels = int(match.group(3)) if match.group(3) else 0
    return (files, ins, dels)
