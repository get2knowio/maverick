"""Expression and condition evaluation for workflow execution.

This module provides utilities for evaluating expressions and conditional
statements during workflow execution.
"""

from __future__ import annotations

from typing import Any

from maverick.dsl.context import WorkflowContext
from maverick.dsl.expressions import ExpressionEvaluator, extract_all, parse_expression


def _get_step_outputs_dict(context: WorkflowContext) -> dict[str, Any]:
    """Convert WorkflowContext.results to step_outputs dict for ExpressionEvaluator.

    ExpressionEvaluator expects step_outputs in the format:
        {"step_name": {"output": <value>}}

    Args:
        context: WorkflowContext with results dict.

    Returns:
        Dictionary in the format expected by ExpressionEvaluator.
    """
    step_outputs = {}
    for step_name, step_result in context.results.items():
        step_outputs[step_name] = {"output": step_result.output}
    return step_outputs


def _resolve_value(value: Any, evaluator: ExpressionEvaluator) -> Any:
    """Resolve a value that might contain expressions.

    If the value is a string with exactly one expression that spans the entire
    string, evaluate it directly to preserve the type. Otherwise, use
    evaluate_string to do template substitution.

    Args:
        value: Value to resolve (any type).
        evaluator: Expression evaluator to use.

    Returns:
        Resolved value with proper type preservation.
    """
    if not isinstance(value, str):
        return value

    if "${{" not in value:
        return value

    # Check if this is a single expression that spans the entire string
    expressions = extract_all(value)

    # If there's exactly one expression and it matches the entire string,
    # evaluate directly
    if len(expressions) == 1 and expressions[0].raw == value:
        return evaluator.evaluate(expressions[0])

    # Otherwise, do template string substitution
    return evaluator.evaluate_string(value)


def evaluate_condition(condition: str, context: WorkflowContext) -> bool:
    """Evaluate a conditional expression.

    Args:
        condition: Condition expression (e.g., "${{ inputs.dry_run }}").
        context: WorkflowContext with inputs and step results.

    Returns:
        Boolean result of the condition.

    Raises:
        Exception: If expression evaluation fails.
    """
    # Create evaluator with current context
    evaluator = ExpressionEvaluator(
        inputs=context.inputs,
        step_outputs=_get_step_outputs_dict(context),
        iteration_context=context.iteration_context,
    )

    # Parse and evaluate the expression
    expr = parse_expression(condition)
    result = evaluator.evaluate(expr)

    # Convert to boolean (support truthy values)
    return bool(result)


def resolve_expressions(
    step: Any,
    context: WorkflowContext,
) -> dict[str, Any]:
    """Resolve expressions in step inputs.

    Args:
        step: Step record containing inputs.
        context: WorkflowContext with inputs and step results.

    Returns:
        Dictionary with resolved values.
    """
    from maverick.dsl.serialization.schema import (
        AgentStepRecord,
        CheckpointStepRecord,
        GenerateStepRecord,
        PythonStepRecord,
        SubWorkflowStepRecord,
        ValidateStepRecord,
    )

    evaluator = ExpressionEvaluator(
        inputs=context.inputs,
        step_outputs=_get_step_outputs_dict(context),
        iteration_context=context.iteration_context,
    )

    resolved = {}

    if isinstance(step, PythonStepRecord):
        # Resolve kwargs (args are positional, less common in workflows)
        for key, value in step.kwargs.items():
            resolved[key] = _resolve_value(value, evaluator)
    elif isinstance(step, (AgentStepRecord, GenerateStepRecord)):
        # Resolve context dict or return as-is
        if isinstance(step.context, dict):
            for key, value in step.context.items():
                resolved[key] = _resolve_value(value, evaluator)
        else:
            # Context is a string reference (context builder name)
            resolved["_context_builder"] = step.context
    elif isinstance(step, SubWorkflowStepRecord):
        # Resolve inputs dict
        for key, value in step.inputs.items():
            resolved[key] = _resolve_value(value, evaluator)
    elif isinstance(step, ValidateStepRecord):
        # Resolve stages (can be list or expression string)
        resolved["stages"] = _resolve_value(step.stages, evaluator)
    elif isinstance(step, CheckpointStepRecord) and step.checkpoint_id:
        # Resolve checkpoint_id (may contain expressions like ${{ index }})
        resolved["checkpoint_id"] = _resolve_value(step.checkpoint_id, evaluator)

    return resolved


def evaluate_for_each_expression(
    expression: str,
    context: WorkflowContext,
) -> list[Any] | tuple[Any, ...]:
    """Evaluate a for_each expression to get iteration items.

    Args:
        expression: Expression that should evaluate to a list/tuple.
        context: WorkflowContext with inputs and step results.

    Returns:
        List or tuple of items to iterate over.

    Raises:
        TypeError: If expression doesn't evaluate to a list or tuple.
    """
    evaluator = ExpressionEvaluator(
        inputs=context.inputs,
        step_outputs=_get_step_outputs_dict(context),
        iteration_context=context.iteration_context,
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
