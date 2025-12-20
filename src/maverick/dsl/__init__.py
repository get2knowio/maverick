"""Core Workflow DSL module for Maverick.

This module provides a declarative DSL for defining and executing workflows
as sequences of named steps. Workflows are defined using the @workflow decorator
and steps are created using the step() builder function.

Example:
    >>> from maverick.dsl import workflow, step, WorkflowEngine
    >>>
    >>> @workflow(name="example", description="Example workflow")
    ... def example_workflow(input_data: str):
    ...     result = yield step("process").python(
    ...         action=str.upper,
    ...         args=(input_data,),
    ...     )
    ...     return {"result": result}
    >>>
    >>> async def main():
    ...     engine = WorkflowEngine()
    ...     async for event in engine.execute(example_workflow, input_data="hello"):
    ...         print(event)
    ...     print(engine.get_result())
"""

from __future__ import annotations

# Builder
from maverick.dsl.builder import StepBuilder, branch, parallel, step

# Context
from maverick.dsl.context import WorkflowContext

# Decorator
from maverick.dsl.decorator import (
    WorkflowDefinition,
    WorkflowParameter,
    workflow,
)

# Engine
from maverick.dsl.engine import WorkflowEngine

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
    ConditionalStep,
    ErrorHandlerStep,
    GenerateStep,
    ParallelStep,
    PythonStep,
    RetryStep,
    RollbackStep,
    StepDefinition,
    SubWorkflowStep,
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
    "SubWorkflowStep",
    # Flow control steps (User Story 1)
    "ConditionalStep",
    "BranchStep",
    "BranchOption",
    "ParallelStep",
    # Reliability steps (User Story 2)
    "RetryStep",
    "ErrorHandlerStep",
    "RollbackStep",
    # Resumability steps (User Story 3)
    "CheckpointStep",
    # Builder
    "step",
    "branch",
    "parallel",
    "StepBuilder",
    # Engine
    "WorkflowEngine",
    # Events
    "StepStarted",
    "StepCompleted",
    "WorkflowStarted",
    "WorkflowCompleted",
    "RollbackStarted",
    "RollbackCompleted",
    "CheckpointSaved",
    "ProgressEvent",
    # Decorator
    "workflow",
    "WorkflowParameter",
    "WorkflowDefinition",
]
