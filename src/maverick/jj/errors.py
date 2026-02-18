"""Jujutsu (jj) error hierarchy — re-exports from :mod:`maverick.exceptions.jj`.

Import from here within the ``maverick.jj`` package for convenience.
Canonical definitions live in :mod:`maverick.exceptions.jj`.
"""

from __future__ import annotations

from maverick.exceptions.jj import (
    JjCloneError,
    JjConflictError,
    JjError,
    JjNotFoundError,
    JjOperationError,
    JjPushError,
)

__all__ = [
    "JjCloneError",
    "JjConflictError",
    "JjError",
    "JjNotFoundError",
    "JjOperationError",
    "JjPushError",
]
