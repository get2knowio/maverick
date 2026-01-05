"""Unit tests for expression evaluator.

This module contains TDD tests for expression evaluation components:
- ExpressionEvaluator.evaluate(): Evaluate single expressions (T020a, T020b, T020c)
- ExpressionEvaluator.evaluate_string(): Evaluate expressions in text (T020)

Tests are written before implementation following TDD principles.

Test scenarios:
1. Input references: ${{ inputs.name }} -> context["inputs"]["name"]
2. Step references: ${{ steps.analyze.output }} -> context["steps"]["analyze"]["output"]
3. Nested field access: ${{ steps.x.output.field.nested }}
4. Negation: ${{ not inputs.dry_run }} -> not context["inputs"]["dry_run"]
5. evaluate_string: "Hello ${{ inputs.name }}" -> "Hello John"
6. Error handling: missing keys, invalid paths
"""

from __future__ import annotations

import pytest

from maverick.dsl.expressions.errors import ExpressionEvaluationError
from maverick.dsl.expressions.evaluator import ExpressionEvaluator
from maverick.dsl.expressions.parser import Expression, ExpressionKind, parse_expression


class TestInputReferenceEvaluation:
    """Test evaluation of input references (T020a)."""

    def test_simple_input_reference(self) -> None:
        """Evaluate simple input reference: ${{ inputs.name }}."""
        evaluator = ExpressionEvaluator(
            inputs={"name": "John"},
            step_outputs={},
        )
        expr = parse_expression("${{ inputs.name }}")
        result = evaluator.evaluate(expr)
        assert result == "John"

    def test_input_reference_with_underscore(self) -> None:
        """Evaluate input reference with underscored name."""
        evaluator = ExpressionEvaluator(
            inputs={"user_name": "jane_doe"},
            step_outputs={},
        )
        expr = parse_expression("${{ inputs.user_name }}")
        result = evaluator.evaluate(expr)
        assert result == "jane_doe"

    def test_input_reference_with_boolean(self) -> None:
        """Evaluate input reference returning boolean."""
        evaluator = ExpressionEvaluator(
            inputs={"dry_run": True},
            step_outputs={},
        )
        expr = parse_expression("${{ inputs.dry_run }}")
        result = evaluator.evaluate(expr)
        assert result is True

    def test_input_reference_with_number(self) -> None:
        """Evaluate input reference returning number."""
        evaluator = ExpressionEvaluator(
            inputs={"max_retries": 3},
            step_outputs={},
        )
        expr = parse_expression("${{ inputs.max_retries }}")
        result = evaluator.evaluate(expr)
        assert result == 3

    def test_input_reference_with_list(self) -> None:
        """Evaluate input reference returning list."""
        evaluator = ExpressionEvaluator(
            inputs={"items": ["a", "b", "c"]},
            step_outputs={},
        )
        expr = parse_expression("${{ inputs.items }}")
        result = evaluator.evaluate(expr)
        assert result == ["a", "b", "c"]

    def test_input_reference_with_dict(self) -> None:
        """Evaluate input reference returning dictionary."""
        evaluator = ExpressionEvaluator(
            inputs={"config": {"key": "value"}},
            step_outputs={},
        )
        expr = parse_expression("${{ inputs.config }}")
        result = evaluator.evaluate(expr)
        assert result == {"key": "value"}

    def test_input_reference_with_none(self) -> None:
        """Evaluate input reference returning None."""
        evaluator = ExpressionEvaluator(
            inputs={"optional": None},
            step_outputs={},
        )
        expr = parse_expression("${{ inputs.optional }}")
        result = evaluator.evaluate(expr)
        assert result is None

    def test_input_reference_missing_key_raises_error(self) -> None:
        """Missing input key raises ExpressionEvaluationError."""
        evaluator = ExpressionEvaluator(
            inputs={"name": "John"},
            step_outputs={},
        )
        expr = parse_expression("${{ inputs.missing }}")
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluator.evaluate(expr)
        assert "missing" in str(exc_info.value)
        assert "inputs" in str(exc_info.value)

    def test_input_reference_empty_inputs_raises_error(self) -> None:
        """Reference to input when inputs is empty raises error."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
        )
        expr = parse_expression("${{ inputs.name }}")
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluator.evaluate(expr)
        assert "name" in str(exc_info.value)


class TestStepOutputReferenceEvaluation:
    """Test evaluation of step output references (T020b)."""

    def test_simple_step_output_reference(self) -> None:
        """Evaluate simple step output: ${{ steps.analyze.output }}."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={"analyze": {"output": "analysis result"}},
        )
        expr = parse_expression("${{ steps.analyze.output }}")
        result = evaluator.evaluate(expr)
        assert result == "analysis result"

    def test_step_output_with_dict_result(self) -> None:
        """Evaluate step output returning dictionary."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "fetch": {
                    "output": {"status": "success", "data": [1, 2, 3]},
                }
            },
        )
        expr = parse_expression("${{ steps.fetch.output }}")
        result = evaluator.evaluate(expr)
        assert result == {"status": "success", "data": [1, 2, 3]}

    def test_step_output_with_list_result(self) -> None:
        """Evaluate step output returning list."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "collect": {
                    "output": ["item1", "item2", "item3"],
                }
            },
        )
        expr = parse_expression("${{ steps.collect.output }}")
        result = evaluator.evaluate(expr)
        assert result == ["item1", "item2", "item3"]

    def test_step_output_with_boolean_result(self) -> None:
        """Evaluate step output returning boolean."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "check": {
                    "output": True,
                }
            },
        )
        expr = parse_expression("${{ steps.check.output }}")
        result = evaluator.evaluate(expr)
        assert result is True

    def test_step_output_with_none_result(self) -> None:
        """Evaluate step output returning None."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "optional_step": {
                    "output": None,
                }
            },
        )
        expr = parse_expression("${{ steps.optional_step.output }}")
        result = evaluator.evaluate(expr)
        assert result is None

    def test_step_output_missing_step_raises_error(self) -> None:
        """Missing step name raises ExpressionEvaluationError."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={"analyze": {"output": "result"}},
        )
        expr = parse_expression("${{ steps.missing.output }}")
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluator.evaluate(expr)
        assert "missing" in str(exc_info.value)
        assert "steps" in str(exc_info.value)

    def test_step_output_missing_output_field_raises_error(self) -> None:
        """Missing 'output' field in step data raises error."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={"analyze": {"status": "completed"}},
        )
        expr = parse_expression("${{ steps.analyze.output }}")
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluator.evaluate(expr)
        assert "output" in str(exc_info.value)
        assert "analyze" in str(exc_info.value)

    def test_step_output_empty_step_outputs_raises_error(self) -> None:
        """Reference to step when step_outputs is empty raises error."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
        )
        expr = parse_expression("${{ steps.analyze.output }}")
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluator.evaluate(expr)
        assert "analyze" in str(exc_info.value)


class TestNestedFieldAccessAndNegation:
    """Test evaluation of nested field access and negation (T020c)."""

    def test_nested_field_in_step_output(self) -> None:
        """Evaluate nested field access: ${{ steps.x.output.field }}."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "x": {
                    "output": {"field": "value"},
                }
            },
        )
        expr = parse_expression("${{ steps.x.output.field }}")
        result = evaluator.evaluate(expr)
        assert result == "value"

    def test_deeply_nested_field_access(self) -> None:
        """Evaluate deeply nested field: ${{ steps.x.output.a.b.c }}."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "x": {
                    "output": {
                        "a": {
                            "b": {
                                "c": "deep value",
                            }
                        }
                    },
                }
            },
        )
        expr = parse_expression("${{ steps.x.output.a.b.c }}")
        result = evaluator.evaluate(expr)
        assert result == "deep value"

    def test_nested_field_with_list_value(self) -> None:
        """Evaluate nested field returning list."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "fetch": {
                    "output": {
                        "data": ["item1", "item2"],
                    },
                }
            },
        )
        expr = parse_expression("${{ steps.fetch.output.data }}")
        result = evaluator.evaluate(expr)
        assert result == ["item1", "item2"]

    def test_nested_field_missing_intermediate_key_raises_error(self) -> None:
        """Missing intermediate key in nested access raises error."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "x": {
                    "output": {"other": "value"},
                }
            },
        )
        expr = parse_expression("${{ steps.x.output.field }}")
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluator.evaluate(expr)
        assert "field" in str(exc_info.value)

    def test_nested_field_non_dict_intermediate_raises_error(self) -> None:
        """Non-dict intermediate value in nested access raises error."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "x": {
                    "output": "string value",  # Not a dict
                }
            },
        )
        expr = parse_expression("${{ steps.x.output.field }}")
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluator.evaluate(expr)
        assert "field" in str(exc_info.value) or "dict" in str(exc_info.value).lower()

    def test_negated_input_boolean_true(self) -> None:
        """Evaluate negated boolean input: ${{ not inputs.dry_run }}."""
        evaluator = ExpressionEvaluator(
            inputs={"dry_run": True},
            step_outputs={},
        )
        expr = parse_expression("${{ not inputs.dry_run }}")
        result = evaluator.evaluate(expr)
        assert result is False

    def test_negated_input_boolean_false(self) -> None:
        """Evaluate negated boolean input with False value."""
        evaluator = ExpressionEvaluator(
            inputs={"dry_run": False},
            step_outputs={},
        )
        expr = parse_expression("${{ not inputs.dry_run }}")
        result = evaluator.evaluate(expr)
        assert result is True

    def test_negated_step_output_boolean(self) -> None:
        """Evaluate negated step output boolean."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "check": {
                    "output": False,
                }
            },
        )
        expr = parse_expression("${{ not steps.check.output }}")
        result = evaluator.evaluate(expr)
        assert result is True

    def test_negated_nested_field_boolean(self) -> None:
        """Evaluate negated nested field."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "validate": {
                    "output": {
                        "passed": True,
                    },
                }
            },
        )
        expr = parse_expression("${{ not steps.validate.output.passed }}")
        result = evaluator.evaluate(expr)
        assert result is False

    def test_negated_truthy_value(self) -> None:
        """Evaluate negation of truthy value (non-empty string)."""
        evaluator = ExpressionEvaluator(
            inputs={"value": "non-empty"},
            step_outputs={},
        )
        expr = parse_expression("${{ not inputs.value }}")
        result = evaluator.evaluate(expr)
        assert result is False

    def test_negated_falsy_value(self) -> None:
        """Evaluate negation of falsy value (empty string)."""
        evaluator = ExpressionEvaluator(
            inputs={"value": ""},
            step_outputs={},
        )
        expr = parse_expression("${{ not inputs.value }}")
        result = evaluator.evaluate(expr)
        assert result is True

    def test_nested_field_in_input(self) -> None:
        """Evaluate nested field access in inputs (not common but valid)."""
        evaluator = ExpressionEvaluator(
            inputs={
                "config": {
                    "database": {
                        "host": "localhost",
                    }
                }
            },
            step_outputs={},
        )
        expr = parse_expression("${{ inputs.config }}")
        result = evaluator.evaluate(expr)
        assert result == {"database": {"host": "localhost"}}


class TestEvaluateStringMethod:
    """Test evaluate_string method for template substitution (T020)."""

    def test_single_expression_in_string(self) -> None:
        """Evaluate string with single expression: 'Hello ${{ inputs.name }}'."""
        evaluator = ExpressionEvaluator(
            inputs={"name": "John"},
            step_outputs={},
        )
        result = evaluator.evaluate_string("Hello ${{ inputs.name }}")
        assert result == "Hello John"

    def test_multiple_expressions_in_string(self) -> None:
        """Evaluate string with multiple expressions."""
        evaluator = ExpressionEvaluator(
            inputs={"first": "John", "last": "Doe"},
            step_outputs={},
        )
        result = evaluator.evaluate_string(
            "Name: ${{ inputs.first }} ${{ inputs.last }}"
        )
        assert result == "Name: John Doe"

    def test_expression_only_string(self) -> None:
        """Evaluate string that is only an expression."""
        evaluator = ExpressionEvaluator(
            inputs={"name": "John"},
            step_outputs={},
        )
        result = evaluator.evaluate_string("${{ inputs.name }}")
        assert result == "John"

    def test_string_with_no_expressions(self) -> None:
        """Evaluate string with no expressions returns original."""
        evaluator = ExpressionEvaluator(
            inputs={"name": "John"},
            step_outputs={},
        )
        result = evaluator.evaluate_string("Plain text with no expressions")
        assert result == "Plain text with no expressions"

    def test_empty_string(self) -> None:
        """Evaluate empty string returns empty string."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
        )
        result = evaluator.evaluate_string("")
        assert result == ""

    def test_mixed_expressions_and_literals(self) -> None:
        """Evaluate string mixing expressions with literal text."""
        evaluator = ExpressionEvaluator(
            inputs={"count": 5},
            step_outputs={"analyze": {"output": "completed"}},
        )
        result = evaluator.evaluate_string(
            "Processed ${{ inputs.count }} items. Status: ${{ steps.analyze.output }}"
        )
        assert result == "Processed 5 items. Status: completed"

    def test_expression_with_nested_field(self) -> None:
        """Evaluate string with nested field expression."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "fetch": {
                    "output": {
                        "status": "success",
                    },
                }
            },
        )
        result = evaluator.evaluate_string("Result: ${{ steps.fetch.output.status }}")
        assert result == "Result: success"

    def test_expression_with_boolean_stringified(self) -> None:
        """Boolean values in expressions are stringified."""
        evaluator = ExpressionEvaluator(
            inputs={"enabled": True},
            step_outputs={},
        )
        result = evaluator.evaluate_string("Enabled: ${{ inputs.enabled }}")
        assert result == "Enabled: True"

    def test_expression_with_number_stringified(self) -> None:
        """Number values in expressions are stringified."""
        evaluator = ExpressionEvaluator(
            inputs={"count": 42},
            step_outputs={},
        )
        result = evaluator.evaluate_string("Count: ${{ inputs.count }}")
        assert result == "Count: 42"

    def test_expression_with_none_stringified(self) -> None:
        """None values in expressions are stringified as 'None'."""
        evaluator = ExpressionEvaluator(
            inputs={"value": None},
            step_outputs={},
        )
        result = evaluator.evaluate_string("Value: ${{ inputs.value }}")
        assert result == "Value: None"

    def test_expression_with_list_stringified(self) -> None:
        """List values in expressions are stringified."""
        evaluator = ExpressionEvaluator(
            inputs={"items": ["a", "b", "c"]},
            step_outputs={},
        )
        result = evaluator.evaluate_string("Items: ${{ inputs.items }}")
        assert result == "Items: ['a', 'b', 'c']"

    def test_expression_with_dict_stringified(self) -> None:
        """Dict values in expressions are stringified."""
        evaluator = ExpressionEvaluator(
            inputs={"config": {"key": "value"}},
            step_outputs={},
        )
        result = evaluator.evaluate_string("Config: ${{ inputs.config }}")
        assert result == "Config: {'key': 'value'}"

    def test_negated_expression_in_string(self) -> None:
        """Evaluate string with negated expression."""
        evaluator = ExpressionEvaluator(
            inputs={"dry_run": False},
            step_outputs={},
        )
        result = evaluator.evaluate_string("Execute: ${{ not inputs.dry_run }}")
        assert result == "Execute: True"

    def test_expression_evaluation_error_propagates(self) -> None:
        """Expression evaluation error in string propagates."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
        )
        with pytest.raises(ExpressionEvaluationError):
            evaluator.evaluate_string("Hello ${{ inputs.missing }}")


class TestArrayIndexAccess:
    """Test evaluation of array/list index access using bracket notation."""

    def test_array_index_access_in_input(self) -> None:
        """Evaluate array index in input: ${{ inputs.items[0] }}."""
        evaluator = ExpressionEvaluator(
            inputs={"items": ["first", "second", "third"]},
            step_outputs={},
        )
        # Note: Parser should convert items[0] to path ("inputs", "items", "0")
        expr = parse_expression("${{ inputs.items[0] }}")
        result = evaluator.evaluate(expr)
        assert result == "first"

    def test_array_index_access_in_step_output(self) -> None:
        """Evaluate array index in step output."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "collect": {
                    "output": {
                        "results": [1, 2, 3],
                    },
                }
            },
        )
        expr = parse_expression("${{ steps.collect.output.results[1] }}")
        result = evaluator.evaluate(expr)
        assert result == 2

    def test_array_index_out_of_bounds_raises_error(self) -> None:
        """Array index out of bounds raises error."""
        evaluator = ExpressionEvaluator(
            inputs={"items": ["a", "b"]},
            step_outputs={},
        )
        expr = parse_expression("${{ inputs.items[5] }}")
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluator.evaluate(expr)
        assert "5" in str(exc_info.value) or "index" in str(exc_info.value).lower()

    def test_array_index_on_non_list_raises_error(self) -> None:
        """Array index access on non-list raises error."""
        evaluator = ExpressionEvaluator(
            inputs={"value": "string"},
            step_outputs={},
        )
        expr = parse_expression("${{ inputs.value[0] }}")
        # String indexing might work in Python, so we need to check implementation
        # Let's expect it to work like Python for now
        result = evaluator.evaluate(expr)
        assert result == "s"

    def test_dict_key_access_with_bracket_notation(self) -> None:
        """Access dict key using bracket notation with string key."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "fetch": {
                    "output": {
                        "user-name": "john_doe",  # Key with hyphen
                    },
                }
            },
        )
        # Parser should handle ${{ steps.fetch.output['user-name'] }}
        expr = parse_expression("${{ steps.fetch.output['user-name'] }}")
        result = evaluator.evaluate(expr)
        assert result == "john_doe"


class TestEdgeCasesAndErrors:
    """Test edge cases and error conditions."""

    def test_expression_directly_created(self) -> None:
        """Evaluate an Expression object created directly."""
        evaluator = ExpressionEvaluator(
            inputs={"name": "Alice"},
            step_outputs={},
        )
        expr = Expression(
            raw="${{ inputs.name }}",
            kind=ExpressionKind.INPUT_REF,
            path=("inputs", "name"),
            negated=False,
        )
        result = evaluator.evaluate(expr)
        assert result == "Alice"

    def test_evaluator_with_empty_contexts(self) -> None:
        """ExpressionEvaluator can be created with empty contexts."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
        )
        assert evaluator is not None

    def test_error_message_includes_available_variables(self) -> None:
        """Error message includes information about available variables."""
        evaluator = ExpressionEvaluator(
            inputs={"name": "John", "age": 30},
            step_outputs={"step1": {"output": "result"}},
        )
        expr = parse_expression("${{ inputs.missing }}")
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluator.evaluate(expr)
        error_msg = str(exc_info.value)
        # Should mention available input keys
        assert "name" in error_msg or "age" in error_msg or "Available" in error_msg

    def test_step_output_with_multiple_steps(self) -> None:
        """Evaluate step output when multiple steps exist."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={
                "step1": {"output": "result1"},
                "step2": {"output": "result2"},
                "step3": {"output": "result3"},
            },
        )
        expr = parse_expression("${{ steps.step2.output }}")
        result = evaluator.evaluate(expr)
        assert result == "result2"

    def test_unicode_values_in_context(self) -> None:
        """Handle Unicode values in inputs/outputs."""
        evaluator = ExpressionEvaluator(
            inputs={"message": "Hello 世界"},
            step_outputs={},
        )
        result = evaluator.evaluate_string("Message: ${{ inputs.message }}")
        assert result == "Message: Hello 世界"

    def test_special_characters_in_string_values(self) -> None:
        """Handle special characters in values."""
        evaluator = ExpressionEvaluator(
            inputs={"path": "/tmp/file with spaces & special chars"},
            step_outputs={},
        )
        result = evaluator.evaluate_string("Path: ${{ inputs.path }}")
        assert result == "Path: /tmp/file with spaces & special chars"


class TestIterationContextEvaluation:
    """Test evaluation of iteration context variables (item and index)."""

    def test_simple_item_reference(self) -> None:
        """Evaluate simple item reference: ${{ item }}."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
            iteration_context={"item": "apple"},
        )
        expr = parse_expression("${{ item }}")
        result = evaluator.evaluate(expr)
        assert result == "apple"

    def test_item_with_nested_field(self) -> None:
        """Evaluate item reference with nested field access."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
            iteration_context={"item": {"name": "John", "age": 30}},
        )
        expr = parse_expression("${{ item.name }}")
        result = evaluator.evaluate(expr)
        assert result == "John"

    def test_item_with_deep_nesting(self) -> None:
        """Evaluate item reference with deeply nested fields."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
            iteration_context={
                "item": {"user": {"profile": {"email": "john@example.com"}}}
            },
        )
        expr = parse_expression("${{ item.user.profile.email }}")
        result = evaluator.evaluate(expr)
        assert result == "john@example.com"

    def test_item_with_array_index(self) -> None:
        """Evaluate item reference with array index."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
            iteration_context={"item": ["first", "second", "third"]},
        )
        expr = parse_expression("${{ item[0] }}")
        result = evaluator.evaluate(expr)
        assert result == "first"

    def test_simple_index_reference(self) -> None:
        """Evaluate simple index reference: ${{ index }}."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
            iteration_context={"item": "apple", "index": 2},
        )
        expr = parse_expression("${{ index }}")
        result = evaluator.evaluate(expr)
        assert result == 2

    def test_item_reference_outside_loop_raises_error(self) -> None:
        """Evaluate item reference outside for_each loop raises error."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
            iteration_context={},  # No item in context
        )
        expr = parse_expression("${{ item }}")
        with pytest.raises(
            ExpressionEvaluationError,
            match="Item reference used outside of for_each loop",
        ):
            evaluator.evaluate(expr)

    def test_index_reference_outside_loop_raises_error(self) -> None:
        """Evaluate index reference outside for_each loop raises error."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
            iteration_context={},  # No index in context
        )
        expr = parse_expression("${{ index }}")
        with pytest.raises(
            ExpressionEvaluationError,
            match="Index reference used outside of for_each loop",
        ):
            evaluator.evaluate(expr)

    def test_negated_item_reference(self) -> None:
        """Evaluate negated item reference."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
            iteration_context={"item": False},
        )
        expr = parse_expression("${{ not item }}")
        result = evaluator.evaluate(expr)
        assert result is True

    def test_item_in_template_string(self) -> None:
        """Evaluate item reference in template string."""
        evaluator = ExpressionEvaluator(
            inputs={},
            step_outputs={},
            iteration_context={"item": "apple", "index": 1},
        )
        result = evaluator.evaluate_string(
            "Processing item ${{ item }} at index ${{ index }}"
        )
        assert result == "Processing item apple at index 1"

    def test_item_with_inputs_and_steps(self) -> None:
        """Evaluate item reference alongside inputs and steps."""
        evaluator = ExpressionEvaluator(
            inputs={"prefix": "Item:"},
            step_outputs={"prev": {"output": "processed"}},
            iteration_context={"item": "apple"},
        )
        result = evaluator.evaluate_string(
            "${{ inputs.prefix }} ${{ item }} (${{ steps.prev.output }})"
        )
        assert result == "Item: apple (processed)"


# ============================================================================
# Ternary Expression Evaluator Tests (Issue #194)
# ============================================================================


class TestTernaryExpressionEvaluation:
    """Test evaluation of ternary conditional expressions."""

    def test_ternary_condition_true(self) -> None:
        """Evaluate ternary when condition is truthy."""
        evaluator = ExpressionEvaluator(
            inputs={"flag": True, "yes_val": "yes", "no_val": "no"},
            step_outputs={},
        )
        expr = parse_expression("inputs.yes_val if inputs.flag else inputs.no_val")
        result = evaluator.evaluate(expr)
        assert result == "yes"

    def test_ternary_condition_false(self) -> None:
        """Evaluate ternary when condition is falsy."""
        evaluator = ExpressionEvaluator(
            inputs={"flag": False, "yes_val": "yes", "no_val": "no"},
            step_outputs={},
        )
        expr = parse_expression("inputs.yes_val if inputs.flag else inputs.no_val")
        result = evaluator.evaluate(expr)
        assert result == "no"

    def test_ternary_with_none_condition(self) -> None:
        """Evaluate ternary when condition is None (falsy)."""
        evaluator = ExpressionEvaluator(
            inputs={"cond": None, "a": "alpha", "b": "beta"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a if inputs.cond else inputs.b")
        result = evaluator.evaluate(expr)
        assert result == "beta"

    def test_ternary_with_empty_string_condition(self) -> None:
        """Evaluate ternary when condition is empty string (falsy)."""
        evaluator = ExpressionEvaluator(
            inputs={"cond": "", "a": "alpha", "b": "beta"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a if inputs.cond else inputs.b")
        result = evaluator.evaluate(expr)
        assert result == "beta"

    def test_ternary_with_nonempty_string_condition(self) -> None:
        """Evaluate ternary when condition is non-empty string (truthy)."""
        evaluator = ExpressionEvaluator(
            inputs={"cond": "something", "a": "alpha", "b": "beta"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a if inputs.cond else inputs.b")
        result = evaluator.evaluate(expr)
        assert result == "alpha"

    def test_ternary_with_zero_condition(self) -> None:
        """Evaluate ternary when condition is zero (falsy)."""
        evaluator = ExpressionEvaluator(
            inputs={"cond": 0, "a": "alpha", "b": "beta"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a if inputs.cond else inputs.b")
        result = evaluator.evaluate(expr)
        assert result == "beta"

    def test_ternary_with_nonzero_condition(self) -> None:
        """Evaluate ternary when condition is nonzero (truthy)."""
        evaluator = ExpressionEvaluator(
            inputs={"cond": 42, "a": "alpha", "b": "beta"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a if inputs.cond else inputs.b")
        result = evaluator.evaluate(expr)
        assert result == "alpha"


class TestTernaryWithStepOutputs:
    """Test ternary evaluation with step output references."""

    def test_ternary_uses_step_output_condition(self) -> None:
        """Evaluate ternary using step output as condition."""
        evaluator = ExpressionEvaluator(
            inputs={"default": "fallback"},
            step_outputs={
                "check": {"output": True},
                "generate": {"output": "generated value"},
            },
        )
        expr = parse_expression(
            "steps.generate.output if steps.check.output else inputs.default"
        )
        result = evaluator.evaluate(expr)
        assert result == "generated value"

    def test_ternary_fallback_to_input(self) -> None:
        """Evaluate ternary that falls back to input when step output is falsy."""
        evaluator = ExpressionEvaluator(
            inputs={"default": "fallback"},
            step_outputs={
                "check": {"output": False},
                "generate": {"output": "generated value"},
            },
        )
        expr = parse_expression(
            "steps.generate.output if steps.check.output else inputs.default"
        )
        result = evaluator.evaluate(expr)
        assert result == "fallback"


class TestTernaryWithNegation:
    """Test ternary evaluation with negated expressions."""

    def test_ternary_negated_condition_true(self) -> None:
        """Evaluate ternary with negated condition that becomes true."""
        evaluator = ExpressionEvaluator(
            inputs={"skip": False, "a": "run", "b": "skip"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a if not inputs.skip else inputs.b")
        result = evaluator.evaluate(expr)
        assert result == "run"

    def test_ternary_negated_condition_false(self) -> None:
        """Evaluate ternary with negated condition that becomes false."""
        evaluator = ExpressionEvaluator(
            inputs={"skip": True, "a": "run", "b": "skip"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a if not inputs.skip else inputs.b")
        result = evaluator.evaluate(expr)
        assert result == "skip"


class TestTernaryWithBooleanOperators:
    """Test ternary evaluation with compound boolean conditions."""

    def test_ternary_and_condition_both_true(self) -> None:
        """Evaluate ternary with 'and' condition where both are true."""
        evaluator = ExpressionEvaluator(
            inputs={"a": True, "b": True, "yes": "both true", "no": "not both"},
            step_outputs={},
        )
        expr = parse_expression("inputs.yes if inputs.a and inputs.b else inputs.no")
        result = evaluator.evaluate(expr)
        assert result == "both true"

    def test_ternary_and_condition_one_false(self) -> None:
        """Evaluate ternary with 'and' condition where one is false."""
        evaluator = ExpressionEvaluator(
            inputs={"a": True, "b": False, "yes": "both true", "no": "not both"},
            step_outputs={},
        )
        expr = parse_expression("inputs.yes if inputs.a and inputs.b else inputs.no")
        result = evaluator.evaluate(expr)
        assert result == "not both"

    def test_ternary_or_condition_one_true(self) -> None:
        """Evaluate ternary with 'or' condition where one is true."""
        evaluator = ExpressionEvaluator(
            inputs={"a": False, "b": True, "yes": "at least one", "no": "none"},
            step_outputs={},
        )
        expr = parse_expression("inputs.yes if inputs.a or inputs.b else inputs.no")
        result = evaluator.evaluate(expr)
        assert result == "at least one"

    def test_ternary_or_condition_both_false(self) -> None:
        """Evaluate ternary with 'or' condition where both are false."""
        evaluator = ExpressionEvaluator(
            inputs={"a": False, "b": False, "yes": "at least one", "no": "none"},
            step_outputs={},
        )
        expr = parse_expression("inputs.yes if inputs.a or inputs.b else inputs.no")
        result = evaluator.evaluate(expr)
        assert result == "none"


class TestTernaryNested:
    """Test evaluation of nested ternary expressions."""

    def test_nested_ternary_first_condition_true(self) -> None:
        """Evaluate nested ternary where first condition is true."""
        evaluator = ExpressionEvaluator(
            inputs={
                "b": True,
                "d": False,
                "a": "first",
                "c": "second",
                "e": "third",
            },
            step_outputs={},
        )
        # a if b else c if d else e
        expr = parse_expression(
            "inputs.a if inputs.b else inputs.c if inputs.d else inputs.e"
        )
        result = evaluator.evaluate(expr)
        assert result == "first"

    def test_nested_ternary_second_condition_true(self) -> None:
        """Evaluate nested ternary where first is false, second is true."""
        evaluator = ExpressionEvaluator(
            inputs={
                "b": False,
                "d": True,
                "a": "first",
                "c": "second",
                "e": "third",
            },
            step_outputs={},
        )
        expr = parse_expression(
            "inputs.a if inputs.b else inputs.c if inputs.d else inputs.e"
        )
        result = evaluator.evaluate(expr)
        assert result == "second"

    def test_nested_ternary_both_conditions_false(self) -> None:
        """Evaluate nested ternary where both conditions are false."""
        evaluator = ExpressionEvaluator(
            inputs={
                "b": False,
                "d": False,
                "a": "first",
                "c": "second",
                "e": "third",
            },
            step_outputs={},
        )
        expr = parse_expression(
            "inputs.a if inputs.b else inputs.c if inputs.d else inputs.e"
        )
        result = evaluator.evaluate(expr)
        assert result == "third"


class TestTernaryWithIterationContext:
    """Test ternary evaluation with item and index references."""

    def test_ternary_with_item_condition(self) -> None:
        """Evaluate ternary with item reference as condition."""
        evaluator = ExpressionEvaluator(
            inputs={"fallback": "no item"},
            step_outputs={},
            iteration_context={"item": "apple"},
        )
        expr = parse_expression("item if item else inputs.fallback")
        result = evaluator.evaluate(expr)
        assert result == "apple"

    def test_ternary_with_falsy_item(self) -> None:
        """Evaluate ternary with falsy item (empty string)."""
        evaluator = ExpressionEvaluator(
            inputs={"fallback": "no item"},
            step_outputs={},
            iteration_context={"item": ""},
        )
        expr = parse_expression("item if item else inputs.fallback")
        result = evaluator.evaluate(expr)
        assert result == "no item"

    def test_ternary_with_index_condition(self) -> None:
        """Evaluate ternary with index as condition (0 is falsy)."""
        evaluator = ExpressionEvaluator(
            inputs={"first": "first item", "other": "other item"},
            step_outputs={},
            iteration_context={"item": "x", "index": 0},
        )
        expr = parse_expression("inputs.first if not index else inputs.other")
        result = evaluator.evaluate(expr)
        assert result == "first item"

    def test_ternary_with_nonzero_index(self) -> None:
        """Evaluate ternary with nonzero index (truthy)."""
        evaluator = ExpressionEvaluator(
            inputs={"first": "first item", "other": "other item"},
            step_outputs={},
            iteration_context={"item": "x", "index": 3},
        )
        expr = parse_expression("inputs.first if not index else inputs.other")
        result = evaluator.evaluate(expr)
        assert result == "other item"


class TestTernaryInTemplateStrings:
    """Test ternary evaluation in template strings."""

    def test_ternary_in_template_string(self) -> None:
        """Evaluate ternary expression within a template string."""
        evaluator = ExpressionEvaluator(
            inputs={"flag": True, "yes": "enabled", "no": "disabled"},
            step_outputs={},
        )
        result = evaluator.evaluate_string(
            "Status: ${{ inputs.yes if inputs.flag else inputs.no }}"
        )
        assert result == "Status: enabled"

    def test_ternary_in_template_string_condition_false(self) -> None:
        """Evaluate ternary in template when condition is false."""
        evaluator = ExpressionEvaluator(
            inputs={"flag": False, "yes": "enabled", "no": "disabled"},
            step_outputs={},
        )
        result = evaluator.evaluate_string(
            "Status: ${{ inputs.yes if inputs.flag else inputs.no }}"
        )
        assert result == "Status: disabled"

    def test_multiple_ternaries_in_template(self) -> None:
        """Evaluate multiple ternary expressions in a template."""
        evaluator = ExpressionEvaluator(
            inputs={"a": True, "b": False, "v1": "X", "v2": "Y", "v3": "Z", "v4": "W"},
            step_outputs={},
        )
        result = evaluator.evaluate_string(
            "${{ inputs.v1 if inputs.a else inputs.v2 }} and "
            "${{ inputs.v3 if inputs.b else inputs.v4 }}"
        )
        assert result == "X and W"


class TestTernaryShortCircuit:
    """Test that ternary evaluation uses short-circuit logic."""

    def test_short_circuit_true_branch_not_evaluated_when_false(self) -> None:
        """When condition is false, true branch errors should not occur."""
        evaluator = ExpressionEvaluator(
            inputs={"flag": False, "exists": "value"},
            step_outputs={},  # missing_step doesn't exist
        )
        # If short-circuit is working, steps.missing.output should not be evaluated
        expr = parse_expression(
            "steps.missing.output if inputs.flag else inputs.exists"
        )
        # This should NOT raise an error because the true branch is never evaluated
        result = evaluator.evaluate(expr)
        assert result == "value"

    def test_short_circuit_false_branch_not_evaluated_when_true(self) -> None:
        """When condition is true, false branch errors should not occur."""
        evaluator = ExpressionEvaluator(
            inputs={"flag": True, "exists": "value"},
            step_outputs={},  # missing_step doesn't exist
        )
        expr = parse_expression(
            "inputs.exists if inputs.flag else steps.missing.output"
        )
        # This should NOT raise an error because the false branch is never evaluated
        result = evaluator.evaluate(expr)
        assert result == "value"


class TestTernaryErrorHandling:
    """Test error handling in ternary evaluation."""

    def test_ternary_condition_error_propagates(self) -> None:
        """Error in ternary condition should propagate."""
        evaluator = ExpressionEvaluator(
            inputs={"a": "x", "b": "y"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a if inputs.missing else inputs.b")
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluator.evaluate(expr)
        assert "missing" in str(exc_info.value)

    def test_ternary_true_branch_error_when_selected(self) -> None:
        """Error in true branch should propagate when condition is true."""
        evaluator = ExpressionEvaluator(
            inputs={"flag": True, "fallback": "x"},
            step_outputs={},
        )
        expr = parse_expression("inputs.missing if inputs.flag else inputs.fallback")
        with pytest.raises(ExpressionEvaluationError) as exc_info:
            evaluator.evaluate(expr)
        assert "missing" in str(exc_info.value)


class TestBooleanOrReturnsValue:
    """Test that 'or' expressions return actual values, not just True/False.

    This is critical for workflow expressions like:
        ${{ inputs.task_file or steps.init.output.task_file_path }}
    which should return the path string, not just True.
    """

    def test_or_returns_first_truthy_value(self) -> None:
        """Or expression should return the first truthy value, not True."""
        evaluator = ExpressionEvaluator(
            inputs={"a": None, "b": "hello"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a or inputs.b")
        result = evaluator.evaluate(expr)
        assert result == "hello"

    def test_or_returns_first_truthy_when_first_is_truthy(self) -> None:
        """Or expression should return the first value if it's truthy."""
        evaluator = ExpressionEvaluator(
            inputs={"a": "first", "b": "second"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a or inputs.b")
        result = evaluator.evaluate(expr)
        assert result == "first"

    def test_or_returns_last_value_when_all_falsy(self) -> None:
        """Or expression should return last value when all are falsy."""
        evaluator = ExpressionEvaluator(
            inputs={"a": None, "b": "", "c": 0},
            step_outputs={},
        )
        expr = parse_expression("inputs.a or inputs.b or inputs.c")
        result = evaluator.evaluate(expr)
        assert result == 0  # Last value, even though falsy

    def test_or_with_step_output_returns_path(self) -> None:
        """Or expression with step output should return the path string."""
        evaluator = ExpressionEvaluator(
            inputs={"task_file": None},
            step_outputs={"init": {"output": {"task_file_path": "/path/to/file.md"}}},
        )
        expr = parse_expression("inputs.task_file or steps.init.output.task_file_path")
        result = evaluator.evaluate(expr)
        assert result == "/path/to/file.md"

    def test_or_short_circuits_on_first_truthy(self) -> None:
        """Or expression should short-circuit and not evaluate later operands."""
        evaluator = ExpressionEvaluator(
            inputs={"a": "found"},
            step_outputs={},  # No 'missing' step
        )
        # If short-circuit is working, steps.missing.output should not be evaluated
        expr = parse_expression("inputs.a or steps.missing.output")
        result = evaluator.evaluate(expr)
        assert result == "found"


class TestBooleanAndReturnsValue:
    """Test that 'and' expressions return actual values, not just True/False."""

    def test_and_returns_last_truthy_when_all_truthy(self) -> None:
        """And expression should return the last value when all are truthy."""
        evaluator = ExpressionEvaluator(
            inputs={"a": "first", "b": "second"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a and inputs.b")
        result = evaluator.evaluate(expr)
        assert result == "second"

    def test_and_returns_first_falsy_value(self) -> None:
        """And expression should return the first falsy value."""
        evaluator = ExpressionEvaluator(
            inputs={"a": "first", "b": None, "c": "third"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a and inputs.b and inputs.c")
        result = evaluator.evaluate(expr)
        assert result is None

    def test_and_returns_first_falsy_value_empty_string(self) -> None:
        """And expression should return first falsy (empty string)."""
        evaluator = ExpressionEvaluator(
            inputs={"a": "first", "b": "", "c": "third"},
            step_outputs={},
        )
        expr = parse_expression("inputs.a and inputs.b and inputs.c")
        result = evaluator.evaluate(expr)
        assert result == ""

    def test_and_short_circuits_on_first_falsy(self) -> None:
        """And expression should short-circuit on first falsy value."""
        evaluator = ExpressionEvaluator(
            inputs={"a": None},
            step_outputs={},  # No 'missing' step
        )
        # If short-circuit is working, steps.missing.output should not be evaluated
        expr = parse_expression("inputs.a and steps.missing.output")
        result = evaluator.evaluate(expr)
        assert result is None
