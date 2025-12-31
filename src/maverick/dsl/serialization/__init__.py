"""Workflow serialization and deserialization support.

This module provides YAML/JSON serialization capabilities for Maverick DSL workflows.
It enables workflows to be defined in declarative configuration files and loaded
at runtime, supporting both human-authored and programmatically-generated workflow
definitions.

The serialization system includes:
- errors.py: Custom exceptions for serialization, parsing, and validation errors
- schema.py: Pydantic models defining the workflow file format
- parser.py: YAML/JSON parsing into WorkflowDefinition and StepDefinition objects
- writer.py: Serializing WorkflowDefinition objects back to YAML/JSON
- registry.py: Component registries for actions, generators, and validators

Example workflow file structure:
    name: my-workflow
    version: "1.0"
    steps:
      - id: step1
        type: agent
        agent: code_reviewer
        config:
          model: claude-opus-4-5
      - id: step2
        type: generate
        generator: commit_message
        depends_on: [step1]

All workflows are validated against the schema during parsing to ensure
structural correctness before execution.
"""

from __future__ import annotations

from maverick.dsl.errors import (
    DuplicateComponentError,
    ReferenceResolutionError,
    UnsupportedVersionError,
    WorkflowParseError,
    WorkflowSerializationError,
)
from maverick.dsl.serialization.editor import (
    EditorStepView,
    PropertySchema,
    StepAddedEvent,
    StepRemovedEvent,
    StepUpdatedEvent,
    WorkflowEditorInterface,
    WorkflowLoadedEvent,
    WorkflowValidatedEvent,
)
from maverick.dsl.serialization.executor import WorkflowFileExecutor
from maverick.dsl.serialization.parser import (
    extract_expressions,
    parse_workflow,
    parse_yaml,
    resolve_references,
    validate_schema,
    validate_version,
)
from maverick.dsl.serialization.registry import (
    ActionRegistry,
    ComponentRegistry,
    ContextBuilderRegistry,
    GeneratorRegistry,
    WorkflowRegistry,
    action_registry,
    component_registry,
    context_builder_registry,
    generator_registry,
    workflow_registry,
)
from maverick.dsl.serialization.schema import (
    AgentStepRecord,
    BranchOptionRecord,
    BranchStepRecord,
    GenerateStepRecord,
    InputDefinition,
    InputType,
    ParallelStepRecord,
    PythonStepRecord,
    StepRecord,
    StepRecordUnion,
    SubWorkflowStepRecord,
    ValidateStepRecord,
    ValidationError,
    ValidationResult,
    ValidationWarning,
    WorkflowFile,
)
from maverick.dsl.serialization.writer import WorkflowWriter
from maverick.dsl.types import StepType

__all__ = [
    # Enums
    "InputType",
    "StepType",
    # Input models
    "InputDefinition",
    # Step models
    "StepRecord",
    "PythonStepRecord",
    "AgentStepRecord",
    "GenerateStepRecord",
    "ValidateStepRecord",
    "SubWorkflowStepRecord",
    "BranchStepRecord",
    "BranchOptionRecord",
    "ParallelStepRecord",
    "StepRecordUnion",
    # Top-level workflow
    "WorkflowFile",
    # Validation results
    "ValidationError",
    "ValidationWarning",
    "ValidationResult",
    # Serialization errors
    "WorkflowSerializationError",
    "WorkflowParseError",
    "UnsupportedVersionError",
    "ReferenceResolutionError",
    "DuplicateComponentError",
    # Registries
    "ActionRegistry",
    "GeneratorRegistry",
    "ContextBuilderRegistry",
    "WorkflowRegistry",
    "ComponentRegistry",
    # Module-level singletons
    "action_registry",
    "generator_registry",
    "context_builder_registry",
    "workflow_registry",
    "component_registry",
    # Parser
    "parse_workflow",
    "parse_yaml",
    "validate_schema",
    "validate_version",
    "extract_expressions",
    "resolve_references",
    # Writer
    "WorkflowWriter",
    # Editor interface
    "WorkflowEditorInterface",
    "PropertySchema",
    "EditorStepView",
    "WorkflowLoadedEvent",
    "StepAddedEvent",
    "StepRemovedEvent",
    "StepUpdatedEvent",
    "WorkflowValidatedEvent",
    # Executor
    "WorkflowFileExecutor",
]
