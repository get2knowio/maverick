"""Input/Output models for the fixer agent.

This module defines the data structures used to communicate with the fixer agent.
These are frozen dataclasses using tuples for immutable sequences.

Models:
- FixerInputItem: Single finding sent to fixer
- FixerInput: Complete input for fixer agent
- FixerOutputItem: Single item in fixer response
- FixerOutput: Complete fixer response with validation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# =============================================================================
# Fixer Input Models (T007)
# =============================================================================


@dataclass(frozen=True, slots=True)
class FixerInputItem:
    """Single finding sent to fixer.

    Contains all information needed for the fixer agent to understand
    and attempt to fix a specific finding.

    Attributes:
        finding_id: Unique ID of the finding (e.g., RS001, RT001).
        severity: Severity level as string (critical, major, minor).
        title: Short title describing the issue.
        description: Detailed description of the issue.
        file_path: Path to the affected file (None if general issue).
        line_range: Tuple of (start, end) line numbers (None if not applicable).
        suggested_fix: Suggested fix for the issue (None if not provided).
        previous_attempts: Tuple of previous attempt dictionaries for context.
    """

    finding_id: str
    severity: str
    title: str
    description: str
    file_path: str | None
    line_range: tuple[int, int] | None
    suggested_fix: str | None
    previous_attempts: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "line_range": list(self.line_range) if self.line_range else None,
            "suggested_fix": self.suggested_fix,
            "previous_attempts": list(self.previous_attempts),
        }


@dataclass(frozen=True, slots=True)
class FixerInput:
    """Complete input for fixer agent.

    Contains all items to be fixed in the current iteration along with
    context information.

    Attributes:
        iteration: Current iteration number (1-indexed for display).
        items: Tuple of FixerInputItem instances to be fixed.
        context: Additional context for the fixer (e.g., PR description).
    """

    iteration: int
    items: tuple[FixerInputItem, ...]
    context: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "iteration": self.iteration,
            "items": [item.to_dict() for item in self.items],
            "context": self.context,
        }


# =============================================================================
# Fixer Output Models (T008)
# =============================================================================


@dataclass(frozen=True, slots=True)
class FixerOutputItem:
    """Single item in fixer response.

    Reports the outcome of attempting to fix a specific finding.

    Attributes:
        finding_id: ID of the finding this response is for.
        status: Outcome status (fixed, blocked, deferred).
        justification: Explanation for blocked/deferred (required for those statuses).
        changes_made: Description of changes made (for fixed status).
    """

    finding_id: str
    status: str  # "fixed", "blocked", "deferred"
    justification: str | None
    changes_made: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "finding_id": self.finding_id,
            "status": self.status,
            "justification": self.justification,
            "changes_made": self.changes_made,
        }


@dataclass(frozen=True, slots=True)
class FixerOutput:
    """Complete fixer response.

    Contains all fix attempt results along with an optional summary.

    Attributes:
        items: Tuple of FixerOutputItem instances.
        summary: Optional summary of all fix attempts.
    """

    items: tuple[FixerOutputItem, ...]
    summary: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "items": [item.to_dict() for item in self.items],
            "summary": self.summary,
        }

    def validate_against_input(self, fixer_input: FixerInput) -> tuple[bool, list[str]]:
        """Validate that output has entry for every input item.

        Checks that:
        1. All input item IDs are present in output
        2. Status values are valid (fixed, blocked, deferred)
        3. Blocked/deferred items have justifications

        Args:
            fixer_input: The input that this output is responding to.

        Returns:
            Tuple of (is_valid, error_messages).
        """
        errors: list[str] = []
        valid_statuses = {"fixed", "blocked", "deferred"}

        # Build set of input IDs
        input_ids = {item.finding_id for item in fixer_input.items}

        # Build set of output IDs
        output_ids = {item.finding_id for item in self.items}

        # Check all input IDs are present in output
        missing_ids = input_ids - output_ids
        if missing_ids:
            errors.append(f"Missing responses for finding IDs: {sorted(missing_ids)}")

        # Check each output item
        for item in self.items:
            # Validate status
            if item.status not in valid_statuses:
                errors.append(
                    f"Invalid status '{item.status}' for finding {item.finding_id}. "
                    f"Must be one of: {sorted(valid_statuses)}"
                )

            # Check blocked/deferred have justifications
            if item.status in {"blocked", "deferred"} and not item.justification:
                errors.append(
                    f"Finding {item.finding_id} has status '{item.status}' "
                    "but no justification provided"
                )

        is_valid = len(errors) == 0
        return is_valid, errors
