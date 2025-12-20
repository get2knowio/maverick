# Workflow Editor Interface Contract

**Feature**: 024-workflow-serialization-viz
**Date**: 2025-12-20

## Overview

This document defines the interface contract for a future "workflow editor screen" (FR-029). This interface enables visual workflow editing in the TUI with live YAML preview.

---

## 1. Interface Definition

### 1.1 WorkflowEditorInterface

```python
from typing import Protocol
from pathlib import Path

class WorkflowEditorInterface(Protocol):
    """Interface for visual workflow editor (FR-029).

    This interface defines the contract for a future TUI screen that allows
    users to visually create and edit workflows. Implementations should
    provide visual step arrangement, property editing, and live YAML preview.
    """

    # -------------------------------------------------------------------------
    # Workflow Loading and Saving
    # -------------------------------------------------------------------------

    def load_workflow(self, source: Path | str) -> None:
        """Load workflow from file or YAML string.

        Args:
            source: Path to workflow file or YAML string.

        Raises:
            WorkflowParseError: If workflow is invalid.
        """
        ...

    def new_workflow(self, name: str, description: str = "") -> None:
        """Create a new empty workflow.

        Args:
            name: Workflow name.
            description: Optional description.
        """
        ...

    def save_workflow(self, path: Path) -> None:
        """Save current workflow to file.

        Args:
            path: Target file path.

        Raises:
            IOError: If file cannot be written.
        """
        ...

    def get_yaml_preview(self) -> str:
        """Get live YAML representation of current state.

        Returns:
            YAML string reflecting current editor state.
        """
        ...

    # -------------------------------------------------------------------------
    # Step Management
    # -------------------------------------------------------------------------

    def add_step(
        self,
        step_type: StepType,
        name: str,
        position: int | None = None,
    ) -> str:
        """Add a new step to the workflow.

        Args:
            step_type: Type of step to add.
            name: Step name.
            position: Index to insert at (None = append).

        Returns:
            ID of created step.

        Raises:
            DuplicateStepNameError: If name already exists.
        """
        ...

    def remove_step(self, step_id: str) -> None:
        """Remove a step from the workflow.

        Args:
            step_id: ID of step to remove.

        Raises:
            StepNotFoundError: If step doesn't exist.
        """
        ...

    def move_step(self, step_id: str, new_position: int) -> None:
        """Move step to new position in sequence.

        Args:
            step_id: ID of step to move.
            new_position: New index position.

        Raises:
            StepNotFoundError: If step doesn't exist.
            InvalidPositionError: If position is out of bounds.
        """
        ...

    def get_steps(self) -> list[EditorStepView]:
        """Get all steps in current order.

        Returns:
            List of EditorStepView for each step.
        """
        ...

    # -------------------------------------------------------------------------
    # Step Property Editing
    # -------------------------------------------------------------------------

    def get_step_properties(self, step_id: str) -> dict[str, Any]:
        """Get editable properties for a step.

        Args:
            step_id: ID of step.

        Returns:
            Dictionary of property name → current value.

        Raises:
            StepNotFoundError: If step doesn't exist.
        """
        ...

    def set_step_property(
        self,
        step_id: str,
        property_name: str,
        value: Any,
    ) -> ValidationResult:
        """Set a step property.

        Args:
            step_id: ID of step.
            property_name: Name of property to set.
            value: New value.

        Returns:
            ValidationResult indicating if change is valid.

        Raises:
            StepNotFoundError: If step doesn't exist.
            UnknownPropertyError: If property name is invalid for step type.
        """
        ...

    def get_property_schema(
        self,
        step_type: StepType,
    ) -> dict[str, PropertySchema]:
        """Get schema for step type's editable properties.

        Args:
            step_type: Type of step.

        Returns:
            Dictionary of property name → PropertySchema.
        """
        ...

    # -------------------------------------------------------------------------
    # Input Management
    # -------------------------------------------------------------------------

    def add_input(
        self,
        name: str,
        input_type: InputType,
        required: bool = True,
        default: Any = None,
        description: str = "",
    ) -> None:
        """Add a workflow input.

        Args:
            name: Input name.
            input_type: Input value type.
            required: Whether input is required.
            default: Default value if not required.
            description: Human-readable description.

        Raises:
            DuplicateInputError: If name already exists.
        """
        ...

    def remove_input(self, name: str) -> None:
        """Remove a workflow input.

        Args:
            name: Input name to remove.

        Raises:
            InputNotFoundError: If input doesn't exist.
            InputInUseError: If input is referenced by expressions.
        """
        ...

    def get_inputs(self) -> dict[str, InputDefinition]:
        """Get all workflow inputs.

        Returns:
            Dictionary of input name → InputDefinition.
        """
        ...

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    def validate(self) -> ValidationResult:
        """Validate current workflow state.

        Returns:
            ValidationResult with errors and warnings.
        """
        ...

    def get_available_references(
        self,
        at_step: str | None = None,
    ) -> list[ReferenceInfo]:
        """Get available references for expressions.

        Args:
            at_step: Step ID to check references for.
                If None, returns all possible references.
                If provided, returns only references available at that step.

        Returns:
            List of ReferenceInfo for available references.
        """
        ...

    # -------------------------------------------------------------------------
    # Undo/Redo
    # -------------------------------------------------------------------------

    def undo(self) -> bool:
        """Undo last change.

        Returns:
            True if undo was performed, False if no history.
        """
        ...

    def redo(self) -> bool:
        """Redo last undone change.

        Returns:
            True if redo was performed, False if no redo available.
        """
        ...

    @property
    def can_undo(self) -> bool:
        """Check if undo is available."""
        ...

    @property
    def can_redo(self) -> bool:
        """Check if redo is available."""
        ...

    @property
    def is_modified(self) -> bool:
        """Check if workflow has unsaved changes."""
        ...
```

---

## 2. Supporting Types

### 2.1 EditorStepView

```python
@dataclass(frozen=True, slots=True)
class EditorStepView:
    """View model for step in editor."""

    id: str  # Unique step ID (may differ from name)
    name: str  # Step name
    step_type: StepType
    position: int  # 0-indexed position
    summary: str  # One-line summary for display
    has_condition: bool  # Has 'when' clause
    has_error: bool  # Has validation error
```

---

### 2.2 PropertySchema

```python
@dataclass(frozen=True, slots=True)
class PropertySchema:
    """Schema for an editable step property."""

    name: str
    display_name: str  # Human-readable label
    property_type: PropertyType  # string, integer, boolean, etc.
    required: bool
    default: Any
    description: str
    options: tuple[str, ...] | None = None  # For enum/choice types
    is_expression: bool = False  # Whether value can be an expression

class PropertyType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    EXPRESSION = "expression"
    CODE = "code"  # Multi-line text
    CHOICE = "choice"  # Select from options
    LIST = "list"  # List of strings
    DICT = "dict"  # Key-value pairs
    STEP_REF = "step_ref"  # Reference to another step
```

---

### 2.3 ReferenceInfo

```python
@dataclass(frozen=True, slots=True)
class ReferenceInfo:
    """Information about an available expression reference."""

    expression: str  # e.g., "${{ inputs.name }}"
    description: str  # e.g., "Workflow input 'name' (string)"
    ref_type: str  # "input", "step_output", "config"
    value_type: str | None  # Expected type if known
```

---

## 3. Editor Events

The editor should emit events for TUI integration:

```python
class EditorEvent(Protocol):
    """Base protocol for editor events."""
    pass

@dataclass(frozen=True)
class WorkflowLoadedEvent:
    """Emitted when workflow is loaded."""
    name: str
    step_count: int

@dataclass(frozen=True)
class StepAddedEvent:
    """Emitted when step is added."""
    step_id: str
    step_type: StepType
    position: int

@dataclass(frozen=True)
class StepRemovedEvent:
    """Emitted when step is removed."""
    step_id: str

@dataclass(frozen=True)
class StepModifiedEvent:
    """Emitted when step property changes."""
    step_id: str
    property_name: str

@dataclass(frozen=True)
class ValidationChangedEvent:
    """Emitted when validation state changes."""
    is_valid: bool
    error_count: int
    warning_count: int

@dataclass(frozen=True)
class YAMLPreviewUpdatedEvent:
    """Emitted when YAML preview should refresh."""
    yaml_content: str
```

---

## 4. Usage Example

```python
# Create editor instance
editor = WorkflowEditor()

# Create new workflow
editor.new_workflow("my-workflow", "A sample workflow")

# Add inputs
editor.add_input("target", InputType.STRING, required=True)
editor.add_input("dry_run", InputType.BOOLEAN, default=False)

# Add steps
step1 = editor.add_step(StepType.PYTHON, "load_data")
editor.set_step_property(step1, "action", "myapp.loaders.load_data")
editor.set_step_property(step1, "args", ["${{ inputs.target }}"])

step2 = editor.add_step(StepType.AGENT, "process")
editor.set_step_property(step2, "agent", "processor")
editor.set_step_property(step2, "context", {"data": "${{ steps.load_data.output }}"})

# Validate
result = editor.validate()
if not result.valid:
    for error in result.errors:
        print(f"Error: {error.message} at {error.path}")

# Get YAML preview
yaml = editor.get_yaml_preview()
print(yaml)

# Save to file
editor.save_workflow(Path("workflow.yaml"))
```

---

## 5. Future TUI Screen Structure

```
┌─────────────────────────────────────────────────────────────────────┐
│ Workflow Editor: my-workflow                          [Save] [Close]│
├─────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────┐ ┌─────────────────────────────────────────┐ │
│ │ Steps               │ │ Properties: load_data                  │ │
│ ├─────────────────────┤ ├─────────────────────────────────────────┤ │
│ │ 1. ○ load_data      │ │ Name:   [load_data              ]      │ │
│ │ 2. ● process        │ │ Type:   python                         │ │
│ │ 3.   validate       │ │ Action: [myapp.loaders.load_data]      │ │
│ │                     │ │ Args:   [${{ inputs.target }}   ]      │ │
│ │ [+ Add Step]        │ │ When:   [                       ]      │ │
│ │                     │ │                                         │ │
│ └─────────────────────┘ └─────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ YAML Preview                                                    │ │
│ ├─────────────────────────────────────────────────────────────────┤ │
│ │ version: "1.0"                                                  │ │
│ │ name: my-workflow                                               │ │
│ │ inputs:                                                         │ │
│ │   target:                                                       │ │
│ │     type: string                                                │ │
│ │     required: true                                              │ │
│ │ steps:                                                          │ │
│ │   - name: load_data                                             │ │
│ │     type: python                                                │ │
│ │     action: myapp.loaders.load_data                            │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│ Validation: ✓ Valid                                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 6. Implementation Notes

This interface is defined for future implementation. Key considerations:

1. **State Management**: Editor should maintain immutable workflow snapshots for undo/redo
2. **Validation**: Run validation after each change; debounce for performance
3. **YAML Preview**: Update preview on change; debounce expensive serialization
4. **Expression Autocomplete**: Use `get_available_references()` for autocomplete in expression fields
5. **TUI Integration**: Use Textual widgets; integrate with existing theme system
