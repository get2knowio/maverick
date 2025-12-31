"""Git operations package using GitPython.

This package provides a unified interface for git operations, replacing the
scattered implementations across runners/git.py, utils/git.py, and
utils/git_operations.py.

Key features:
- GitPython-based operations (no subprocess management needed)
- Both sync (GitRepository) and async (AsyncGitRepository) APIs
- Tenacity-based retry logic for network operations
- Full backward compatibility with existing interfaces

Usage:
    ```python
    # Sync usage
    from maverick.git import GitRepository

    repo = GitRepository("/path/to/repo")
    status = repo.status()
    repo.commit("feat: add feature", add_all=True)
    repo.push()

    # Async usage
    from maverick.git import AsyncGitRepository

    repo = AsyncGitRepository("/path/to/repo")
    status = await repo.status()
    await repo.commit("feat: add feature", add_all=True)
    await repo.push()
    ```

Migration from old modules:
    - `maverick.runners.git.GitRunner` -> `maverick.git.GitRepository`
    - `maverick.utils.git_operations.GitOperations` -> `maverick.git.GitRepository`
    - `maverick.utils.git_operations.AsyncGitOperations` -> `AsyncGitRepository`
    - `maverick.utils.git.*` -> Use `GitRepository` methods directly

The old modules still work but emit deprecation warnings.
"""

from __future__ import annotations

from maverick.git.repository import (
    AsyncGitRepository,
    CommitInfo,
    DiffStats,
    GitRepository,
    GitStatus,
    is_recoverable_error,
)

__all__ = [
    "AsyncGitRepository",
    "CommitInfo",
    "DiffStats",
    "GitRepository",
    "GitStatus",
    "is_recoverable_error",
]
