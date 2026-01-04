"""Expression evaluator for the Maverick workflow DSL.

This module provides the ExpressionEvaluator class for evaluating parsed
expressions against a context containing workflow inputs and step outputs.

Expression evaluation:
- Input references: ${{ inputs.name }} -> context["inputs"]["name"]
- Step references: ${{ steps.x.output }} -> context["steps"]["x"]["output"]
- Nested field access: ${{ steps.x.output.field.nested }}
- Negation: ${{ not inputs.dry_run }} -> not context["inputs"]["dry_run"]
- Template substitution: "Hello ${{ inputs.name }}" -> "Hello John"
"""

from __future__ import annotations

from typing import Any

from maverick.dsl.expressions.errors import ExpressionEvaluationError
from maverick.dsl.expressions.parser import (
    AnyExpression,
    BooleanExpression,
    ExpressionKind,
    TernaryExpression,
    extract_all,
)

__all__ = ["ExpressionEvaluator"]


class ExpressionEvaluator:
    """Evaluates parsed expressions against a context.

    This class provides methods to evaluate Expression objects by looking up
    values in the provided inputs and step_outputs dictionaries. It supports
    nested field access, array indexing, and boolean negation.

    Attributes:
        inputs: Dictionary of workflow inputs (read-only).
        step_outputs: Dictionary of step outputs (read-only).

    Example:
        ```python
        evaluator = ExpressionEvaluator(
            inputs={"name": "John", "dry_run": False},
            step_outputs={"analyze": {"output": {"status": "success"}}},
        )

        # Evaluate single expression
        expr = parse_expression("${{ inputs.name }}")
        result = evaluator.evaluate(expr)  # "John"

        # Evaluate template string
        text = "Hello ${{ inputs.name }}, status: ${{ steps.analyze.output.status }}"
        result = evaluator.evaluate_string(text)  # "Hello John, status: success"
        ```
    """

    def __init__(
        self,
        inputs: dict[str, Any],
        step_outputs: dict[str, Any],
        iteration_context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the ExpressionEvaluator.

        Args:
            inputs: Dictionary of workflow inputs.
            step_outputs: Dictionary of step outputs (keyed by step name).
            iteration_context: Optional iteration context containing 'item' and 'index'
                for for_each loops.
        """
        self._inputs = inputs
        self._step_outputs = step_outputs
        self._iteration_context = iteration_context or {}

    def evaluate(self, expr: AnyExpression) -> Any:
        """Evaluate a single expression against the context.

        Resolves the expression path through the inputs or step_outputs,
        supporting nested field access and array indexing. Applies negation
        if the expression is negated. For BooleanExpression, evaluates all
        operands and combines them with the operator.

        Args:
            expr: Parsed Expression or BooleanExpression object to evaluate.

        Returns:
            The value at the expression path (any JSON-serializable type).

        Raises:
            ExpressionEvaluationError: If the path cannot be resolved
                (missing key, invalid index, type mismatch).

        Examples:
            >>> evaluator = ExpressionEvaluator(
            ...     inputs={"name": "Alice"},
            ...     step_outputs={},
            ... )
            >>> expr = parse_expression("${{ inputs.name }}")
            >>> evaluator.evaluate(expr)
            'Alice'
        """
        # Handle compound boolean expressions
        if isinstance(expr, BooleanExpression):
            return self._evaluate_boolean(expr)
        # Handle ternary conditional expressions
        if isinstance(expr, TernaryExpression):
            return self._evaluate_ternary(expr)
        # Determine the root context based on expression kind
        if expr.kind == ExpressionKind.INPUT_REF:
            root = self._inputs
            root_name = "inputs"
        elif expr.kind == ExpressionKind.STEP_REF:
            root = self._step_outputs
            root_name = "steps"
        elif expr.kind == ExpressionKind.ITEM_REF:
            # For item references, start with the item value from iteration context
            if "item" not in self._iteration_context:
                raise ExpressionEvaluationError(
                    "Item reference used outside of for_each loop",
                    expression=expr.raw,
                    context_vars=(),
                )
            # If path is just ("item",), return the item value directly
            if len(expr.path) == 1 and expr.path[0] == "item":
                value = self._iteration_context["item"]
                if expr.negated:
                    return not value
                return value
            # Otherwise, use item as root for nested access
            root = self._iteration_context["item"]
            root_name = "item"
        elif expr.kind == ExpressionKind.INDEX_REF:
            # For index references, return the index directly
            if "index" not in self._iteration_context:
                raise ExpressionEvaluationError(
                    "Index reference used outside of for_each loop",
                    expression=expr.raw,
                    context_vars=(),
                )
            # Index is a simple value, return it directly after negation check
            value = self._iteration_context["index"]
            if expr.negated:
                return not value
            return value
        else:
            raise ExpressionEvaluationError(
                f"Unknown expression kind: {expr.kind}",
                expression=expr.raw,
            )

        # Navigate through the path
        current = root
        for i, key in enumerate(expr.path):
            # Skip the root identifier (inputs/steps/item) - it's just metadata
            if i == 0 and key in ("inputs", "steps", "item", "index"):
                continue

            try:
                # Handle array/list index access
                if isinstance(current, (list, tuple)):
                    # Try to convert key to integer for list indexing
                    try:
                        index = int(key)
                        current = current[index]
                    except (ValueError, IndexError) as e:
                        # ValueError: key is not a valid integer
                        # IndexError: index out of bounds
                        available_keys = self._get_available_keys(root, root_name)
                        if isinstance(e, IndexError):
                            msg = (
                                f"List index {index} out of range "
                                f"(length: {len(current)})"
                            )
                            raise ExpressionEvaluationError(
                                msg,
                                expression=expr.raw,
                                context_vars=available_keys,
                            ) from e
                        msg = (
                            f"Cannot access key '{key}' on list "
                            f"(expected integer index)"
                        )
                        raise ExpressionEvaluationError(
                            msg,
                            expression=expr.raw,
                            context_vars=available_keys,
                        ) from e
                # Handle dictionary access
                elif isinstance(current, dict):
                    if key not in current:
                        available_keys = self._get_available_keys(root, root_name)
                        # Provide helpful error message
                        if i == 1 and root_name == "inputs":
                            raise ExpressionEvaluationError(
                                f"Input '{key}' not found",
                                expression=expr.raw,
                                context_vars=available_keys,
                            )
                        elif i == 1 and root_name == "steps":
                            raise ExpressionEvaluationError(
                                f"Step '{key}' not found",
                                expression=expr.raw,
                                context_vars=available_keys,
                            )
                        else:
                            raise ExpressionEvaluationError(
                                f"Key '{key}' not found in {'.'.join(expr.path[:i])}",
                                expression=expr.raw,
                                context_vars=available_keys,
                            )
                    current = current[key]
                # Handle string indexing (Python allows this)
                elif isinstance(current, str):
                    try:
                        index = int(key)
                        current = current[index]
                    except (ValueError, IndexError) as e:
                        available_keys = self._get_available_keys(root, root_name)
                        if isinstance(e, IndexError):
                            msg = (
                                f"String index {index} out of range "
                                f"(length: {len(current)})"
                            )
                            raise ExpressionEvaluationError(
                                msg,
                                expression=expr.raw,
                                context_vars=available_keys,
                            ) from e
                        raise ExpressionEvaluationError(
                            f"Cannot access key '{key}' on string",
                            expression=expr.raw,
                            context_vars=available_keys,
                        ) from e
                # Handle object attribute access (for dataclasses, etc.)
                elif hasattr(current, key):
                    current = getattr(current, key)
                else:
                    # Current value is not subscriptable (e.g., int, bool, None)
                    available_keys = self._get_available_keys(root, root_name)
                    raise ExpressionEvaluationError(
                        f"Cannot access key '{key}' on {type(current).__name__} value",
                        expression=expr.raw,
                        context_vars=available_keys,
                    )
            except ExpressionEvaluationError:
                # Re-raise our own exceptions
                raise
            except Exception as e:
                # Catch any unexpected errors and wrap them
                available_keys = self._get_available_keys(root, root_name)
                raise ExpressionEvaluationError(
                    f"Error accessing path element '{key}': {e}",
                    expression=expr.raw,
                    context_vars=available_keys,
                ) from e

        # Apply negation if needed
        if expr.negated:
            return not current

        return current

    def _evaluate_boolean(self, expr: BooleanExpression) -> Any:
        """Evaluate a compound boolean expression.

        This method implements Python-style short-circuit evaluation where
        the actual values are returned, not just True/False. This allows
        expressions like `inputs.x or steps.y.output` to return the value
        of the first truthy operand, not just True.

        Args:
            expr: BooleanExpression with 'and' or 'or' operator.

        Returns:
            For 'and': last value if all truthy, otherwise first falsy value.
            For 'or': first truthy value, or last value if all falsy.
        """
        if expr.operator == "and":
            # Python-style 'and': return last value if all truthy,
            # otherwise return first falsy value
            result: Any = True
            for operand in expr.operands:
                result = self.evaluate(operand)
                if not result:
                    return result
            return result
        elif expr.operator == "or":
            # Python-style 'or': return first truthy value,
            # or last value if all falsy
            result = None
            for operand in expr.operands:
                result = self.evaluate(operand)
                if result:
                    return result
            return result
        else:
            # Should not happen, but handle gracefully
            raise ExpressionEvaluationError(
                f"Unknown boolean operator: {expr.operator}",
                expression=expr.raw,
                context_vars=(),
            )

    def _evaluate_ternary(self, expr: TernaryExpression) -> Any:
        """Evaluate a ternary conditional expression.

        Evaluates the condition first, then returns the evaluated value of
        either value_if_true or value_if_false based on the condition result.
        Short-circuit evaluation is used: only the selected branch is evaluated.

        Args:
            expr: TernaryExpression with condition, value_if_true, value_if_false.

        Returns:
            The evaluated value of either value_if_true or value_if_false.
        """
        condition_result = self.evaluate(expr.condition)
        if condition_result:
            return self.evaluate(expr.value_if_true)
        else:
            return self.evaluate(expr.value_if_false)

    def evaluate_string(self, text: str) -> str:
        """Evaluate all expressions in a text string.

        Finds all ${{ ... }} expressions in the text, evaluates them,
        and substitutes the results back into the string. Non-string
        values are converted to strings using str().

        Args:
            text: Text containing zero or more expressions.

        Returns:
            Text with all expressions replaced by their evaluated values.

        Raises:
            ExpressionEvaluationError: If any expression cannot be evaluated.

        Examples:
            >>> evaluator = ExpressionEvaluator(
            ...     inputs={"name": "Bob", "count": 5},
            ...     step_outputs={},
            ... )
            >>> text = "Hello ${{ inputs.name }}, count: ${{ inputs.count }}"
            >>> evaluator.evaluate_string(text)
            'Hello Bob, count: 5'
        """
        if not text:
            return text

        # Extract all expressions from the text
        expressions = extract_all(text)

        # If no expressions found, return text as-is
        if not expressions:
            return text

        # Evaluate each expression and build replacement map
        replacements: dict[str, str] = {}
        for expr in expressions:
            if expr.raw not in replacements:
                # Evaluate the expression
                value = self.evaluate(expr)
                # Convert to string
                replacements[expr.raw] = str(value)

        # Perform replacements in the text
        result = text
        for expr_raw, value_str in replacements.items():
            result = result.replace(expr_raw, value_str)

        return result

    def _get_available_keys(
        self,
        root: dict[str, Any],
        root_name: str,
    ) -> tuple[str, ...]:
        """Get available keys from the root context for error messages.

        Args:
            root: The root dictionary (inputs or step_outputs).
            root_name: Name of the root ("inputs" or "steps").

        Returns:
            Tuple of available variable names in the format "root.key".
        """
        if not root:
            return ()

        keys: list[str] = []
        for key in sorted(root.keys()):
            keys.append(f"{root_name}.{key}")

        return tuple(keys)
