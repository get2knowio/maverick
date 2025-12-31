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
- ${{ item[0] }} - Array index access (bracket notation)
- ${{ a and b }} - Boolean AND expression
- ${{ a or b }} - Boolean OR expression
- ${{ a if b else c }} - Ternary conditional expression

Implementation:
This module uses a Lark-based parser with a formal EBNF grammar (grammar.lark)
for robust expression parsing. The public API remains unchanged for backward
compatibility.

Grammar Specification:
For the complete BNF grammar, operator precedence, and detailed syntax rules,
see docs/expression-grammar.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from lark import Lark, Token, Transformer, UnexpectedCharacters, UnexpectedToken

from maverick.dsl.expressions.errors import ExpressionSyntaxError

__all__ = [
    "ExpressionKind",
    "Expression",
    "BooleanExpression",
    "TernaryExpression",
    "AnyExpression",
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


@dataclass(frozen=True, slots=True)
class BooleanExpression:
    """Compound boolean expression combining multiple expressions with and/or.

    Attributes:
        raw: Original expression string (including ${{ }} wrapper)
        operator: Boolean operator ('and' or 'or')
        operands: Tuple of Expression, BooleanExpression, or TernaryExpression objects
    """

    raw: str
    operator: Literal["and", "or"]
    operands: tuple[Expression | BooleanExpression | TernaryExpression, ...]


@dataclass(frozen=True, slots=True)
class TernaryExpression:
    """Ternary conditional expression: value_if_true if condition else value_if_false.

    This enables inline value selection based on conditions within DSL expressions.

    Attributes:
        raw: Original expression string (including ${{ }} wrapper)
        condition: The condition expression to evaluate
        value_if_true: Expression to return if condition is truthy
        value_if_false: Expression to return if condition is falsy

    Examples:
        >>> # Select between two values based on a condition
        >>> # ${{ inputs.title if inputs.title else steps.generate_title.output }}
        >>> expr = TernaryExpression(
        ...     raw="${{ a if b else c }}",
        ...     condition=parse_expression("b"),
        ...     value_if_true=parse_expression("a"),
        ...     value_if_false=parse_expression("c"),
        ... )  # doctest: +SKIP
    """

    raw: str
    condition: AnyExpression
    value_if_true: AnyExpression
    value_if_false: AnyExpression


# Type alias for any expression
AnyExpression = Expression | BooleanExpression | TernaryExpression


# Load grammar from file
_GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"
_GRAMMAR = _GRAMMAR_PATH.read_text()

# Create Lark parser instance (cached)
_parser = Lark(
    _GRAMMAR,
    parser="lalr",
    start="start",
    propagate_positions=True,
)

# Pattern for extracting ${{ ... }} expressions from text
_EXPRESSION_PATTERN = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")


class _ExpressionTransformer(Transformer[Token, object]):
    """Transform parse tree into Expression or BooleanExpression objects."""

    def __init__(self, raw: str) -> None:
        super().__init__()
        self._raw = raw

    def start(self, items: list[AnyExpression]) -> AnyExpression:
        """Return the top-level expression.

        Grammar: start: ternary_expr
        The ternary_expr handles the expression hierarchy.
        """
        return items[0]

    def ternary(self, items: list[AnyExpression]) -> TernaryExpression:
        """Handle ternary expression: value_if_true if condition else value_if_false.

        Grammar: bool_expr "if" bool_expr "else" ternary_expr -> ternary
        - items[0] = value_if_true (the expression before 'if')
        - items[1] = condition (between 'if' and 'else')
        - items[2] = value_if_false (after 'else')
        """
        return TernaryExpression(
            raw=self._raw,
            condition=items[1],
            value_if_true=items[0],
            value_if_false=items[2],
        )

    def bool_expr(self, items: list[AnyExpression]) -> AnyExpression:
        """Handle OR boolean expressions.

        Grammar: ?bool_expr: bool_term (OR bool_term)*
        """
        if len(items) == 1:
            return items[0]
        return BooleanExpression(
            raw=self._raw,
            operator="or",
            operands=tuple(items),
        )

    def bool_term(self, items: list[AnyExpression]) -> AnyExpression:
        """Handle AND boolean expressions.

        Grammar: ?bool_term: unary_expr (AND unary_expr)*
        """
        if len(items) == 1:
            return items[0]
        return BooleanExpression(
            raw=self._raw,
            operator="and",
            operands=tuple(items),
        )

    def negated_expr(self, items: list[object]) -> Expression:
        """Handle negated expressions (not X).

        Grammar: ?unary_expr: negation unary_expr -> negated_expr
        """
        # The expression to negate is the last item
        expr = items[-1]
        if isinstance(expr, Expression):
            return Expression(
                raw=self._raw,
                kind=expr.kind,
                path=expr.path,
                negated=True,
            )
        # For negated boolean expressions, this is not currently supported
        raise ExpressionSyntaxError(
            "Cannot negate compound boolean expressions",
            expression=self._raw,
            position=0,
        )

    def negation(self, items: list[object]) -> str:
        """Handle negation keyword."""
        return "not"

    def reference(self, items: list[Expression]) -> Expression:
        """Pass through reference expression."""
        return items[0]

    def input_ref(self, items: list[str]) -> Expression:
        """Handle input reference."""
        return Expression(
            raw=self._raw,
            kind=ExpressionKind.INPUT_REF,
            path=tuple(["inputs"] + list(items)),
            negated=False,
        )

    def step_ref(self, items: list[str]) -> Expression:
        """Handle step reference.

        Grammar: step_ref: "steps" "." IDENTIFIER "." "output" accessor*
        items[0] is the step_id (IDENTIFIER), items[1:] are accessors
        """
        if items:
            accessors = [str(x) for x in items[1:]]
            path = ["steps", str(items[0]), "output"] + accessors
        else:
            path = ["steps", "output"]
        return Expression(
            raw=self._raw,
            kind=ExpressionKind.STEP_REF,
            path=tuple(path),
            negated=False,
        )

    def item_ref(self, items: list[str]) -> Expression:
        """Handle item reference."""
        return Expression(
            raw=self._raw,
            kind=ExpressionKind.ITEM_REF,
            path=tuple(["item"] + list(items)),
            negated=False,
        )

    def index_ref(self, items: list[object]) -> Expression:
        """Handle index reference."""
        return Expression(
            raw=self._raw,
            kind=ExpressionKind.INDEX_REF,
            path=("index",),
            negated=False,
        )

    def accessor(self, items: list[str]) -> str:
        """Pass through accessor value."""
        return items[0]

    def dot_accessor(self, items: list[Token]) -> str:
        """Extract identifier from dot accessor."""
        return str(items[0])

    def bracket_accessor(self, items: list[str]) -> str:
        """Extract content from bracket accessor."""
        return items[0]

    def bracket_content(self, items: list[Token]) -> str:
        """Extract bracket content value."""
        value = str(items[0])
        # Strip quotes from string values
        if value.startswith(("'", '"')):
            return value[1:-1]
        return value

    def IDENTIFIER(self, token: Token) -> str:  # noqa: N802
        """Pass through identifier token."""
        return str(token)

    def INT(self, token: Token) -> str:  # noqa: N802
        """Pass through integer token as string."""
        return str(token)

    def STRING(self, token: Token) -> str:  # noqa: N802
        """Pass through string token."""
        return str(token)


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


def _validate_expression(expr: Expression, original: str) -> None:
    """Validate expression-specific rules after parsing.

    Args:
        expr: Parsed expression to validate
        original: Original expression string for error messages

    Raises:
        ExpressionSyntaxError: For validation failures
    """
    if expr.kind == ExpressionKind.INPUT_REF:
        if len(expr.path) < 2:
            raise ExpressionSyntaxError(
                "Input reference requires a property name (e.g., inputs.name)\n"
                "Grammar: input-ref ::= 'inputs' accessor+\n"
                "See docs/expression-grammar.md for details",
                expression=original,
                position=0,
            )

    elif expr.kind == ExpressionKind.STEP_REF:
        if len(expr.path) < 3:
            raise ExpressionSyntaxError(
                "Step reference requires step name and 'output' "
                "(e.g., steps.x.output)\n"
                "Grammar: step-ref ::= 'steps' '.' identifier '.' 'output' "
                "accessor*\n"
                "See docs/expression-grammar.md for details",
                expression=original,
                position=0,
            )
        # 'output' is guaranteed by grammar at position 2

    elif expr.kind == ExpressionKind.INDEX_REF and len(expr.path) > 1:
        raise ExpressionSyntaxError(
            "Index reference must be a single element (e.g., ${{ index }})\n"
            "Grammar: index-ref ::= 'index' (no accessors allowed)\n"
            "See docs/expression-grammar.md for details",
            expression=original,
            position=0,
        )


def _validate_boolean_expression(expr: BooleanExpression, original: str) -> None:
    """Validate a boolean expression by validating all its operands.

    Args:
        expr: BooleanExpression to validate
        original: Original expression string for error messages

    Raises:
        ExpressionSyntaxError: For validation failures
    """
    for operand in expr.operands:
        if isinstance(operand, Expression):
            _validate_expression(operand, original)
        elif isinstance(operand, BooleanExpression):
            _validate_boolean_expression(operand, original)
        elif isinstance(operand, TernaryExpression):
            _validate_ternary_expression(operand, original)


def _validate_ternary_expression(expr: TernaryExpression, original: str) -> None:
    """Validate a ternary expression by validating all its sub-expressions.

    Args:
        expr: TernaryExpression to validate
        original: Original expression string for error messages

    Raises:
        ExpressionSyntaxError: For validation failures
    """
    for sub_expr in (expr.condition, expr.value_if_true, expr.value_if_false):
        if isinstance(sub_expr, Expression):
            _validate_expression(sub_expr, original)
        elif isinstance(sub_expr, BooleanExpression):
            _validate_boolean_expression(sub_expr, original)
        elif isinstance(sub_expr, TernaryExpression):
            _validate_ternary_expression(sub_expr, original)


def parse_expression(expression: str) -> AnyExpression:
    """Parse expression string into Expression, BooleanExpression, or TernaryExpression.

    Converts expression strings into structured AST objects, determining the
    expression kind (input, step, item, or index reference) and extracting the
    access path. Compound expressions using 'and'/'or' operators return
    BooleanExpression objects. Ternary conditionals return TernaryExpression objects.

    Args:
        expression: Expression string to parse (with or without ${{ }} wrapper)

    Returns:
        Parsed Expression, BooleanExpression, or TernaryExpression object

    Raises:
        ExpressionSyntaxError: For invalid expression syntax

    Examples:
        >>> parse_expression("${{ inputs.name }}")  # doctest: +ELLIPSIS
        Expression(raw='${{ inputs.name }}', kind=..., path=..., negated=False)
        >>> parse_expression("not inputs.dry_run")  # doctest: +ELLIPSIS
        Expression(raw='not inputs.dry_run', kind=..., path=..., negated=True)
        >>> parse_expression("inputs.a if inputs.b else inputs.c")  # doctest: +ELLIPSIS
        TernaryExpression(raw='inputs.a if inputs.b else inputs.c', ...)
    """
    # Store original for raw field
    original = expression

    # Strip wrapper if present
    inner, _ = _strip_wrapper(expression)

    if not inner or inner.isspace():
        raise ExpressionSyntaxError(
            "Empty expression\n"
            "Expression must be one of: input-ref, step-ref, item-ref, or index-ref\n"
            "See docs/expression-grammar.md for syntax details",
            expression=original,
            position=0,
        )

    # Check for double negation before parsing
    if inner.startswith("not "):
        after_not = inner[4:].lstrip()
        if after_not.startswith("not "):
            raise ExpressionSyntaxError(
                "Double negation is not allowed\n"
                "Grammar allows only single 'not' prefix\n"
                "See docs/expression-grammar.md for operator details",
                expression=original,
                position=0,
            )

    try:
        tree = _parser.parse(inner)
        transformer = _ExpressionTransformer(original)
        result = transformer.transform(tree)

        if not isinstance(result, (Expression, BooleanExpression, TernaryExpression)):
            # Should not happen, but handle gracefully
            raise ExpressionSyntaxError(
                "Failed to parse expression",
                expression=original,
                position=0,
            )

        # Validate expression-specific rules
        if isinstance(result, Expression):
            _validate_expression(result, original)
        elif isinstance(result, BooleanExpression):
            _validate_boolean_expression(result, original)
        elif isinstance(result, TernaryExpression):
            _validate_ternary_expression(result, original)

        return result

    except UnexpectedCharacters as e:
        # Map Lark position to meaningful error
        pos = e.column - 1 if e.column else 0
        char = e.char if hasattr(e, "char") else "unknown"

        # Provide specific error messages for common cases
        # Check if this is index.field (index cannot have accessors)
        if inner.startswith("index.") or inner.startswith("index["):
            raise ExpressionSyntaxError(
                "Index reference must be a single element (e.g., ${{ index }})\n"
                "Grammar: index-ref ::= 'index' (no accessors allowed)\n"
                "See docs/expression-grammar.md for details",
                expression=original,
                position=pos,
            ) from e

        raise ExpressionSyntaxError(
            f"Invalid character '{char}' in expression\n"
            "Expression syntax: ${{{{ reference }}}}\n"
            "See docs/expression-grammar.md for valid syntax",
            expression=original,
            position=pos,
        ) from e

    except UnexpectedToken as e:
        pos = e.column - 1 if e.column else 0

        # Provide specific error messages for common cases
        # Check if this is index.field (index cannot have accessors)
        if inner.startswith("index.") or inner.startswith("index["):
            raise ExpressionSyntaxError(
                "Index reference must be a single element (e.g., ${{ index }})\n"
                "Grammar: index-ref ::= 'index' (no accessors allowed)\n"
                "See docs/expression-grammar.md for details",
                expression=original,
                position=pos,
            ) from e

        # Check if the expression starts with an invalid prefix
        first_parts = inner.split(".")[0].split() if inner else []
        first_word = first_parts[0] if first_parts else ""
        if first_word and first_word not in ("inputs", "steps", "item", "index", "not"):
            raise ExpressionSyntaxError(
                f"Expression must start with 'inputs', 'steps', 'item', "
                f"or 'index', got '{first_word}'\n"
                f"Grammar: reference ::= input-ref | step-ref | item-ref | index-ref\n"
                f"See docs/expression-grammar.md for valid prefixes",
                expression=original,
                position=0,
            ) from e

        # Check if this is a step reference without 'output'
        if inner.startswith("steps.") and ".output" not in inner:
            parts = inner.split(".")
            if len(parts) == 2:
                raise ExpressionSyntaxError(
                    "Step reference requires step name and 'output' "
                    "(e.g., steps.x.output)\n"
                    "Grammar: step-ref ::= 'steps' '.' identifier '.' 'output' "
                    "accessor*\n"
                    "See docs/expression-grammar.md for details",
                    expression=original,
                    position=pos,
                ) from e
            elif len(parts) >= 3 and parts[2] != "output":
                raise ExpressionSyntaxError(
                    "Step reference must include 'output' "
                    "(e.g., steps.x.output)\n"
                    "The keyword 'output' is required between step ID and "
                    "field accessors\n"
                    "See docs/expression-grammar.md for details",
                    expression=original,
                    position=pos,
                ) from e

        raise ExpressionSyntaxError(
            "Unexpected token in expression\n"
            "Check expression syntax against grammar specification\n"
            "See docs/expression-grammar.md for valid syntax",
            expression=original,
            position=pos,
        ) from e

    except Exception as e:
        # Catch any other Lark exceptions
        error_msg = str(e) if str(e) else "Invalid expression syntax"
        raise ExpressionSyntaxError(
            f"{error_msg}\n"
            "Check expression syntax against grammar specification\n"
            "See docs/expression-grammar.md for valid syntax",
            expression=original,
            position=0,
        ) from e


def extract_all(text: str) -> list[AnyExpression]:
    """Find and parse all expressions in text.

    Locates all ${{ ... }} expressions in a text string and parses them
    into Expression or BooleanExpression objects. Expressions are returned
    in the order they appear in the text.

    Args:
        text: Text containing zero or more expressions

    Returns:
        List of parsed Expression/BooleanExpression objects (empty if none found)

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

    expressions: list[AnyExpression] = []

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
