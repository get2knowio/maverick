"""Comprehensive grammar validation tests for the DSL expression language.

This module validates that the parser implementation correctly follows the
formal BNF grammar specification documented in docs/expression-grammar.md.

Test Organization:
- Grammar Productions: Test each grammar rule
- Operator Precedence: Verify precedence table
- Error Cases: Validate error messages reference grammar
- Complex Expressions: Test real-world scenarios
"""

from __future__ import annotations

import pytest

from maverick.dsl.expressions.errors import ExpressionSyntaxError
from maverick.dsl.expressions.parser import (
    BooleanExpression,
    Expression,
    ExpressionKind,
    TernaryExpression,
    parse_expression,
)

# ============================================================================
# Grammar Production Tests
# ============================================================================


class TestGrammarProductions:
    """Test that each grammar production works correctly."""

    def test_start_production(self) -> None:
        """Test start ::= ternary-expr."""
        # start should accept any valid ternary-expr
        result = parse_expression("inputs.a")
        assert isinstance(result, (Expression, BooleanExpression, TernaryExpression))

    def test_ternary_expr_production_simple(self) -> None:
        """Test ternary-expr ::= bool-expr."""
        result = parse_expression("inputs.a")
        assert isinstance(result, Expression)

    def test_ternary_expr_production_conditional(self) -> None:
        """Test ternary-expr ::= bool-expr 'if' bool-expr 'else' ternary-expr."""
        result = parse_expression("inputs.a if inputs.b else inputs.c")
        assert isinstance(result, TernaryExpression)

    def test_bool_expr_production_single(self) -> None:
        """Test bool-expr ::= bool-term."""
        result = parse_expression("inputs.a")
        assert isinstance(result, Expression)

    def test_bool_expr_production_or(self) -> None:
        """Test bool-expr ::= bool-term ('or' bool-term)*."""
        result = parse_expression("inputs.a or inputs.b")
        assert isinstance(result, BooleanExpression)
        assert result.operator == "or"

    def test_bool_term_production_single(self) -> None:
        """Test bool-term ::= unary-expr."""
        result = parse_expression("inputs.a")
        assert isinstance(result, Expression)

    def test_bool_term_production_and(self) -> None:
        """Test bool-term ::= unary-expr ('and' unary-expr)*."""
        result = parse_expression("inputs.a and inputs.b")
        assert isinstance(result, BooleanExpression)
        assert result.operator == "and"

    def test_unary_expr_production_simple(self) -> None:
        """Test unary-expr ::= reference."""
        result = parse_expression("inputs.a")
        assert isinstance(result, Expression)

    def test_unary_expr_production_negated(self) -> None:
        """Test unary-expr ::= 'not' unary-expr."""
        result = parse_expression("not inputs.a")
        assert isinstance(result, Expression)
        assert result.negated is True

    def test_reference_production_input(self) -> None:
        """Test reference ::= input-ref."""
        result = parse_expression("inputs.name")
        assert isinstance(result, Expression)
        assert result.kind == ExpressionKind.INPUT_REF

    def test_reference_production_step(self) -> None:
        """Test reference ::= step-ref."""
        result = parse_expression("steps.x.output")
        assert isinstance(result, Expression)
        assert result.kind == ExpressionKind.STEP_REF

    def test_reference_production_item(self) -> None:
        """Test reference ::= item-ref."""
        result = parse_expression("item")
        assert isinstance(result, Expression)
        assert result.kind == ExpressionKind.ITEM_REF

    def test_reference_production_index(self) -> None:
        """Test reference ::= index-ref."""
        result = parse_expression("index")
        assert isinstance(result, Expression)
        assert result.kind == ExpressionKind.INDEX_REF


class TestInputRefProduction:
    """Test input-ref ::= 'inputs' accessor+."""

    def test_input_ref_minimum_one_accessor(self) -> None:
        """Input reference requires at least one accessor."""
        result = parse_expression("inputs.name")
        assert result.kind == ExpressionKind.INPUT_REF
        assert result.path == ("inputs", "name")

    def test_input_ref_multiple_accessors(self) -> None:
        """Input reference can have multiple accessors."""
        result = parse_expression("inputs.config.database.host")
        assert result.path == ("inputs", "config", "database", "host")

    def test_input_ref_missing_accessor_fails(self) -> None:
        """Input reference without accessor fails validation."""
        with pytest.raises(
            ExpressionSyntaxError,
            match="(Input reference requires a property name|Unexpected token)",
        ):
            parse_expression("inputs")


class TestStepRefProduction:
    """Test step-ref ::= 'steps' '.' identifier '.' 'output' accessor*."""

    def test_step_ref_minimum_required_parts(self) -> None:
        """Step reference requires steps.id.output."""
        result = parse_expression("steps.x.output")
        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == ("steps", "x", "output")

    def test_step_ref_with_accessors(self) -> None:
        """Step reference can have field accessors after output."""
        result = parse_expression("steps.x.output.field.nested")
        assert result.path == ("steps", "x", "output", "field", "nested")

    def test_step_ref_missing_output_fails(self) -> None:
        """Step reference without 'output' fails."""
        with pytest.raises(
            ExpressionSyntaxError,
            match="output",
        ):
            parse_expression("steps.x")

    def test_step_ref_wrong_field_after_id_fails(self) -> None:
        """Step reference with non-'output' field after ID fails."""
        with pytest.raises(ExpressionSyntaxError):
            parse_expression("steps.x.result")


class TestItemRefProduction:
    """Test item-ref ::= 'item' accessor*."""

    def test_item_ref_alone(self) -> None:
        """Item reference can be used alone."""
        result = parse_expression("item")
        assert result.kind == ExpressionKind.ITEM_REF
        assert result.path == ("item",)

    def test_item_ref_with_accessors(self) -> None:
        """Item reference can have accessors."""
        result = parse_expression("item.name.first")
        assert result.path == ("item", "name", "first")

    def test_item_ref_with_bracket(self) -> None:
        """Item reference can use bracket notation."""
        result = parse_expression("item[0]")
        assert result.kind == ExpressionKind.ITEM_REF
        assert result.path == ("item", "0")


class TestIndexRefProduction:
    """Test index-ref ::= 'index'."""

    def test_index_ref_alone(self) -> None:
        """Index reference must be used alone."""
        result = parse_expression("index")
        assert result.kind == ExpressionKind.INDEX_REF
        assert result.path == ("index",)

    def test_index_ref_with_accessor_fails(self) -> None:
        """Index reference cannot have accessors."""
        with pytest.raises(
            ExpressionSyntaxError,
            match="Index reference must be a single element",
        ):
            parse_expression("index.field")

    def test_index_ref_with_bracket_fails(self) -> None:
        """Index reference cannot use bracket notation."""
        with pytest.raises(
            ExpressionSyntaxError,
            match="Index reference must be a single element",
        ):
            parse_expression("index[0]")


class TestAccessorProductions:
    """Test accessor ::= dot-accessor | bracket-accessor."""

    def test_dot_accessor(self) -> None:
        """Test dot-accessor ::= '.' identifier."""
        result = parse_expression("inputs.name")
        assert result.path == ("inputs", "name")

    def test_bracket_accessor_integer(self) -> None:
        """Test bracket-accessor with integer."""
        result = parse_expression("item[0]")
        assert result.path == ("item", "0")

    def test_bracket_accessor_negative_integer(self) -> None:
        """Test bracket-accessor with negative integer."""
        result = parse_expression("item[-1]")
        assert result.path == ("item", "-1")

    def test_bracket_accessor_string_single_quote(self) -> None:
        """Test bracket-accessor with single-quoted string."""
        result = parse_expression("item['key']")
        assert result.path == ("item", "key")

    def test_bracket_accessor_string_double_quote(self) -> None:
        """Test bracket-accessor with double-quoted string."""
        result = parse_expression('item["key"]')
        assert result.path == ("item", "key")

    def test_mixed_accessors(self) -> None:
        """Test combination of dot and bracket accessors."""
        result = parse_expression("item[0].name['field']")
        assert result.path == ("item", "0", "name", "field")


# ============================================================================
# Operator Precedence Tests
# ============================================================================


class TestOperatorPrecedence:
    """Test operator precedence according to grammar specification.

    Precedence (lowest to highest):
    1. if...else (ternary)
    2. or
    3. and
    4. not
    """

    def test_and_binds_tighter_than_or(self) -> None:
        """Test that 'and' has higher precedence than 'or'.

        Expression: a or b and c
        Should parse as: a or (b and c)
        """
        result = parse_expression("inputs.a or inputs.b and inputs.c")
        assert isinstance(result, BooleanExpression)
        assert result.operator == "or"
        assert len(result.operands) == 2

        # First operand is inputs.a
        assert isinstance(result.operands[0], Expression)
        assert result.operands[0].path == ("inputs", "a")

        # Second operand is (inputs.b and inputs.c)
        assert isinstance(result.operands[1], BooleanExpression)
        assert result.operands[1].operator == "and"

    def test_not_binds_tighter_than_and(self) -> None:
        """Test that 'not' has higher precedence than 'and'.

        Expression: not a and b
        Should parse as: (not a) and b
        """
        result = parse_expression("not inputs.a and inputs.b")
        assert isinstance(result, BooleanExpression)
        assert result.operator == "and"
        assert len(result.operands) == 2

        # First operand is (not inputs.a)
        assert isinstance(result.operands[0], Expression)
        assert result.operands[0].negated is True
        assert result.operands[0].path == ("inputs", "a")

        # Second operand is inputs.b
        assert isinstance(result.operands[1], Expression)
        assert result.operands[1].path == ("inputs", "b")

    def test_not_binds_tighter_than_or(self) -> None:
        """Test that 'not' has higher precedence than 'or'.

        Expression: not a or b
        Should parse as: (not a) or b
        """
        result = parse_expression("not inputs.a or inputs.b")
        assert isinstance(result, BooleanExpression)
        assert result.operator == "or"

        # First operand is (not inputs.a)
        assert isinstance(result.operands[0], Expression)
        assert result.operands[0].negated is True

    def test_ternary_has_lowest_precedence(self) -> None:
        """Test that ternary has lowest precedence.

        Expression: a if b and c else d
        Should parse as: a if (b and c) else d
        """
        result = parse_expression("inputs.a if inputs.b and inputs.c else inputs.d")
        assert isinstance(result, TernaryExpression)

        # Condition should be (inputs.b and inputs.c)
        assert isinstance(result.condition, BooleanExpression)
        assert result.condition.operator == "and"

    def test_ternary_is_right_associative(self) -> None:
        """Test that ternary is right-associative.

        Expression: a if b else c if d else e
        Should parse as: a if b else (c if d else e)
        """
        result = parse_expression(
            "inputs.a if inputs.b else inputs.c if inputs.d else inputs.e"
        )
        assert isinstance(result, TernaryExpression)

        # value_if_true should be inputs.a
        assert isinstance(result.value_if_true, Expression)
        assert result.value_if_true.path == ("inputs", "a")

        # condition should be inputs.b
        assert isinstance(result.condition, Expression)
        assert result.condition.path == ("inputs", "b")

        # value_if_false should be another ternary
        assert isinstance(result.value_if_false, TernaryExpression)

    def test_complex_precedence(self) -> None:
        """Test complex precedence: a or b and not c if d else e.

        Should parse as: (a or (b and (not c))) if d else e
        """
        result = parse_expression(
            "inputs.a or inputs.b and not inputs.c if inputs.d else inputs.e"
        )
        assert isinstance(result, TernaryExpression)

        # value_if_true should be: a or (b and (not c))
        assert isinstance(result.value_if_true, BooleanExpression)
        assert result.value_if_true.operator == "or"


class TestAssociativity:
    """Test operator associativity."""

    def test_and_is_left_associative(self) -> None:
        """Test that 'and' is left-associative.

        Expression: a and b and c
        Should parse as: (a and b) and c
        But since 'and' is commutative, both are equivalent.
        """
        result = parse_expression("inputs.a and inputs.b and inputs.c")
        assert isinstance(result, BooleanExpression)
        assert result.operator == "and"
        assert len(result.operands) == 3

    def test_or_is_left_associative(self) -> None:
        """Test that 'or' is left-associative.

        Expression: a or b or c
        Should parse as: (a or b) or c
        But since 'or' is commutative, both are equivalent.
        """
        result = parse_expression("inputs.a or inputs.b or inputs.c")
        assert isinstance(result, BooleanExpression)
        assert result.operator == "or"
        assert len(result.operands) == 3

    def test_ternary_is_right_associative(self) -> None:
        """Test that ternary is right-associative.

        Expression: a if b else c if d else e
        Should parse as: a if b else (c if d else e)
        """
        result = parse_expression(
            "inputs.a if inputs.b else inputs.c if inputs.d else inputs.e"
        )
        assert isinstance(result, TernaryExpression)
        assert isinstance(result.value_if_false, TernaryExpression)


# ============================================================================
# Error Message Grammar Reference Tests
# ============================================================================


class TestErrorMessagesReferenceGrammar:
    """Test that error messages provide helpful grammar-based guidance."""

    def test_invalid_start_references_valid_prefixes(self) -> None:
        """Error for invalid start should mention valid prefixes."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("outputs.name")

        error_msg = str(exc_info.value).lower()
        # Should mention at least one valid prefix
        assert any(
            prefix in error_msg for prefix in ["inputs", "steps", "item", "index"]
        )

    def test_missing_output_references_grammar(self) -> None:
        """Error for missing 'output' should reference step-ref production."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("steps.x")

        error_msg = str(exc_info.value).lower()
        assert "output" in error_msg

    def test_index_accessor_references_grammar(self) -> None:
        """Error for index accessor should reference grammar restriction."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("index.field")

        error_msg = str(exc_info.value).lower()
        assert "index" in error_msg
        assert "single element" in error_msg

    def test_empty_expression_error(self) -> None:
        """Error for empty expression should be clear."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("${{ }}")

        error_msg = str(exc_info.value).lower()
        assert "empty" in error_msg

    def test_double_negation_error(self) -> None:
        """Error for double negation should reference grammar restriction."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("not not inputs.flag")

        error_msg = str(exc_info.value).lower()
        assert "double negation" in error_msg or "not allowed" in error_msg


# ============================================================================
# Complex Real-World Expression Tests
# ============================================================================


class TestComplexExpressions:
    """Test complex real-world expressions from the grammar documentation."""

    def test_conditional_step_execution(self) -> None:
        """Test: inputs.enabled and not inputs.dry_run and steps.validate.output.success."""  # noqa: E501
        result = parse_expression(
            "inputs.enabled and not inputs.dry_run and steps.validate.output.success"
        )
        assert isinstance(result, BooleanExpression)
        assert result.operator == "and"
        assert len(result.operands) == 3

    def test_dynamic_branch_name_fallback(self) -> None:
        """Test: inputs.branch if inputs.branch else steps.default.output."""
        result = parse_expression(
            "inputs.branch if inputs.branch else steps.default.output"
        )
        assert isinstance(result, TernaryExpression)
        assert result.value_if_true.path == ("inputs", "branch")
        assert result.condition.path == ("inputs", "branch")
        assert result.value_if_false.path == ("steps", "default", "output")

    def test_nested_data_access(self) -> None:
        """Test: steps.config.output.api.endpoints.production."""
        result = parse_expression("steps.config.output.api.endpoints.production")
        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == (
            "steps",
            "config",
            "output",
            "api",
            "endpoints",
            "production",
        )

    def test_conditional_nested_access(self) -> None:
        """Test: steps.cfg.output.api.prod if inputs.prod else steps.cfg.output.api.staging."""  # noqa: E501
        result = parse_expression(
            "steps.cfg.output.api.prod if inputs.prod else steps.cfg.output.api.staging"
        )
        assert isinstance(result, TernaryExpression)
        assert result.value_if_true.path == ("steps", "cfg", "output", "api", "prod")
        assert result.condition.path == ("inputs", "prod")
        assert result.value_if_false.path == (
            "steps",
            "cfg",
            "output",
            "api",
            "staging",
        )

    def test_multiple_or_conditions(self) -> None:
        """Test: inputs.a or inputs.b or inputs.c or inputs.default."""
        result = parse_expression("inputs.a or inputs.b or inputs.c or inputs.default")
        assert isinstance(result, BooleanExpression)
        assert result.operator == "or"
        assert len(result.operands) == 4

    def test_mixed_boolean_operators(self) -> None:
        """Test: (a and b) or (c and d)."""
        result = parse_expression("inputs.a and inputs.b or inputs.c and inputs.d")
        assert isinstance(result, BooleanExpression)
        assert result.operator == "or"
        # Should have two operands: (a and b) and (c and d)
        assert len(result.operands) == 2
        assert isinstance(result.operands[0], BooleanExpression)
        assert result.operands[0].operator == "and"
        assert isinstance(result.operands[1], BooleanExpression)
        assert result.operands[1].operator == "and"

    def test_negated_ternary_condition(self) -> None:
        """Test: inputs.a if not inputs.flag else inputs.b."""
        result = parse_expression("inputs.a if not inputs.flag else inputs.b")
        assert isinstance(result, TernaryExpression)
        assert isinstance(result.condition, Expression)
        assert result.condition.negated is True

    def test_ternary_with_boolean_condition(self) -> None:
        """Test: inputs.a if inputs.b and inputs.c else inputs.d."""
        result = parse_expression("inputs.a if inputs.b and inputs.c else inputs.d")
        assert isinstance(result, TernaryExpression)
        assert isinstance(result.condition, BooleanExpression)
        assert result.condition.operator == "and"


# ============================================================================
# Grammar Consistency Tests
# ============================================================================


class TestGrammarConsistency:
    """Test that grammar implementation is consistent and complete."""

    def test_all_expression_kinds_parseable(self) -> None:
        """Test that all ExpressionKind values can be parsed."""
        test_cases = {
            ExpressionKind.INPUT_REF: "inputs.name",
            ExpressionKind.STEP_REF: "steps.x.output",
            ExpressionKind.ITEM_REF: "item",
            ExpressionKind.INDEX_REF: "index",
        }

        for expected_kind, expr in test_cases.items():
            result = parse_expression(expr)
            assert isinstance(result, Expression)
            assert result.kind == expected_kind

    def test_all_operators_parseable(self) -> None:
        """Test that all operators can be parsed."""
        # not
        result = parse_expression("not inputs.a")
        assert isinstance(result, Expression)
        assert result.negated is True

        # and
        result = parse_expression("inputs.a and inputs.b")
        assert isinstance(result, BooleanExpression)
        assert result.operator == "and"

        # or
        result = parse_expression("inputs.a or inputs.b")
        assert isinstance(result, BooleanExpression)
        assert result.operator == "or"

        # if...else
        result = parse_expression("inputs.a if inputs.b else inputs.c")
        assert isinstance(result, TernaryExpression)

    def test_all_accessor_types_parseable(self) -> None:
        """Test that all accessor types can be parsed."""
        # Dot accessor
        result = parse_expression("inputs.name.first")
        assert "name" in result.path
        assert "first" in result.path

        # Bracket accessor with integer
        result = parse_expression("item[0]")
        assert "0" in result.path

        # Bracket accessor with string (single quote)
        result = parse_expression("item['key']")
        assert "key" in result.path

        # Bracket accessor with string (double quote)
        result = parse_expression('item["key"]')
        assert "key" in result.path

    def test_whitespace_handling(self) -> None:
        """Test that whitespace is properly ignored per grammar."""
        # Extra whitespace around operators
        result = parse_expression("inputs.a  or  inputs.b")
        assert isinstance(result, BooleanExpression)

        # Extra whitespace in wrapper
        result = parse_expression("${{  inputs.a  }}")
        assert isinstance(result, Expression)

        # Tabs and newlines (if supported)
        result = parse_expression("inputs.a\tor\ninputs.b")
        assert isinstance(result, BooleanExpression)


# ============================================================================
# Grammar Edge Cases
# ============================================================================


class TestGrammarEdgeCases:
    """Test edge cases and boundary conditions of the grammar."""

    def test_deeply_nested_ternary(self) -> None:
        """Test deeply nested ternary expressions."""
        result = parse_expression(
            "inputs.a if inputs.b else inputs.c if inputs.d else "
            "inputs.e if inputs.f else inputs.g"
        )
        assert isinstance(result, TernaryExpression)
        assert isinstance(result.value_if_false, TernaryExpression)
        nested = result.value_if_false
        assert isinstance(nested.value_if_false, TernaryExpression)

    def test_deeply_nested_boolean(self) -> None:
        """Test deeply nested boolean expressions."""
        result = parse_expression(
            "inputs.a and inputs.b and inputs.c and inputs.d and inputs.e"
        )
        assert isinstance(result, BooleanExpression)
        assert len(result.operands) == 5

    def test_deeply_nested_accessors(self) -> None:
        """Test deeply nested field access."""
        result = parse_expression("item.a.b.c.d.e.f.g.h")
        assert len(result.path) == 9  # item + 8 fields

    def test_mixed_complex_expression(self) -> None:
        """Test expression combining all features."""
        result = parse_expression(
            "item.name if inputs.use_item and not inputs.force else "
            "steps.default.output.value"
        )
        assert isinstance(result, TernaryExpression)
        assert isinstance(result.condition, BooleanExpression)
        assert isinstance(result.value_if_true, Expression)
        assert isinstance(result.value_if_false, Expression)

    def test_negation_of_complex_expression(self) -> None:
        """Test negation applied to first operand of boolean expression."""
        result = parse_expression("not inputs.a and inputs.b")
        assert isinstance(result, BooleanExpression)
        assert result.operator == "and"
        assert isinstance(result.operands[0], Expression)
        assert result.operands[0].negated is True

    def test_single_character_identifiers(self) -> None:
        """Test that single-character identifiers are valid."""
        result = parse_expression("inputs.a")
        assert result.path == ("inputs", "a")

        result = parse_expression("steps.x.output")
        assert result.path == ("steps", "x", "output")

    def test_long_identifiers(self) -> None:
        """Test that long identifiers are valid."""
        long_id = "very_long_identifier_name_with_many_underscores_and_numbers_123"
        result = parse_expression(f"inputs.{long_id}")
        assert long_id in result.path
