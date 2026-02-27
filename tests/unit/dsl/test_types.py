"""Unit tests for DSL type definitions.

Tests for StepType enum and related type definitions.
"""

from __future__ import annotations

import pytest

from maverick.dsl import AutonomyLevel, StepMode, StepType


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
        assert StepType.LOOP in all_types
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


class TestStepMode:
    """Test suite for StepMode enum."""

    def test_all_enum_values_exist(self) -> None:
        """Test that all expected enum values are defined."""
        assert hasattr(StepMode, "DETERMINISTIC")
        assert hasattr(StepMode, "AGENT")

    def test_enum_values_are_strings(self) -> None:
        """Test that enum values are strings with expected values."""
        assert StepMode.DETERMINISTIC == "deterministic"
        assert StepMode.AGENT == "agent"

    def test_enum_from_string_value(self) -> None:
        """Test creating enum instances from string values."""
        assert StepMode("deterministic") == StepMode.DETERMINISTIC
        assert StepMode("agent") == StepMode.AGENT

    def test_invalid_enum_value_raises_error(self) -> None:
        """Test that invalid enum values raise ValueError."""
        with pytest.raises(ValueError):
            StepMode("invalid")

    def test_str_serialization(self) -> None:
        """Test that enum members work as strings for YAML serialization."""
        # .value must return the raw string for YAML round-tripping
        assert StepMode.DETERMINISTIC.value == "deterministic"
        assert StepMode.AGENT.value == "agent"

        # String comparison should work (StrEnum behaviour)
        assert StepMode.DETERMINISTIC == "deterministic"
        assert StepMode.AGENT == "agent"

    def test_enum_iteration(self) -> None:
        """Test that all enum values can be iterated."""
        all_modes = list(StepMode)
        assert len(all_modes) == 2
        assert StepMode.DETERMINISTIC in all_modes
        assert StepMode.AGENT in all_modes

    def test_enum_is_hashable(self) -> None:
        """Test that enum values can be used as dict keys."""
        mapping = {
            StepMode.DETERMINISTIC: "Deterministic step",
            StepMode.AGENT: "Agent step",
        }
        assert mapping[StepMode.DETERMINISTIC] == "Deterministic step"
        assert mapping[StepMode.AGENT] == "Agent step"


class TestAutonomyLevel:
    """Test suite for AutonomyLevel enum."""

    def test_all_enum_values_exist(self) -> None:
        """Test that all expected enum values are defined."""
        assert hasattr(AutonomyLevel, "OPERATOR")
        assert hasattr(AutonomyLevel, "COLLABORATOR")
        assert hasattr(AutonomyLevel, "CONSULTANT")
        assert hasattr(AutonomyLevel, "APPROVER")

    def test_enum_values_are_strings(self) -> None:
        """Test that enum values are strings with expected values."""
        assert AutonomyLevel.OPERATOR == "operator"
        assert AutonomyLevel.COLLABORATOR == "collaborator"
        assert AutonomyLevel.CONSULTANT == "consultant"
        assert AutonomyLevel.APPROVER == "approver"

    def test_enum_from_string_value(self) -> None:
        """Test creating enum instances from string values."""
        assert AutonomyLevel("operator") == AutonomyLevel.OPERATOR
        assert AutonomyLevel("collaborator") == AutonomyLevel.COLLABORATOR
        assert AutonomyLevel("consultant") == AutonomyLevel.CONSULTANT
        assert AutonomyLevel("approver") == AutonomyLevel.APPROVER

    def test_invalid_enum_value_raises_error(self) -> None:
        """Test that invalid enum values raise ValueError."""
        with pytest.raises(ValueError):
            AutonomyLevel("invalid")

    def test_str_serialization(self) -> None:
        """Test that enum members work as strings for YAML serialization."""
        # .value must return the raw string for YAML round-tripping
        assert AutonomyLevel.OPERATOR.value == "operator"
        assert AutonomyLevel.COLLABORATOR.value == "collaborator"
        assert AutonomyLevel.CONSULTANT.value == "consultant"
        assert AutonomyLevel.APPROVER.value == "approver"

        # String comparison should work (StrEnum behaviour)
        assert AutonomyLevel.OPERATOR == "operator"
        assert AutonomyLevel.COLLABORATOR == "collaborator"
        assert AutonomyLevel.CONSULTANT == "consultant"
        assert AutonomyLevel.APPROVER == "approver"

    def test_enum_iteration(self) -> None:
        """Test that all enum values can be iterated."""
        all_levels = list(AutonomyLevel)
        assert len(all_levels) == 4
        assert AutonomyLevel.OPERATOR in all_levels
        assert AutonomyLevel.COLLABORATOR in all_levels
        assert AutonomyLevel.CONSULTANT in all_levels
        assert AutonomyLevel.APPROVER in all_levels

    def test_enum_is_hashable(self) -> None:
        """Test that enum values can be used as dict keys."""
        mapping = {
            AutonomyLevel.OPERATOR: "Operator level",
            AutonomyLevel.COLLABORATOR: "Collaborator level",
            AutonomyLevel.CONSULTANT: "Consultant level",
            AutonomyLevel.APPROVER: "Approver level",
        }
        assert mapping[AutonomyLevel.OPERATOR] == "Operator level"
        assert mapping[AutonomyLevel.COLLABORATOR] == "Collaborator level"
        assert mapping[AutonomyLevel.CONSULTANT] == "Consultant level"
        assert mapping[AutonomyLevel.APPROVER] == "Approver level"

    def test_ordering_information(self) -> None:
        """Test that all four autonomy levels exist in expected order.

        AutonomyLevel is ordered from most restrictive to most autonomous:
        OPERATOR < COLLABORATOR < CONSULTANT < APPROVER.
        This test verifies all members exist and documents the intended ordering.
        """
        levels = list(AutonomyLevel)
        assert levels[0] == AutonomyLevel.OPERATOR
        assert levels[1] == AutonomyLevel.COLLABORATOR
        assert levels[2] == AutonomyLevel.CONSULTANT
        assert levels[3] == AutonomyLevel.APPROVER
