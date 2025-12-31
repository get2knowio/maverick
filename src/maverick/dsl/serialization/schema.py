"""Pydantic schema models for workflow serialization.

This module defines the schema for YAML/JSON workflow files, including:
- WorkflowFile: Top-level workflow file schema
- InputDefinition: Input parameter declarations
- StepRecord: Discriminated union of step types
- ValidationResult: Schema validation results

All models use Pydantic v2 for validation and provide comprehensive error messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from maverick.dsl.config import DEFAULTS
from maverick.dsl.types import StepType

__all__ = [
    # Enums
    "InputType",
    # Input models
    "InputDefinition",
    # Step models - base
    "StepRecord",
    # Step models - concrete types
    "PythonStepRecord",
    "AgentStepRecord",
    "GenerateStepRecord",
    "ValidateStepRecord",
    "SubWorkflowStepRecord",
    "BranchStepRecord",
    "BranchOptionRecord",
    "ParallelStepRecord",
    "CheckpointStepRecord",
    # Discriminated union
    "StepRecordUnion",
    # Top-level workflow
    "WorkflowFile",
    # Validation results
    "ValidationError",
    "ValidationWarning",
    "ValidationResult",
]


# =============================================================================
# Input Type System
# =============================================================================


class InputType(str, Enum):
    """Supported input parameter types (FR-007)."""

    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    FLOAT = "float"
    OBJECT = "object"  # dict[str, Any]
    ARRAY = "array"  # list[Any]


class InputDefinition(BaseModel):
    """Workflow input parameter declaration (FR-007).

    Declares an input parameter with type constraints, default values,
    and documentation.

    Validation Rules:
        - If required=True, default must be None
        - If default is provided, it must be valid for the declared type
    """

    type: InputType
    required: bool = True
    default: Any = None
    description: str = ""

    @model_validator(mode="after")
    def validate_default_consistency(self) -> InputDefinition:
        """Ensure required/default consistency."""
        if self.required and self.default is not None:
            raise ValueError("Required inputs cannot have default values")
        # TODO: Add type-specific default validation in a future enhancement
        return self


# =============================================================================
# Step Record Models
# =============================================================================


class StepRecord(BaseModel):
    """Base schema for step definitions (FR-008).

    All step types share these common fields. The 'type' field acts as
    the discriminator for the union of step subtypes.
    """

    name: str = Field(..., min_length=1)
    type: StepType
    when: str | None = Field(None, description="Optional condition expression")

    @field_validator("name")
    @classmethod
    def validate_name_format(cls, v: str) -> str:
        """Ensure step name is valid."""
        if not v.strip():
            raise ValueError("Step name cannot be empty or whitespace")
        return v


class PythonStepRecord(StepRecord):
    """Python callable step (FR-009).

    Invokes a registered Python function with the specified arguments.

    Fields:
        action: Fully qualified function name or registry key
        args: Positional arguments (may contain expressions)
        kwargs: Keyword arguments (may contain expressions)
        rollback: Optional action to call if workflow fails after this step
    """

    type: Literal[StepType.PYTHON] = StepType.PYTHON
    action: str = Field(..., min_length=1)
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    rollback: str | None = Field(
        None,
        description="Optional action to call for rollback/compensation",
    )


class AgentStepRecord(StepRecord):
    """Agent invocation step (FR-009).

    Executes a MaverickAgent with the specified context.

    Fields:
        agent: Agent registry name
        context: Static dict or context builder name
        rollback: Optional action to call if workflow fails after this step
    """

    type: Literal[StepType.AGENT] = StepType.AGENT
    agent: str = Field(..., min_length=1)
    context: dict[str, Any] | str = Field(default_factory=dict)
    rollback: str | None = Field(
        None,
        description="Optional action to call for rollback/compensation",
    )


class GenerateStepRecord(StepRecord):
    """Text generation step (FR-009).

    Executes a GeneratorAgent to produce text content.

    Fields:
        generator: Generator registry name
        context: Static dict or context builder name
        rollback: Optional action to call if workflow fails after this step
    """

    type: Literal[StepType.GENERATE] = StepType.GENERATE
    generator: str = Field(..., min_length=1)
    context: dict[str, Any] | str = Field(default_factory=dict)
    rollback: str | None = Field(
        None,
        description="Optional action to call for rollback/compensation",
    )


class ValidateStepRecord(StepRecord):
    """Validation step with retry logic (FR-009, FR-010).

    Executes validation stages with automatic retry on failure.

    Fields:
        stages: Stage list or config key
        retry: Maximum retry attempts (0 = no retry, default from
            DEFAULTS.DEFAULT_RETRY_ATTEMPTS)
        on_failure: Optional step to execute before each retry
    """

    type: Literal[StepType.VALIDATE] = StepType.VALIDATE
    stages: list[str] | str
    retry: int = Field(default=DEFAULTS.DEFAULT_RETRY_ATTEMPTS, ge=0)
    on_failure: StepRecordUnion | None = None


class SubWorkflowStepRecord(StepRecord):
    """Sub-workflow invocation step (FR-009).

    Invokes another workflow as a nested step.

    Fields:
        workflow: Workflow registry name or file path
        inputs: Input values for the sub-workflow (may contain expressions)
    """

    type: Literal[StepType.SUBWORKFLOW] = StepType.SUBWORKFLOW
    workflow: str = Field(..., min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)


class BranchOptionRecord(BaseModel):
    """Single branch option in a branch step (FR-010).

    Represents one condition → step pair in a branching decision.

    Fields:
        when: Condition expression (evaluated in order)
        step: Step to execute if condition evaluates to true
    """

    when: str = Field(..., min_length=1)
    # Forward reference - resolved via model_rebuild after StepRecordUnion is defined
    step: StepRecordUnion


class BranchStepRecord(StepRecord):
    """Branching step with condition-based selection (FR-010).

    Executes the first matching branch based on condition evaluation.

    Fields:
        options: Ordered list of condition → step pairs
    """

    type: Literal[StepType.BRANCH] = StepType.BRANCH
    options: list[BranchOptionRecord] = Field(..., min_length=1)


class ParallelStepRecord(StepRecord):
    """Parallel execution step (FR-011).

    Executes multiple steps concurrently.

    Fields:
        steps: Steps to execute in parallel (names must be unique)
        for_each: Optional expression evaluating to a list for iteration.
            When provided, steps are executed once per item in the list,
            with the current item available as 'item' in expressions.
    """

    type: Literal[StepType.PARALLEL] = StepType.PARALLEL
    steps: list[StepRecordUnion] = Field(..., min_length=1)
    for_each: str | None = Field(
        None, description="Optional expression evaluating to a list for iteration"
    )

    @field_validator("steps")
    @classmethod
    def validate_unique_step_names(
        cls, v: list[StepRecordUnion]
    ) -> list[StepRecordUnion]:
        """Ensure all parallel step names are unique."""
        names = [step.name for step in v]
        if len(names) != len(set(names)):
            duplicates = {name for name in names if names.count(name) > 1}
            raise ValueError(f"Duplicate step names in parallel block: {duplicates}")
        return v


class CheckpointStepRecord(StepRecord):
    """Checkpoint marker step (FR-022).

    Marks a workflow state boundary for resumability. When a checkpoint
    step succeeds, workflow state (inputs, completed steps, outputs) is
    persisted to the checkpoint store. The workflow can later resume from
    this checkpoint, skipping already-completed steps.

    Fields:
        checkpoint_id: Optional unique identifier for this checkpoint.
            If omitted, defaults to the step name. Used as the key in
            the checkpoint store for saving/loading state.

    Usage:
        # Basic checkpoint (uses step name as ID)
        - name: after_implementation
          type: checkpoint

        # Explicit checkpoint ID (for multiple checkpoints with same name pattern)
        - name: checkpoint_stage_1
          type: checkpoint
          checkpoint_id: implementation_complete
    """

    type: Literal[StepType.CHECKPOINT] = StepType.CHECKPOINT
    checkpoint_id: str | None = Field(
        None,
        description="Unique checkpoint identifier (defaults to step name)",
    )


# =============================================================================
# Discriminated Union
# =============================================================================

# Forward reference resolution for recursive types (branch, parallel, validate)
# This allows BranchOptionRecord.step and ParallelStepRecord.steps to reference
# the full union type including themselves
StepRecordUnion = Annotated[
    PythonStepRecord
    | AgentStepRecord
    | GenerateStepRecord
    | ValidateStepRecord
    | SubWorkflowStepRecord
    | BranchStepRecord
    | ParallelStepRecord
    | CheckpointStepRecord,
    Field(discriminator="type"),
]

# Update forward references now that union is defined
BranchOptionRecord.model_rebuild()
BranchStepRecord.model_rebuild()
ParallelStepRecord.model_rebuild()
ValidateStepRecord.model_rebuild()


# =============================================================================
# Top-Level Workflow File
# =============================================================================


class WorkflowFile(BaseModel):
    """Top-level workflow file schema (FR-006).

    Defines a complete workflow with inputs, steps, and metadata.

    Validation Rules:
        - version: Must match pattern ^\\d+\\.\\d+$
        - name: Must match pattern ^[a-z][a-z0-9-]{0,63}$
        - steps: At least one step required; step names must be unique

    Convenience Methods:
        - to_dict(): Convert workflow to dictionary representation (FR-001)
        - to_yaml(): Convert workflow to YAML string (FR-002)
        - from_dict(): Create workflow from dictionary (FR-003)
        - from_yaml(): Create workflow from YAML string (FR-004)
    """

    version: str = Field(..., pattern=r"^\d+\.\d+$")
    name: str = Field(..., pattern=r"^[a-z][a-z0-9-]{0,63}$")
    description: str = ""
    inputs: dict[str, InputDefinition] = Field(default_factory=dict)
    steps: list[StepRecordUnion] = Field(..., min_length=1)

    @field_validator("steps")
    @classmethod
    def validate_unique_step_names(
        cls, v: list[StepRecordUnion]
    ) -> list[StepRecordUnion]:
        """Ensure all top-level step names are unique."""
        names = [step.name for step in v]
        if len(names) != len(set(names)):
            duplicates = {name for name in names if names.count(name) > 1}
            raise ValueError(f"Duplicate step names in workflow: {duplicates}")
        return v

    def to_dict(self) -> dict[str, Any]:
        """Convert workflow to dictionary representation (FR-001).

        Returns:
            Dictionary suitable for JSON/YAML serialization.

        Example:
            >>> workflow = WorkflowFile(version="1.0", name="test", steps=[...])
            >>> data = workflow.to_dict()
            >>> data["version"]
            "1.0"
        """
        # Import here to avoid circular imports
        from maverick.dsl.serialization.writer import WorkflowWriter

        return WorkflowWriter().to_dict(self)

    def to_yaml(self) -> str:
        """Convert workflow to YAML string (FR-002).

        Returns:
            YAML representation of the workflow.

        Example:
            >>> workflow = WorkflowFile(version="1.0", name="test", steps=[...])
            >>> yaml_str = workflow.to_yaml()
            >>> print(yaml_str)
            version: "1.0"
            name: test
            ...
        """
        # Import here to avoid circular imports
        from maverick.dsl.serialization.writer import WorkflowWriter

        return WorkflowWriter().to_yaml(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowFile:
        """Create workflow from dictionary (FR-003).

        Args:
            data: Dictionary containing workflow definition.

        Returns:
            Validated WorkflowFile instance.

        Raises:
            pydantic.ValidationError: If validation fails.

        Example:
            >>> data = {"version": "1.0", "name": "test", "steps": [...]}
            >>> workflow = WorkflowFile.from_dict(data)
        """
        return cls.model_validate(data)

    @classmethod
    def from_yaml(cls, yaml_content: str) -> WorkflowFile:
        """Create workflow from YAML string (FR-004).

        Args:
            yaml_content: YAML string containing workflow definition.

        Returns:
            Validated WorkflowFile instance.

        Raises:
            WorkflowParseError: If YAML parsing or validation fails.

        Example:
            >>> yaml_str = '''
            ... version: "1.0"
            ... name: test
            ... steps:
            ...   - name: step1
            ...     type: python
            ...     action: my_action
            ... '''
            >>> workflow = WorkflowFile.from_yaml(yaml_str)
        """
        # Import here to avoid circular imports
        from maverick.dsl.serialization.parser import parse_workflow

        return parse_workflow(yaml_content)


# =============================================================================
# Validation Result Models
# =============================================================================


@dataclass(frozen=True, slots=True)
class ValidationError:
    """Validation error with location context (FR-017).

    Represents a fatal validation error that prevents workflow execution.

    Fields:
        code: Error code (e.g., "E001", "E002")
        message: Human-readable error message
        path: JSON path to error location (e.g., "steps[2].agent")
        suggestion: Optional fix suggestion
    """

    code: str
    message: str
    path: str
    suggestion: str = ""


@dataclass(frozen=True, slots=True)
class ValidationWarning:
    """Validation warning (non-fatal) (FR-017).

    Represents a non-fatal issue that should be reviewed but doesn't
    prevent workflow execution.

    Fields:
        code: Warning code (e.g., "W001")
        message: Human-readable warning message
        path: JSON path to warning location
    """

    code: str
    message: str
    path: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of workflow file validation (FR-017).

    Aggregates all validation errors and warnings found during
    schema validation and semantic analysis.

    Fields:
        valid: True if no errors were found
        errors: Tuple of validation errors (empty if valid)
        warnings: Tuple of validation warnings (may be non-empty even if valid)
    """

    valid: bool
    errors: tuple[ValidationError, ...]
    warnings: tuple[ValidationWarning, ...]
