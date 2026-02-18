"""VcsRepository protocol definition.

This protocol defines the read-only VCS interface consumed by context
builders, MCP tools, and other workspace-aware components.  Both
:class:`~maverick.git.repository.AsyncGitRepository` (git) and
:class:`~maverick.jj.repository.JjRepository` (jj) satisfy it via
structural typing — no explicit inheritance required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from maverick.git.repository import CommitInfo, DiffStats, GitStatus


@runtime_checkable
class VcsRepository(Protocol):
    """Read-only VCS repository abstraction.

    Any object exposing this interface can be used by context builders
    and MCP tools without knowing whether the backend is git or jj.
    """

    @property
    def path(self) -> Path:
        """Root path of the repository."""
        ...

    async def current_branch(self) -> str:
        """Return the current branch (or bookmark / change ID)."""
        ...

    async def diff(
        self,
        base: str = "HEAD",
        head: str | None = None,
    ) -> str:
        """Return diff text between *base* and *head*."""
        ...

    async def diff_stats(self, base: str = "HEAD") -> DiffStats:
        """Return diff statistics between *base* and the working tree."""
        ...

    async def get_changed_files(self, ref: str = "HEAD") -> list[str]:
        """Return list of changed file paths relative to *ref*."""
        ...

    async def log(self, n: int = 10) -> list[CommitInfo]:
        """Return the *n* most recent commits/changes."""
        ...

    async def status(self) -> GitStatus:
        """Return repository status snapshot."""
        ...

    async def commit_messages(self, limit: int = 10) -> list[str]:
        """Return recent commit messages (subject lines)."""
        ...
