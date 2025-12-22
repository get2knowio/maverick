"""Unit tests for DSL type definitions.

Tests for StepType enum and related type definitions.
"""

from __future__ import annotations

import pytest

from maverick.dsl import StepType


class TestStepType:
    """Test suite for StepType enum."""

    def test_all_enum_values_exist(self) -> None:
        """Test that all expected enum values are defined."""
        assert hasattr(StepType, "PYTHON")
        assert hasattr(StepType, "AGENT")
        assert hasattr(StepType, "GENERATE")
        assert hasattr(StepType, "VALIDATE")
        assert hasattr(StepType, "SUBWORKFLOW")

    def test_enum_values_are_strings(self) -> None:
        """Test that enum values are strings with expected values."""
        assert StepType.PYTHON == "python"
        assert StepType.AGENT == "agent"
        assert StepType.GENERATE == "generate"
        assert StepType.VALIDATE == "validate"
        assert StepType.SUBWORKFLOW == "subworkflow"

    def test_enum_values_match_expected_strings(self) -> None:
        """Test that .value attribute returns expected strings."""
        assert StepType.PYTHON.value == "python"
        assert StepType.AGENT.value == "agent"
        assert StepType.GENERATE.value == "generate"
        assert StepType.VALIDATE.value == "validate"
        assert StepType.SUBWORKFLOW.value == "subworkflow"

    def test_can_use_in_fstrings(self) -> None:
        """Test that enum values work correctly in f-strings."""
        step_type = StepType.PYTHON
        result = f"Step type: {step_type}"
        # StrEnum format varies by Python version:
        # - Python 3.10: returns the value ("python")
        # - Python 3.11+: returns "ClassName.MEMBER_NAME"
        assert "python" in result.lower()

        # Test with .value explicitly to get the string value
        result_explicit = f"Step type: {step_type.value}"
        assert result_explicit == "Step type: python"

    def test_can_use_in_comparisons(self) -> None:
        """Test that enum values work in equality comparisons."""
        assert StepType.PYTHON == StepType.PYTHON
        assert StepType.PYTHON != StepType.AGENT

        # Test comparison with string values
        assert StepType.PYTHON == "python"
        assert StepType.AGENT == "agent"
        assert StepType.PYTHON != "agent"

    def test_enum_iteration(self) -> None:
        """Test that all enum values can be iterated."""
        all_types = list(StepType)
        assert len(all_types) == 8
        assert StepType.PYTHON in all_types
        assert StepType.AGENT in all_types
        assert StepType.GENERATE in all_types
        assert StepType.VALIDATE in all_types
        assert StepType.SUBWORKFLOW in all_types
        assert StepType.BRANCH in all_types
        assert StepType.PARALLEL in all_types
        assert StepType.CHECKPOINT in all_types

    def test_enum_membership(self) -> None:
        """Test enum membership checks."""
        assert "python" in StepType._value2member_map_
        assert "agent" in StepType._value2member_map_
        assert "generate" in StepType._value2member_map_
        assert "validate" in StepType._value2member_map_
        assert "subworkflow" in StepType._value2member_map_
        assert "invalid" not in StepType._value2member_map_

    def test_enum_from_string_value(self) -> None:
        """Test creating enum instances from string values."""
        assert StepType("python") == StepType.PYTHON
        assert StepType("agent") == StepType.AGENT
        assert StepType("generate") == StepType.GENERATE
        assert StepType("validate") == StepType.VALIDATE
        assert StepType("subworkflow") == StepType.SUBWORKFLOW

    def test_invalid_enum_value_raises_error(self) -> None:
        """Test that invalid enum values raise ValueError."""
        with pytest.raises(ValueError):
            StepType("invalid")

    def test_enum_is_hashable(self) -> None:
        """Test that enum values can be used as dict keys."""
        mapping = {
            StepType.PYTHON: "Python step",
            StepType.AGENT: "Agent step",
        }
        assert mapping[StepType.PYTHON] == "Python step"
        assert mapping[StepType.AGENT] == "Agent step"
