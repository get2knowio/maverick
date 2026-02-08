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
        from_id: ID of the bead the dependency originates from.
        to_id: ID of the bead the dependency targets.
    """

    def __init__(
        self,
        message: str,
        from_id: str | None = None,
        to_id: str | None = None,
    ) -> None:
        """Initialize the BeadDependencyError.

        Args:
            message: Human-readable error message.
            from_id: ID of the source bead.
            to_id: ID of the target bead.
        """
        self.from_id = from_id
        self.to_id = to_id
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
