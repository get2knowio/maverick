"""Contract: Workflow Discovery API.

This module defines the public interface for multi-location workflow discovery.
Implementation will be in maverick.dsl.discovery.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from maverick.dsl.serialization.schema import WorkflowFile


# =============================================================================
# Enums (from data-model.md)
# =============================================================================


class WorkflowSource:
    """Origin location of a workflow definition.

    Values:
        BUILTIN: Packaged with Maverick
        USER: ~/.config/maverick/workflows/
        PROJECT: .maverick/workflows/
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

    Attributes:
        name: Workflow name (matches WorkflowFile.name).
        version: Workflow version string.
        description: Human-readable description.
        input_names: Tuple of input parameter names.
        step_count: Number of top-level steps.
        file_path: Absolute path to workflow file.
        source: Origin location (builtin/user/project).
    """

    name: str
    version: str
    description: str
    input_names: tuple[str, ...]
    step_count: int
    file_path: Path
    source: str  # WorkflowSource value


@dataclass(frozen=True, slots=True)
class DiscoveredWorkflow:
    """A fully parsed workflow with source information.

    Attributes:
        workflow: The parsed WorkflowFile.
        file_path: Absolute path to source file.
        source: Origin location (builtin/user/project).
        overrides: Paths of workflows with same name that this overrides.
    """

    workflow: WorkflowFile
    file_path: Path
    source: str  # WorkflowSource value
    overrides: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class SkippedWorkflow:
    """A workflow file skipped due to errors.

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
class DiscoveryResult:
    """Aggregated result of workflow discovery.

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
        """Return sorted unique workflow names."""
        return tuple(sorted({w.workflow.name for w in self.workflows}))

    @property
    def fragment_names(self) -> tuple[str, ...]:
        """Return sorted unique fragment names."""
        return tuple(sorted({f.workflow.name for f in self.fragments}))

    def get_workflow(self, name: str) -> DiscoveredWorkflow | None:
        """Lookup workflow by name (returns highest precedence)."""
        for w in self.workflows:
            if w.workflow.name == name:
                return w
        return None

    def get_fragment(self, name: str) -> DiscoveredWorkflow | None:
        """Lookup fragment by name (returns highest precedence)."""
        for f in self.fragments:
            if f.workflow.name == name:
                return f
        return None


# =============================================================================
# Exceptions
# =============================================================================


class WorkflowDiscoveryError(Exception):
    """Base exception for discovery errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class WorkflowConflictError(WorkflowDiscoveryError):
    """Raised when multiple workflows share name at same precedence level.

    Attributes:
        name: The conflicting workflow name.
        source: The precedence level where conflict occurred.
        conflicting_paths: Paths of the conflicting files.
    """

    def __init__(
        self,
        name: str,
        source: str,
        conflicting_paths: tuple[Path, ...],
    ) -> None:
        self.name = name
        self.source = source
        self.conflicting_paths = conflicting_paths
        paths_str = ", ".join(str(p) for p in conflicting_paths)
        message = (
            f"Multiple workflows named '{name}' at {source} level: {paths_str}"
        )
        super().__init__(message)


# =============================================================================
# Service Protocols
# =============================================================================


class WorkflowLocator(Protocol):
    """Protocol for finding workflow files in a location.

    Implementations scan a directory for workflow YAML files.
    """

    def scan(self, directory: Path) -> list[Path]:
        """Find all workflow files in directory.

        Args:
            directory: Directory to scan.

        Returns:
            List of paths to workflow YAML files.
        """
        ...


class WorkflowLoader(Protocol):
    """Protocol for parsing workflow files.

    Implementations handle YAML parsing and schema validation.
    """

    def load_metadata(self, path: Path) -> WorkflowMetadata:
        """Load workflow metadata without full validation.

        Args:
            path: Path to workflow file.

        Returns:
            Parsed metadata.

        Raises:
            WorkflowParseError: If file cannot be parsed.
        """
        ...

    def load_full(self, path: Path) -> WorkflowFile:
        """Load and fully validate workflow file.

        Args:
            path: Path to workflow file.

        Returns:
            Fully validated WorkflowFile.

        Raises:
            WorkflowParseError: If validation fails.
        """
        ...


class WorkflowDiscovery(ABC):
    """Abstract base for workflow discovery service.

    Implementations scan multiple locations and apply precedence rules.
    """

    @abstractmethod
    def discover(
        self,
        project_dir: Path | None = None,
        user_dir: Path | None = None,
        include_builtin: bool = True,
    ) -> DiscoveryResult:
        """Discover workflows from all configured locations.

        Args:
            project_dir: Override project workflows directory.
            user_dir: Override user workflows directory.
            include_builtin: Whether to include built-in workflows.

        Returns:
            DiscoveryResult with all discovered workflows.

        Raises:
            WorkflowConflictError: If same-name conflict at same precedence.
        """
        ...

    @abstractmethod
    def get_builtin_path(self) -> Path:
        """Get path to built-in workflows package resource.

        Returns:
            Path to built-in workflows directory.
        """
        ...

    @abstractmethod
    def get_user_path(self) -> Path:
        """Get path to user workflows directory.

        Returns:
            Path to ~/.config/maverick/workflows/
        """
        ...

    @abstractmethod
    def get_project_path(self, project_root: Path | None = None) -> Path:
        """Get path to project workflows directory.

        Args:
            project_root: Project root directory (defaults to cwd).

        Returns:
            Path to .maverick/workflows/
        """
        ...


# =============================================================================
# Factory Functions
# =============================================================================


def create_discovery(
    locator: WorkflowLocator | None = None,
    loader: WorkflowLoader | None = None,
) -> WorkflowDiscovery:
    """Create a workflow discovery service.

    Args:
        locator: Custom locator implementation (uses default if None).
        loader: Custom loader implementation (uses default if None).

    Returns:
        Configured WorkflowDiscovery instance.
    """
    # Implementation will be in maverick.dsl.discovery
    raise NotImplementedError("Implementation in maverick.dsl.discovery")
