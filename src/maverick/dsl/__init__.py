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
from maverick.dsl.builder import StepBuilder, step

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

# Events
from maverick.dsl.events import (
    ProgressEvent,
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)

# Results
from maverick.dsl.results import (
    StepResult,
    SubWorkflowInvocationResult,
    WorkflowResult,
)

# Steps
from maverick.dsl.steps import (
    AgentStep,
    GenerateStep,
    PythonStep,
    StepDefinition,
    SubWorkflowStep,
    ValidateStep,
)

# Types
from maverick.dsl.types import ContextBuilder, StepType

__all__: list[str] = [
    # Types
    "ContextBuilder",
    "StepType",
    # Context
    "WorkflowContext",
    # Results
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
    # Builder
    "step",
    "StepBuilder",
    # Engine
    "WorkflowEngine",
    # Events
    "StepStarted",
    "StepCompleted",
    "WorkflowStarted",
    "WorkflowCompleted",
    "ProgressEvent",
    # Decorator
    "workflow",
    "WorkflowParameter",
    "WorkflowDefinition",
]
