"""Lark expression parser example snippets for Slidev presentation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lark import Lark, Token, Transformer, v_args

# =============================================================================
# 9.1 - Basic Lark Example
# =============================================================================


# The wrong way - regex-based parsing
def parse_expression_regex(text: str) -> tuple[str, ...] | None:
    """Parse expression using regex - DON'T DO THIS."""
    import re

    match = re.match(
        r"\$\{\{\s*(inputs|steps)\.(\w+)" r"(?:\.(\w+))?(?:\[(\d+)\])?\s*\}\}",
        text,
    )
    if match:
        return match.groups()
    return None


# The Lark way
SIMPLE_GRAMMAR = """
    start: "inputs" "." IDENTIFIER
    IDENTIFIER: /[a-zA-Z_]\\w*/
"""

simple_parser = Lark(SIMPLE_GRAMMAR)


# =============================================================================
# 9.3 - Calculator Grammar Example
# =============================================================================

CALC_GRAMMAR = """
    ?start: expr

    ?expr: term (("+" | "-") term)*
    ?term: factor (("*" | "/") factor)*
    ?factor: NUMBER
           | "(" expr ")"
           | "-" factor -> neg

    NUMBER: /\\d+(\\.\\d+)?/

    %ignore /\\s+/
"""

calc_parser = Lark(CALC_GRAMMAR)


# =============================================================================
# 9.4 - Parse Tree Example
# =============================================================================

GREETING_GRAMMAR = """
    start: greeting NAME
    greeting: "hello" | "hi"
    NAME: /[A-Za-z]+/
"""

greeting_parser = Lark(GREETING_GRAMMAR)


def demonstrate_parse_tree() -> None:
    """Show how to work with parse trees."""
    from lark import Tree

    tree = greeting_parser.parse("hello Alice")

    # Tree is the parsed structure
    print(f"Type: {type(tree)}")  # <class 'lark.Tree'>
    print(f"Data: {tree.data}")  # 'start'

    # Access children
    for child in tree.children:
        if isinstance(child, Tree):
            print(f"Rule: {child.data}")
            print(f"Children: {child.children}")
        elif isinstance(child, Token):
            print(f"Token: {child.type} = {child.value}")


# =============================================================================
# 9.5 - Transformer Example
# =============================================================================


@v_args(inline=True)
class CalcTransformer(Transformer[Token, float]):
    """Transform parse tree into computed values."""

    def NUMBER(self, token: Token) -> float:
        """Transform NUMBER terminal."""
        return float(token.value)

    def neg(self, value: float) -> float:
        """Handle negation: "-" factor -> neg."""
        return -value

    def factor(self, value: float) -> float:
        """Pass through factor."""
        return value

    def term(self, *values: float) -> float:
        """Multiply/divide terms (simplified - just multiply)."""
        result = values[0]
        for v in values[1:]:
            result *= v
        return result

    def expr(self, *values: float) -> float:
        """Add/subtract expressions (simplified - just add)."""
        return sum(values)


def demonstrate_transformer() -> None:
    """Show how transformers work."""
    tree = calc_parser.parse("2 + 3 * 4")

    transformer = CalcTransformer()
    result = transformer.transform(tree)

    print(f"Result: {result}")  # 14.0


# =============================================================================
# 9.7 - Expression Types (simplified from Maverick)
# =============================================================================


@dataclass(frozen=True)
class Expression:
    """Single reference expression."""

    raw: str
    kind: str  # "input_ref", "step_ref", etc.
    path: tuple[str, ...]
    negated: bool = False


@dataclass(frozen=True)
class BooleanExpression:
    """Compound boolean expression."""

    raw: str
    operator: str  # "and" or "or"
    operands: tuple[Expression, ...]


class ExpressionEvaluator:
    """Evaluates parsed expressions against a context."""

    def __init__(
        self,
        inputs: dict[str, Any],
        step_outputs: dict[str, Any],
    ) -> None:
        self._inputs = inputs
        self._step_outputs = step_outputs

    def evaluate(self, expr: Expression | BooleanExpression) -> Any:
        """Evaluate a single expression against the context."""
        if isinstance(expr, BooleanExpression):
            return self._evaluate_boolean(expr)

        # Navigate the path
        if expr.kind == "input_ref":
            value = self._navigate(self._inputs, expr.path[1:])
        elif expr.kind == "step_ref":
            value = self._navigate(self._step_outputs, expr.path[1:])
        else:
            raise ValueError(f"Unknown kind: {expr.kind}")

        return not value if expr.negated else value

    def _navigate(self, root: Any, path: tuple[str, ...]) -> Any:
        """Navigate a path through nested dicts/lists."""
        current = root
        for key in path:
            if isinstance(current, dict):
                current = current[key]
            elif isinstance(current, list):
                current = current[int(key)]
            else:
                raise KeyError(f"Cannot access {key} on {type(current)}")
        return current

    def _evaluate_boolean(self, expr: BooleanExpression) -> bool:
        """Evaluate a boolean expression."""
        results = [self.evaluate(op) for op in expr.operands]
        if expr.operator == "and":
            return all(results)
        return any(results)


# =============================================================================
# 9.8 - Template Interpolation
# =============================================================================


def extract_all(text: str) -> list[str]:
    """Find all ${{ }} expressions in text."""
    import re

    pattern = r"\$\{\{\s*(.*?)\s*\}\}"
    return re.findall(pattern, text)


def evaluate_string(evaluator: ExpressionEvaluator, text: str) -> str:
    """Evaluate all expressions in text and substitute."""
    import re

    def replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        # In real code, would parse and evaluate
        # This is simplified for demonstration
        if inner.startswith("inputs."):
            key = inner.split(".", 1)[1]
            return str(evaluator._inputs.get(key, ""))
        return match.group(0)

    return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", replace, text)


def demonstrate_template() -> None:
    """Show template string evaluation."""
    evaluator = ExpressionEvaluator(
        inputs={"name": "Bob", "count": 5},
        step_outputs={"step1": {"output": "done"}},
    )

    template = "User ${{ inputs.name }} has ${{ inputs.count }} items"
    result = evaluate_string(evaluator, template)
    print(result)  # "User Bob has 5 items"


if __name__ == "__main__":
    print("=== Parse Tree Demo ===")
    demonstrate_parse_tree()

    print("\n=== Transformer Demo ===")
    demonstrate_transformer()

    print("\n=== Template Demo ===")
    demonstrate_template()
