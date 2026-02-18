"""Jujutsu (jj) VCS client package.

Provides :class:`JjClient` for async-safe jj CLI operations, typed result
models, and a domain-specific error hierarchy.
"""

from __future__ import annotations

from maverick.jj.client import JjClient
from maverick.jj.errors import (
    JjCloneError,
    JjConflictError,
    JjError,
    JjNotFoundError,
    JjOperationError,
    JjPushError,
)
from maverick.jj.models import (
    JjBookmark,
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

__all__ = [
    # Client
    "JjClient",
    # Errors
    "JjCloneError",
    "JjConflictError",
    "JjError",
    "JjNotFoundError",
    "JjOperationError",
    "JjPushError",
    # Models
    "JjBookmark",
    "JjChangeInfo",
    "JjCloneResult",
    "JjCommitResult",
    "JjDescribeResult",
    "JjDiffResult",
    "JjDiffStatResult",
    "JjFetchResult",
    "JjLogResult",
    "JjNewResult",
    "JjPushResult",
    "JjRebaseResult",
    "JjRestoreResult",
    "JjShowResult",
    "JjSnapshotResult",
    "JjSquashResult",
    "JjStatusResult",
]
