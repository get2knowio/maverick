"""VCS backend factory.

Auto-detects whether a path is a jj-only workspace or a git repository
and returns the appropriate :class:`~maverick.vcs.protocol.VcsRepository`
implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.vcs.protocol import VcsRepository


def create_vcs_repository(
    path: Path,
    backend: str = "auto",
) -> VcsRepository:
    """Create a VcsRepository for *path*.

    Args:
        path: Root directory of the repository.
        backend: ``"auto"`` (detect), ``"jj"``, or ``"git"``.

    Returns:
        A :class:`VcsRepository` implementation.

    Raises:
        ValueError: If *backend* is unknown.
    """
    if backend == "jj" or (backend == "auto" and _is_jj_workspace(path)):
        from maverick.jj.repository import JjRepository

        return JjRepository(path)

    if backend in ("git", "auto"):
        from maverick.git.repository import AsyncGitRepository

        return AsyncGitRepository(path)

    msg = f"Unknown VCS backend: {backend!r}"
    raise ValueError(msg)


def _is_jj_workspace(path: Path) -> bool:
    """Return True if *path* contains a ``.jj/`` directory but no ``.git/``."""
    return (path / ".jj").is_dir() and not (path / ".git").is_dir()
