"""Step definition classes for the Workflow DSL.

This module contains all step types that can be used in workflows:
- PythonStep: Execute a Python callable
- AgentStep: Invoke a MaverickAgent
- GenerateStep: Invoke a GeneratorAgent
- ValidateStep: Run validation stages with retry logic
- SubWorkflowStep: Execute another workflow as a step
- ConditionalStep: Conditionally execute a step based on a predicate
- BranchStep: Select and execute one of multiple step options
- ParallelStep: Execute multiple steps (initially sequential)
- RetryStep: Wrap a step to add retry with exponential backoff
- ErrorHandlerStep: Wrap a step to add error handling/fallback
- RollbackStep: Wrap a step to register rollback action on success
- CheckpointStep: Mark a step as a checkpoint boundary for resumability
"""

from __future__ import annotations

from maverick.dsl.steps.agent import AgentStep
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.steps.branch import BranchOption, BranchStep
from maverick.dsl.steps.checkpoint import CheckpointStep
from maverick.dsl.steps.generate import GenerateStep
from maverick.dsl.steps.parallel import ParallelStep
from maverick.dsl.steps.python import PythonStep
from maverick.dsl.steps.validate import ValidateStep

__all__: list[str] = [
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
]
