"""Expression parsing and evaluation for Maverick DSL.

This module provides string-based expression parsing and evaluation for the ${{ }}
syntax used throughout Maverick workflows. Expressions allow dynamic value resolution
at runtime, referencing workflow context, step outputs, and environment variables.

Expression Syntax
-----------------
Expressions are enclosed in ${{ }} delimiters and support:
- Context variable access: ${{ context.var_name }}
- Step output access: ${{ steps.step_id.output_key }}
- Nested property access: ${{ steps.analysis.result.recommendations[0] }}
- Environment variables: ${{ env.VAR_NAME }}
- String literals: ${{ "literal value" }}
- Numeric literals: ${{ 42 }}, ${{ 3.14 }}
- Boolean literals: ${{ true }}, ${{ false }}
- Null literal: ${{ null }}

Examples
--------
    # Reference a context variable
    ${{ context.branch_name }}

    # Access a step's output
    ${{ steps.analyze.result.file_count }}

    # Use environment variable
    ${{ env.GITHUB_TOKEN }}

    # Literal value
    ${{ "default-branch" }}

Module Structure
----------------
- parser.py: Expression AST parsing from ${{ }} strings
- evaluator.py: Runtime evaluation against WorkflowContext
- errors.py: Expression-specific error types (ExpressionSyntaxError, etc.)

The expression evaluator is stateless and thread-safe, operating purely on the
provided WorkflowContext at evaluation time.
"""

from __future__ import annotations

from maverick.dsl.expressions.errors import (
    ExpressionError,
    ExpressionErrorInfo,
    ExpressionEvaluationError,
    ExpressionSyntaxError,
)
from maverick.dsl.expressions.evaluator import ExpressionEvaluator
from maverick.dsl.expressions.parser import (
    BooleanExpression,
    Expression,
    ExpressionKind,
    TernaryExpression,
    extract_all,
    parse_expression,
    tokenize,
)

__all__: list[str] = [
    # Error types
    "ExpressionError",
    "ExpressionSyntaxError",
    "ExpressionEvaluationError",
    "ExpressionErrorInfo",
    # Parser types
    "Expression",
    "BooleanExpression",
    "TernaryExpression",
    "ExpressionKind",
    # Parser functions
    "tokenize",
    "parse_expression",
    "extract_all",
    # Evaluator
    "ExpressionEvaluator",
]
