"""JjRepository — :class:`~maverick.vcs.protocol.VcsRepository` backed by jj.

Translates git-centric concepts to jj equivalents:
- ``HEAD`` → ``@-`` (parent of working copy)
- ``diff(base="main")`` → ``jj diff --from main --git``
- ``status()`` → ``jj status`` parsed into :class:`GitStatus`
- ``current_branch()`` → active bookmark name, or change-ID prefix
"""

from __future__ import annotations

import re
from pathlib import Path

from maverick.git.repository import CommitInfo, DiffStats, GitStatus
from maverick.jj.client import JjClient
from maverick.logging import get_logger

logger = get_logger(__name__)

# Map the git default "HEAD" to jj's working-copy parent.
_HEAD_ALIAS = "@-"


class JjRepository:
    """Read-only VCS repository backed by jj.

    Satisfies :class:`~maverick.vcs.protocol.VcsRepository` via structural
    typing — no explicit inheritance.

    Args:
        path: Root directory of the jj workspace.
        client: Optional pre-configured :class:`JjClient`.
    """

    def __init__(
        self,
        path: Path | str,
        client: JjClient | None = None,
    ) -> None:
        self._path = Path(path).resolve()
        self._client = client or JjClient(cwd=self._path)

    @property
    def path(self) -> Path:
        """Root path of the repository."""
        return self._path

    # -----------------------------------------------------------------
    # Branch / bookmark
    # -----------------------------------------------------------------

    async def current_branch(self) -> str:
        """Return the active bookmark name, or the working-copy change ID."""
        log_result = await self._client.log(revset="@", limit=1)
        if log_result.changes:
            change = log_result.changes[0]
            if change.bookmarks:
                return change.bookmarks[0]
            return change.change_id
        # Fallback: parse status
        status = await self._client.status()
        return status.working_copy_change_id or "unknown"

    # -----------------------------------------------------------------
    # Diff
    # -----------------------------------------------------------------

    async def diff(
        self,
        base: str = "HEAD",
        head: str | None = None,
    ) -> str:
        """Return diff text between *base* and *head*.

        Translates ``HEAD`` → ``@-`` for jj.
        """
        jj_base = _translate_ref(base)
        if head:
            result = await self._client.diff(
                revision=_translate_ref(head), from_rev=jj_base
            )
        else:
            result = await self._client.diff(revision="@", from_rev=jj_base)
        return result.output

    async def diff_stats(self, base: str = "HEAD") -> DiffStats:
        """Return diff statistics."""
        jj_base = _translate_ref(base)
        stat = await self._client.diff_stat(revision="@", from_rev=jj_base)

        # Parse per-file stats from the stat output
        files, per_file = _parse_stat_output(stat.output)

        return DiffStats(
            files_changed=stat.files_changed,
            insertions=stat.insertions,
            deletions=stat.deletions,
            file_list=tuple(files),
            per_file=per_file,
        )

    async def get_changed_files(self, ref: str = "HEAD") -> list[str]:
        """Return list of changed file paths relative to *ref*."""
        jj_ref = _translate_ref(ref)
        result = await self._client.diff(revision="@", from_rev=jj_ref)
        return _extract_changed_files(result.output)

    # -----------------------------------------------------------------
    # Log
    # -----------------------------------------------------------------

    async def log(self, n: int = 10) -> list[CommitInfo]:
        """Return the *n* most recent changes as :class:`CommitInfo`."""
        result = await self._client.log(revset="@-", limit=n)
        commits: list[CommitInfo] = []
        for change in result.changes:
            commits.append(
                CommitInfo(
                    sha=change.commit_id,
                    short_sha=change.commit_id[:7] if change.commit_id else "",
                    message=change.description,
                    author=change.author,
                    date=change.timestamp,
                )
            )
        return commits

    # -----------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------

    async def status(self) -> GitStatus:
        """Return repository status snapshot.

        jj has no staging area, so ``staged`` is always empty.
        """
        result = await self._client.status()

        # Parse modified and added files from jj status output
        modified: list[str] = []
        added: list[str] = []
        for line in result.output.splitlines():
            stripped = line.strip()
            if stripped.startswith("M "):
                modified.append(stripped[2:].strip())
            elif stripped.startswith("A "):
                added.append(stripped[2:].strip())

        branch = result.working_copy_change_id or "unknown"

        return GitStatus(
            staged=(),  # jj has no staging area
            unstaged=tuple(modified),
            untracked=tuple(added),
            branch=branch,
            ahead=0,
            behind=0,
        )

    # -----------------------------------------------------------------
    # Commit messages
    # -----------------------------------------------------------------

    async def commit_messages(self, limit: int = 10) -> list[str]:
        """Return recent change descriptions (subject lines)."""
        result = await self._client.log(revset="@-", limit=limit)
        return [c.description for c in result.changes if c.description]


# =====================================================================
# Helpers
# =====================================================================


def _translate_ref(ref: str) -> str:
    """Translate a git ref to a jj revset.

    - ``HEAD`` → ``@-``
    - Everything else passes through unchanged.
    """
    if ref == "HEAD":
        return _HEAD_ALIAS
    return ref


_DIFF_FILE_RE = re.compile(r"^diff --git a/(.+?) b/")


def _extract_changed_files(diff_output: str) -> list[str]:
    """Extract file paths from a git-format diff."""
    files: list[str] = []
    for line in diff_output.splitlines():
        m = _DIFF_FILE_RE.match(line)
        if m:
            files.append(m.group(1))
    return files


_STAT_LINE_RE = re.compile(r"^\s*(.+?)\s+\|\s+\d+")


def _parse_stat_output(raw: str) -> tuple[list[str], dict[str, tuple[int, int]]]:
    """Parse ``--stat`` output into file list and per-file (add, del) dict."""
    files: list[str] = []
    per_file: dict[str, tuple[int, int]] = {}
    for line in raw.splitlines():
        m = _STAT_LINE_RE.match(line)
        if m:
            filename = m.group(1).strip()
            files.append(filename)
            # Count + and - characters in the rest of the line
            rest = line[m.end() :]
            adds = rest.count("+")
            dels = rest.count("-")
            per_file[filename] = (adds, dels)
    return files, per_file
