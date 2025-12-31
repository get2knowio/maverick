"""Unit tests for expression parser (tokenizer and parser).

This module contains TDD tests for expression parsing components:
- tokenize(): Split expression strings into tokens (T017a)
- parse_expression(): Parse tokens into Expression AST (T017b)

Tests are written before implementation following TDD principles.

Expression syntax:
- ${{ inputs.name }} - Input reference
- ${{ steps.x.output }} - Step output reference
- ${{ steps.x.output.field }} - Nested field access
- ${{ not inputs.dry_run }} - Boolean negation
- ${{ items[0] }} - Array index access (bracket notation)
"""

from __future__ import annotations

import pytest

from maverick.dsl.expressions.errors import ExpressionSyntaxError
from maverick.dsl.expressions.parser import (
    Expression,
    ExpressionKind,
    TernaryExpression,
    parse_expression,
    tokenize,
)


class TestTokenizeSimpleIdentifiers:
    """Test tokenizing simple identifiers."""

    def test_single_identifier(self) -> None:
        """Tokenize a single identifier."""
        tokens = tokenize("inputs")
        assert tokens == ["inputs"]

    def test_multiple_word_identifier(self) -> None:
        """Tokenize identifier with underscores."""
        tokens = tokenize("dry_run")
        assert tokens == ["dry_run"]

    def test_identifier_with_numbers(self) -> None:
        """Tokenize identifier containing numbers."""
        tokens = tokenize("step123")
        assert tokens == ["step123"]

    def test_identifier_starting_with_underscore(self) -> None:
        """Tokenize identifier starting with underscore."""
        tokens = tokenize("_private")
        assert tokens == ["_private"]


class TestTokenizeDotSeparatedPaths:
    """Test tokenizing dot-separated access paths."""

    def test_simple_dot_path(self) -> None:
        """Tokenize simple two-part dot path."""
        tokens = tokenize("inputs.name")
        assert tokens == ["inputs", ".", "name"]

    def test_three_part_dot_path(self) -> None:
        """Tokenize three-part dot path."""
        tokens = tokenize("steps.analyze.output")
        assert tokens == ["steps", ".", "analyze", ".", "output"]

    def test_four_part_dot_path(self) -> None:
        """Tokenize four-part nested field access."""
        tokens = tokenize("steps.x.output.field")
        assert tokens == ["steps", ".", "x", ".", "output", ".", "field"]

    def test_dot_path_with_underscores(self) -> None:
        """Tokenize dot path with underscored identifiers."""
        tokens = tokenize("inputs.user_name")
        assert tokens == ["inputs", ".", "user_name"]

    def test_dot_path_with_numbers(self) -> None:
        """Tokenize dot path with numbered identifiers."""
        tokens = tokenize("steps.step1.output")
        assert tokens == ["steps", ".", "step1", ".", "output"]


class TestTokenizeBracketNotation:
    """Test tokenizing bracket notation for array/object access."""

    def test_simple_array_index(self) -> None:
        """Tokenize simple array index access."""
        tokens = tokenize("items[0]")
        assert tokens == ["items", "[", "0", "]"]

    def test_array_index_with_dot_path(self) -> None:
        """Tokenize array index after dot path."""
        tokens = tokenize("steps.x.items[0]")
        assert tokens == ["steps", ".", "x", ".", "items", "[", "0", "]"]

    def test_nested_array_indices(self) -> None:
        """Tokenize nested array indices."""
        tokens = tokenize("matrix[0][1]")
        assert tokens == ["matrix", "[", "0", "]", "[", "1", "]"]

    def test_array_index_with_field_access(self) -> None:
        """Tokenize array index followed by field access."""
        tokens = tokenize("items[0].name")
        assert tokens == ["items", "[", "0", "]", ".", "name"]

    def test_string_key_in_brackets(self) -> None:
        """Tokenize string key in bracket notation."""
        tokens = tokenize("obj['key']")
        assert tokens == ["obj", "[", "'key'", "]"]

    def test_double_quoted_string_key(self) -> None:
        """Tokenize double-quoted string key in brackets."""
        tokens = tokenize('obj["key"]')
        assert tokens == ["obj", "[", '"key"', "]"]


class TestTokenizeNotOperator:
    """Test tokenizing the 'not' operator."""

    def test_not_with_simple_identifier(self) -> None:
        """Tokenize 'not' with simple identifier."""
        tokens = tokenize("not enabled")
        assert tokens == ["not", "enabled"]

    def test_not_with_dot_path(self) -> None:
        """Tokenize 'not' with dot-separated path."""
        tokens = tokenize("not inputs.dry_run")
        assert tokens == ["not", "inputs", ".", "dry_run"]

    def test_not_with_step_output(self) -> None:
        """Tokenize 'not' with step output reference."""
        tokens = tokenize("not steps.check.output")
        assert tokens == ["not", "steps", ".", "check", ".", "output"]

    def test_not_with_nested_field(self) -> None:
        """Tokenize 'not' with nested field access."""
        tokens = tokenize("not steps.x.output.success")
        assert tokens == ["not", "steps", ".", "x", ".", "output", ".", "success"]


class TestTokenizeWhitespace:
    """Test tokenizing with various whitespace patterns."""

    def test_leading_whitespace(self) -> None:
        """Tokenize with leading whitespace."""
        tokens = tokenize("  inputs.name")
        assert tokens == ["inputs", ".", "name"]

    def test_trailing_whitespace(self) -> None:
        """Tokenize with trailing whitespace."""
        tokens = tokenize("inputs.name  ")
        assert tokens == ["inputs", ".", "name"]

    def test_whitespace_around_dots(self) -> None:
        """Tokenize with whitespace around dots."""
        tokens = tokenize("inputs . name")
        assert tokens == ["inputs", ".", "name"]

    def test_multiple_spaces_between_tokens(self) -> None:
        """Tokenize with multiple spaces between tokens."""
        tokens = tokenize("not   inputs.name")
        assert tokens == ["not", "inputs", ".", "name"]

    def test_tabs_and_spaces(self) -> None:
        """Tokenize with tabs and spaces."""
        tokens = tokenize("\tinputs\t.\tname\t")
        assert tokens == ["inputs", ".", "name"]

    def test_whitespace_in_brackets(self) -> None:
        """Tokenize with whitespace inside brackets."""
        tokens = tokenize("items[ 0 ]")
        assert tokens == ["items", "[", "0", "]"]


class TestTokenizeInvalidSyntax:
    """Test tokenizer error handling for invalid syntax."""

    def test_empty_string(self) -> None:
        """Tokenize empty string returns empty list (validation at parse level)."""
        tokens = tokenize("")
        assert tokens == []

    def test_only_whitespace(self) -> None:
        """Tokenize whitespace-only string returns empty list."""
        tokens = tokenize("   ")
        assert tokens == []

    def test_starts_with_dot(self) -> None:
        """Tokenize expression starting with dot raises error."""
        with pytest.raises(ExpressionSyntaxError, match="cannot start with a dot"):
            tokenize(".name")

    def test_ends_with_dot(self) -> None:
        """Tokenize expression ending with dot raises error."""
        with pytest.raises(ExpressionSyntaxError, match="cannot end with a dot"):
            tokenize("inputs.")

    def test_consecutive_dots(self) -> None:
        """Tokenize consecutive dots raises error."""
        with pytest.raises(ExpressionSyntaxError, match="double dot"):
            tokenize("inputs..name")

    def test_unmatched_opening_bracket(self) -> None:
        """Tokenize unmatched opening bracket raises error."""
        with pytest.raises(ExpressionSyntaxError, match="Unclosed bracket"):
            tokenize("items[0")

    def test_unmatched_closing_bracket(self) -> None:
        """Tokenize unmatched closing bracket raises error."""
        with pytest.raises(ExpressionSyntaxError, match="Unmatched closing bracket"):
            tokenize("items0]")

    def test_empty_brackets(self) -> None:
        """Tokenize empty brackets raises error."""
        with pytest.raises(ExpressionSyntaxError, match="Invalid content in bracket"):
            tokenize("items[]")

    def test_invalid_character(self) -> None:
        """Tokenize invalid character raises error."""
        with pytest.raises(ExpressionSyntaxError, match="Invalid character"):
            tokenize("inputs@name")

    def test_unterminated_string_single_quote(self) -> None:
        """Tokenize unterminated single-quoted string raises error."""
        with pytest.raises(ExpressionSyntaxError, match="Unterminated string"):
            tokenize("obj['key]")

    def test_unterminated_string_double_quote(self) -> None:
        """Tokenize unterminated double-quoted string raises error."""
        with pytest.raises(ExpressionSyntaxError, match="Unterminated string"):
            tokenize('obj["key]')


class TestTokenizeEdgeCases:
    """Test tokenizer edge cases and corner cases."""

    def test_single_character_identifier(self) -> None:
        """Tokenize single character identifier."""
        tokens = tokenize("x")
        assert tokens == ["x"]

    def test_very_long_identifier(self) -> None:
        """Tokenize very long identifier."""
        long_id = "very_long_identifier_with_many_words_" + "a" * 100
        tokens = tokenize(long_id)
        assert tokens == [long_id]

    def test_deep_nesting(self) -> None:
        """Tokenize deeply nested path."""
        tokens = tokenize("a.b.c.d.e.f.g.h")
        expected = [
            "a",
            ".",
            "b",
            ".",
            "c",
            ".",
            "d",
            ".",
            "e",
            ".",
            "f",
            ".",
            "g",
            ".",
            "h",
        ]
        assert tokens == expected

    def test_mixed_access_patterns(self) -> None:
        """Tokenize mixed dot and bracket access."""
        tokens = tokenize("steps.x.items[0].data.values[1].name")
        expected = [
            "steps",
            ".",
            "x",
            ".",
            "items",
            "[",
            "0",
            "]",
            ".",
            "data",
            ".",
            "values",
            "[",
            "1",
            "]",
            ".",
            "name",
        ]
        assert tokens == expected

    def test_number_as_identifier(self) -> None:
        """Tokenize number-only string raises error.

        Identifiers can't start with numbers.
        """
        # Numbers cannot be standalone identifiers - they require brackets [0]
        with pytest.raises(ExpressionSyntaxError, match="Invalid character"):
            tokenize("123")

    def test_not_as_part_of_identifier(self) -> None:
        """Tokenize 'not' when it's part of a larger identifier."""
        # 'notify' should be treated as single identifier, not 'not' + 'ify'
        tokens = tokenize("notify")
        assert tokens == ["notify"]

    def test_not_with_no_space(self) -> None:
        """Tokenize 'not' followed directly by identifier.

        Treated as one identifier.
        """
        # 'notinputs' is a valid identifier (not keyword only when followed by space)
        tokens = tokenize("notinputs.name")
        assert tokens == ["notinputs", ".", "name"]


class TestTokenizeRealWorldExamples:
    """Test tokenizer with real-world expression examples."""

    def test_input_reference(self) -> None:
        """Tokenize typical input reference."""
        tokens = tokenize("inputs.repository_name")
        assert tokens == ["inputs", ".", "repository_name"]

    def test_step_output_reference(self) -> None:
        """Tokenize typical step output reference."""
        tokens = tokenize("steps.analyze.output")
        assert tokens == ["steps", ".", "analyze", ".", "output"]

    def test_nested_step_output(self) -> None:
        """Tokenize nested step output field."""
        tokens = tokenize("steps.fetch_data.output.results")
        assert tokens == ["steps", ".", "fetch_data", ".", "output", ".", "results"]

    def test_negated_input(self) -> None:
        """Tokenize negated input reference."""
        tokens = tokenize("not inputs.skip_tests")
        assert tokens == ["not", "inputs", ".", "skip_tests"]

    def test_array_item_from_step(self) -> None:
        """Tokenize array item access from step output."""
        tokens = tokenize("steps.list_files.output[0]")
        assert tokens == ["steps", ".", "list_files", ".", "output", "[", "0", "]"]

    def test_complex_nested_access(self) -> None:
        """Tokenize complex nested field and array access."""
        tokens = tokenize("steps.api_call.output.data.items[0].id")
        assert tokens == [
            "steps",
            ".",
            "api_call",
            ".",
            "output",
            ".",
            "data",
            ".",
            "items",
            "[",
            "0",
            "]",
            ".",
            "id",
        ]


class TestTokenizePositionTracking:
    """Test that tokenizer tracks positions for error reporting."""

    def test_error_position_for_invalid_char(self) -> None:
        """Test error position is reported for invalid character."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            tokenize("inputs@name")

        # Position should point to the '@' character (position 6)
        assert exc_info.value.position == 6

    def test_error_position_for_trailing_dot(self) -> None:
        """Test error position for trailing dot."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            tokenize("inputs.name.")

        # Position should point to the trailing dot
        assert exc_info.value.position == 11

    def test_error_position_for_consecutive_dots(self) -> None:
        """Test error position for consecutive dots."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            tokenize("inputs..name")

        # Position should point to second dot
        assert exc_info.value.position == 7

    def test_error_position_for_unmatched_bracket(self) -> None:
        """Test error position for unmatched bracket."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            tokenize("items[0")

        # Position should point to the opening bracket or end
        assert exc_info.value.position > 0


class TestTokenizeSpecialCases:
    """Test tokenizer special cases and boundary conditions."""

    def test_keyword_not_case_sensitive(self) -> None:
        """Test 'not' keyword is case-sensitive."""
        # 'NOT' should be treated as identifier, not operator
        tokens = tokenize("NOT")
        assert tokens == ["NOT"]

    def test_not_followed_by_bracket(self) -> None:
        """Test 'not' followed by bracket notation."""
        tokens = tokenize("not items[0]")
        assert tokens == ["not", "items", "[", "0", "]"]

    def test_underscore_only_identifier(self) -> None:
        """Test single underscore as identifier."""
        tokens = tokenize("_")
        assert tokens == ["_"]

    def test_multiple_underscores_identifier(self) -> None:
        """Test multiple underscores as identifier."""
        tokens = tokenize("___")
        assert tokens == ["___"]

    def test_identifier_ending_with_numbers(self) -> None:
        """Test identifier ending with numbers."""
        tokens = tokenize("step123.output456")
        assert tokens == ["step123", ".", "output456"]

    def test_unicode_in_identifier(self) -> None:
        """Test Unicode characters in identifier (allowed by Python's isalpha)."""
        # Python's isalpha() includes unicode letters
        tokens = tokenize("inputsα.name")
        assert tokens == ["inputsα", ".", "name"]

    def test_bracket_with_negative_index(self) -> None:
        """Test bracket notation with negative index."""
        tokens = tokenize("items[-1]")
        # This might be supported for Python-style negative indexing
        assert tokens == ["items", "[", "-1", "]"]

    def test_nested_brackets_with_strings(self) -> None:
        """Test nested object access with string keys."""
        tokens = tokenize("obj['outer']['inner']")
        assert tokens == ["obj", "[", "'outer'", "]", "[", "'inner'", "]"]


# ============================================================================
# Parser Tests (T017b)
# ============================================================================


class TestParseExpressionBasicInputs:
    """Test suite for parsing basic input references."""

    def test_parse_simple_input_reference(self) -> None:
        """Test parsing simple input reference: inputs.name."""
        result = parse_expression("inputs.name")

        assert isinstance(result, Expression)
        assert result.kind == ExpressionKind.INPUT_REF
        assert result.path == ("inputs", "name")
        assert result.negated is False
        assert result.raw == "inputs.name"

    def test_parse_input_reference_with_wrapper(self) -> None:
        """Test parsing input reference with ${{ }} wrapper."""
        result = parse_expression("${{ inputs.name }}")

        assert isinstance(result, Expression)
        assert result.kind == ExpressionKind.INPUT_REF
        assert result.path == ("inputs", "name")
        assert result.negated is False
        assert result.raw == "${{ inputs.name }}"

    def test_parse_input_reference_with_extra_whitespace(self) -> None:
        """Test parsing input reference with extra whitespace."""
        result = parse_expression("${{  inputs.name  }}")

        assert isinstance(result, Expression)
        assert result.kind == ExpressionKind.INPUT_REF
        assert result.path == ("inputs", "name")
        assert result.negated is False

    def test_parse_input_reference_multipart_name(self) -> None:
        """Test parsing input with multi-part identifier like dry_run."""
        result = parse_expression("inputs.dry_run")

        assert result.kind == ExpressionKind.INPUT_REF
        assert result.path == ("inputs", "dry_run")
        assert result.negated is False

    def test_parse_input_reference_with_numbers(self) -> None:
        """Test parsing input with numbers in identifier."""
        result = parse_expression("inputs.option_1")

        assert result.kind == ExpressionKind.INPUT_REF
        assert result.path == ("inputs", "option_1")


class TestParseExpressionBasicSteps:
    """Test suite for parsing basic step references."""

    def test_parse_simple_step_reference(self) -> None:
        """Test parsing simple step reference: steps.x.output."""
        result = parse_expression("steps.x.output")

        assert isinstance(result, Expression)
        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == ("steps", "x", "output")
        assert result.negated is False
        assert result.raw == "steps.x.output"

    def test_parse_step_reference_with_wrapper(self) -> None:
        """Test parsing step reference with ${{ }} wrapper."""
        result = parse_expression("${{ steps.build.output }}")

        assert isinstance(result, Expression)
        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == ("steps", "build", "output")
        assert result.negated is False

    def test_parse_step_reference_long_id(self) -> None:
        """Test parsing step with long underscore-separated ID."""
        result = parse_expression("steps.run_validation_tests.output")

        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == ("steps", "run_validation_tests", "output")

    def test_parse_step_reference_with_numbers(self) -> None:
        """Test parsing step with numbers in ID."""
        result = parse_expression("steps.step_123.output")

        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == ("steps", "step_123", "output")


class TestParseExpressionNestedPaths:
    """Test suite for parsing nested field access."""

    def test_parse_step_nested_output_field(self) -> None:
        """Test parsing step output with nested field access."""
        result = parse_expression("steps.x.output.field")

        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == ("steps", "x", "output", "field")
        assert result.negated is False

    def test_parse_step_deeply_nested_output(self) -> None:
        """Test parsing step output with deeply nested fields."""
        result = parse_expression("steps.x.output.metadata.version")

        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == ("steps", "x", "output", "metadata", "version")

    def test_parse_step_nested_with_underscores(self) -> None:
        """Test parsing nested fields with underscores."""
        result = parse_expression("steps.my_step.output.error_code")

        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == ("steps", "my_step", "output", "error_code")

    def test_parse_step_very_deep_nesting(self) -> None:
        """Test parsing very deeply nested field access."""
        result = parse_expression("steps.x.output.a.b.c.d.e")

        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == ("steps", "x", "output", "a", "b", "c", "d", "e")


class TestParseExpressionNegation:
    """Test suite for parsing negated expressions."""

    def test_parse_negated_input(self) -> None:
        """Test parsing negated input: not inputs.dry_run."""
        result = parse_expression("not inputs.dry_run")

        assert result.kind == ExpressionKind.INPUT_REF
        assert result.path == ("inputs", "dry_run")
        assert result.negated is True
        assert result.raw == "not inputs.dry_run"

    def test_parse_negated_input_with_wrapper(self) -> None:
        """Test parsing negated input with ${{ }} wrapper."""
        result = parse_expression("${{ not inputs.enabled }}")

        assert result.kind == ExpressionKind.INPUT_REF
        assert result.path == ("inputs", "enabled")
        assert result.negated is True

    def test_parse_negated_step(self) -> None:
        """Test parsing negated step reference."""
        result = parse_expression("not steps.check.output")

        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == ("steps", "check", "output")
        assert result.negated is True

    def test_parse_negated_with_extra_whitespace(self) -> None:
        """Test parsing negated expression with extra whitespace."""
        result = parse_expression("${{  not   inputs.flag  }}")

        assert result.kind == ExpressionKind.INPUT_REF
        assert result.path == ("inputs", "flag")
        assert result.negated is True

    def test_parse_negated_nested_field(self) -> None:
        """Test parsing negated reference with nested field."""
        result = parse_expression("not steps.x.output.success")

        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == ("steps", "x", "output", "success")
        assert result.negated is True


class TestParseExpressionEdgeCases:
    """Test suite for edge cases and special scenarios."""

    def test_parse_empty_wrapper(self) -> None:
        """Test parsing empty ${{ }} raises error."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("${{ }}")

        err_msg = str(exc_info.value).lower()
        assert "empty" in err_msg or "missing" in err_msg

    def test_parse_only_whitespace(self) -> None:
        """Test parsing only whitespace raises error."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("${{    }}")

        assert exc_info.value.expression

    def test_parse_empty_string(self) -> None:
        """Test parsing empty string raises error."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("")

        assert exc_info.value.expression == ""

    def test_parse_single_identifier(self) -> None:
        """Test parsing single identifier without dots raises error."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("inputs")

        assert exc_info.value.expression == "inputs"

    def test_parse_wrapper_only_left(self) -> None:
        """Test parsing with only opening ${{ is treated as raw expression with $."""
        # Without closing }}, the ${{ is treated as part of expression text
        # The $ is an invalid character in identifiers
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("${{ inputs.name")

        # Error is about invalid character '$' since it's not recognized as wrapper
        assert "invalid character" in str(exc_info.value).lower()

    def test_parse_wrapper_only_right(self) -> None:
        """Test parsing with only closing }} raises error."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("inputs.name }}")

        assert exc_info.value.expression

    def test_parse_mismatched_wrapper(self) -> None:
        """Test parsing with mismatched wrapper raises error."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("${ inputs.name }}")

        assert exc_info.value.expression


class TestParseExpressionInvalidSyntax:
    """Test suite for invalid syntax detection."""

    def test_parse_invalid_prefix(self) -> None:
        """Test parsing with invalid prefix (not inputs/steps)."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("outputs.name")

        assert exc_info.value.expression == "outputs.name"
        err_msg = str(exc_info.value).lower()
        assert "inputs" in err_msg or "steps" in err_msg

    def test_parse_trailing_dot(self) -> None:
        """Test parsing with trailing dot raises error."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("inputs.name.")

        assert exc_info.value.expression == "inputs.name."

    def test_parse_double_dot(self) -> None:
        """Test parsing with double dot raises error."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("inputs..name")

        assert exc_info.value.expression == "inputs..name"

    def test_parse_leading_dot(self) -> None:
        """Test parsing with leading dot raises error."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression(".inputs.name")

        assert exc_info.value.expression == ".inputs.name"

    def test_parse_invalid_step_no_output(self) -> None:
        """Test parsing step reference without 'output' field raises error."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("steps.x")

        assert exc_info.value.expression == "steps.x"
        # Step references must have at least steps.id.output
        err_msg = str(exc_info.value).lower()
        assert "output" in err_msg or "minimum" in err_msg

    def test_parse_step_wrong_second_level(self) -> None:
        """Test parsing step reference with invalid second-level field."""
        # Only 'output' is valid as second field after step ID
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("steps.x.result")

        assert exc_info.value.expression == "steps.x.result"

    def test_parse_invalid_identifier_chars(self) -> None:
        """Test parsing with invalid characters in identifier."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("inputs.my-name")

        assert exc_info.value.expression == "inputs.my-name"

    def test_parse_identifier_starts_with_number(self) -> None:
        """Test parsing identifier starting with number raises error."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("inputs.123name")

        assert exc_info.value.expression == "inputs.123name"

    def test_parse_double_negation(self) -> None:
        """Test parsing double negation raises error."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("not not inputs.flag")

        assert exc_info.value.expression == "not not inputs.flag"

    def test_parse_negation_at_end(self) -> None:
        """Test parsing 'not' at end is treated as path element."""
        # 'not' at end is a valid identifier, so it becomes part of the path
        result = parse_expression("inputs.flag.not")

        assert result.path == ("inputs", "flag", "not")
        assert result.negated is False  # 'not' is not at start


class TestParseExpressionErrorPositions:
    """Test suite for error position reporting."""

    def test_error_position_invalid_prefix(self) -> None:
        """Test that error position is reported for invalid prefix."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("outputs.name")

        # Position should be set (exact value depends on implementation)
        assert hasattr(exc_info.value, "position")
        assert isinstance(exc_info.value.position, int)

    def test_error_position_trailing_dot(self) -> None:
        """Test that error position is reported for trailing dot."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("inputs.name.")

        assert hasattr(exc_info.value, "position")
        # Position should be near the trailing dot
        assert exc_info.value.position > 0

    def test_error_position_invalid_char(self) -> None:
        """Test that error position is reported for invalid character."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("inputs.my-name")

        assert hasattr(exc_info.value, "position")
        # Position should point to the hyphen
        assert exc_info.value.position > 0

    def test_error_message_includes_position(self) -> None:
        """Test that error message includes position indicator."""
        with pytest.raises(ExpressionSyntaxError) as exc_info:
            parse_expression("inputs.bad-char")

        error_str = str(exc_info.value)
        # Error should mention position
        assert "position" in error_str.lower() or "^" in error_str


class TestParseExpressionTypeChecking:
    """Test suite for type checking and return types."""

    def test_parse_returns_expression_instance(self) -> None:
        """Test that parse_expression returns Expression instance."""
        result = parse_expression("inputs.name")

        assert isinstance(result, Expression)
        assert hasattr(result, "raw")
        assert hasattr(result, "kind")
        assert hasattr(result, "path")
        assert hasattr(result, "negated")

    def test_parsed_expression_is_frozen(self) -> None:
        """Test that returned Expression is immutable (frozen dataclass)."""
        result = parse_expression("inputs.name")

        # FrozenInstanceError or dataclasses.FrozenInstanceError
        with pytest.raises((AttributeError, TypeError)):
            result.kind = ExpressionKind.STEP_REF  # type: ignore[misc]

    def test_expression_kind_is_enum(self) -> None:
        """Test that expression kind is ExpressionKind enum."""
        result = parse_expression("inputs.name")

        assert isinstance(result.kind, ExpressionKind)
        assert result.kind in (ExpressionKind.INPUT_REF, ExpressionKind.STEP_REF)

    def test_expression_path_is_tuple(self) -> None:
        """Test that expression path is a tuple of strings."""
        result = parse_expression("inputs.name")

        assert isinstance(result.path, tuple)
        assert all(isinstance(part, str) for part in result.path)

    def test_expression_negated_is_bool(self) -> None:
        """Test that expression negated field is boolean."""
        result = parse_expression("inputs.name")

        assert isinstance(result.negated, bool)
        assert result.negated in (True, False)


class TestParseExpressionRawField:
    """Test suite for the raw field preservation."""

    def test_raw_field_preserves_wrapper(self) -> None:
        """Test that raw field preserves ${{ }} wrapper."""
        result = parse_expression("${{ inputs.name }}")

        assert result.raw == "${{ inputs.name }}"

    def test_raw_field_without_wrapper(self) -> None:
        """Test that raw field is set when no wrapper present."""
        result = parse_expression("inputs.name")

        assert result.raw == "inputs.name"

    def test_raw_field_preserves_whitespace(self) -> None:
        """Test that raw field preserves original whitespace."""
        result = parse_expression("${{  inputs.name  }}")

        # Raw should preserve the exact input
        assert result.raw == "${{  inputs.name  }}"

    def test_raw_field_with_negation(self) -> None:
        """Test that raw field preserves 'not' keyword."""
        result = parse_expression("not inputs.flag")

        assert result.raw == "not inputs.flag"

    def test_raw_field_with_wrapper_and_negation(self) -> None:
        """Test that raw field preserves wrapper and negation."""
        result = parse_expression("${{ not inputs.enabled }}")

        assert result.raw == "${{ not inputs.enabled }}"


class TestParseExpressionComprehensive:
    """Comprehensive test cases covering complex scenarios."""

    def test_parse_all_input_variations(self) -> None:
        """Test parsing various valid input references."""
        test_cases = [
            ("inputs.a", ("inputs", "a")),
            ("inputs.my_var", ("inputs", "my_var")),
            ("inputs.var_123", ("inputs", "var_123")),
            ("inputs.camelCase", ("inputs", "camelCase")),
        ]

        for expr, expected_path in test_cases:
            result = parse_expression(expr)
            assert result.kind == ExpressionKind.INPUT_REF
            assert result.path == expected_path
            assert result.negated is False

    def test_parse_all_step_variations(self) -> None:
        """Test parsing various valid step references."""
        test_cases = [
            ("steps.a.output", ("steps", "a", "output")),
            ("steps.my_step.output", ("steps", "my_step", "output")),
            ("steps.step_1.output", ("steps", "step_1", "output")),
            ("steps.x.output.field", ("steps", "x", "output", "field")),
            ("steps.x.output.a.b", ("steps", "x", "output", "a", "b")),
        ]

        for expr, expected_path in test_cases:
            result = parse_expression(expr)
            assert result.kind == ExpressionKind.STEP_REF
            assert result.path == expected_path
            assert result.negated is False

    def test_parse_wrapper_variations(self) -> None:
        """Test parsing with different wrapper styles."""
        expressions = [
            "inputs.name",
            "${{ inputs.name }}",
            "${{inputs.name}}",
            "${{  inputs.name  }}",
        ]

        for expr in expressions:
            result = parse_expression(expr)
            assert result.kind == ExpressionKind.INPUT_REF
            assert result.path == ("inputs", "name")

    def test_parse_negation_variations(self) -> None:
        """Test parsing with different negation styles."""
        expressions = [
            "not inputs.flag",
            "${{ not inputs.flag }}",
            "${{not inputs.flag}}",
            "${{  not  inputs.flag  }}",
        ]

        for expr in expressions:
            result = parse_expression(expr)
            assert result.kind == ExpressionKind.INPUT_REF
            assert result.negated is True


class TestParseExpressionDocumentation:
    """Test cases matching documentation examples."""

    def test_example_inputs_name(self) -> None:
        """Test parsing example from docstring: inputs.name."""
        result = parse_expression("${{ inputs.name }}")

        assert result.kind == ExpressionKind.INPUT_REF
        assert result.path == ("inputs", "name")
        assert result.negated is False

    def test_example_steps_x_output(self) -> None:
        """Test parsing example from docstring: steps.x.output."""
        result = parse_expression("${{ steps.x.output }}")

        assert result.kind == ExpressionKind.STEP_REF
        assert result.path == ("steps", "x", "output")
        assert result.negated is False

    def test_example_not_inputs_condition(self) -> None:
        """Test parsing example from docstring: not inputs.condition."""
        result = parse_expression("${{ not inputs.condition }}")

        assert result.kind == ExpressionKind.INPUT_REF
        assert result.path == ("inputs", "condition")
        assert result.negated is True


class TestParseExpressionIterationVariables:
    """Test parsing iteration variables (item and index) for for_each loops."""

    def test_parse_item_simple(self) -> None:
        """Test parsing simple item reference."""
        result = parse_expression("${{ item }}")

        assert result.kind == ExpressionKind.ITEM_REF
        assert result.path == ("item",)
        assert result.negated is False

    def test_parse_item_with_field(self) -> None:
        """Test parsing item reference with nested field access."""
        result = parse_expression("${{ item.name }}")

        assert result.kind == ExpressionKind.ITEM_REF
        assert result.path == ("item", "name")
        assert result.negated is False

    def test_parse_item_with_deep_nesting(self) -> None:
        """Test parsing item reference with deeply nested fields."""
        result = parse_expression("${{ item.user.profile.email }}")

        assert result.kind == ExpressionKind.ITEM_REF
        assert result.path == ("item", "user", "profile", "email")
        assert result.negated is False

    def test_parse_item_with_array_index(self) -> None:
        """Test parsing item reference with array index."""
        result = parse_expression("${{ item[0] }}")

        assert result.kind == ExpressionKind.ITEM_REF
        assert result.path == ("item", "0")
        assert result.negated is False

    def test_parse_index_simple(self) -> None:
        """Test parsing simple index reference."""
        result = parse_expression("${{ index }}")

        assert result.kind == ExpressionKind.INDEX_REF
        assert result.path == ("index",)
        assert result.negated is False

    def test_parse_index_with_field_raises_error(self) -> None:
        """Test that index with field access raises error."""
        with pytest.raises(
            ExpressionSyntaxError,
            match="Index reference must be a single element",
        ):
            parse_expression("${{ index.field }}")

    def test_parse_negated_item(self) -> None:
        """Test parsing negated item reference."""
        result = parse_expression("${{ not item }}")

        assert result.kind == ExpressionKind.ITEM_REF
        assert result.path == ("item",)
        assert result.negated is True

    def test_parse_item_without_wrapper(self) -> None:
        """Test parsing item reference without ${{ }} wrapper."""
        result = parse_expression("item")

        assert result.kind == ExpressionKind.ITEM_REF
        assert result.path == ("item",)
        assert result.negated is False

    def test_parse_index_without_wrapper(self) -> None:
        """Test parsing index reference without ${{ }} wrapper."""
        result = parse_expression("index")

        assert result.kind == ExpressionKind.INDEX_REF
        assert result.path == ("index",)
        assert result.negated is False


# ============================================================================
# Ternary Expression Parser Tests (Issue #194)
# ============================================================================


class TestParseTernaryExpressionBasic:
    """Test parsing basic ternary expressions."""

    def test_parse_simple_ternary(self) -> None:
        """Test parsing simple ternary: a if b else c."""
        result = parse_expression("inputs.a if inputs.b else inputs.c")

        assert isinstance(result, TernaryExpression)
        assert result.raw == "inputs.a if inputs.b else inputs.c"

        # Check condition
        assert isinstance(result.condition, Expression)
        assert result.condition.kind == ExpressionKind.INPUT_REF
        assert result.condition.path == ("inputs", "b")

        # Check value_if_true
        assert isinstance(result.value_if_true, Expression)
        assert result.value_if_true.kind == ExpressionKind.INPUT_REF
        assert result.value_if_true.path == ("inputs", "a")

        # Check value_if_false
        assert isinstance(result.value_if_false, Expression)
        assert result.value_if_false.kind == ExpressionKind.INPUT_REF
        assert result.value_if_false.path == ("inputs", "c")

    def test_parse_ternary_with_wrapper(self) -> None:
        """Test parsing ternary with ${{ }} wrapper."""
        result = parse_expression("${{ inputs.x if inputs.y else inputs.z }}")

        assert isinstance(result, TernaryExpression)
        assert result.raw == "${{ inputs.x if inputs.y else inputs.z }}"

    def test_parse_ternary_with_step_refs(self) -> None:
        """Test parsing ternary with step references."""
        result = parse_expression(
            "steps.a.output if steps.b.output else steps.c.output"
        )

        assert isinstance(result, TernaryExpression)

        assert isinstance(result.condition, Expression)
        assert result.condition.kind == ExpressionKind.STEP_REF
        assert result.condition.path == ("steps", "b", "output")

        assert isinstance(result.value_if_true, Expression)
        assert result.value_if_true.kind == ExpressionKind.STEP_REF
        assert result.value_if_true.path == ("steps", "a", "output")

        assert isinstance(result.value_if_false, Expression)
        assert result.value_if_false.kind == ExpressionKind.STEP_REF
        assert result.value_if_false.path == ("steps", "c", "output")

    def test_parse_ternary_mixed_refs(self) -> None:
        """Test parsing ternary with mixed reference types."""
        result = parse_expression(
            "inputs.title if inputs.title else steps.generate_title.output"
        )

        assert isinstance(result, TernaryExpression)

        assert isinstance(result.value_if_true, Expression)
        assert result.value_if_true.kind == ExpressionKind.INPUT_REF

        assert isinstance(result.condition, Expression)
        assert result.condition.kind == ExpressionKind.INPUT_REF

        assert isinstance(result.value_if_false, Expression)
        assert result.value_if_false.kind == ExpressionKind.STEP_REF


class TestParseTernaryWithNegation:
    """Test parsing ternary expressions with negation."""

    def test_parse_ternary_with_negated_condition(self) -> None:
        """Test parsing ternary with negated condition: a if not b else c."""
        result = parse_expression("inputs.a if not inputs.b else inputs.c")

        assert isinstance(result, TernaryExpression)

        assert isinstance(result.condition, Expression)
        assert result.condition.negated is True
        assert result.condition.path == ("inputs", "b")

    def test_parse_ternary_with_negated_true_value(self) -> None:
        """Test parsing ternary with negated value_if_true."""
        result = parse_expression("not inputs.a if inputs.b else inputs.c")

        assert isinstance(result, TernaryExpression)

        assert isinstance(result.value_if_true, Expression)
        assert result.value_if_true.negated is True

    def test_parse_ternary_with_negated_false_value(self) -> None:
        """Test parsing ternary with negated value_if_false."""
        result = parse_expression("inputs.a if inputs.b else not inputs.c")

        assert isinstance(result, TernaryExpression)

        assert isinstance(result.value_if_false, Expression)
        assert result.value_if_false.negated is True


class TestParseTernaryWithBooleanOperators:
    """Test parsing ternary expressions with boolean operators."""

    def test_parse_ternary_with_and_condition(self) -> None:
        """Test parsing ternary with 'and' in condition."""
        result = parse_expression("inputs.a if inputs.b and inputs.c else inputs.d")

        assert isinstance(result, TernaryExpression)
        # Condition should be a BooleanExpression with 'and'
        from maverick.dsl.expressions.parser import BooleanExpression

        assert isinstance(result.condition, BooleanExpression)
        assert result.condition.operator == "and"
        assert len(result.condition.operands) == 2

    def test_parse_ternary_with_or_condition(self) -> None:
        """Test parsing ternary with 'or' in condition."""
        result = parse_expression("inputs.a if inputs.b or inputs.c else inputs.d")

        assert isinstance(result, TernaryExpression)
        from maverick.dsl.expressions.parser import BooleanExpression

        assert isinstance(result.condition, BooleanExpression)
        assert result.condition.operator == "or"


class TestParseTernaryNested:
    """Test parsing nested ternary expressions."""

    def test_parse_nested_ternary_right(self) -> None:
        """Test parsing right-nested ternary: a if b else c if d else e."""
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

        # value_if_false should be another TernaryExpression
        assert isinstance(result.value_if_false, TernaryExpression)
        nested = result.value_if_false

        assert isinstance(nested.value_if_true, Expression)
        assert nested.value_if_true.path == ("inputs", "c")

        assert isinstance(nested.condition, Expression)
        assert nested.condition.path == ("inputs", "d")

        assert isinstance(nested.value_if_false, Expression)
        assert nested.value_if_false.path == ("inputs", "e")


class TestParseTernaryWithIterationVariables:
    """Test parsing ternary expressions with item and index."""

    def test_parse_ternary_with_item(self) -> None:
        """Test parsing ternary with item reference."""
        result = parse_expression("item.name if item.valid else item.fallback")

        assert isinstance(result, TernaryExpression)

        assert isinstance(result.value_if_true, Expression)
        assert result.value_if_true.kind == ExpressionKind.ITEM_REF

        assert isinstance(result.condition, Expression)
        assert result.condition.kind == ExpressionKind.ITEM_REF

        assert isinstance(result.value_if_false, Expression)
        assert result.value_if_false.kind == ExpressionKind.ITEM_REF

    def test_parse_ternary_with_index(self) -> None:
        """Test parsing ternary with index reference in condition."""
        result = parse_expression("inputs.first if not index else item")

        assert isinstance(result, TernaryExpression)

        # Condition should be negated index
        assert isinstance(result.condition, Expression)
        assert result.condition.kind == ExpressionKind.INDEX_REF
        assert result.condition.negated is True


class TestParseTernaryEdgeCases:
    """Test edge cases for ternary expression parsing."""

    def test_parse_ternary_preserves_raw(self) -> None:
        """Test that raw field preserves original expression."""
        expr_str = "${{ inputs.a if inputs.b else inputs.c }}"
        result = parse_expression(expr_str)

        assert isinstance(result, TernaryExpression)
        assert result.raw == expr_str

    def test_parse_ternary_with_extra_whitespace(self) -> None:
        """Test parsing ternary with extra whitespace."""
        result = parse_expression("${{  inputs.a  if  inputs.b  else  inputs.c  }}")

        assert isinstance(result, TernaryExpression)

    def test_parse_ternary_is_frozen(self) -> None:
        """Test that TernaryExpression is immutable (frozen dataclass)."""
        result = parse_expression("inputs.a if inputs.b else inputs.c")

        assert isinstance(result, TernaryExpression)
        with pytest.raises((AttributeError, TypeError)):
            result.condition = None  # type: ignore[misc]

    def test_parse_non_ternary_still_works(self) -> None:
        """Test that non-ternary expressions still parse correctly."""
        result = parse_expression("inputs.name")

        assert isinstance(result, Expression)
        assert result.kind == ExpressionKind.INPUT_REF
        assert result.path == ("inputs", "name")
