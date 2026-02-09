"""Bead-related exceptions.

Exceptions for bead creation, dependency wiring, and SpecKit parsing.
"""

from __future__ import annotations

from pathlib import Path

from maverick.exceptions.base import MaverickError


class BeadError(MaverickError):
    """Base exception for bead operations.

    Attributes:
        message: Human-readable error message.
    """

    pass


class BeadCreationError(BeadError):
    """Failed to create a bead via ``bd create``.

    Attributes:
        message: Human-readable error message.
        bead_title: Title of the bead that failed to create.
    """

    def __init__(self, message: str, bead_title: str | None = None) -> None:
        """Initialize the BeadCreationError.

        Args:
            message: Human-readable error message.
            bead_title: Title of the bead that failed to create.
        """
        self.bead_title = bead_title
        super().__init__(message)


class BeadDependencyError(BeadError):
    """Failed to add a dependency between beads via ``bd dep add``.

    Attributes:
        message: Human-readable error message.
        blocker_id: ID of the prerequisite bead.
        blocked_id: ID of the dependent bead.
    """

    def __init__(
        self,
        message: str,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
        blocker_id: str | None = None,
        blocked_id: str | None = None,
    ) -> None:
        """Initialize the BeadDependencyError.

        Args:
            message: Human-readable error message.
            blocker_id: ID of the prerequisite bead.
            blocked_id: ID of the dependent bead.
            from_id: Deprecated alias for blocker_id.
            to_id: Deprecated alias for blocked_id.
        """
        self.blocker_id = blocker_id or from_id
        self.blocked_id = blocked_id or to_id
        super().__init__(message)


class BeadCloseError(BeadError):
    """Failed to close a bead via ``bd close``.

    Attributes:
        message: Human-readable error message.
        bead_id: ID of the bead that failed to close.
    """

    def __init__(self, message: str, bead_id: str | None = None) -> None:
        """Initialize the BeadCloseError.

        Args:
            message: Human-readable error message.
            bead_id: ID of the bead that failed to close.
        """
        self.bead_id = bead_id
        super().__init__(message)


class BeadQueryError(BeadError):
    """Failed to query beads via ``bd query`` or similar.

    Attributes:
        message: Human-readable error message.
        query: The query expression or command that failed.
    """

    def __init__(self, message: str, query: str | None = None) -> None:
        """Initialize the BeadQueryError.

        Args:
            message: Human-readable error message.
            query: The query expression that failed.
        """
        self.query = query
        super().__init__(message)


class SpecKitParseError(BeadError):
    """Failed to parse a SpecKit specification directory.

    Attributes:
        message: Human-readable error message.
        spec_dir: Path to the spec directory that failed to parse.
    """

    def __init__(self, message: str, spec_dir: Path | str | None = None) -> None:
        """Initialize the SpecKitParseError.

        Args:
            message: Human-readable error message.
            spec_dir: Path to the spec directory that failed to parse.
        """
        self.spec_dir = spec_dir
        super().__init__(message)
