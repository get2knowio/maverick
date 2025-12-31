"""Core Workflow DSL module for Maverick.

This module provides the YAML-based serialization DSL for defining and executing
workflows. Workflows are defined in YAML files and executed using the
WorkflowFileExecutor.

Note: The Python decorator DSL (@workflow decorator) has been deprecated and removed.
Use YAML-based workflows with maverick.dsl.serialization instead.

Example:
    >>> from maverick.dsl.serialization import WorkflowFile, WorkflowFileExecutor
    >>> from maverick.dsl.serialization.registry import ComponentRegistry
    >>>
    >>> # Load workflow from YAML
    >>> workflow = WorkflowFile.from_yaml(yaml_content)
    >>>
    >>> # Execute with registry
    >>> registry = ComponentRegistry()
    >>> executor = WorkflowFileExecutor(workflow, registry)
    >>> async for event in executor.execute(inputs={"input": "value"}):
    ...     print(event)
"""

from __future__ import annotations

# Context
from maverick.dsl.context import WorkflowContext

# Errors (DSL-specific)
from maverick.dsl.errors import (
    CheckpointNotFoundError,
    InputMismatchError,
)
from maverick.dsl.errors import (
    DSLWorkflowError as WorkflowError,
)

# Events
from maverick.dsl.events import (
    CheckpointSaved,
    ProgressEvent,
    RollbackCompleted,
    RollbackStarted,
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)

# Results
from maverick.dsl.results import (
    BranchResult,
    ParallelResult,
    RollbackError,
    SkipMarker,
    StepResult,
    SubWorkflowInvocationResult,
    WorkflowResult,
)

# Steps
from maverick.dsl.steps import (
    AgentStep,
    BranchOption,
    BranchStep,
    CheckpointStep,
    GenerateStep,
    ParallelStep,
    PythonStep,
    StepDefinition,
    ValidateStep,
)

# Types
from maverick.dsl.types import ContextBuilder, Predicate, RollbackAction, StepType

__all__: list[str] = [
    # Types
    "ContextBuilder",
    "Predicate",
    "RollbackAction",
    "StepType",
    # Context
    "WorkflowContext",
    # Errors
    "WorkflowError",
    "CheckpointNotFoundError",
    "InputMismatchError",
    # Results
    "BranchResult",
    "ParallelResult",
    "RollbackError",
    "SkipMarker",
    "StepResult",
    "WorkflowResult",
    "SubWorkflowInvocationResult",
    # Steps
    "StepDefinition",
    "PythonStep",
    "AgentStep",
    "GenerateStep",
    "ValidateStep",
    # Flow control steps (User Story 1)
    "BranchStep",
    "BranchOption",
    "ParallelStep",
    # Resumability steps (User Story 3)
    "CheckpointStep",
    # Events
    "StepStarted",
    "StepCompleted",
    "WorkflowStarted",
    "WorkflowCompleted",
    "RollbackStarted",
    "RollbackCompleted",
    "CheckpointSaved",
    "ProgressEvent",
]
