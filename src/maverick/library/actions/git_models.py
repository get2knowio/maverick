"""Typed result dataclasses for :mod:`maverick.library.actions.git`.

CLAUDE.md guardrail #3: action outputs must have a single, typed
contract — frozen dataclasses or TypedDicts, not ad-hoc
``dict[str, Any]`` blobs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GitStatusResult:
    """Staged/unstaged/untracked change detection."""

    has_staged: bool
    has_unstaged: bool
    has_untracked: bool
    has_any: bool


@dataclass(frozen=True)
class GitOperationResult:
    """Generic success/error pair used by ``git_add`` / ``git_stage_all``."""

    success: bool
    error: str | None = None


@dataclass(frozen=True)
class GitCommitResult:
    """Result of ``git_commit``.

    ``commit_sha`` is ``None`` when there was nothing to commit or the
    commit itself failed. ``files_committed`` is an empty tuple in
    those cases.
    """

    success: bool
    message: str
    commit_sha: str | None = None
    files_committed: tuple[str, ...] = ()
    nothing_to_commit: bool = False
    error: str | None = None


@dataclass(frozen=True)
class GitPushResult:
    """Result of ``git_push``."""

    success: bool
    remote: str
    branch: str
    upstream_set: bool
    error: str | None = None


@dataclass(frozen=True)
class GitMergeResult:
    """Result of ``git_merge``."""

    success: bool
    branch: str
    merge_commit: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class SnapshotDiffStats:
    """Diff stats gathered before a snapshot commit."""

    file_count: int = 0
    insertions: int = 0
    deletions: int = 0
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class SnapshotResult:
    """Result of ``snapshot_uncommitted_changes``."""

    success: bool
    committed: bool
    commit_sha: str | None = None
    diff_stats: SnapshotDiffStats | None = None
    warning: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class GitBranchResult:
    """Result of ``create_git_branch``."""

    success: bool
    branch_name: str
    base_branch: str
    created: bool
    error: str | None = None


__all__ = [
    "GitBranchResult",
    "GitCommitResult",
    "GitMergeResult",
    "GitOperationResult",
    "GitPushResult",
    "GitStatusResult",
    "SnapshotDiffStats",
    "SnapshotResult",
]
