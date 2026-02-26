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
    LOOP = "loop"
    CHECKPOINT = "checkpoint"


class StepMode(str, Enum):
    """Execution mode for a workflow step.

    Determines whether a step runs deterministically (fixed logic, no LLM
    involvement) or is delegated to an AI agent for judgment-based execution.

    Attributes:
        DETERMINISTIC: Step executes fixed, repeatable logic (e.g., Python
            functions, shell commands, validation scripts).
        AGENT: Step is delegated to an AI agent that applies judgment
            (e.g., code generation, review, refactoring).
    """

    DETERMINISTIC = "deterministic"
    AGENT = "agent"


class AutonomyLevel(str, Enum):
    """Agent independence level for workflow steps.

    Controls how much independence an agent has within a step, ordered
    from most restrictive to most autonomous.

    Attributes:
        OPERATOR: Deterministic only. Step follows exact instructions
            with no agent judgment.
        COLLABORATOR: Agent proposes changes, code validates before
            applying.
        CONSULTANT: Agent executes autonomously, code verifies after
            completion.
        APPROVER: Agent is fully autonomous, escalates only on
            exceptions.
    """

    OPERATOR = "operator"
    COLLABORATOR = "collaborator"
    CONSULTANT = "consultant"
    APPROVER = "approver"


# Type alias for context builder functions
# Context builders are async functions that accept a WorkflowContext and return
# a dictionary of values to be merged into the context for step execution
ContextBuilder = Callable[["WorkflowContext"], Awaitable[dict[str, Any]]]

# Type aliases for flow control
Predicate = Callable[["WorkflowContext"], bool | Awaitable[bool]]
RollbackAction = Callable[["WorkflowContext"], None | Awaitable[None]]
