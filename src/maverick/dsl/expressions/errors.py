"""Expression-specific error types for the Maverick workflow DSL.

This module defines exceptions for expression parsing and evaluation,
following the pattern from maverick.dsl.errors.
"""

from __future__ import annotations

from dataclasses import dataclass

from maverick.exceptions import MaverickError


class ExpressionError(MaverickError):
    """Base exception for all expression-related errors.

    This is the parent class for all exceptions that can occur during
    expression parsing or evaluation. It provides context about the
    expression that failed.

    Attributes:
        message: Human-readable error message.
        expression: The expression that caused the error (if known).
    """

    def __init__(
        self,
        message: str,
        expression: str | None = None,
    ) -> None:
        """Initialize the ExpressionError.

        Args:
            message: Human-readable error message.
            expression: The expression that caused the error.
        """
        self.expression = expression
        super().__init__(message)


class ExpressionSyntaxError(ExpressionError):
    """Exception raised for syntax errors in ${{ }} expressions.

    Raised when an expression cannot be parsed due to invalid syntax,
    such as unmatched brackets, invalid operators, or malformed identifiers.

    Attributes:
        message: Human-readable error message.
        expression: The expression that failed to parse.
        position: Character position in the expression where the error occurred.
    """

    def __init__(
        self,
        message: str,
        expression: str,
        position: int = 0,
    ) -> None:
        """Initialize the ExpressionSyntaxError.

        Args:
            message: Human-readable error message.
            expression: The expression that failed to parse.
            position: Character position where the error occurred.
        """
        self.position = position
        # Format message with position indicator if available
        if position > 0 and expression:
            # Create a helpful error message with a caret pointing to the error
            error_line = f"{expression}\n{' ' * position}^"
            full_message = f"{message} at position {position}:\n{error_line}"
        else:
            full_message = f"{message}: {expression}"
        super().__init__(full_message, expression=expression)


class ExpressionEvaluationError(ExpressionError):
    """Exception raised for runtime evaluation errors in expressions.

    Raised when an expression parses correctly but fails during evaluation,
    such as accessing undefined variables, type mismatches, or division by zero.

    Attributes:
        message: Human-readable error message.
        expression: The expression that failed to evaluate.
        context_vars: Names of available variables in the context (for debugging).
    """

    def __init__(
        self,
        message: str,
        expression: str,
        context_vars: tuple[str, ...] = (),
    ) -> None:
        """Initialize the ExpressionEvaluationError.

        Args:
            message: Human-readable error message.
            expression: The expression that failed to evaluate.
            context_vars: Names of available variables in the context.
        """
        self.context_vars = context_vars
        # Add helpful context about available variables
        if context_vars:
            available = ", ".join(sorted(context_vars))
            full_message = (
                f"{message} in expression: {expression}\n"
                f"Available variables: {available}"
            )
        else:
            full_message = f"{message} in expression: {expression}"
        super().__init__(full_message, expression=expression)


@dataclass(frozen=True, slots=True)
class ExpressionErrorInfo:
    """Expression parsing or evaluation error information.

    This dataclass captures detailed information about an expression error
    for use in events and error reporting. It is immutable and uses slots
    for memory efficiency.

    Attributes:
        expression: The expression that failed.
        message: Human-readable error message.
        position: Character position in expression (0 if not applicable).
    """

    expression: str
    message: str
    position: int = 0
