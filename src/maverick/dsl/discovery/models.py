"""Data models for workflow discovery.

This module implements the discovery data models defined in the contracts.
All models use frozen dataclasses with slots for efficiency and immutability.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.dsl.serialization.schema import WorkflowFile


# =============================================================================
# Enums
# =============================================================================


class WorkflowSource(str, Enum):
    """Origin location of a workflow definition.

    Values:
        BUILTIN: Packaged with Maverick
        USER: ~/.config/maverick/workflows/
        PROJECT: .maverick/workflows/

    Precedence Order: PROJECT > USER > BUILTIN (higher overrides lower)
    """

    BUILTIN = "builtin"
    USER = "user"
    PROJECT = "project"


# =============================================================================
# Data Transfer Objects
# =============================================================================


@dataclass(frozen=True, slots=True)
class WorkflowMetadata:
    """Lightweight metadata for a discovered workflow.

    Parsed from workflow file header without full validation.
    Used for listing and display operations.

    Attributes:
        name: Workflow name (matches WorkflowFile.name).
        version: Workflow version string.
        description: Human-readable description.
        input_names: Tuple of input parameter names.
        step_count: Number of top-level steps.
        file_path: Absolute path to workflow file.
        source: Origin location (builtin/user/project).

    Validation Rules:
        - name: Must match ^[a-z][a-z0-9-]{0,63}$
        - version: Must match ^\\d+\\.\\d+$
        - file_path: Must exist and be readable
    """

    name: str
    version: str
    description: str
    input_names: tuple[str, ...]
    step_count: int
    file_path: Path
    source: str  # WorkflowSource value

    @property
    def qualified_name(self) -> str:
        """Return source-qualified name for disambiguation.

        Returns:
            String in format "source:name" (e.g., "builtin:fly").
        """
        return f"{self.source}:{self.name}"


@dataclass(frozen=True, slots=True)
class DiscoveredWorkflow:
    """A fully parsed workflow with source information.

    Contains the complete WorkflowFile plus source tracking
    for precedence and override display.

    Attributes:
        workflow: The parsed WorkflowFile.
        file_path: Absolute path to source file.
        source: Origin location (builtin/user/project).
        overrides: Paths of workflows with same name that this overrides.

    Relationships:
        - Contains one WorkflowFile (from dsl.serialization.schema)
        - May override zero or more workflows with same name from
          lower-precedence sources
    """

    workflow: WorkflowFile
    file_path: Path
    source: str  # WorkflowSource value
    overrides: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class SkippedWorkflow:
    """A workflow file skipped due to errors.

    Captures error context for reporting while allowing
    discovery to continue for remaining files.

    Attributes:
        file_path: Path to the skipped file.
        error_message: Human-readable error description.
        error_type: Category of error (parse_error, schema_error, io_error).
        line_number: Optional line number where error occurred.
    """

    file_path: Path
    error_message: str
    error_type: str
    line_number: int | None = None


@dataclass(frozen=True, slots=True)
class WorkflowConflict:
    """Conflict when multiple workflows share name at same precedence.

    Discovery must fail when this occurs (FR-016).

    Attributes:
        name: The conflicting workflow name.
        source: The precedence level where conflict occurred.
        conflicting_paths: Paths of the conflicting files.
    """

    name: str
    source: str  # WorkflowSource value
    conflicting_paths: tuple[Path, ...]

    def to_error_message(self) -> str:
        """Generate human-readable error message.

        Returns:
            Formatted error message with file paths listed.
        """
        paths_str = "\n  - ".join(str(p) for p in self.conflicting_paths)
        return (
            f"Multiple workflows named '{self.name}' at {self.source} level:\n"
            f"  - {paths_str}"
        )


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Aggregated result of workflow discovery.

    Contains the resolved workflow registry plus metadata
    about the discovery process for debugging and display.

    Attributes:
        workflows: Discovered workflows (highest precedence wins).
        fragments: Discovered fragments (highest precedence wins).
        skipped: Workflows that failed to parse.
        locations_scanned: Paths that were scanned.
        discovery_time_ms: Time taken for discovery.
    """

    workflows: tuple[DiscoveredWorkflow, ...]
    fragments: tuple[DiscoveredWorkflow, ...]
    skipped: tuple[SkippedWorkflow, ...]
    locations_scanned: tuple[Path, ...]
    discovery_time_ms: float

    @property
    def workflow_names(self) -> tuple[str, ...]:
        """Return sorted unique workflow names.

        Returns:
            Tuple of workflow names in alphabetical order.
        """
        return tuple(sorted({w.workflow.name for w in self.workflows}))

    @property
    def fragment_names(self) -> tuple[str, ...]:
        """Return sorted unique fragment names.

        Returns:
            Tuple of fragment names in alphabetical order.
        """
        return tuple(sorted({f.workflow.name for f in self.fragments}))

    def get_workflow(self, name: str) -> DiscoveredWorkflow | None:
        """Lookup workflow by name (returns highest precedence).

        Args:
            name: Workflow name to search for.

        Returns:
            DiscoveredWorkflow if found, None otherwise.
        """
        for w in self.workflows:
            if w.workflow.name == name:
                return w
        return None

    def get_fragment(self, name: str) -> DiscoveredWorkflow | None:
        """Lookup fragment by name (returns highest precedence).

        Args:
            name: Fragment name to search for.

        Returns:
            DiscoveredWorkflow if found, None otherwise.
        """
        for f in self.fragments:
            if f.workflow.name == name:
                return f
        return None
