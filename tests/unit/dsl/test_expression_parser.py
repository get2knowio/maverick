"""Tests for expression parser models.

This module tests the basic structure and functionality of the Expression
dataclass and ExpressionKind enum. Full parsing logic will be tested when
implemented in later tasks.
"""

from __future__ import annotations

import pytest

from maverick.dsl.expressions import (
    Expression,
    ExpressionKind,
    extract_all,
    parse_expression,
    tokenize,
)


class TestExpressionKind:
    """Test ExpressionKind enum."""

    def test_enum_values(self) -> None:
        """Verify enum has expected values."""
        assert ExpressionKind.INPUT_REF == "input_ref"
        assert ExpressionKind.STEP_REF == "step_ref"
        assert ExpressionKind.ITEM_REF == "item_ref"
        assert ExpressionKind.INDEX_REF == "index_ref"

    def test_enum_members(self) -> None:
        """Verify all enum members are present."""
        members = list(ExpressionKind)
        assert len(members) == 4
        assert ExpressionKind.INPUT_REF in members
        assert ExpressionKind.STEP_REF in members
        assert ExpressionKind.ITEM_REF in members
        assert ExpressionKind.INDEX_REF in members


class TestExpression:
    """Test Expression dataclass."""

    def test_create_input_ref(self) -> None:
        """Create an input reference expression."""
        expr = Expression(
            raw="${{ inputs.name }}",
            kind=ExpressionKind.INPUT_REF,
            path=("inputs", "name"),
        )

        assert expr.raw == "${{ inputs.name }}"
        assert expr.kind == ExpressionKind.INPUT_REF
        assert expr.path == ("inputs", "name")
        assert expr.negated is False

    def test_create_step_ref(self) -> None:
        """Create a step reference expression."""
        expr = Expression(
            raw="${{ steps.analyze.output }}",
            kind=ExpressionKind.STEP_REF,
            path=("steps", "analyze", "output"),
        )

        assert expr.raw == "${{ steps.analyze.output }}"
        assert expr.kind == ExpressionKind.STEP_REF
        assert expr.path == ("steps", "analyze", "output")
        assert expr.negated is False

    def test_create_negated_expression(self) -> None:
        """Create a negated expression."""
        expr = Expression(
            raw="${{ not inputs.skip }}",
            kind=ExpressionKind.INPUT_REF,
            path=("inputs", "skip"),
            negated=True,
        )

        assert expr.raw == "${{ not inputs.skip }}"
        assert expr.kind == ExpressionKind.INPUT_REF
        assert expr.path == ("inputs", "skip")
        assert expr.negated is True

    def test_expression_is_frozen(self) -> None:
        """Verify Expression is frozen (immutable)."""
        expr = Expression(
            raw="${{ inputs.name }}",
            kind=ExpressionKind.INPUT_REF,
            path=("inputs", "name"),
        )

        with pytest.raises(AttributeError):
            expr.raw = "${{ inputs.other }}"  # type: ignore

    def test_expression_equality(self) -> None:
        """Verify Expression equality works correctly."""
        expr1 = Expression(
            raw="${{ inputs.name }}",
            kind=ExpressionKind.INPUT_REF,
            path=("inputs", "name"),
        )
        expr2 = Expression(
            raw="${{ inputs.name }}",
            kind=ExpressionKind.INPUT_REF,
            path=("inputs", "name"),
        )
        expr3 = Expression(
            raw="${{ inputs.other }}",
            kind=ExpressionKind.INPUT_REF,
            path=("inputs", "other"),
        )

        assert expr1 == expr2
        assert expr1 != expr3

    def test_expression_hashable(self) -> None:
        """Verify Expression can be used in sets/dicts."""
        expr1 = Expression(
            raw="${{ inputs.name }}",
            kind=ExpressionKind.INPUT_REF,
            path=("inputs", "name"),
        )
        expr2 = Expression(
            raw="${{ steps.x.output }}",
            kind=ExpressionKind.STEP_REF,
            path=("steps", "x", "output"),
        )

        # Should be hashable
        expr_set = {expr1, expr2}
        assert len(expr_set) == 2
        assert expr1 in expr_set
        assert expr2 in expr_set


class TestFunctionsBasic:
    """Basic tests for parser functions (full tests in test_parser.py)."""

    def test_tokenize_basic(self) -> None:
        """Verify tokenize returns tokens."""
        tokens = tokenize("inputs.name")
        assert isinstance(tokens, list)
        assert len(tokens) == 3
        assert tokens == ["inputs", ".", "name"]

    def test_parse_expression_basic(self) -> None:
        """Verify parse_expression returns Expression."""
        expr = parse_expression("${{ inputs.name }}")
        assert isinstance(expr, Expression)
        assert expr.kind == ExpressionKind.INPUT_REF
        assert expr.path == ("inputs", "name")

    def test_extract_all_basic(self) -> None:
        """Verify extract_all returns list of expressions."""
        exprs = extract_all("Hello ${{ inputs.name }}")
        assert isinstance(exprs, list)
        assert len(exprs) == 1
        assert exprs[0].kind == ExpressionKind.INPUT_REF
