"""Editor interface for TUI/GUI workflow editing.

This module provides the interface layer between workflow serialization components
and interactive editing interfaces (TUI/GUI). It defines:
- WorkflowEditorInterface: Protocol for editor implementations
- PropertySchema: Editable property schemas for step types
- EditorStepView: Read-only view of steps for display
- Editor events: Event classes for workflow editing operations

The editor interface enables interactive workflow creation and modification while
maintaining immutability and type safety.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from maverick.dsl.serialization.schema import StepRecord, WorkflowFile
from maverick.dsl.types import StepType

__all__ = [
    # Protocol
    "WorkflowEditorInterface",
    # Schema models
    "PropertySchema",
    "EditorStepView",
    # Events
    "WorkflowLoadedEvent",
    "StepAddedEvent",
    "StepRemovedEvent",
    "StepUpdatedEvent",
    "WorkflowValidatedEvent",
]


# =============================================================================
# Editor Protocol
# =============================================================================


class WorkflowEditorInterface(Protocol):
    """Interface for TUI/GUI workflow editing.

    This protocol defines the contract that workflow editor implementations
    must satisfy. It provides operations for loading, saving, and manipulating
    workflows in an interactive context.

    Implementations should emit appropriate events (WorkflowLoadedEvent, etc.)
    when operations complete to enable reactive UI updates.
    """

    def load_workflow(self, path: Path) -> WorkflowFile:
        """Load workflow from file.

        Args:
            path: Path to workflow YAML/JSON file

        Returns:
            Parsed and validated WorkflowFile

        Raises:
            WorkflowParseError: If file cannot be parsed
            ValidationError: If workflow is invalid
            FileNotFoundError: If file does not exist
        """
        ...

    def save_workflow(self, workflow: WorkflowFile, path: Path) -> None:
        """Save workflow to file.

        Args:
            workflow: WorkflowFile instance to serialize
            path: Destination file path

        Raises:
            WorkflowSerializationError: If workflow cannot be serialized
            OSError: If file cannot be written
        """
        ...

    def add_step(self, step: StepRecord, position: int | None = None) -> None:
        """Add step to workflow.

        Args:
            step: StepRecord instance to add
            position: Optional 0-based position (appends if None)

        Raises:
            ValueError: If step name conflicts with existing step
            IndexError: If position is out of bounds
        """
        ...

    def remove_step(self, step_name: str) -> None:
        """Remove step by name.

        Args:
            step_name: Name of step to remove

        Raises:
            KeyError: If step name does not exist
        """
        ...

    def update_step(self, step_name: str, changes: dict[str, Any]) -> None:
        """Update step properties.

        Args:
            step_name: Name of step to update
            changes: Dict of property name → new value

        Raises:
            KeyError: If step name does not exist
            ValueError: If changes would make step invalid
        """
        ...

    def get_step_schema(self, step_type: StepType) -> PropertySchema:
        """Get editable property schema for step type.

        Returns the schema defining which properties can be edited for
        the given step type, including types, constraints, and defaults.

        Args:
            step_type: Type of step (AGENT, GENERATE, etc.)

        Returns:
            PropertySchema for the step type

        Raises:
            ValueError: If step_type is not recognized
        """
        ...


# =============================================================================
# Property Schema
# =============================================================================


@dataclass(frozen=True, slots=True)
class PropertySchema:
    """Schema for an editable property.

    Defines the structure, constraints, and metadata for a single
    editable property in a workflow step. Used by editor UIs to
    generate appropriate input controls.

    Attributes:
        name: Property name (matches field in StepRecord)
        type: Type identifier ("string", "integer", "boolean", "array", "object")
        required: Whether property must have a value
        default: Default value if not required
        description: Human-readable description for UI display
        enum_values: Allowed values for choice/enum fields (empty if not a choice)
    """

    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    required: bool = False
    default: Any = None
    description: str = ""
    enum_values: tuple[str, ...] = ()  # For choice fields


# =============================================================================
# Editor Step View
# =============================================================================


@dataclass(frozen=True, slots=True)
class EditorStepView:
    """Read-only view of a step for display in editor.

    Provides a flattened, UI-friendly representation of a step
    including its editable properties and validation status.

    Attributes:
        name: Step name
        type: Step type (AGENT, GENERATE, etc.)
        description: Human-readable description
        properties: Tuple of editable property schemas
        is_valid: Whether step passes validation
        validation_errors: Validation error messages (empty if valid)
    """

    name: str
    type: StepType
    description: str
    properties: tuple[PropertySchema, ...]
    is_valid: bool
    validation_errors: tuple[str, ...] = ()


# =============================================================================
# Editor Events
# =============================================================================


@dataclass(frozen=True, slots=True)
class WorkflowLoadedEvent:
    """Emitted when workflow is loaded.

    Signals that a workflow file has been successfully loaded
    and is ready for editing.

    Attributes:
        workflow: Loaded and validated WorkflowFile
        path: Path to source file
    """

    workflow: WorkflowFile
    path: Path


@dataclass(frozen=True, slots=True)
class StepAddedEvent:
    """Emitted when step is added.

    Signals that a new step has been added to the workflow.

    Attributes:
        step: StepRecord that was added
        position: 0-based position in step list
    """

    step: StepRecord
    position: int


@dataclass(frozen=True, slots=True)
class StepRemovedEvent:
    """Emitted when step is removed.

    Signals that a step has been removed from the workflow.

    Attributes:
        step_name: Name of removed step
    """

    step_name: str


@dataclass(frozen=True, slots=True)
class StepUpdatedEvent:
    """Emitted when step is updated.

    Signals that a step's properties have been modified.

    Attributes:
        step_name: Name of updated step
        changes: Dict of property name → new value
    """

    step_name: str
    changes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WorkflowValidatedEvent:
    """Emitted when workflow validation completes.

    Signals that the entire workflow has been validated,
    providing aggregate validation status.

    Attributes:
        is_valid: True if workflow has no validation errors
        errors: Tuple of validation error messages
    """

    is_valid: bool
    errors: tuple[str, ...]
