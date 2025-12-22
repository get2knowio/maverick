"""Expression parser models and functions.

This module provides the core data structures for parsing template expressions
in the format ${{ ... }} used throughout workflow definitions.

Expression syntax:
- ${{ inputs.name }} - Reference to workflow input
- ${{ steps.step_id.output }} - Reference to step output
- ${{ item }} - Reference to current iteration item (for_each loops)
- ${{ index }} - Reference to current iteration index (for_each loops)
- ${{ not inputs.condition }} - Negated expression
- ${{ steps.x.output.field }} - Nested field access
- ${{ items[0] }} - Array index access (bracket notation)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from maverick.dsl.expressions.errors import ExpressionSyntaxError

__all__ = [
    "ExpressionKind",
    "Expression",
    "tokenize",
    "parse_expression",
    "extract_all",
]


class ExpressionKind(str, Enum):
    """Kind of expression reference."""

    INPUT_REF = "input_ref"  # ${{ inputs.name }}
    STEP_REF = "step_ref"  # ${{ steps.x.output }}
    ITEM_REF = "item_ref"  # ${{ item }} - current iteration item
    INDEX_REF = "index_ref"  # ${{ index }} - current iteration index


@dataclass(frozen=True, slots=True)
class Expression:
    """Parsed expression from ${{ ... }} syntax.

    Attributes:
        raw: Original expression string (including ${{ }} wrapper)
        kind: Type of expression (input_ref or step_ref)
        path: Access path as tuple (e.g., ("inputs", "name"))
        negated: True if expression is wrapped in 'not'

    Examples:
        >>> expr = Expression(
        ...     raw="${{ inputs.name }}",
        ...     kind=ExpressionKind.INPUT_REF,
        ...     path=("inputs", "name")
        ... )
        >>> expr.kind
        <ExpressionKind.INPUT_REF: 'input_ref'>
        >>> expr.path
        ('inputs', 'name')
    """

    raw: str
    kind: ExpressionKind
    path: tuple[str, ...]
    negated: bool = False


# Pattern for extracting ${{ ... }} expressions from text
_EXPRESSION_PATTERN = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")

# Pattern for tokenizing identifiers
_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def tokenize(expression: str) -> list[str]:
    """Tokenize expression string into tokens.

    Splits an expression into meaningful tokens: identifiers, operators,
    dots, brackets, and string literals.

    Args:
        expression: Expression string to tokenize (without ${{ }} wrapper)

    Returns:
        List of tokens

    Raises:
        ExpressionSyntaxError: For invalid syntax

    Examples:
        >>> tokenize("inputs.name")
        ['inputs', '.', 'name']
        >>> tokenize("not inputs.dry_run")
        ['not', 'inputs', '.', 'dry_run']
        >>> tokenize("items[0]")
        ['items', '[', '0', ']']
    """
    tokens: list[str] = []
    expr = expression.strip()
    i = 0

    while i < len(expr):
        char = expr[i]

        # Skip whitespace
        if char.isspace():
            i += 1
            continue

        # Dot operator
        if char == ".":
            if not tokens:
                raise ExpressionSyntaxError(
                    "Expression cannot start with a dot",
                    expression=expression,
                    position=i,
                )
            if tokens and tokens[-1] == ".":
                raise ExpressionSyntaxError(
                    "Invalid double dot in expression",
                    expression=expression,
                    position=i,
                )
            tokens.append(".")
            i += 1
            continue

        # Bracket notation
        if char == "[":
            tokens.append("[")
            i += 1
            # Look for bracket content
            if i >= len(expr):
                raise ExpressionSyntaxError(
                    "Unclosed bracket in expression",
                    expression=expression,
                    position=i - 1,
                )

            # Skip whitespace inside brackets
            while i < len(expr) and expr[i].isspace():
                i += 1

            if i >= len(expr):
                raise ExpressionSyntaxError(
                    "Unclosed bracket in expression",
                    expression=expression,
                    position=len(expr) - 1,
                )

            # Handle string keys in brackets
            if expr[i] in ("'", '"'):
                quote_char = expr[i]
                start = i
                i += 1
                while i < len(expr) and expr[i] != quote_char:
                    i += 1
                if i >= len(expr):
                    raise ExpressionSyntaxError(
                        "Unterminated string in bracket notation",
                        expression=expression,
                        position=start,
                    )
                tokens.append(expr[start : i + 1])  # Include quotes
                i += 1
            # Handle numeric indices
            elif expr[i].isdigit() or (
                expr[i] == "-" and i + 1 < len(expr) and expr[i + 1].isdigit()
            ):
                start = i
                if expr[i] == "-":
                    i += 1
                while i < len(expr) and expr[i].isdigit():
                    i += 1
                tokens.append(expr[start:i])
            else:
                raise ExpressionSyntaxError(
                    "Invalid content in bracket notation",
                    expression=expression,
                    position=i,
                )

            # Skip whitespace before closing bracket
            while i < len(expr) and expr[i].isspace():
                i += 1

            continue

        if char == "]":
            if "[" not in tokens:
                raise ExpressionSyntaxError(
                    "Unmatched closing bracket",
                    expression=expression,
                    position=i,
                )
            tokens.append("]")
            i += 1
            continue

        # Identifiers (including 'not' keyword)
        if char.isalpha() or char == "_":
            start = i
            while i < len(expr) and (expr[i].isalnum() or expr[i] == "_"):
                i += 1
            token = expr[start:i]
            tokens.append(token)
            continue

        # Invalid character
        raise ExpressionSyntaxError(
            f"Invalid character '{char}' in expression",
            expression=expression,
            position=i,
        )

    # Validate no trailing dot
    if tokens and tokens[-1] == ".":
        raise ExpressionSyntaxError(
            "Expression cannot end with a dot",
            expression=expression,
            position=len(expr) - 1,
        )

    # Check for unclosed brackets
    bracket_count = tokens.count("[") - tokens.count("]")
    if bracket_count > 0:
        raise ExpressionSyntaxError(
            "Unclosed bracket in expression",
            expression=expression,
            position=len(expr) - 1,
        )

    return tokens


def _strip_wrapper(expression: str) -> tuple[str, bool]:
    """Strip ${{ }} wrapper from expression.

    Args:
        expression: Expression string (may or may not have wrapper)

    Returns:
        Tuple of (inner expression, whether wrapper was present)
    """
    stripped = expression.strip()
    if stripped.startswith("${{") and stripped.endswith("}}"):
        inner = stripped[3:-2].strip()
        return inner, True
    return stripped, False


def parse_expression(expression: str) -> Expression:
    """Parse expression string into Expression AST.

    Converts expression strings into structured Expression objects,
    determining the expression kind (input or step reference) and
    extracting the access path.

    Args:
        expression: Expression string to parse (with or without ${{ }} wrapper)

    Returns:
        Parsed Expression object

    Raises:
        ExpressionSyntaxError: For invalid expression syntax

    Examples:
        >>> parse_expression("${{ inputs.name }}")  # doctest: +ELLIPSIS
        Expression(raw='${{ inputs.name }}', kind=..., path=..., negated=False)
        >>> parse_expression("not inputs.dry_run")  # doctest: +ELLIPSIS
        Expression(raw='not inputs.dry_run', kind=..., path=..., negated=True)
    """
    # Store original for raw field
    original = expression

    # Strip wrapper if present
    inner, had_wrapper = _strip_wrapper(expression)

    if not inner or inner.isspace():
        raise ExpressionSyntaxError(
            "Empty expression",
            expression=original,
            position=0,
        )

    # Tokenize
    tokens = tokenize(inner)

    if not tokens:
        raise ExpressionSyntaxError(
            "Empty expression",
            expression=original,
            position=0,
        )

    # Check for negation
    negated = False
    idx = 0
    if tokens[0] == "not":
        negated = True
        idx = 1
        if idx >= len(tokens):
            raise ExpressionSyntaxError(
                "'not' operator requires an expression",
                expression=original,
                position=len(inner) - 1,
            )

    # Build path from remaining tokens
    path: list[str] = []

    while idx < len(tokens):
        token = tokens[idx]

        if token == ".":
            # Skip dots in path building
            idx += 1
            continue

        if token == "[":
            # Handle bracket notation - add index to path
            idx += 1
            if idx >= len(tokens):
                raise ExpressionSyntaxError(
                    "Incomplete bracket notation",
                    expression=original,
                    position=len(inner) - 1,
                )
            bracket_content = tokens[idx]
            # Strip quotes from string keys
            if bracket_content.startswith(("'", '"')):
                bracket_content = bracket_content[1:-1]
            path.append(bracket_content)
            idx += 1
            # Skip closing bracket
            if idx < len(tokens) and tokens[idx] == "]":
                idx += 1
            continue

        if token == "]":
            # Skip standalone closing brackets (already handled)
            idx += 1
            continue

        # Regular identifier
        path.append(token)
        idx += 1

    if not path:
        raise ExpressionSyntaxError(
            "Expression has no valid path",
            expression=original,
            position=0,
        )

    # Determine expression kind based on first path element
    first_element = path[0]

    if first_element == "inputs":
        if len(path) < 2:
            raise ExpressionSyntaxError(
                "Input reference requires a property name (e.g., inputs.name)",
                expression=original,
                position=0,
            )
        kind = ExpressionKind.INPUT_REF
    elif first_element == "steps":
        if len(path) < 3:
            raise ExpressionSyntaxError(
                "Step reference requires step name and 'output' (e.g., steps.x.output)",
                expression=original,
                position=0,
            )
        # Validate 'output' is in the path (usually at index 2)
        if "output" not in path[2:]:
            raise ExpressionSyntaxError(
                "Step reference must include 'output' (e.g., steps.x.output)",
                expression=original,
                position=0,
            )
        kind = ExpressionKind.STEP_REF
    elif first_element == "item":
        # ${{ item }} or ${{ item.field }} for for_each iteration
        kind = ExpressionKind.ITEM_REF
    elif first_element == "index":
        # ${{ index }} for for_each iteration index (must be single element)
        if len(path) > 1:
            raise ExpressionSyntaxError(
                "Index reference must be a single element (e.g., ${{ index }})",
                expression=original,
                position=0,
            )
        kind = ExpressionKind.INDEX_REF
    else:
        raise ExpressionSyntaxError(
            f"Expression must start with 'inputs', 'steps', 'item', "
            f"or 'index', got '{first_element}'",
            expression=original,
            position=0,
        )

    return Expression(
        raw=original,
        kind=kind,
        path=tuple(path),
        negated=negated,
    )


def extract_all(text: str) -> list[Expression]:
    """Find and parse all expressions in text.

    Locates all ${{ ... }} expressions in a text string and parses them
    into Expression objects. Expressions are returned in the order they
    appear in the text.

    Args:
        text: Text containing zero or more expressions

    Returns:
        List of parsed Expression objects (empty if none found)

    Raises:
        ExpressionSyntaxError: For invalid expression syntax in any match

    Examples:
        >>> extract_all("Hello ${{ inputs.name }}")  # doctest: +ELLIPSIS
        [Expression(raw='${{ inputs.name }}', kind=..., path=..., negated=False)]
        >>> extract_all("No expressions here")
        []
    """
    if not text:
        return []

    expressions: list[Expression] = []

    for match in _EXPRESSION_PATTERN.finditer(text):
        full_match = match.group(0)
        inner = match.group(1)

        # Skip empty or whitespace-only expressions
        if not inner or inner.isspace():
            raise ExpressionSyntaxError(
                "Empty expression",
                expression=full_match,
                position=0,
            )

        try:
            expr = parse_expression(full_match)
            expressions.append(expr)
        except ExpressionSyntaxError:
            # Re-raise with context
            raise

    return expressions
