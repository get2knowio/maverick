"""Spec Kit ingestion exception hierarchy.

Backs the error catalog in ``contracts/cli-refuel-speckit.md`` (E01-E07).
E01 (name matches both classic and speckit) and E02 (unresolvable name)
are raised as plain :class:`SpeckitError` from the CLI dispatch layer —
their messages are fully determined by resolution context and need no
extra structured fields. E03-E07 carry structured fields callers can
render or inspect programmatically.
"""

from __future__ import annotations

from maverick.exceptions.base import MaverickError


class SpeckitError(MaverickError):
    """Base exception for Spec Kit ingestion errors.

    Attributes:
        message: Human-readable error message.
    """


class SpeckitParseError(SpeckitError):
    """Hard grammar violation in a Spec Kit artifact (E05).

    Attributes:
        message: Human-readable error message.
        file: Path to the file that failed to parse.
        line: 1-based line number where the violation occurred.
        expected: Description of the expected structure.
        suggestion: Suggested fix for the offending line.
    """

    def __init__(
        self,
        message: str,
        *,
        file: str,
        line: int,
        expected: str,
        suggestion: str,
    ) -> None:
        self.file = file
        self.line = line
        self.expected = expected
        self.suggestion = suggestion
        super().__init__(message)


class SpeckitValidationError(SpeckitError):
    """Graph/identity validation failure (E06): duplicate task ID,
    unknown dependency reference, or a dependency cycle.

    Attributes:
        message: Human-readable error message.
        file: Path to the file containing the offending reference(s).
        task_id: The task ID involved in the violation, if applicable.
        lines: Line numbers implicated (e.g. both lines of a duplicate).
        unknown_ref: The unresolved dependency ID, if applicable.
        cycle: Task IDs forming a dependency cycle, if applicable.
    """

    def __init__(
        self,
        message: str,
        *,
        file: str | None = None,
        task_id: str | None = None,
        lines: tuple[int, ...] = (),
        unknown_ref: str | None = None,
        cycle: tuple[str, ...] = (),
    ) -> None:
        self.file = file
        self.task_id = task_id
        self.lines = lines
        self.unknown_ref = unknown_ref
        self.cycle = cycle
        super().__init__(message)


class AmbiguousFeatureError(SpeckitError):
    """Ambiguous feature resolution — multiple candidates found (E01/E03).

    Attributes:
        message: Human-readable error message.
        query: The name argument as given.
        candidates: All matching candidate paths/labels, for display.
    """

    def __init__(
        self,
        message: str,
        *,
        query: str,
        candidates: tuple[str, ...],
    ) -> None:
        self.query = query
        self.candidates = candidates
        super().__init__(message)


class UnsupportedTemplateError(SpeckitError):
    """Vendored Spec Kit template version is outside the supported range (E04).

    Attributes:
        message: Human-readable error message.
        found_version: The vendored version that failed the range check.
        supported_range: The declared supported version range.
    """

    def __init__(
        self,
        message: str,
        *,
        found_version: str,
        supported_range: str,
    ) -> None:
        self.found_version = found_version
        self.supported_range = supported_range
        super().__init__(message)


class NothingToIngestError(SpeckitError):
    """Every task in the feature is already completed (E07): no epic,
    zero beads created.

    Attributes:
        message: Human-readable error message.
        completed_count: Number of tasks checked ``[x]``.
        total_count: Total number of tasks in the feature.
    """

    def __init__(
        self,
        message: str,
        *,
        completed_count: int,
        total_count: int,
    ) -> None:
        self.completed_count = completed_count
        self.total_count = total_count
        super().__init__(message)


__all__ = [
    "AmbiguousFeatureError",
    "NothingToIngestError",
    "SpeckitError",
    "SpeckitParseError",
    "SpeckitValidationError",
    "UnsupportedTemplateError",
]
