"""Jujutsu (jj) exceptions.

Exceptions for jj VCS operations: cloning, pushing, conflicts, and
operation log management.
"""

from __future__ import annotations

from maverick.exceptions.base import MaverickError


class JjError(MaverickError):
    """Base exception for jj operations.

    Attributes:
        message: Human-readable error message.
        command: The jj subcommand that failed (e.g. ``"describe"``).
        stderr: Raw stderr from the jj process.
    """

    def __init__(
        self,
        message: str,
        *,
        command: str | None = None,
        stderr: str | None = None,
    ) -> None:
        self.command = command
        self.stderr = stderr
        super().__init__(message)


class JjNotFoundError(JjError):
    """``jj`` binary is not on PATH."""

    def __init__(self, message: str = "jj CLI not found. Please install jj.") -> None:
        super().__init__(message)


class JjCloneError(JjError):
    """``jj git clone`` failed.

    Attributes:
        source: The clone source that was attempted.
    """

    def __init__(
        self,
        message: str,
        *,
        source: str | None = None,
        command: str | None = "git clone",
        stderr: str | None = None,
    ) -> None:
        self.source = source
        super().__init__(message, command=command, stderr=stderr)


class JjPushError(JjError):
    """``jj git push`` failed.

    Attributes:
        remote: The remote that rejected the push.
        bookmark: The bookmark being pushed.
    """

    def __init__(
        self,
        message: str,
        *,
        remote: str | None = None,
        bookmark: str | None = None,
        command: str | None = "git push",
        stderr: str | None = None,
    ) -> None:
        self.remote = remote
        self.bookmark = bookmark
        super().__init__(message, command=command, stderr=stderr)


class JjConflictError(JjError):
    """Conflicts detected during a jj operation."""

    def __init__(
        self,
        message: str = "Conflicts detected",
        *,
        command: str | None = None,
        stderr: str | None = None,
    ) -> None:
        super().__init__(message, command=command, stderr=stderr)


class JjOperationError(JjError):
    """Operation log error (snapshot / restore failure).

    Attributes:
        operation_id: The operation ID that failed.
    """

    def __init__(
        self,
        message: str,
        *,
        operation_id: str | None = None,
        command: str | None = None,
        stderr: str | None = None,
    ) -> None:
        self.operation_id = operation_id
        super().__init__(message, command=command, stderr=stderr)


__all__ = [
    "JjCloneError",
    "JjConflictError",
    "JjError",
    "JjNotFoundError",
    "JjOperationError",
    "JjPushError",
]
