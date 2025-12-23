"""Expression and condition evaluation for workflow execution.

This module provides utilities for evaluating expressions and conditional
statements during workflow execution.
"""

from __future__ import annotations

from typing import Any

from maverick.dsl.expressions import ExpressionEvaluator, parse_expression


def evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
    """Evaluate a conditional expression.

    Args:
        condition: Condition expression (e.g., "${{ inputs.dry_run }}").
        context: Execution context with inputs and steps.

    Returns:
        Boolean result of the condition.

    Raises:
        Exception: If expression evaluation fails.
    """
    # Create evaluator with current context
    evaluator = ExpressionEvaluator(
        inputs=context.get("inputs", {}),
        step_outputs=context.get("steps", {}),
        iteration_context=context.get("iteration", {}),
    )

    # Parse and evaluate the expression
    expr = parse_expression(condition)
    result = evaluator.evaluate(expr)

    # Convert to boolean (support truthy values)
    return bool(result)


def resolve_expressions(
    step: Any,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Resolve expressions in step inputs.

    Args:
        step: Step record containing inputs.
        context: Execution context with inputs and step outputs.

    Returns:
        Dictionary with resolved values.
    """
    from maverick.dsl.serialization.schema import (
        AgentStepRecord,
        GenerateStepRecord,
        PythonStepRecord,
        SubWorkflowStepRecord,
    )

    evaluator = ExpressionEvaluator(
        inputs=context.get("inputs", {}),
        step_outputs=context.get("steps", {}),
        iteration_context=context.get("iteration", {}),
    )

    resolved = {}

    if isinstance(step, PythonStepRecord):
        # Resolve kwargs (args are positional, less common in workflows)
        for key, value in step.kwargs.items():
            if isinstance(value, str) and "${{" in value:
                resolved[key] = evaluator.evaluate_string(value)
            else:
                resolved[key] = value
    elif isinstance(step, (AgentStepRecord, GenerateStepRecord)):
        # Resolve context dict or return as-is
        if isinstance(step.context, dict):
            for key, value in step.context.items():
                if isinstance(value, str) and "${{" in value:
                    resolved[key] = evaluator.evaluate_string(value)
                else:
                    resolved[key] = value
        else:
            # Context is a string reference (context builder name)
            resolved["_context_builder"] = step.context
    elif isinstance(step, SubWorkflowStepRecord):
        # Resolve inputs dict
        for key, value in step.inputs.items():
            if isinstance(value, str) and "${{" in value:
                resolved[key] = evaluator.evaluate_string(value)
            else:
                resolved[key] = value

    return resolved


def evaluate_for_each_expression(
    expression: str,
    context: dict[str, Any],
) -> list[Any] | tuple[Any, ...]:
    """Evaluate a for_each expression to get iteration items.

    Args:
        expression: Expression that should evaluate to a list/tuple.
        context: Execution context.

    Returns:
        List or tuple of items to iterate over.

    Raises:
        TypeError: If expression doesn't evaluate to a list or tuple.
    """
    evaluator = ExpressionEvaluator(
        inputs=context.get("inputs", {}),
        step_outputs=context.get("steps", {}),
        iteration_context=context.get("iteration", {}),
    )

    # Parse and evaluate the expression
    expr = parse_expression(expression)
    items = evaluator.evaluate(expr)

    # Validate that items is a list or tuple
    if not isinstance(items, (list, tuple)):
        raise TypeError(
            f"for_each expression must evaluate to a list or tuple, "
            f"got {type(items).__name__}"
        )

    return items
