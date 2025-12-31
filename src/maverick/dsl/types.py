"""DSL type definitions for Maverick workflows.

This module defines foundational types used throughout the workflow DSL,
including step types and type aliases for context building.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maverick.dsl.context import WorkflowContext


class StepType(str, Enum):
    """Step type categorization.

    Defines the different types of steps that can be executed in a workflow.
    Each type corresponds to a specific execution pattern and result type.
    """

    PYTHON = "python"
    AGENT = "agent"
    GENERATE = "generate"
    VALIDATE = "validate"
    SUBWORKFLOW = "subworkflow"
    BRANCH = "branch"
    PARALLEL = "parallel"
    CHECKPOINT = "checkpoint"


# Type alias for context builder functions
# Context builders are async functions that accept a WorkflowContext and return
# a dictionary of values to be merged into the context for step execution
ContextBuilder = Callable[["WorkflowContext"], Awaitable[dict[str, Any]]]

# Type aliases for flow control
Predicate = Callable[["WorkflowContext"], bool | Awaitable[bool]]
RollbackAction = Callable[["WorkflowContext"], None | Awaitable[None]]
