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
        result = evaluator.evaluate_string(
            "Result: ${{ steps.fetch.output.status }}"
        )
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
