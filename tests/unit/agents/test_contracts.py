"""Unit tests for maverick.agents.contracts."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from maverick.agents.contracts import OutputValidationError, validate_output
from maverick.exceptions.base import MaverickError

# ---------------------------------------------------------------------------
# Test model
# ---------------------------------------------------------------------------


class SampleModel(BaseModel):
    name: str
    value: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap_json(data: dict, *, lang: str = "json") -> str:
    """Wrap a dict in a markdown code block."""
    tag = lang if lang else ""
    return f"```{tag}\n{json.dumps(data)}\n```"


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestValidateOutputHappyPath:
    """Tests for successful extraction + parsing + validation."""

    def test_valid_json_code_block_returns_model(self) -> None:
        raw = _wrap_json({"name": "alice", "value": 42})
        result = validate_output(raw, SampleModel)
        assert isinstance(result, SampleModel)
        assert result.name == "alice"
        assert result.value == 42

    def test_code_block_surrounded_by_prose(self) -> None:
        raw = (
            "Here is the result:\n\n"
            + _wrap_json({"name": "bob", "value": 7})
            + "\n\nDone."
        )
        result = validate_output(raw, SampleModel)
        assert result is not None
        assert result.name == "bob"
        assert result.value == 7

    def test_code_block_without_json_language_tag(self) -> None:
        """A code block with just ``` (no json tag) should still be matched."""
        raw = "```\n" + json.dumps({"name": "carol", "value": 99}) + "\n```"
        result = validate_output(raw, SampleModel)
        assert result is not None
        assert result.name == "carol"
        assert result.value == 99

    def test_multiple_code_blocks_first_wins(self) -> None:
        first = {"name": "first", "value": 1}
        second = {"name": "second", "value": 2}
        raw = _wrap_json(first) + "\n\n" + _wrap_json(second)
        result = validate_output(raw, SampleModel)
        assert result is not None
        assert result.name == "first"
        assert result.value == 1

    def test_extra_whitespace_inside_code_block(self) -> None:
        raw = "```json\n  \n" + json.dumps({"name": "ws", "value": 0}) + "\n  \n```"
        result = validate_output(raw, SampleModel)
        assert result is not None
        assert result.name == "ws"

    def test_multiline_json_in_code_block(self) -> None:
        payload = json.dumps({"name": "multi", "value": 55}, indent=2)
        raw = f"```json\n{payload}\n```"
        result = validate_output(raw, SampleModel)
        assert result is not None
        assert result.name == "multi"
        assert result.value == 55


# ---------------------------------------------------------------------------
# Extraction failures (no code block found)
# ---------------------------------------------------------------------------


class TestExtractionFailure:
    """Tests for when no code block is found in the raw output."""

    def test_no_code_block_strict_raises(self) -> None:
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output("just plain text", SampleModel)
        err = exc_info.value
        assert err.stage == "extraction"
        assert err.expected_model == "SampleModel"
        assert "No " in err.parse_error

    def test_no_code_block_non_strict_returns_none(self) -> None:
        result = validate_output("just plain text", SampleModel, strict=False)
        assert result is None

    def test_empty_string_strict_raises_extraction(self) -> None:
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output("", SampleModel)
        assert exc_info.value.stage == "extraction"

    def test_empty_string_non_strict_returns_none(self) -> None:
        result = validate_output("", SampleModel, strict=False)
        assert result is None

    def test_backticks_without_newlines_not_matched(self) -> None:
        """Inline code (``` on same line) should NOT match the regex."""
        raw = '```{"name": "inline", "value": 1}```'
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output(raw, SampleModel)
        assert exc_info.value.stage == "extraction"


# ---------------------------------------------------------------------------
# JSON parse failures
# ---------------------------------------------------------------------------


class TestJsonParseFailure:
    """Tests for when the code block contains invalid JSON."""

    def test_invalid_json_strict_raises(self) -> None:
        raw = "```json\n{not valid json}\n```"
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output(raw, SampleModel)
        err = exc_info.value
        assert err.stage == "json_parse"
        assert "JSON parse error" in err.parse_error

    def test_invalid_json_non_strict_returns_none(self) -> None:
        raw = "```json\n{broken: json}\n```"
        result = validate_output(raw, SampleModel, strict=False)
        assert result is None

    def test_truncated_json_raises_json_parse(self) -> None:
        raw = '```json\n{"name": "trunc\n```'
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output(raw, SampleModel)
        assert exc_info.value.stage == "json_parse"

    def test_empty_code_block_raises_json_parse(self) -> None:
        """An empty code block body should fail at JSON parse, not extraction."""
        raw = "```json\n\n```"
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output(raw, SampleModel)
        assert exc_info.value.stage == "json_parse"


# ---------------------------------------------------------------------------
# Pydantic validation failures
# ---------------------------------------------------------------------------


class TestValidationFailure:
    """Tests for when JSON is valid but does not match the Pydantic model."""

    def test_schema_mismatch_strict_raises(self) -> None:
        raw = _wrap_json({"wrong_field": "oops"})
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output(raw, SampleModel)
        err = exc_info.value
        assert err.stage == "validation"
        assert "Pydantic validation error" in err.parse_error

    def test_schema_mismatch_non_strict_returns_none(self) -> None:
        raw = _wrap_json({"wrong_field": "oops"})
        result = validate_output(raw, SampleModel, strict=False)
        assert result is None

    def test_wrong_type_raises_validation(self) -> None:
        """Non-coercible str for int field should fail validation."""
        raw = _wrap_json({"name": "ok", "value": "not_an_int"})
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output(raw, SampleModel)
        assert exc_info.value.stage == "validation"

    def test_missing_required_field_raises_validation(self) -> None:
        raw = _wrap_json({"name": "only_name"})
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output(raw, SampleModel)
        assert exc_info.value.stage == "validation"

    def test_extra_fields_accepted_by_default(self) -> None:
        """Pydantic v2 ignores extra fields by default, so this should pass."""
        raw = _wrap_json({"name": "extra", "value": 10, "bonus": True})
        result = validate_output(raw, SampleModel)
        assert result is not None
        assert result.name == "extra"
        assert result.value == 10


# ---------------------------------------------------------------------------
# strict parameter behaviour
# ---------------------------------------------------------------------------


class TestStrictParameter:
    """Verify strict=True raises and strict=False returns None for each stage."""

    @pytest.mark.parametrize(
        ("raw", "expected_stage"),
        [
            ("no code block here", "extraction"),
            ("```json\n{invalid}\n```", "json_parse"),
            (_wrap_json({"wrong": True}), "validation"),
        ],
        ids=["extraction", "json_parse", "validation"],
    )
    def test_strict_true_raises_for_all_stages(
        self, raw: str, expected_stage: str
    ) -> None:
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output(raw, SampleModel, strict=True)
        assert exc_info.value.stage == expected_stage

    @pytest.mark.parametrize(
        "raw",
        [
            "no code block here",
            "```json\n{invalid}\n```",
            _wrap_json({"wrong": True}),
        ],
        ids=["extraction", "json_parse", "validation"],
    )
    def test_strict_false_returns_none_for_all_stages(self, raw: str) -> None:
        result = validate_output(raw, SampleModel, strict=False)
        assert result is None


# ---------------------------------------------------------------------------
# OutputValidationError attribute tests
# ---------------------------------------------------------------------------


class TestOutputValidationError:
    """Tests for OutputValidationError itself."""

    def test_inherits_from_maverick_error(self) -> None:
        err = OutputValidationError(
            expected_model="Foo",
            raw_output="bar",
            parse_error="boom",
            stage="extraction",
        )
        assert isinstance(err, MaverickError)

    def test_fields_populated_correctly(self) -> None:
        err = OutputValidationError(
            expected_model="MyModel",
            raw_output="the raw text",
            parse_error="something broke",
            stage="json_parse",
        )
        assert err.expected_model == "MyModel"
        assert err.raw_output == "the raw text"
        assert err.parse_error == "something broke"
        assert err.stage == "json_parse"

    def test_message_includes_stage_and_model(self) -> None:
        err = OutputValidationError(
            expected_model="MyModel",
            raw_output="x",
            parse_error="oops",
            stage="validation",
        )
        msg = str(err)
        assert "validation" in msg
        assert "MyModel" in msg
        assert "oops" in msg

    def test_raw_output_truncated_to_500_chars(self) -> None:
        long_text = "x" * 1000
        err = OutputValidationError(
            expected_model="M",
            raw_output=long_text,
            parse_error="p",
            stage="extraction",
        )
        assert len(err.raw_output) == 500
        assert err.raw_output == "x" * 500

    def test_raw_output_shorter_than_500_not_truncated(self) -> None:
        short_text = "abc"
        err = OutputValidationError(
            expected_model="M",
            raw_output=short_text,
            parse_error="p",
            stage="extraction",
        )
        assert err.raw_output == "abc"

    def test_raw_output_exactly_500_not_truncated(self) -> None:
        text_500 = "y" * 500
        err = OutputValidationError(
            expected_model="M",
            raw_output=text_500,
            parse_error="p",
            stage="extraction",
        )
        assert len(err.raw_output) == 500

    def test_error_raised_in_validate_output_has_truncated_raw(self) -> None:
        """Integration: validate_output populates raw_output with truncation."""
        long_raw = "a" * 1000
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output(long_raw, SampleModel)
        assert len(exc_info.value.raw_output) == 500


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and tricky inputs."""

    def test_nested_code_blocks_outer_wins(self) -> None:
        """When code blocks appear sequentially, the first match wins."""
        inner_json = json.dumps({"name": "inner", "value": 2})
        outer_json = json.dumps({"name": "outer", "value": 1})
        raw = f"```json\n{outer_json}\n```\n```json\n{inner_json}\n```"
        result = validate_output(raw, SampleModel)
        assert result is not None
        assert result.name == "outer"

    def test_code_block_with_leading_trailing_whitespace_in_json(self) -> None:
        raw = '```json\n   {"name": "spaces", "value": 3}   \n```'
        result = validate_output(raw, SampleModel)
        assert result is not None
        assert result.name == "spaces"

    def test_json_array_at_top_level_causes_validation_error(self) -> None:
        """A JSON array is valid JSON but not a valid Pydantic model input."""
        raw = "```json\n[1, 2, 3]\n```"
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output(raw, SampleModel)
        assert exc_info.value.stage == "validation"

    def test_json_with_unicode(self) -> None:
        raw = _wrap_json({"name": "caf\u00e9", "value": 42})
        result = validate_output(raw, SampleModel)
        assert result is not None
        assert result.name == "caf\u00e9"

    def test_json_with_nested_objects(self) -> None:
        """Model with nested structure validates correctly."""

        class Nested(BaseModel):
            child: SampleModel

        raw = _wrap_json({"child": {"name": "nested", "value": 5}})
        result = validate_output(raw, Nested)
        assert result is not None
        assert result.child.name == "nested"
        assert result.child.value == 5

    def test_code_block_with_only_whitespace_body(self) -> None:
        """Code block containing only whitespace should fail at json_parse."""
        raw = "```json\n   \n```"
        with pytest.raises(OutputValidationError) as exc_info:
            validate_output(raw, SampleModel)
        assert exc_info.value.stage == "json_parse"


# ---------------------------------------------------------------------------
# Import-validation: all output types available from contracts module (T026)
# ---------------------------------------------------------------------------


class TestContractsModuleReExports:
    """Verify all agent output types are importable from maverick.agents.contracts."""

    def test_all_output_types_importable_from_contracts(self) -> None:
        """Single import statement can access all output types."""
        from maverick.agents.contracts import (
            AgentResult,
            Finding,
            FindingGroup,
            FixerResult,
            FixOutcome,
            FixResult,
            GroupedReviewResult,
            ImplementationResult,
            OutputValidationError,
            ReviewFinding,
            ReviewResult,
            validate_output,
        )

        # Verify they are the canonical types (not stubs)
        assert AgentResult is not None
        assert Finding is not None
        assert FindingGroup is not None
        assert FixerResult is not None
        assert FixOutcome is not None
        assert FixResult is not None
        assert GroupedReviewResult is not None
        assert ImplementationResult is not None
        assert OutputValidationError is not None
        assert ReviewFinding is not None
        assert ReviewResult is not None
        assert validate_output is not None

    def test_contracts_all_list_complete(self) -> None:
        """__all__ contains every re-exported type."""
        import maverick.agents.contracts as contracts_mod

        expected = {
            "validate_output",
            "OutputValidationError",
            "AgentResult",
            "Finding",
            "FindingGroup",
            "FixerResult",
            "FixOutcome",
            "FixResult",
            "GroupedReviewResult",
            "ImplementationResult",
            "ReviewFinding",
            "ReviewResult",
        }
        assert set(contracts_mod.__all__) == expected

    def test_agents_with_output_model_set(self) -> None:
        """Agents that parse output from Claude have output_model wired."""
        from maverick.agents.fixer import FixerAgent
        from maverick.agents.reviewers.unified_reviewer import UnifiedReviewerAgent

        fixer = FixerAgent()
        assert fixer._output_model is not None
        assert fixer._output_model.__name__ == "FixerResult"

        reviewer = UnifiedReviewerAgent()
        assert reviewer._output_model is not None
        assert reviewer._output_model.__name__ == "GroupedReviewResult"
